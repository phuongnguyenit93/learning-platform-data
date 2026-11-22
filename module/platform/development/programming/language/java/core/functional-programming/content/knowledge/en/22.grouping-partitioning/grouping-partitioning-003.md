# Choosing the Map Type to Control Key Order When Grouping and Partitioning in Java

## 1. Why Does the Result Map of Grouping Need a Clear Order?

When using Java Stream to **group data** with `Collectors.groupingBy(...)`, the result is usually a `Map<K, ...>`: each key represents a group, and the value is the elements or statistics of that group. Grouping correctly is not enough if an API, report, or UI needs to display **the groups in a specific order**.

For example, an order source appears in this order:

~~~text
Games(15), Books(10), Food(8), Games(5), Books(20)
~~~

After grouping by product category and summing, there are three keys:
- `Games` has a total of 20.
- `Books` has a total of 30.
- `Food` has a total of 8.

We may want to display the groups according to two different rules:

~~~text
First-seen order: Games → Books → Food
Ascending name order: Books → Food → Games
~~~

With the same data and the same grouping function, **the chosen Map type can control the key iteration order**. Therefore, the requirement must be determined before calling the collector.

Three foundational choices:

| Requirement | Suitable Map Type | Ordering Meaning |
| --- | --- | --- |
| Lookup and statistics only, order-independent | `Map` provided by the collector, or `HashMap` if chosen manually | No iteration order guarantee |
| Iterate in the order **keys are first added** | Insertion-order `LinkedHashMap` | Remembers key insertion order |
| Iterate keys **in comparison order** | `TreeMap` | Sorted ascending by natural order or by a Comparator |

**Important note:** `Map<K,V>` itself does not guarantee a general iteration order. You must consider the **actual implementation** and the **contract** of the collector. A result that looks sorted on your machine is not enough to claim that its order is guaranteed.

## 2. Default groupingBy Does Not Guarantee Map Type or Key Order

The shortest way to write it is:

~~~java
Map<String, List<Sale>> grouped = sales.stream()
        .collect(Collectors.groupingBy(Sale::category));
~~~

This is an **illustrative snippet inside a method**, requiring imports for `java.util.Map`, `java.util.List`, `java.util.stream.Collectors`, and a `Sale` class with a `category()` method.

The general signature of this collector form can be read as:

~~~java
groupingBy(classifier)
~~~

The `classifier` function takes each element and returns the **grouping key**. Elements with the same key according to the Map's equality criteria are placed into the same group.

By API contract, the `groupingBy(classifier)` overload **does not guarantee** the specific type, mutability, serializability, or thread-safety of the resulting Map. Therefore, you should not write business logic assuming it is necessarily a `HashMap` or has a stable random order.

For example, one run might produce keys that look like:

~~~text
[Books, Games, Food]
~~~

However, that sequence must not be treated as a **required expectation**. Another run, different data, or a different implementation may produce a different order.

### 2.1. Do Not Rely on HashMap Coincidences

`HashMap` guarantees neither insertion order nor sorted iteration order. The actual appearance order can be affected by hashes, table capacity, rehashing, and implementation details.

If iterating by key is part of the requirement (e.g., alphabetical categories, statistics preserving source order), you must **choose a Map by its contract** rather than trying to control order based on currently observed hash values.

## 3. groupingBy with mapFactory — The Key Extension Point

Java provides the overload:

~~~java
groupingBy(classifier, mapFactory, downstream)
~~~

It allows passing a `Supplier<M extends Map<K,D>>` to **create the result Map**. That is how you control the Map type used in grouping.

Example:

~~~java
Map<String, Long> counts = sales.stream()
        .collect(Collectors.groupingBy(
                Sale::category,
                LinkedHashMap::new,
                Collectors.counting()));
~~~

This illustrative snippet requires importing `java.util.LinkedHashMap`, `java.util.Map`, `java.util.stream.Collectors`. `Collectors.counting()` is the *downstream collector*, producing an aggregated value that is the number of elements in each group.

**Reading the three parameters in order:**

1. **classifier**: `Sale::category` determines the grouping key.
2. **mapFactory**: `LinkedHashMap::new` determines the Map storing the result and the key insertion order.
3. **downstream**: `Collectors.counting()` determines that the value at each key is the total count of elements.

If you want to group into a list instead of counting:

~~~java
Map<String, List<Sale>> grouped = sales.stream()
        .collect(Collectors.groupingBy(
                Sale::category,
                LinkedHashMap::new,
                Collectors.toList()));
~~~

Thus, the **Map type** and **how each group's values are accumulated** are two separate choices. Do not treat `LinkedHashMap` as a counting collector or assume it replaces `Collectors.toList()`.

### 3.1. Why Not Pass LinkedHashMap Directly to groupingBy(classifier, downstream)?

The two-argument form:

~~~java
groupingBy(classifier, downstream)
~~~

does not have a mapFactory parameter. If you want to control the output Map, use the **three-argument form**. The code needs a supplier that actually creates a Map, such as `LinkedHashMap::new`, rather than passing `new LinkedHashMap<>()` as an argument there.

## 4. LinkedHashMap — Preserving First-Seen Key Order

By default, `LinkedHashMap` stores **insertion order**. If a key is added and later appears again, updating that key's value in a standard insertion-order Map does not move it to the end just because of the update.

For example, with input:

~~~text
Games, Books, Food, Games, Books
~~~

with a **sequential Stream having encounter order**, using `groupingBy(..., LinkedHashMap::new, ...)`:

~~~java
Map<String, Long> counts = sales.stream()
        .collect(Collectors.groupingBy(
                Sale::category,
                LinkedHashMap::new,
                Collectors.counting()));

System.out.println(counts.keySet());
~~~

If the source elements are in the exact order above, the keys inserted for the first time are `Games`, `Books`, `Food` in that order. Expected result:

~~~text
[Games, Books, Food]
~~~

For grouped data, that is usually the right way to satisfy the requirement **"preserve the order in which groups appear in the input file or source list"**.

### 4.1. Conditions for Saying "Appearance Order"

Not every Stream source has a well-defined encounter order. Cases:

- `List.of(...)` and `ArrayList` have encounter order matching element order.
- `LinkedHashSet` typically provides iteration order matching insertion order.
- `HashSet` does not promise order by insertion position.
- After `sorted(...)`, the encounter order is determined by the new sort.
- After `unordered()`, you can no longer rely on the same encounter order constraint.

With `HashSet.stream()`, even if the target is `LinkedHashMap`, **the order in which groups are first added during traversal is not necessarily the desired business source order**. LinkedHashMap remembers insertion order, but it does not create a business-valid order if the source has no order.

### 4.2. Be Careful with Parallel Streams

When using `parallelStream()`, splitting the source and merging results makes reasoning like "whichever group is discovered first on any thread will be inserted first" dangerous. Do not rely on **physical execution scheduling** or partial Map insertions to infer key order.

If the goal is **first-seen group order**, the simple, easy-to-explain, and testable approach is to use a **sequential ordered Stream** and then `LinkedHashMap::new`. If the goal is a stable report table order independent of processing schedule, `TreeMap` or an explicit sort step after aggregation may be more appropriate.

Do not interpret the word "Linked" as meaning the Map is automatically thread-safe: `LinkedHashMap` does **not** provide safety for arbitrary concurrent writes.

### 4.3. LinkedHashMap Also Has Access-Order

A special constructor of `LinkedHashMap` enables access-order, for example:

~~~java
LinkedHashMap<String, Integer> cache =
        new LinkedHashMap<>(16, 0.75f, true);
~~~

This is illustrative code inside a method, requiring importing `java.util.LinkedHashMap`. The `true` value enables **recent-access** order, which differs from insertion order. Certain access operations can change the iteration position of a key.

In grouping problems that need first-seen order, you should use the default **insertion-order** `LinkedHashMap::new`. Do not supply an access-order mapFactory and assume key order will still follow first appearance.

## 5. TreeMap — Sorting Keys by Natural Order or Comparator

If the requirement is **"display groups in ascending name order"**, use `TreeMap`:

~~~java
Map<String, Integer> totals = sales.stream()
        .collect(Collectors.groupingBy(
                Sale::category,
                TreeMap::new,
                Collectors.summingInt(Sale::amount)));
~~~

The illustrative snippet requires importing `java.util.Map`, `java.util.TreeMap`, `java.util.stream.Collectors`. With the keys `Games`, `Books`, and `Food`, the iteration order of `TreeMap` is:

~~~text
[Books, Food, Games]
~~~

`TreeMap` implements `SortedMap` and `NavigableMap`, sorting keys by **natural ordering** or a `Comparator` you provide. This is a rule about the order of **key values**, not the appearance order of elements in the Stream.

### 5.1. Reversing Order with a Comparator

~~~java
Map<String, Integer> reversed = sales.stream()
        .collect(Collectors.groupingBy(
                Sale::category,
                () -> new TreeMap<>(Comparator.reverseOrder()),
                Collectors.summingInt(Sale::amount)));
~~~

The illustrative snippet requires importing `java.util.Comparator`, `TreeMap`, `Map`, and `Collectors`. When iterating keys, the result is:

~~~text
[Games, Food, Books]
~~~

Use this approach when you need to group by keys in descending order. Do not use `HashMap` and hope that printing it happens to look descending.

### 5.2. TreeMap Sorts by Key, Not Automatically by Group Total

For example, if the totals are:

~~~text
Games=20, Books=30, Food=8
~~~

`TreeMap<String,Integer>` sorts by **String key**, so the ascending order is `Books`, `Food`, `Games`. It does **not** automatically put Food (8) first because of its lower value.

If you want to **sort groups by total amount descending**, you must compute the totals first and then **sort the entries by value**, with an appropriate tie-breaker:

~~~java
List<Map.Entry<String, Integer>> byAmount = totals.entrySet().stream()
        .sorted(Map.Entry.<String, Integer>comparingByValue().reversed()
                .thenComparing(Map.Entry.comparingByKey()))
        .toList();
~~~

This is illustrative code inside a method, where `totals` is `Map<String,Integer>`, requiring imports for `java.util.List`, `java.util.Map`. The output is ordered by descending value and, on ties, compared by key name. If you need to return a Map that still preserves this entry order, after the sort step you can collect into a `LinkedHashMap` with an explicit merge policy, instead of a `TreeMap`.

### 5.3. String Comparison Is Not Equivalent to Language Collation

The natural order of `String` is based on character comparison according to Java rules, **not locale-specific dictionary order** (such as Vietnamese).

If a report requires region/language-specific sorting order, an appropriate comparator is needed; you can look into `java.text.Collator` or an intentionally normalized sort key. However, choosing a Comparator for `TreeMap` also determines **when two keys are considered equivalent**; see the next section.

## 6. TreeMap Pitfall: A Comparator Can Merge Two Different Keys

In `TreeMap`, two keys are treated as the same Map position when the comparator returns **0**. This directly affects `groupingBy`.

For example, with data:

~~~text
Java, java, JAVA, Go
~~~

and collector:

~~~java
Map<String, Long> grouped = words.stream()
        .collect(Collectors.groupingBy(
                name -> name,
                () -> new TreeMap<>(String.CASE_INSENSITIVE_ORDER),
                Collectors.counting()));
~~~

The illustrative snippet requires importing `Map`, `TreeMap`, and `Collectors`. The comparator ignores case when comparing; therefore, the three strings `Java`, `java`, and `JAVA` belong to **one equivalent key** in the TreeMap, even though `String.equals` distinguishes the three strings.

Java 17 test result:

~~~text
grouped.size() = 2
grouped.get("Java") = 3
grouped.get("Go") = 1
~~~

**Consequence:** A Comparator does not only sort—it can also **change how grouping works**! If keys must remain distinct according to `equals`, ensure the comparator is **consistent with equals** or separate the grouping step and the display step into two structures.

For example, if you want to keep `Java` and `java` as two distinct keys while sorting them next to each other, you can use a case-insensitive comparator **with a natural-order tie-breaker** so it does not return 0 for two different strings:

~~~java
Comparator<String> order = String.CASE_INSENSITIVE_ORDER
        .thenComparing(Comparator.naturalOrder());

Map<String, Integer> map = new TreeMap<>(order);
~~~

This is an illustrative snippet inside a method, requiring importing `java.util.Comparator`, `Map`, `TreeMap`. Using a comparator should be tested on the actual key domain, especially with Unicode, letter casing, and normalized strings.

### 6.1. Nulls and Comparability

With `TreeMap` using natural order, keys must be validly comparable; types without a suitable natural ordering can lead to a `ClassCastException` during insertion/comparison. Support for `null` depends on the comparator; a natural-order TreeMap does not accept null keys under its standard contract.

Specifically, `Collectors.groupingBy` in Java 17 is also not suitable for a classifier that returns null in normal scenarios; the implementation checks and may throw a `NullPointerException`. If source data has missing keys, clarify the policy: filter out the element, use an appropriate sentinel key, or model "uncategorized" as an explicit business category.

## 7. Distinguishing Key Order from Element Order Within Each Group

There are at least **two independent ordering axes**:

1. **Order in which keys are iterated:** determined by the Map type.
2. **Order of elements within each group:** determined by the source, pipeline, and downstream collector.

Example:

~~~java
Map<String, List<Integer>> amounts = sales.stream()
        .collect(Collectors.groupingBy(
                Sale::category,
                LinkedHashMap::new,
                Collectors.mapping(Sale::amount, Collectors.toList())));
~~~

With the sample data:

~~~text
Games=[15, 5]
Books=[10, 20]
Food=[8]
~~~

`LinkedHashMap` determines that the keys are displayed as Games, Books, Food. Meanwhile, `Collectors.mapping(Sale::amount, Collectors.toList())` determines that each group's value is a list of amounts; from the sequential Stream of a `List` with encounter order in the example, they appear in the order corresponding to the source elements within each group.

If you change mapFactory to `TreeMap::new`, **the key order changes**, but that does not automatically sort the amounts inside each group. To sort each group's values, you need another downstream collector or processing step, such as `collectingAndThen(toList(), list -> list.stream().sorted().toList())` when semantically appropriate.

Do not mistake "TreeMap is sorted" for "every sublist inside the Map is sorted".

## 8. partitioningBy: Only Two Boolean Keys, No mapFactory

`Collectors.partitioningBy(predicate)` splits elements into two sets according to a condition:

- Key `Boolean.FALSE`: elements that do not satisfy the condition.
- Key `Boolean.TRUE`: elements that satisfy the condition.

Example:

~~~java
Map<Boolean, Long> partition = sales.stream()
        .collect(Collectors.partitioningBy(
                sale -> sale.amount() >= 10,
                Collectors.counting()));
~~~

With the sample data:

~~~text
false -> 2 elements
true  -> 3 elements
~~~

**Important distinction:** `partitioningBy` does not provide an overload with a mapFactory parameter like `groupingBy(classifier, mapFactory, downstream)`. The API guarantees that the resulting Map contains the two keys `true` and `false`, but **does not guarantee the Map type or the iteration order of the two keys**.

Therefore, if the UI requires **"Failed" before "Passed"**, access them explicitly:

~~~java
System.out.println("Failed: " + partition.get(false));
System.out.println("Passed: " + partition.get(true));
~~~

Instead of:

~~~java
// Do not treat iteration order as business order:
// partition.forEach((key, value) -> System.out.println(key + ": " + value));
~~~

### 8.1. Empty Source Case

A useful property is that `partitioningBy` with a downstream is designed around two partitions: the resulting Map still contains **both Boolean keys**, even if one side or both have no elements.

For example, on an empty source and the default `toList()` downstream:

~~~java
Map<Boolean, List<String>> empty = Stream.<String>empty()
        .collect(Collectors.partitioningBy(s -> s.length() >= 3));

System.out.println(empty.get(false).size()); // 0
System.out.println(empty.get(true).size());  // 0
~~~

The illustrative snippet requires importing `Map`, `List`, `Stream`, `Collectors`. This access pattern does not rely on key order or the Map class chosen by the implementation.

### 8.2. If You Truly Need an Ordered Map After Partitioning

You can create **a separate Map** with the structure needed for reporting, for example:

~~~java
Map<Boolean, Long> ordered = new LinkedHashMap<>();
ordered.put(false, partition.get(false));
ordered.put(true, partition.get(true));
~~~

The illustrative snippet is placed inside a method, requiring importing `Map` and `LinkedHashMap`. It makes the presentation order explicit, **without changing the contract of partitioningBy**. With only two business labels, sometimes a record with two fields or printing two explicit lines is even easier to understand.

## 9. toMap: Choosing the Map via the Four-Argument Overload

Besides `groupingBy`, `Collectors.toMap(...)` also has a form that accepts a Map supplier:

~~~java
toMap(keyMapper, valueMapper, mergeFunction, mapFactory)
~~~

Example of summing totals by category using `TreeMap`:

~~~java
Map<String, Integer> totals = sales.stream()
        .collect(Collectors.toMap(
                Sale::category,
                Sale::amount,
                Integer::sum,
                TreeMap::new));
~~~

This is an illustrative snippet inside a method. `keyMapper` selects the product category, `valueMapper` selects the amount value, `mergeFunction` is used when multiple elements share the same key, and `mapFactory` determines the Map type.

With the sample data, the result is iterated in the natural ordering of TreeMap:

~~~text
{Books=30, Food=8, Games=20}
~~~

**Note on duplicate keys:** if you use the `toMap(keyMapper, valueMapper)` form and encounter multiple elements with the same key without providing a suitable merge function, the collector may throw an `IllegalStateException`. Therefore, when you want to sum multiple rows sharing a key, you need `Integer::sum` (or a domain-appropriate merge operation). `groupingBy(..., summingInt(...))` often expresses the intent to group and aggregate more directly.

The `toMap` form with mapFactory is suitable when key mapping and duplicate-key handling are well defined, and it is not the only way to group.

## 10. groupingByConcurrent and Ordering in Parallel Processing

When using `parallelStream()` with large volumes, `Collectors.groupingByConcurrent(...)` can be suitable for certain performance and data-combining requirements that **do not need to preserve encounter order**.

However, you must distinguish:

| Collector | Characteristics | Suitable When Clear Key Order Is Needed? |
| --- | --- | --- |
| `groupingBy(...)` without mapFactory | Does not guarantee Map type | No, if relying only on the default |
| `groupingBy(..., LinkedHashMap::new, ...)` | Chooses insertion-order Map | Suitable with an ordered, sequential source when first-seen order is desired |
| `groupingBy(..., TreeMap::new, ...)` | Chooses sorted-key Map | Suitable when comparator-based order is needed |
| `groupingByConcurrent(...)` | Concurrent and unordered collector | Does not guarantee key order like LinkedHashMap/TreeMap |
| `partitioningBy(...)` | Two Boolean keys by predicate | Access false/true explicitly to control presentation order |

`groupingByConcurrent` produces a result of the `ConcurrentMap` family and has overloads accepting a concurrent-style mapFactory, but you should not assume you can pass a regular `LinkedHashMap` to get both concurrency and insertion-order. Concurrent Maps have their own contracts regarding safety and ordering.

When both parallel processing **and** report-ordered keys are needed, a straightforward strategy is to **collect the data validly**, and then **sort the results** with a documented rule. Measure the actual cost if the data is large; do not assume groupingByConcurrent is always faster than groupingBy across all workloads.

**Distinction:** collector thread-safety within Stream reduction does not allow callbacks to arbitrarily mutate source Maps or external shared result containers.

## 11. Complete Java 17 Example: Comparing Three Maps and Partitioning

Create the file **GroupingMapOrderDemo.java**. The example includes:
- Default `groupingBy` for value lookup, **without relying on key order**.
- `LinkedHashMap` to preserve first-seen group order.
- `TreeMap` to sort keys in ascending and descending order.
- Downstream `mapping(..., toList())` showing element order within each group.
- `partitioningBy` with two Boolean keys.
- `toMap` with merge and Map factory.

~~~java
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class GroupingMapOrderDemo {
    record Sale(String category, int amount) {}

    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("Games", 15),
                new Sale("Books", 10),
                new Sale("Food", 8),
                new Sale("Games", 5),
                new Sale("Books", 20)
        );

        Map<String, Integer> defaultGroups = sales.stream()
                .collect(Collectors.groupingBy(
                        Sale::category,
                        Collectors.summingInt(Sale::amount)));

        Map<String, Integer> insertionGroups = sales.stream()
                .collect(Collectors.groupingBy(
                        Sale::category,
                        LinkedHashMap::new,
                        Collectors.summingInt(Sale::amount)));

        Map<String, Integer> sortedGroups = sales.stream()
                .collect(Collectors.groupingBy(
                        Sale::category,
                        TreeMap::new,
                        Collectors.summingInt(Sale::amount)));

        Map<String, Integer> reversedGroups = sales.stream()
                .collect(Collectors.groupingBy(
                        Sale::category,
                        () -> new TreeMap<>(Comparator.reverseOrder()),
                        Collectors.summingInt(Sale::amount)));

        System.out.println("default lookups=" + defaultGroups.get("Games")
                + "/" + defaultGroups.get("Books")
                + "/" + defaultGroups.get("Food"));
        System.out.println("first-seen keys=" + insertionGroups.keySet());
        System.out.println("alphabetical keys=" + sortedGroups.keySet());
        System.out.println("reverse keys=" + reversedGroups.keySet());
        System.out.println("insertion totals=" + insertionGroups);

        Map<String, List<Integer>> amountByCategory = sales.stream()
                .collect(Collectors.groupingBy(
                        Sale::category,
                        LinkedHashMap::new,
                        Collectors.mapping(Sale::amount, Collectors.toList())));
        System.out.println("amounts=" + amountByCategory);

        Map<Boolean, Long> partition = sales.stream()
                .collect(Collectors.partitioningBy(
                        sale -> sale.amount() >= 10,
                        Collectors.counting()));
        System.out.println("partition false=" + partition.get(false)
                + ", true=" + partition.get(true));

        Map<String, Integer> viaToMap = sales.stream()
                .collect(Collectors.toMap(
                        Sale::category,
                        Sale::amount,
                        Integer::sum,
                        TreeMap::new));
        System.out.println("toMap sorted=" + viaToMap);
    }
}
~~~

Compile and run from the directory containing the file using JDK 17 or later:

~~~bash
javac --release 17 GroupingMapOrderDemo.java
java GroupingMapOrderDemo
~~~

**Directly verified stdout:**

~~~text
default lookups=20/30/8
first-seen keys=[Games, Books, Food]
alphabetical keys=[Books, Food, Games]
reverse keys=[Games, Food, Books]
insertion totals={Games=20, Books=30, Food=8}
amounts={Games=[15, 5], Books=[10, 20], Food=[8]}
partition false=2, true=3
toMap sorted={Books=30, Food=8, Games=20}
~~~

### 11.1. Output Explanation

1. `default lookups=20/30/8`: the three values are accessed **directly by key**, independent of the default Map's iteration order.
2. `first-seen keys=[Games, Books, Food]`: the three keys are inserted into `LinkedHashMap` for the first time in their order of appearance in the sequential List source.
3. `alphabetical keys=[Books, Food, Games]`: `TreeMap` automatically iterates keys in natural String ordering.
4. `reverse keys=[Games, Food, Books]`: the comparator reverses natural ordering.
5. `insertion totals={Games=20, Books=30, Food=8}`: group summation is correct, and Map printing follows LinkedHashMap's insertion order.
6. `amounts={Games=[15,5], Books=[10,20], Food=[8]}`: the order of amounts in each group reflects the order of source elements in the sequential example; that is **downstream order**, distinct from key order.
7. `partition false=2, true=3`: classified by `amount >= 10`; the two non-matching values are 8 and 5.
8. `toMap sorted={Books=30, Food=8, Games=20}`: `TreeMap` used with toMap and `Integer::sum` merge still yields ascending key order.

The program intentionally **does not directly print** the default Map or `partition.entrySet()` to avoid output whose key order is not guaranteed by the API. The numbers and lists were verified with `javac --release 17` and an actual JVM.

## 12. Common Mistakes When Controlling Key Order

| Mistake | Why It Is Wrong | How to Fix |
| --- | --- | --- |
| Assuming default groupingBy returns a HashMap with a specific order | The API does not guarantee Map type or order | Use mapFactory |
| Using HashMap for reports requiring insertion order | Insertion order is not guaranteed | Use LinkedHashMap |
| Using LinkedHashMap with an unordered source | There is no business-valid first-seen order | Choose an ordered source, or sort beforehand |
| Using TreeMap to "sort by total amount" | TreeMap sorts by **key**, not by value | Sort entries after aggregating |
| Using a case-insensitive TreeMap comparator while wanting keys differing in case kept separate | A comparator returning 0 merges two keys | Use a comparator with a tie-breaker or change the design |
| Confusing Map order with List order inside group values | The two orders are controlled by two different mechanisms | Design downstream/sorting explicitly |
| Assuming partitioningBy iterates false then true | The API does not guarantee iteration order | Access via `get(false)`, `get(true)` |
| Passing LinkedHashMap::new to groupingByConcurrent | The Map type is not an appropriate ConcurrentMap | Use a compatible collector and sort results afterward |
| Using toMap without merge when keys duplicate | Can throw IllegalStateException | Provide a merge function |
| Assuming TreeMap automatically supports all key types | Requires Comparable or a valid Comparator | Choose a domain-appropriate comparator |
| Assuming all String ordering is Vietnamese dictionary order | Natural ordering is not locale-aware | Use Collator/a clearly contracted comparison key |
| Replacing the result Map with Map.copyOf and still expecting original iteration order | Immutable Maps created by that API do not promise to preserve iteration order | Choose an appropriate presentation result structure/DTO |

## 13. Checklist for Choosing a Map Type in Grouping/Partitioning

Before using `collect(...)`, check:

1. **Is key order a business requirement?** If not, do not add unnecessary sorting overhead.
2. **Do you want first-seen order or comparison order?** For the first, choose LinkedHashMap on a sequential ordered source; for the second, choose TreeMap/Comparator.
3. **Does the source have a guaranteed encounter order?** If not, insertion-order does not equal business order.
4. **Is the key type Comparable?** If not, TreeMap needs a Comparator.
5. **Can the Comparator return 0 for two keys that the domain treats as distinct?** If yes, TreeMap may merge groups unexpectedly.
6. **Does the order of values within each group need separate handling?** If yes, design the downstream accordingly.
7. **Is the collector groupingBy or partitioningBy?** PartitioningBy has two Boolean keys and does not accept a Map factory.
8. **Are there duplicate keys when using toMap?** If yes, a merge function is needed.
9. **Are you using parallel or groupingByConcurrent?** Do not infer order from physical execution scheduling; design reporting/sorting separately.
10. **Do you need to sort by aggregated statistics instead of keys?** You must sort entries by value with a proper tie-breaker.
11. **Is the output JSON/API requiring a specific order?** If yes, decide on the representation structure and ensure the serializer preserves order as contracted, rather than inferring it from Map.
12. **Have you tested empty-source cases and seemingly equivalent keys?** These inputs easily expose grouping and comparator bugs.

## 14. Self-Check Exercises

**Exercise 1.** A List contains keys in the order `["B","A","B","C"]`. You want the grouped Map to iterate in the order `B,A,C`—what do you use?

**Answer:** `groupingBy(x -> x, LinkedHashMap::new, Collectors.toList())` on a sequential Stream of the List. LinkedHashMap records keys when they first appear.

**Exercise 2.** With that same data, you want to display `A,B,C` regardless of source order—what do you use?

**Answer:** `TreeMap::new` as mapFactory if the keys have the desired natural order; or an explicit comparator when a different order is needed.

**Exercise 3.** Why is `Collectors.groupingBy(classifier)` insufficient if the system needs to print groups in a specific order?

**Answer:** The default overload does not promise a Map type or iteration order; an appropriate mapFactory or a separate sort step is required.

**Exercise 4.** Does `partitioningBy(predicate)` guarantee that `entrySet()` always iterates `false` before `true`?

**Answer:** No. Access `map.get(false)` and then `map.get(true)` explicitly.

**Exercise 5.** If TreeMap uses `String.CASE_INSENSITIVE_ORDER`, how many groups can the three keys `Java`, `java`, `JAVA` become?

**Answer:** One group, because the comparator treats them as equivalent (returns 0). Check the comparator to avoid unintended key merging.

**Exercise 6.** What will using TreeMap with a numeric `price` key do?

**Answer:** Sort **by the price key**, not by the value containing element counts or other group information.

**Exercise 7.** What happens if `Collectors.toMap(key, value)` has two elements with the same key and no merge is provided?

**Answer:** A duplicate key error occurs per the collector contract; when merging is needed, you must provide a merge function.

**Exercise 8.** With the sale List in the example, does `LinkedHashMap` automatically sort the Games amounts in ascending order from 5 to 15?

**Answer:** No. It only controls the iteration order of the Map keys; the child values are determined by the downstream collector.

**Exercise 9.** If you need a table with groups ordered by descending total amount, should you use TreeMap directly?

**Answer:** No, not if the TreeMap keys are the group names. First aggregate, then sort entries by value descending; use an explicit tie-breaker for deterministic order.

## 15. References

- [Java SE 17 — Collectors.groupingBy / partitioningBy / toMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html).
- [Java SE 17 — LinkedHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html).
- [Java SE 17 — TreeMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html).
- [Java SE 17 — Map](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html).
- [Java SE 17 — Stream ordering](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/package-summary.html).

**Conclusion:** When grouping or partitioning data, **key order is not automatically guaranteed by Map or the default groupingBy**. When grouping from a sequential ordered source, use **`LinkedHashMap::new`** if you want to preserve first-seen key order; use **`TreeMap::new` or a Comparator** if you want to sort by key. With **`partitioningBy`**, access `false`/`true` explicitly because there is no mapFactory; with **`toMap`**, choose the mapFactory and merge function properly. Finally, always distinguish **key order, element order within a group, order by aggregated value, and concurrency** to avoid results that only happen to be right on a single run.
