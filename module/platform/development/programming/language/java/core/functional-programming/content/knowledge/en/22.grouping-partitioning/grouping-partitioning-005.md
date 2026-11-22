# Distinguishing `partitioningBy()` from `groupingBy()` by Boolean in Java Stream

## 1. Both Split into Two Groups, but Their Result Contracts Are Not the Same

When using the Stream API to collect data (*collect*), we often want to split elements into two groups, for example:

- Orders with a total amount of 100 or more and orders under 100.
- Passing students and non-passing students.
- Valid requests and invalid requests.
- Completed tasks and incomplete tasks.

Two commonly seen collectors are:

```java
Collectors.partitioningBy(predicate)
Collectors.groupingBy(classifier)
```

Both **can produce `Map<Boolean, List<T>>`** when the grouping condition returns a boolean. However, the way they define the key set is very different:

**`partitioningBy(predicate)` always has both keys `Boolean.TRUE` and `Boolean.FALSE`**, even when one group has no elements or the entire source is empty. The corresponding list may be empty.

**`groupingBy(element -> booleanExpression)` only creates keys for classification results actually encountered in the source.** If no element returns false, the map has no false key. With an empty source, the result is an empty map.

This is a **contract** difference, not just a syntax preference. It affects the use of `get(false)`, the possibility of `null`, the number of groups when there is no data, statistics collectors, and how APIs are designed.

Example:

```java
List<Integer> numbers = List.of(10, 20, 30);

Map<Boolean, List<Integer>> partition =
        numbers.stream().collect(
                Collectors.partitioningBy(n -> n >= 10));

Map<Boolean, List<Integer>> grouping =
        numbers.stream().collect(
                Collectors.groupingBy(n -> n >= 10));

// partition.get(false) is an empty List.
// grouping.get(false) is null because the false key does not exist.
```

This is an illustrative snippet inside a method; `java.util.List`, `java.util.Map`, and `java.util.stream.Collectors` need to be imported.

## 2. Signatures and How to Read the Two Collectors

### `partitioningBy` Accepts a `Predicate`

The main overloads:

```java
static <T> Collector<T, ?, Map<Boolean, List<T>>>
    partitioningBy(Predicate<? super T> predicate);

static <T, D, A> Collector<T, ?, Map<Boolean, D>>
    partitioningBy(
        Predicate<? super T> predicate,
        Collector<? super T, A, D> downstream);
```

The signatures above are simplified for type clarity; in the real API, `Collectors` contains the full generic declarations.

- `Predicate<T>.test(T)` returns a **primitive `boolean`**.
- A `true` result puts the element into the true group; a `false` result puts it into the false group.
- `partitioningBy` does not use an arbitrary "group label"; it fixes **two branches** corresponding to the two boolean values.
- The overload with `downstream` allows collecting into a list, counting, summing, finding min/max, or processing each branch separately.

### `groupingBy` Accepts a Classifier `Function`

Some overloads:

```java
static <T, K> Collector<T, ?, Map<K, List<T>>>
    groupingBy(Function<? super T, ? extends K> classifier);

static <T, K, A, D> Collector<T, ?, Map<K, D>>
    groupingBy(
        Function<? super T, ? extends K> classifier,
        Collector<? super T, A, D> downstream);
```

- `Function<T,K>.apply(T)` returns a **key of type `K`**.
- If you write `order -> order.amount() >= 100`, the boolean expression is boxed into `Boolean` to serve as the key.
- `groupingBy` can group by `String`, `Integer`, enum, record, or other valid keys, rather than being limited to boolean.
- The map only has groups for keys that appear in the input data.

**For a requirement to split into two true/false branches, `partitioningBy` expresses the intent more clearly.** `groupingBy` is more suitable when the problem requires classifying into multiple labels or when having only the groups that actually appear is part of the data's meaning.

## 3. Contract Comparison Table

| Criterion | `partitioningBy(predicate)` | `groupingBy(e -> condition)` |
| --- | --- | --- |
| Accepted mapper | `Predicate<? super T>` | `Function<? super T, ? extends K>` |
| Key type when splitting by boolean | `Boolean` | `Boolean` |
| Does the false key always exist? | **Yes** | **No**, only when there is a false element |
| Does the true key always exist? | **Yes** | **No**, only when there is a true element |
| Empty source | Map containing true and false, each group empty | Empty map |
| All elements true | `true -> list`; `false -> []` | Only `true -> list` |
| All elements false | `false -> list`; `true -> []` | Only `false -> list` |
| More than two groups | Not suitable | Suitable for multi-key classifiers |
| Downstream parameter | Yes | Yes |
| Has a map factory selection overload? | No `mapFactory` overload for `partitioningBy` | Has `groupingBy(classifier, mapFactory, downstream)` |
| Map key iteration order guarantee | No | Not by default |
| Specific Map implementation type guarantee | Should not be relied upon | Should not be relied upon |
| Guarantee that the result is always mutable | No general contract | No general contract |

Because Map iteration order is not the goal of either collector, **do not write expected stdout based on `System.out.println(map)`** if implementation-independent testing is needed. Instead, explicitly access `get(true)` then `get(false)`, or choose a deterministic presentation order yourself.

## 4. Complete Java 17 Example: Splitting Orders by a Threshold

The following program fully demonstrates:

1. Partitioning and grouping the same data containing both true/false.
2. Comparing **true-only** data and **empty** data.
3. Using downstream `counting()` and `summingInt()`.
4. Safely retrieving the false group with `partitioningBy`, and handling a missing key with `groupingBy`.
5. Printing results in a way that does not depend on Map order.

Create the file **`BooleanCollectorsDemo.java`**:

```java
import java.util.List;
import java.util.Map;
import java.util.function.Predicate;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class BooleanCollectorsDemo {
    record Order(String id, int amount) {}

    static List<String> ids(List<Order> orders) {
        return orders.stream()
                .map(Order::id)
                .toList();
    }

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("A01", 120),
                new Order("A02", 80),
                new Order("A03", 200),
                new Order("A04", 110)
        );

        Predicate<Order> isLarge = order -> order.amount() >= 100;

        Map<Boolean, List<Order>> partition = orders.stream()
                .collect(Collectors.partitioningBy(isLarge));

        Map<Boolean, List<Order>> grouped = orders.stream()
                .collect(Collectors.groupingBy(
                        order -> order.amount() >= 100));

        System.out.println("Partition keys: "
                + partition.containsKey(true) + "/"
                + partition.containsKey(false));
        System.out.println("Grouped keys: "
                + grouped.containsKey(true) + "/"
                + grouped.containsKey(false));
        System.out.println("Partition true: " + ids(partition.get(true)));
        System.out.println("Partition false: " + ids(partition.get(false)));
        System.out.println("Grouped true: " + ids(grouped.get(true)));
        System.out.println("Grouped false: " + ids(grouped.get(false)));

        // Case where all elements satisfy the condition.
        List<Order> onlyLarge = orders.stream()
                .filter(isLarge)
                .toList();

        Map<Boolean, List<Order>> onlyPartition =
                onlyLarge.stream().collect(
                        Collectors.partitioningBy(isLarge));

        Map<Boolean, List<Order>> onlyGrouped =
                onlyLarge.stream().collect(
                        Collectors.groupingBy(isLarge::test));

        System.out.println("Only-large partition false: "
                + ids(onlyPartition.get(false)));
        System.out.println("Only-large group has false: "
                + onlyGrouped.containsKey(false));
        System.out.println("Only-large group false via get: "
                + onlyGrouped.get(false));

        // Case where there are no elements at all.
        Map<Boolean, List<Order>> emptyPartition =
                Stream.<Order>empty().collect(
                        Collectors.partitioningBy(isLarge));

        Map<Boolean, List<Order>> emptyGrouped =
                Stream.<Order>empty().collect(
                        Collectors.groupingBy(isLarge::test));

        System.out.println("Empty partition keys: "
                + emptyPartition.containsKey(true) + "/"
                + emptyPartition.containsKey(false));
        System.out.println("Empty partition sizes: "
                + emptyPartition.get(true).size() + "/"
                + emptyPartition.get(false).size());
        System.out.println("Empty grouped isEmpty: "
                + emptyGrouped.isEmpty());

        // Downstream: count for each branch, including the group missing data.
        Map<Boolean, Long> counts = onlyLarge.stream()
                .collect(Collectors.partitioningBy(
                        isLarge, Collectors.counting()));

        System.out.println("Counts true/false: "
                + counts.get(true) + "/" + counts.get(false));

        // Downstream: total amount of each branch.
        Map<Boolean, Integer> sums = orders.stream()
                .collect(Collectors.partitioningBy(
                        isLarge, Collectors.summingInt(Order::amount)));

        System.out.println("Sums true/false: "
                + sums.get(true) + "/" + sums.get(false));

        // GroupingBy may lack the key => choose an explicit fallback.
        long missingCount = onlyLarge.stream()
                .collect(Collectors.groupingBy(
                        isLarge::test, Collectors.counting()))
                .getOrDefault(false, 0L);

        System.out.println("Grouped missing count: " + missingCount);
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac --release 17 BooleanCollectorsDemo.java
java BooleanCollectorsDemo
```

**Deterministic stdout:**

```text
Partition keys: true/true
Grouped keys: true/true
Partition true: [A01, A03, A04]
Partition false: [A02]
Grouped true: [A01, A03, A04]
Grouped false: [A02]
Only-large partition false: []
Only-large group has false: false
Only-large group false via get: null
Empty partition keys: true/true
Empty partition sizes: 0/0
Empty grouped isEmpty: true
Counts true/false: 3/0
Sums true/false: 430/80
Grouped missing count: 0
```

### Line-by-Line Comparison

- `orders` has three orders meeting `amount >= 100`: A01 (120), A03 (200), A04 (110). Order A02 (80) belongs to the false group.
- With data containing **both true and false**, both collectors contain both keys, so the initial lines have equivalent content in their results.
- `onlyLarge` only has A01, A03, A04. `partitioningBy` still has the false key with `List.of()` equivalent in content to an empty list. `groupingBy` sees no false element, so it **does not create the false key**.
- Because the key is missing, `onlyGrouped.get(false)` returns `null`. This is **not an empty list**. Calling `onlyGrouped.get(false).size()` will throw a `NullPointerException`.
- With empty input, `partitioningBy` has two empty lists, while `groupingBy` returns an empty map.
- `Collectors.counting()` is a downstream returning `Long`. With `onlyLarge`, the true branch has 3 elements, and the false branch has 0.
- `Collectors.summingInt(Order::amount)` produces a primitive int sum and then boxes it to `Integer` in the result map: true = 120+200+110 = 430, false = 80.
- `groupingBy(..., counting())` with true-only input **has no false key**; `getOrDefault(false,0L)` returns 0 to present a statistic with a default value per the caller's intent.

> The example uses a sequential stream with encounter order from `List`, so each group's list of order IDs is printed in encounter order. There is no assumption about map key iteration order.

## 5. Cases That Cause Code to Change Behavior

Consider two lines:

```java
Map<Boolean, List<Order>> partition =
        orders.stream().collect(
                Collectors.partitioningBy(order -> order.amount() >= 100));

Map<Boolean, List<Order>> grouping =
        orders.stream().collect(
                Collectors.groupingBy(order -> order.amount() >= 100));
```

Here `Order`/`orders` are illustrative types/data as in the full program. If both order types are present, the caller may not notice a difference.

But when one order type is missing:

```java
List<Order> small = partition.get(false); // Not null.
List<Order> possiblyNull = grouping.get(false); // Possibly null.
```

Calling `partition.get(false).size()` always reads the element count of the false group. Meanwhile, `grouping.get(false).size()` may throw a `NullPointerException` if there is no false key.

Solution for `groupingBy` when the output may be missing a key:

```java
List<Order> small = grouping.getOrDefault(false, List.of());
System.out.println(small.size());
```

Or check `containsKey(false)` if the business requirement needs to explicitly know whether **the group actually appeared** or not.

**Important:** `getOrDefault` only returns the fallback specified by the caller; it **does not add the false key into the original map**. If you need the result structure to always have two groups, `partitioningBy` expresses the contract better.

## 6. Why Cannot `partitioningBy` Be Used for More Than Two Labels?

`partitioningBy` only splits by a `Predicate<T>` returning `boolean`. If the problem is classifying orders by:

- `LOW`: under 100;
- `MEDIUM`: from 100 to under 200;
- `HIGH`: 200 and above;

then `groupingBy` is more suitable:

```java
enum Band { LOW, MEDIUM, HIGH }

Map<Band, List<Order>> byBand = orders.stream()
        .collect(Collectors.groupingBy(order -> {
            if (order.amount() < 100) return Band.LOW;
            if (order.amount() < 200) return Band.MEDIUM;
            return Band.HIGH;
        }));
```

This is an **illustrative snippet** assuming `Order` and `orders` are already declared and the `Band` enum is in a valid scope. Enum keys still only appear if there is an order belonging to the corresponding group. `groupingBy` allows customizing the comparator/map factory in the three-parameter overload, but by itself it **does not automatically add all enum values** to the map.

To guarantee the result always has LOW, MEDIUM, HIGH groups, the caller must specify and build the appropriate output, such as adding default values for each key in an explicit step.

## 7. With a Downstream Collector: Behavior of an Empty Group

The downstream form of `partitioningBy` is very useful:

```java
Collectors.partitioningBy(predicate, downstream)
```

For a group with no elements, the collector still produces **the downstream's result value for an empty group**. For example:

| Downstream | Result of the empty branch |
| --- | --- |
| `Collectors.toList()` | Empty list |
| `Collectors.counting()` | `0L` |
| `Collectors.summingInt(...)` | `0` |
| `Collectors.averagingInt(...)` | `0.0` |
| `Collectors.maxBy(...)` | `Optional.empty()` |
| `Collectors.mapping(mapper, toList())` | Empty list |

Conversely, when using `groupingBy(classifier, downstream)` and the corresponding key **never appears**, the map generally **has no entry** for that key, regardless of whether the downstream could compute a value on an empty group.

Example:

```java
Map<Boolean, Long> counts =
        onlyLarge.stream().collect(
            Collectors.partitioningBy(
                isLarge, Collectors.counting()));

System.out.println(counts.get(false)); // 0
```

Replacing `partitioningBy` with `groupingBy(isLarge::test, counting())` causes `get(false)` to return `null`, not `0L`.

**Do not equate `0` with "no group yet".** In a report, "this group has 0 orders" and "this group's state was never recorded" can be two states that need to be distinguished. Choose the collector according to the reporting contract.

## 8. Combining Downstream `mapping`, `collectingAndThen`, and `toSet`

Both collectors support downstream collectors to control the value type in the map.

### Taking Only Order IDs Instead of Whole Objects

```java
Map<Boolean, List<String>> idsBySize = orders.stream()
        .collect(Collectors.partitioningBy(
                order -> order.amount() >= 100,
                Collectors.mapping(Order::id, Collectors.toList())
        ));
```

Result in content: true has A01, A03, A04; false has A02. With true-only input, false will be an empty `List<String>`.

### Collecting to Counts

```java
Map<Boolean, Long> countBySize = orders.stream()
        .collect(Collectors.partitioningBy(
                order -> order.amount() >= 100,
                Collectors.counting()
        ));
```

You do not need to declare two mutable counter variables yourself and update them in `forEach`. The collector coordinates accumulating and combining results.

### Returning an Unmodifiable List

```java
Map<Boolean, List<String>> immutableGroups =
        orders.stream().collect(
            Collectors.partitioningBy(
                order -> order.amount() >= 100,
                Collectors.mapping(
                    Order::id,
                    Collectors.collectingAndThen(
                        Collectors.toList(),
                        List::copyOf)
                )
            )
        );
```

`List.copyOf` creates a structurally unmodifiable list and **does not accept null elements**. Since `Order::id` in the example is non-null, this is appropriate. However, having the downstream create an unmodifiable list **does not by itself guarantee whether the Map itself is modifiable/unmodifiable**. Do not depend on a specific collector implementation if the contract does not require it.

### Removing Duplicate IDs

```java
Map<Boolean, java.util.Set<String>> uniqueIds =
        orders.stream().collect(
            Collectors.partitioningBy(
                order -> order.amount() >= 100,
                Collectors.mapping(
                    Order::id,
                    Collectors.toSet()
                )
            )
        );
```

`Collectors.toSet()` does not guarantee encounter order of the resulting set; if it must be displayed in order, proactively use a sorted/appropriate collection. Even with an empty set, `partitioningBy` still has both keys.

## 9. How Does `Predicate` Differ from `Function<T, Boolean>`?

`Predicate<T>` has the method:

```java
boolean test(T value);
```

`Function<T, Boolean>` has the method:

```java
Boolean apply(T value);
```

This is a real difference between **primitive boolean** and **wrapper Boolean**.

Valid example:

```java
Predicate<Order> large = order -> order.amount() >= 100;

Map<Boolean, List<Order>> partition =
        orders.stream().collect(
                Collectors.partitioningBy(large));

Map<Boolean, List<Order>> grouping =
        orders.stream().collect(
                Collectors.groupingBy(large::test));
```

`large::test` is a method reference to the instance method `test` of the `large` object; the boolean result is boxed to match the `Boolean` key of `groupingBy`.

**If the `groupingBy` classifier returns `null`:** `groupingBy` does not accept null as a classification result and may throw a `NullPointerException`. With `partitioningBy`, the predicate has a primitive `boolean` result, so `Predicate.test` itself has no valid null value. However, a lambda that auto-unboxes from a nullable `Boolean` can still throw an NPE:

```java
// Risk of NPE if order.flag() returns null Boolean:
// Predicate<Order> p = order -> order.flag();
```

`Order.flag()` is a hypothetical illustrative property; it does not exist in the `Order` record of the main program. Specify how to handle the **unknown** state. If there are truly three states—true/false/unknown—`partitioningBy` does not model it sufficiently; you should use an enum or another state type with `groupingBy`/a corresponding model.

## 10. When Is `groupingBy(boolean)` Appropriate Instead?

Although splitting into two branches should usually use `partitioningBy`, `groupingBy(boolean)` still has valid use cases:

- You already have a `Function<T, Boolean>` classifier and need to share a `groupingBy` architecture with other keys.
- **The absence of a key is meaningful** and the caller intentionally wants to know only the states that have occurred.
- You need the `groupingBy` overload with a **mapFactory** per a specific design requirement.
- The problem will soon expand from boolean to an enum or multiple groups.

With the three-parameter overload:

```java
Map<Boolean, List<Order>> grouped = orders.stream()
        .collect(Collectors.groupingBy(
                order -> order.amount() >= 100,
                java.util.LinkedHashMap::new,
                Collectors.toList()
        ));
```

`LinkedHashMap` preserves the order of **key insertion when groups are first created**, which does not mean always false before true or vice versa. In a parallel pipeline, you should not rely on key appearance order as business order; to fix true/false, print/access them by their specific keys.

**Do not choose a collector just because of its name or speculated speed.** Determine the output contract and empty-source case first.

## 11. Empty Source and Reporting Semantics

An empty source is a situation that easily exposes differences that happy-path code cannot show.

With `partitioningBy`:

```java
Map<Boolean, List<Integer>> parts =
        Stream.<Integer>empty()
                .collect(Collectors.partitioningBy(n -> n >= 0));

System.out.println(parts.containsKey(true));  // true
System.out.println(parts.containsKey(false)); // true
System.out.println(parts.get(true).size());   // 0
System.out.println(parts.get(false).size());  // 0
```

With `groupingBy`:

```java
Map<Boolean, List<Integer>> groups =
        Stream.<Integer>empty()
                .collect(Collectors.groupingBy(n -> n >= 0));

System.out.println(groups.isEmpty());         // true
System.out.println(groups.get(false));        // null
```

Therefore:

- For a dashboard that must always display "Valid: 0, Invalid: 0", `partitioningBy` is very natural.
- For a catalog that only displays groups that have data, `groupingBy` yields a map containing only the encountered keys.
- For an API that needs to distinguish "no records" from "no group labels", design an explicit Result/DTO structure instead of inferring only from a map.

## 12. Reading Results Safely: `get`, `getOrDefault`, `containsKey`

`partitioningBy` guarantees both entries exist, so `get(true)`/`get(false)` gives the result defined by the downstream. With the default downstream, that is a `List<T>` (which may be empty).

`groupingBy` does not guarantee both keys are present, so:

```java
List<Order> trueItems =
        grouped.getOrDefault(true, List.of());

List<Order> falseItems =
        grouped.getOrDefault(false, List.of());
```

If the caller needs to distinguish "no key" from "key with an empty list", check `containsKey` first. Do not use `grouped.get(false) == null` to replace all checks in an API that may allow null map values from other sources; with the default result of `groupingBy`, a missing key is the main case, but general API design should still define a contract.

`getOrDefault` does not add an entry to the map. If subsequent code does `grouped.put(false, new ArrayList<>())`, it is **mutating the result map** and must be aware of whether mutability is guaranteed; usually, you should create an application-specific output map/DTO with both keys initialized when a stable structure is needed.

### Do Not Write Expressions with NPE Risk

```java
// May fail if grouped is missing the false key:
// int count = grouped.get(false).size();

// Valid for grouped data that may be missing a key:
int count = grouped.getOrDefault(false, List.of()).size();
```

The illustrative code assumes `grouped` has type `Map<Boolean,List<Order>>` and `Order` is declared.

## 13. Element Order, Mutable Result, and Concurrent Data

### Element Order Within Each Group

With a `List` having encounter order and a sequential pipeline, the default downstream of both collectors is a list containing the elements belonging to the group in encounter order. For example, A01, A03, A04 in the true branch.

In a parallel pipeline with encounter order, the corresponding collector must still satisfy the downstream's ordering semantics when applicable; **do not infer the order in which threads run the predicate** from the order of result elements. The predicate should **not interfere with source state or use shared mutable state**.

### Do Not Depend on the Map Implementation

The collectors do not commit to a specific map class for the caller to rely on class names or iteration order. Do not write unit tests comparing `map.toString()` against a hardcoded key order. Check `map.get(true)`/`map.get(false)` or compare the values of each branch.

### Is Parallelization Possible?

You can call:

```java
Map<Boolean, List<Order>> partition =
        orders.parallelStream()
                .collect(Collectors.partitioningBy(
                        order -> order.amount() >= 100));
```

`collect` manages accumulating and combining results according to the collector. There is no need to declare two shared `ArrayList`s yourself and call `add` on them in `parallelStream().forEach(...)`, as that poses a data race risk.

**Performance note:** `partitioningBy` and `groupingBy` may differ in overhead/combining characteristics, but there is no rule that "partitioningBy is always faster" for all data/JDKs. Choose by output contract first; run representative benchmarks if performance actually matters.

## 14. Common Mistakes

| Mistake | Why it is wrong | Right approach |
| --- | --- | --- |
| Thinking `partitioningBy` only creates groups that have elements | The contract always has true and false | Handle both groups, allowing empty lists |
| Thinking `groupingBy(boolean)` also always has two keys | It only creates a key when an element belongs to that group | `getOrDefault`/`containsKey` or choose `partitioningBy` |
| Calling `grouped.get(false).size()` unconditionally | May NPE when the key is missing | `getOrDefault(false,List.of()).size()` |
| Thinking an empty source returns the same result | Partition has two empty groups; grouping has an empty map | Test the no-data edge case |
| Printing `map.toString()` and asserting key order | No suitable key order contract | Access each key explicitly |
| Using `partitioningBy` to create 3 labels | Predicate only has true/false | `groupingBy` with enum/labels |
| Using a nullable `Boolean` and auto-unboxing | May NPE | Define an unknown state |
| Classifying with `groupingBy` returning a null key | Null classifier result is not accepted | Validate/normalize or use a valid label type |
| Thinking `counting` on an absent group is always a 0 entry | Grouping does not create an entry for an absent branch | `getOrDefault(false,0L)` |
| Using `forEach` to mutate two external `ArrayList`s | Hard-to-control side effects, dangerous in parallel | Accumulating collector |
| Treating `Map<Boolean,...>` as a sufficient definition for all business states | There may be error/undetermined states | Explicit Enum/Result/DTO |
| Relying on mutability of the collector's map/list | Should not rely on implementation | Create your own output if modification is needed |

## 15. Practice Exercises

1. Given the numbers `[1,2,3,4]`, use `partitioningBy(n -> n % 2 == 0)`. Predict the two true/false lists. Answer: true `[2,4]`; false `[1,3]`.
2. Run the same list with `groupingBy(n -> n % 2 == 0)`. Since both even and odd numbers are present, how is the result similar to and different from `partitioningBy` in content?
3. With `List.of(2,4,6)`, check `partition.get(false)` and `grouped.get(false)`. Why is one value an empty list while the other is null?
4. Collect `Stream.<Integer>empty()` through both collectors. Verify that `partitioningBy` has both keys while `groupingBy` has no keys.
5. Use `partitioningBy(n -> n > 10, counting())` on `[1,2,3]`. Predict `true=0L`, `false=3L`.
6. Use `groupingBy(n -> n > 10, counting())` on the same data. Why does `get(true)` return null instead of 0?
7. Replace `Collectors.toList()` with `Collectors.mapping(Order::id, toList())` so the groups only contain order IDs. Identify the type `Map<Boolean,List<String>>`.
8. Use `summingInt(Order::amount)` to calculate the amount per branch. With `BooleanCollectorsDemo` data, explain the result true=430, false=80.
9. Design a three-group classification `LOW/MEDIUM/HIGH` using an enum and `groupingBy`. Why can `partitioningBy` not represent all three labels?
10. Write a unit test checking both keys of `partitioningBy`, including when data is empty; write a test for `groupingBy` where only one label is present.
11. Write code taking `Map<Boolean, List<Order>>` from `groupingBy` and using `getOrDefault` to return statistics without NPE. Note clearly that `getOrDefault` does not add an entry.
12. Compare choosing `partitioningBy` and `groupingBy` when preparing a response for a dashboard that must always have two cards: "passed"/"failed".
13. Create `Predicate<Order> large = order -> order.amount() >= 100` and use both `partitioningBy(large)` and `groupingBy(large::test)`. Explain `boolean` versus `Boolean`.
14. Run the collector on a parallel stream and use the result by each key; why must neither the order of predicate invocations nor the iteration order of the Map be used as a test criterion?

## 16. Checklist When Choosing a Collector

- Does the problem have exactly **two boolean branches** or is it multi-label classification?
- Is the map required to **always have both true and false keys**, even when empty?
- Does the caller use `get(false)` and immediately call `size`/`stream`?
- Should a branch with no data be represented as **an empty group** or an **absent key**?
- Should the downstream collect a list, count, sum, average, min/max, or identifiers?
- For an empty group, does the downstream return a semantically correct default value?
- Is the predicate/classifier pure, consistent, and handling null data according to contract?
- Are you inferring key order or map mutability based on the current implementation?
- Have you tested true-only, false-only, both, and empty-source data?
- If using a parallel stream, are side effects outside the collector and shared mutable data kept to a minimum?

**Conclusion:** `Collectors.partitioningBy(predicate)` is the direct choice for **two true/false branches and guaranteeing both Boolean keys**, even with an empty source. `Collectors.groupingBy(element -> booleanExpression)` can produce the same data when both types appear, but **only keeps keys that actually have elements**. This subtle difference in the key set determines the safety of `get(...)`, default statistical values, and the meaning of results when data is missing.
