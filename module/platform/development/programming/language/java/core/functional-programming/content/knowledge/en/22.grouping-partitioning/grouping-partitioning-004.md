# Collectors.partitioningBy(): Partitioning Data by a Predicate in Java

When you need to split a collection of elements into **two groups based on a true/false condition**, the Java Stream API provides the **`Collectors.partitioningBy()`** collector in the `java.util.stream` package. Instead of writing two loops, creating two lists manually, and checking each element, you can describe a **`Predicate<T>`** and let the collector gather the results into a `Map<Boolean, ...>`.

For example: classifying even and odd numbers, passing/failing students, orders above/below a threshold, in-stock/out-of-stock products, or valid/invalid records. For each element, the predicate determines the branch:

- **`true`**: the element satisfies the condition.
- **`false`**: the element does not satisfy the condition.

Unlike many grouping operations by an arbitrary key, `partitioningBy` always describes **exactly two Boolean partitions**, even when one partition has no elements. Pay attention to **the difference between the classification condition and the aggregation operation within each partition**: a downstream collector allows counting, extracting names, summing, computing statistics, or grouping further instead of just creating two lists.

After this lesson, you will:
1. Write `partitioningBy(predicate)` and `partitioningBy(predicate, downstream)` correctly.
2. Understand `Map<Boolean,List<T>>` and `Map<Boolean,D>` results, including with empty data.
3. Use clear `Predicate<T>` instances, handling null and boundary conditions properly.
4. Combine `counting`, `mapping`, `summingInt`, `averagingInt`, `summarizingInt`, and `groupingBy`.
5. Compare with `filter`, `groupingBy`, and `toMap` and choose based on your needs.
6. Avoid shared mutable state, false assumptions about `Map` ordering, and bugs in parallel processing.

The complete programs use **JDK 17+**; the compile/run commands and stdout have been chosen so they do not depend on HashMap iteration order or thread scheduling.

## 1. Syntax and Return Types

There are two main overloads on `Collectors`:

```java
static <T> Collector<T, ?, Map<Boolean, List<T>>>
partitioningBy(Predicate<? super T> predicate)

static <T, D, A> Collector<T, ?, Map<Boolean, D>>
partitioningBy(
    Predicate<? super T> predicate,
    Collector<? super T, A, D> downstream
)
```

These are **abbreviated API signatures for learning**, not two methods you declare yourself in a program. With one argument, the default downstream collects elements into a list. With two arguments, the downstream determines the result type `D` of **each partition**.

Example code snippet inside a method (requires importing `java.util.List`, `java.util.Map`, and `java.util.stream.Collectors`):

```java
List<Integer> numbers = List.of(1, 2, 3, 4, 5);
Map<Boolean, List<Integer>> byEven = numbers.stream()
        .collect(Collectors.partitioningBy(n -> n % 2 == 0));

List<Integer> evens = byEven.get(true);  // [2, 4]
List<Integer> odds  = byEven.get(false); // [1, 3, 5]
```

Note that `n -> n % 2 == 0` is a **predicate**, not a method that creates a list. The predicate is used to classify elements into the true/false branches; the collector takes responsibility for accumulating the elements.

### Why is there a Map<Boolean, ...>?

`Map<Boolean,List<Integer>>` has two keys: `Boolean.TRUE` and `Boolean.FALSE`. The caller reads each branch using `get(true)` or `get(false)`. Java auto-boxes boolean literals `true`/`false` when needed.

If you only want the list of elements that **meet the condition** and do not care about the remaining group, `filter(predicate).toList()` is usually simpler. `partitioningBy` makes sense when you **need both branches** or need statistics for both the true and false branches in a single collection pass.

## 2. Both Branches Are Always Present, Even When Empty

An important property: the result of `partitioningBy` **always contains both keys `true` and `false`**. That does not mean both lists have elements.

```java
Map<Boolean, List<Integer>> onlyOdd = List.of(1, 3, 5)
        .stream()
        .collect(Collectors.partitioningBy(n -> n % 2 == 0));

// onlyOdd.get(true)  -> []
// onlyOdd.get(false) -> [1, 3, 5]
```

With an empty source:

```java
Map<Boolean, List<String>> empty = List.<String>of()
        .stream()
        .collect(Collectors.partitioningBy(s -> s.length() > 3));

// empty.get(true)  -> []
// empty.get(false) -> []
// empty.size()     -> 2
```

The two examples above are **standalone code snippets**; `List.<String>of()` explicitly specifies the generic type for the empty source. Even though the Stream has no elements to test, the collector still creates two partitions with the appropriate downstream results.

Unlike `groupingBy(x -> condition)`, regular grouping may **not create a key** for a group that does not appear. For example, if all numbers are odd, `groupingBy(n -> n % 2 == 0)` may only contain the key `false`; `partitioningBy` guarantees that `true` is also present with an empty list.

**Do not rely on Map iteration order.** The API does not promise whether `true` or `false` will be printed first when calling `System.out.println(result)`. If you want stable stdout or UI output, print each value `result.get(true)` and `result.get(false)` with its corresponding label.

## 3. Java 17 Program: Partitioning Numbers and Empty Data

Save the file **`PartitionBasicsDemo.java`**:

```java
import java.util.List;
import java.util.Map;
import java.util.function.Predicate;
import java.util.stream.Collectors;

public class PartitionBasicsDemo {
    public static void main(String[] args) {
        List<Integer> numbers = List.of(1, 2, 3, 4, 5, 6);
        Predicate<Integer> isEven = n -> n % 2 == 0;

        Map<Boolean, List<Integer>> groups = numbers.stream()
                .collect(Collectors.partitioningBy(isEven));

        Map<Boolean, List<Integer>> onlyOdds = List.of(1, 3, 5)
                .stream()
                .collect(Collectors.partitioningBy(isEven));

        Map<Boolean, List<Integer>> empty = List.<Integer>of()
                .stream()
                .collect(Collectors.partitioningBy(isEven));

        System.out.println("even=" + groups.get(true));
        System.out.println("odd=" + groups.get(false));
        System.out.println("keys=" + groups.size());
        System.out.println("onlyOddsTrue=" + onlyOdds.get(true));
        System.out.println("onlyOddsFalse=" + onlyOdds.get(false));
        System.out.println("emptyTrue=" + empty.get(true));
        System.out.println("emptyFalse=" + empty.get(false));
        System.out.println("emptyKeys=" + empty.size());
    }
}
```

Compile/run in the directory containing the file:

```bash
javac -encoding UTF-8 PartitionBasicsDemo.java
java PartitionBasicsDemo
```

**Exact stdout:**

```text
even=[2, 4, 6]
odd=[1, 3, 5]
keys=2
onlyOddsTrue=[]
onlyOddsFalse=[1, 3, 5]
emptyTrue=[]
emptyFalse=[]
emptyKeys=2
```

Explanation:
- `isEven` matches true for 2, 4, 6.
- Odd numbers are placed in the `false` branch.
- Both `onlyOdds` and `empty` have two keys, even though the true branch list is empty.
- Lists from a source with an encounter order are collected in encounter order; the example does not depend on the Map's order.

In business APIs, you should name predicates to match the `true` branch, such as `isPassing`, `isActive`, or `requiresReview`. With vague names like `check`, readers can easily confuse the two branches.

## 4. Predicate<T> Determines Partitioning Semantics

`partitioningBy` accepts a `Predicate<? super T>`. The functional method of `Predicate<T>` is:

```java
boolean test(T value);
```

This is an **illustrative signature**. The condition must return a boolean, for example:

```java
Predicate<String> longName = name -> name.length() >= 5;
Predicate<Integer> positive = n -> n > 0;
Predicate<String> containsJava = text -> text.contains("Java");
```

This illustrative snippet requires `import java.util.function.Predicate;`. A predicate can be combined using `and`, `or`, and `negate`:

```java
Predicate<Integer> positiveEven = positive.and(n -> n % 2 == 0);
Map<Boolean, List<Integer>> grouped = List.of(-2, 0, 2, 3, 4)
        .stream()
        .collect(Collectors.partitioningBy(positiveEven));

// true  -> [2, 4]
// false -> [-2, 0, 3]
```

This is a code snippet using the same `positive` variable from the snippet above.

### Condition Boundaries Matter

For example, a student “passes” when their score is **70 or above**:

```java
Predicate<Student> passing = student -> student.score() >= 70;
```

When the score is 70, the predicate returns `true`; if you accidentally use `> 70`, a score of 70 is put into the `false` branch. This is a common business logic bug that still compiles cleanly.

### Intentional Null Handling

If the source contains null, writing `s -> s.length() > 3` will throw a `NullPointerException` when it encounters null. Choose a clear policy:

```java
Predicate<String> longNonNull = s -> s != null && s.length() > 3;
```

In that case, null goes into the false branch. If null is invalid data and should not belong in the “failing” group, use `filter(Objects::nonNull)` before partitioning or return a separate validation error. Do not automatically turn corrupt data into the false branch without understanding the requirements.

Similarly, if a predicate has side effects, the order and number of invocations can become a concern; prefer **stateless** and **non-interfering** functions, especially when the pipeline runs in parallel.

## 5. Overload with a Downstream Collector

The second form:

```java
Collectors.partitioningBy(predicate, downstreamCollector)
```

allows **aggregating each partition separately**. Instead of two `List<T>` instances, you can get two counts, sums, averages, sets of keys, statistics, or nested maps.

| Downstream | Overall Result Type | Meaning |
| --- | --- | --- |
| `Collectors.counting()` | `Map<Boolean,Long>` | Number of elements in each branch |
| `Collectors.mapping(f, toList())` | `Map<Boolean,List<R>>` | Transform each element then collect |
| `Collectors.summingInt(f)` | `Map<Boolean,Integer>` | Sum of an int property per branch |
| `Collectors.averagingInt(f)` | `Map<Boolean,Double>` | Average of an int property |
| `Collectors.summarizingInt(f)` | `Map<Boolean,IntSummaryStatistics>` | Count, sum, min, max, average |
| `Collectors.toSet()` | `Map<Boolean,Set<T>>` | Deduplicate by equals/hashCode |
| `Collectors.groupingBy(f)` | `Map<Boolean,Map<K,List<T>>>` | Split into two branches, then group by another key |

Example:

```java
Map<Boolean, Long> counts = List.of(1, 2, 3, 4, 5)
        .stream()
        .collect(Collectors.partitioningBy(
                n -> n % 2 == 0,
                Collectors.counting()
        ));

// counts.get(true)  -> 2
// counts.get(false) -> 3
```

This snippet requires importing `List`, `Map`, and `Collectors`. The benefit: there is no need to retain both lists if the final goal is only **counting**.

**An important note about downstream collectors:** `partitioningBy` guarantees two keys, but the value type for an empty group depends on the **downstream**. With `counting()`, an empty group receives `0L`; with `toList()`, it receives an empty list; with `maxBy(...)`, it receives `Optional.empty()`; with `averagingInt(...)`, an empty group receives `0.0` per the collector's contract. If you need to distinguish “no samples” from “average equals 0”, you must also check `counting` or use an appropriate stateful result.

## 6. Java 17 Program: Counting, Extracting Names, Averaging, and Statistics

Create the file **`PartitionDownstreamDemo.java`**:

```java
import java.util.IntSummaryStatistics;
import java.util.List;
import java.util.Map;
import java.util.function.Predicate;
import java.util.stream.Collectors;

public class PartitionDownstreamDemo {
    record Student(String name, int score) {}

    public static void main(String[] args) {
        List<Student> students = List.of(
                new Student("Lan", 85),
                new Student("Minh", 62),
                new Student("Mai", 92),
                new Student("An", 59)
        );
        Predicate<Student> passing = s -> s.score() >= 70;

        Map<Boolean, Long> counts = students.stream()
                .collect(Collectors.partitioningBy(
                        passing,
                        Collectors.counting()));

        Map<Boolean, List<String>> names = students.stream()
                .collect(Collectors.partitioningBy(
                        passing,
                        Collectors.mapping(Student::name, Collectors.toList())));

        Map<Boolean, Double> averages = students.stream()
                .collect(Collectors.partitioningBy(
                        passing,
                        Collectors.averagingInt(Student::score)));

        Map<Boolean, IntSummaryStatistics> statistics = students.stream()
                .collect(Collectors.partitioningBy(
                        passing,
                        Collectors.summarizingInt(Student::score)));

        System.out.println("passedCount=" + counts.get(true));
        System.out.println("failedCount=" + counts.get(false));
        System.out.println("passedNames=" + names.get(true));
        System.out.println("failedNames=" + names.get(false));
        System.out.println("passedAverage=" + averages.get(true));
        System.out.println("failedAverage=" + averages.get(false));
        System.out.println("passedTotal=" + statistics.get(true).getSum());
        System.out.println("failedMin=" + statistics.get(false).getMin());
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 PartitionDownstreamDemo.java
java PartitionDownstreamDemo
```

**Exact stdout:**

```text
passedCount=2
failedCount=2
passedNames=[Lan, Mai]
failedNames=[Minh, An]
passedAverage=88.5
failedAverage=60.5
passedTotal=177
failedMin=59
```

Details:
- `score >= 70` is true for Lan (85) and Mai (92): sum 177, average 88.5.
- Minh (62) and An (59) are in the false branch: average 60.5, min 59.
- `mapping(Student::name, toList())` collects only the names, without keeping the entire `Student` objects.
- Each `collect` consumes **a new Stream** created from `students.stream()`. Never reuse a Stream that has already been terminated.
- `record Student` provides the accessors `name()` and `score()` and keeps the example concise in Java 17.

When you need multiple metrics and the dataset is large, `summarizingInt` provides count, sum, min, max, and average in **a single collection pass**; the example separates the pipelines to clarify each downstream collector, not necessarily as the most performance-optimal choice.

## 7. How Does partitioningBy Differ from groupingBy?

Both are collectors, but they serve different purposes:

| Criterion | `partitioningBy(predicate)` | `groupingBy(classifier)` |
| --- | --- | --- |
| Input for criterion | `Predicate<T>` returning boolean | `Function<T,K>` returning key `K` |
| Number of groups | Two partitions `true` and `false` | Depends on the number of distinct keys |
| Common result type | `Map<Boolean,List<T>>` | `Map<K,List<T>>` |
| Group with no elements | Still has both Boolean keys | Does not force creating unseen keys |
| Best suited for | Pass/fail, valid/invalid, yes/no | Grouping by category, department, region, year |
| Downstream | Yes | Yes |

Example of splitting by pass/fail score:

```java
Collectors.partitioningBy(student -> student.score() >= 70)
```

Example of grouping into three grade levels:

```java
Collectors.groupingBy(student ->
        student.score() >= 85 ? "A" :
        student.score() >= 70 ? "B" : "C")
```

Both snippets are **illustrative collector expressions** in the context of a Stream with element type `Student` having a `score()` accessor. Grouping into three labels A/B/C is a job for `groupingBy`, not `partitioningBy`.

### The Case of the Same Boolean Condition

For data that is present, `groupingBy(s -> condition)` can produce similar groups, but **it does not have the same two-key contract**. If the business logic must always display “Passed: 0” and “Failed: n” even when nobody passed, `partitioningBy` expresses that intent more accurately.

### If You Only Need One Branch

```java
List<Integer> even = List.of(1, 2, 3, 4)
        .stream()
        .filter(n -> n % 2 == 0)
        .toList();
```

This snippet illustrates `filter`. There is no need to partition everything and then call `get(true)` if the false group is never used. `filter` can also reduce storage overhead when only one side is needed.

## 8. Nesting partitioningBy and groupingBy for Business Data

You can split orders by a sales condition first, then group each branch by region. You should only do this when you need both analysis axes.

For example: orders with `total >= 100` are high-value, and within each branch you need to count by `region`.

Save as **`PartitionNestedGroupingDemo.java`**:

```java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.function.Predicate;
import java.util.stream.Collectors;

public class PartitionNestedGroupingDemo {
    record Order(String id, String region, int total) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("A", "North", 120),
                new Order("B", "South", 80),
                new Order("C", "North", 45),
                new Order("D", "South", 160),
                new Order("E", "North", 200)
        );
        Predicate<Order> highValue = order -> order.total() >= 100;

        Map<Boolean, Map<String, Long>> regionCounts = orders.stream()
                .collect(Collectors.partitioningBy(
                        highValue,
                        Collectors.groupingBy(
                                Order::region,
                                TreeMap::new,
                                Collectors.counting())));

        Map<Boolean, Integer> totals = orders.stream()
                .collect(Collectors.partitioningBy(
                        highValue,
                        Collectors.summingInt(Order::total)));

        System.out.println("highRegions=" + regionCounts.get(true));
        System.out.println("lowRegions=" + regionCounts.get(false));
        System.out.println("highSum=" + totals.get(true));
        System.out.println("lowSum=" + totals.get(false));
    }
}
```

Run command:

```bash
javac -encoding UTF-8 PartitionNestedGroupingDemo.java
java PartitionNestedGroupingDemo
```

**Exact stdout:**

```text
highRegions={North=2, South=1}
lowRegions={North=1, South=1}
highSum=480
lowSum=125
```

Explanation:
1. The true branch consists of A/North/120, D/South/160, and E/North/200. Grouping by region produces `North=2`, `South=1`; the sum is 480.
2. The false branch consists of B/South/80 and C/North/45, so each region has one order; the sum is 125.
3. `TreeMap::new` in the downstream `groupingBy` guarantees the order of region keys when printing the inner Map.
4. Each partition may have an empty inner Map when there are no orders belonging to that partition; the outer Map's true/false keys still exist.

If the requirement is “total sales per region and then split regions into above/below threshold”, **the analysis order must be different**: first group/sum by region, then evaluate the condition on each region's total. `partitioningBy` on each Order does not automatically turn into partitioning by group totals.

## 9. partitioningBy with Set, min/max, and Empty Partitions

The downstream can use collectors other than `toList`. For example:

```java
Map<Boolean, java.util.Set<Integer>> uniqueByEven =
        List.of(2, 2, 3, 3, 4)
                .stream()
                .collect(Collectors.partitioningBy(
                        n -> n % 2 == 0,
                        Collectors.toSet()));
```

This is an illustrative snippet requiring `List`, `Map`, and `Collectors`. The true branch contains the set 2, 4; the false branch contains the set 3. **Do not rely on the print order of a `Set`** from `toSet()`.

If you want the maximum value in each partition:

```java
Map<Boolean, java.util.Optional<Integer>> maximum =
        List.of(1, 2, 3, 5)
                .stream()
                .collect(Collectors.partitioningBy(
                        n -> n % 2 == 0,
                        Collectors.maxBy(Integer::compare)));
```

`maximum.get(true)` contains 2 and `maximum.get(false)` contains 5. The result of the `maxBy` downstream is `Optional<Integer>`, not `Integer` directly. If a branch is empty, the corresponding Optional is **empty**, yet the partition's Boolean key is still present.

**Never call `get()` on an empty Optional.** Use `orElse`, `orElseThrow`, or check its state. Distinguish between the two levels: “does the branch exist?” and “does the branch have elements to compute a max?”: `partitioningBy` guarantees the first level, not the second.

### Does the Downstream Result Need to Be Mutable?

`Collectors.toList()` makes no guarantees about the concrete implementation or mutability. `Collectors.toUnmodifiableList()` returns a list that cannot be modified via its API and rejects null elements. If you need a specific container, use `Collectors.toCollection(ArrayList::new)`; if you only need to read the results, do not assume the two lists can be freely modified or belong to a specific class.

## 10. Running in Parallel: Use a Collector, Not Shared External Lists

With `parallelStream()`, a collector can split the work into multiple accumulators and combine the results. Usage:

```java
Map<Boolean, List<Integer>> groups = List.of(1, 2, 3, 4)
        .parallelStream()
        .collect(Collectors.partitioningBy(n -> n % 2 == 0));
```

This illustrative snippet is semantically sound. Using `partitioningBy` with a standard collector lets the Stream framework manage the collection process, without having to manually update two shared lists across multiple threads.

**Do not** write:

```java
// UNSAFE PATTERN with parallelStream():
List<Integer> yes = new java.util.ArrayList<>();
List<Integer> no = new java.util.ArrayList<>();
List.of(1, 2, 3, 4)
        .parallelStream()
        .forEach(n -> {
            if (n % 2 == 0) yes.add(n);
            else no.add(n);
        });
```

This is an **intentionally cautionary** snippet. Two `ArrayList` instances are not safe for concurrent updates by multiple threads, leading to race conditions, missing results, or unstable ordering. Using a collector is the better choice.

**Predicates should be stateless and non-interfering**: do not modify the source being traversed, and do not depend on an incrementing mutable counter or execution order. If a predicate has side effects, results on a parallel stream are hard to verify; do not use `partitioningBy` as an automatic synchronization mechanism.

### Encounter Order of Lists in Partitions

With an ordered source like `List` and a suitable downstream like `toList()`, elements in each partition are collected in **encounter order**. In a parallel stream, execution order across workers may differ, but the resulting Lists still follow this ordering contract. **The iteration order of the two Map keys themselves** is not guaranteed.

## 11. Java 17 Program: Parallel Partitioning Still Has Deterministic Output

Save as **`ParallelPartitionDemo.java`**:

```java
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class ParallelPartitionDemo {
    public static void main(String[] args) {
        List<Integer> numbers = IntStream.rangeClosed(1, 12)
                .boxed()
                .toList();

        Map<Boolean, List<Integer>> divisibleByThree =
                numbers.parallelStream()
                        .collect(Collectors.partitioningBy(
                                n -> n % 3 == 0));

        Map<Boolean, Long> counts = numbers.parallelStream()
                .collect(Collectors.partitioningBy(
                        n -> n % 3 == 0,
                        Collectors.counting()));

        Map<Boolean, Optional<Integer>> maximum = numbers.parallelStream()
                .collect(Collectors.partitioningBy(
                        n -> n % 3 == 0,
                        Collectors.maxBy(Integer::compare)));

        System.out.println("divisible=" + divisibleByThree.get(true));
        System.out.println("other=" + divisibleByThree.get(false));
        System.out.println("divisibleCount=" + counts.get(true));
        System.out.println("otherCount=" + counts.get(false));
        System.out.println("divisibleMax=" + maximum.get(true).orElse(-1));
        System.out.println("otherMax=" + maximum.get(false).orElse(-1));
    }
}
```

Compile/run with JDK 17+:

```bash
javac -encoding UTF-8 ParallelPartitionDemo.java
java ParallelPartitionDemo
```

**Exact stdout:**

```text
divisible=[3, 6, 9, 12]
other=[1, 2, 4, 5, 7, 8, 10, 11]
divisibleCount=4
otherCount=8
divisibleMax=12
otherMax=11
```

The values 3, 6, 9, 12 are divisible by 3. The resulting lists preserve the encounter order of the `IntStream.rangeClosed(...).boxed().toList()` source. The remaining numbers consist of eight elements; the max of that branch is 11.

The program does not print the `Map` object directly, so it does not depend on the order of the true/false keys. It also does not print thread IDs or log from `forEach`, because those details do not produce deterministic stdout when running in parallel.

**Performance:** with 12 numbers, a parallel stream is almost certainly not an example demonstrating a speedup. If the dataset is large and the computation is heavy enough, parallel execution can be helpful; otherwise, the overhead of splitting work, combining results, and preserving encounter order can make it slower. Benchmark real workloads rather than inferring from the name `parallel`.

## 12. Common Mistakes When Partitioning

1. **Inverting key meaning:** `get(true)` is the group that **satisfies the predicate**, not “passed” by default if the predicate is written for “failed”.
2. **Confusing comparison operators:** `>= 70` differs from `> 70` when the score is exactly 70.
3. **Only wanting the true group but using complex partitioningBy:** use `filter` if the false group is not needed.
4. **Assuming the Map only has keys that appeared:** `partitioningBy` always has both true and false.
5. **Assuming `groupingBy(predicate)` always has two keys:** a group with no elements may not have a key.
6. **Relying on Map iteration order:** it is not guaranteed; access `get(true)`/`get(false)` explicitly.
7. **Not considering null:** a predicate calling a method on a null element will throw an exception if not handled.
8. **Letting the predicate have side effects:** this can make classification unpredictable and wrong in parallel.
9. **Mutating external shared Lists with parallel forEach:** risks race conditions; use a collector.
10. **Mistaking downstream counting for returning int:** `Collectors.counting()` returns `Long`.
11. **Confusing downstream averagingInt on an empty branch with Optional.empty:** it returns `Double` per the collector's averaging contract, with a result of 0.0 for a branch with no samples.
12. **Calling Optional.get on the maxBy result of an empty group:** throws `NoSuchElementException`.
13. **Assuming `Collectors.toList()` always returns an ArrayList:** implementation and mutability are not guaranteed.
14. **Using two-branch partitioning for a problem with three or more states:** `groupingBy` or another structure is usually more appropriate.
15. **Believing partitioningBy runs only once over the source despite multiple terminal operations:** each `collect` on a new Stream triggers a separate pipeline.
16. **Assuming parallel partitioning is always faster than sequential:** combining costs, collector management, and ordering constraints can be high.

## 13. Quick Selection Guide by Requirement

| Requirement | Appropriate API |
| --- | --- |
| Only need elements matching a condition | `stream.filter(predicate).toList()` |
| Need both true and false groups | `collect(partitioningBy(predicate))` |
| Count true and false groups | `collect(partitioningBy(predicate, counting()))` |
| Get a list of names in each group | `collect(partitioningBy(predicate, mapping(..., toList())))` |
| Sum a property across two groups | `collect(partitioningBy(predicate, summingInt(...)))` |
| Min/max/avg/count statistics across two groups | `collect(partitioningBy(predicate, summarizingInt(...)))` |
| Split into two groups then classify by region | `collect(partitioningBy(predicate, groupingBy(...)))` |
| Group by multiple labels (A/B/C/...) | `collect(groupingBy(classifier))` |
| Only need to know if any element matches | `stream.anyMatch(predicate)` |

`partitioningBy` is not the default choice for every Boolean problem. If the goal is only to return a boolean, `anyMatch`, `allMatch`, or `noneMatch` usually expresses that better and can short-circuit. `partitioningBy` needs to process/aggregate elements for both branches rather than stopping automatically upon seeing one matching element.

## 14. Self-Check Exercises

**Question 1.** With `List.of(1,2,3,4,5)`, what two groups does `partitioningBy(n -> n > 3)` create?

**Answer:** `true -> [4, 5]` and `false -> [1, 2, 3]`.

**Question 2.** With an empty Stream, how many keys does `partitioningBy(predicate)` create?

**Answer:** Always **2** keys: `true` and `false`. Each value is an empty list.

**Question 3.** If you only want to count passing/failing students without needing the Student lists, which downstream collector should you use?

**Answer:** `Collectors.counting()`, with result type `Map<Boolean,Long>`.

**Question 4.** Why can't `groupingBy(n -> n % 2 == 0)` completely replace `partitioningBy(n -> n % 2 == 0)`?

Because `groupingBy` is not required to create keys for groups with no elements, whereas `partitioningBy` has a two-partition contract.

**Question 5.** Can you use `partitioningBy(predicate, Collectors.groupingBy(classifier))`?

**Yes.** The result is a Map with two Boolean branches, each containing a Map grouped by the classifier. This is a two-level analysis pattern.

**Question 6.** Why is `parallelStream().forEach(x -> sharedList.add(x))` not a safe replacement for a collector?

**Answer:** An external `ArrayList` updated concurrently can cause race conditions and non-deterministic ordering. A collector manages the accumulator and combiner according to the Stream contract.

**Question 7.** When the downstream uses `maxBy` and one branch is empty, is `map.get(true)` null?

**Answer:** The true key still exists, but its value is `Optional.empty()` (if true is the empty branch). Do not call `get()` on an empty Optional.

**Question 8.** Why shouldn't you print `Map<Boolean,List<T>>` directly and write a unit test expecting a specific key order?

Because Map iteration order is not part of `partitioningBy`'s contract. Check each branch via `get(true)` and `get(false)`, or compare Map contents by equality without relying on display order.

**Takeaway:** **`partitioningBy(predicate)` splits a Stream into two `true`/`false` partitions that always exist.** When you need more than lists of elements, add a downstream collector to count, extract properties, sum, compute statistics, or group further. If you only need one branch, use `filter`; if you need multiple arbitrary keys, use `groupingBy`. Keep the Predicate clear in meaning and free of side effects for a reliable pipeline.
