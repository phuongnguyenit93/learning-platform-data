# Distinguishing Deduplication from Keeping All Elements and Sorting

When working with Java data, **sorting** and **deduplicating** are two distinct operations. Sorting only changes the order of elements according to a rule; deduplicating reduces the number of elements by keeping one representative for each group considered equivalent. A `TreeSet` performs both behaviors: maintaining order and keeping only **one element per group whose comparison result is `0`**. Conversely, `List.sort(...)` or `Stream.sorted(...)` sorts while **preserving all occurrences**, including duplicate values.

This is an important distinction in the topic of **ordered collections** and object contracts: deciding whether two elements are “duplicates” in `TreeSet` relies on **`compareTo` or `Comparator.compare`**, which does not necessarily match `equals`.

## 1. Two different requirements lead to two different results

Suppose the input data is:

```text
[pear, apple, pear, banana, apple]
```

We might want:

| Requirement | Result | Meaning |
| --- | --- | --- |
| Keep data unchanged | `[pear, apple, pear, banana, apple]` | Input order and occurrence counts unchanged |
| **Sort only** ascending | `[apple, apple, banana, pear, pear]` | Keep all 5 elements, only change positions |
| **Deduplicate then sort** | `[apple, banana, pear]` | 3 distinct values remain |
| **Count occurrences in key order** | `{apple=2, banana=1, pear=2}` | Preserve frequency information even though each key appears once |

If processing orders, visit logs, log records, or scores, carelessly putting data into a `Set` can **lose meaningful duplicate records**. Conversely, if the goal is a set of unique skill names, deduplication may be the exact requirement.

**The first design question must be:** do we need to *keep every occurrence*, *keep one representative element*, or *keep the occurrence count of each group*?

## 2. `List.sort` and `Stream.sorted`: order elements without deleting any

A `List` allows multiple equal elements to appear at different positions. With a mutable `ArrayList`, we can sort in place:

```java
// Illustrates a snippet inside a method, not a standalone program.
List<String> words = new ArrayList<>(
        List.of("pear", "apple", "pear", "banana", "apple"));
words.sort(Comparator.naturalOrder());
// words: [apple, apple, banana, pear, pear]
```

`List.sort(comparator)` changes order **directly inside the list**. Duplicate elements still occupy their own positions. It is a *stable sort*: when the comparator returns `0` for two elements, their original relative order is preserved. If a list does not allow structural/content modification, such as `List.of(...)`, do not call `sort` directly on it; create `new ArrayList<>(source)` or use a stream.

`Stream.sorted()` produces a newly sorted stream without deduplicating:

```java
// Illustrates a snippet inside a method:
List<String> sorted = source.stream()
        .sorted()
        .toList();
```

For an *ordered stream*, `sorted` is guaranteed stable; for a stream without encounter order, stability is not guaranteed. `toList()` returns a list that cannot be modified via list-mutating methods under `Stream.toList()`'s contract, so if modification after sorting is needed, collect into a suitable `ArrayList`.

**There is no `distinct()` step in the two operations above**, so the element count is preserved.

## 3. `TreeSet`: both sorts and deduplicates by comparison order

`TreeSet<E>` belongs to the `NavigableSet`/`SortedSet` family, maintaining elements according to:

- **Natural ordering** of `Comparable`, when using `new TreeSet<>()` and elements are mutually comparable.
- **Ordering specified by `Comparator`**, when using `new TreeSet<>(comparator)`.

`TreeSet`'s rule for distinguishing elements is:

```text
compare(a, b) < 0  -> a comes before b
compare(a, b) = 0  -> a and b are treated as the same element under the set's ordering
compare(a, b) > 0  -> a comes after b
```

Under natural ordering, `compare(a,b)` means `a.compareTo(b)`; with a comparator, it is `comparator.compare(a,b)`.

When adding a new element whose comparison against an existing element returns `0`, `TreeSet.add` returns `false` and does not add a second entry. `size()` does not increase. To check whether a representative for an element is already present, `contains` can be used under the same ordering rule, though **do not infer that two objects are identical across all fields**.

Basic add/remove/search operations in `TreeSet` are guaranteed by Java documentation to have `log(n)`-order cost in the tree structure. Meanwhile, building a whole set from `n` elements has a cumulative cost corresponding to the insertions. The difference **is not solely about performance**: more importantly, `TreeSet` drops data according to the comparator's equivalence relation.

## 4. Runnable Java 17+ example: seeing counts and ordering clearly

Save the entire program as **`SortVersusSetDemo.java`**:

```java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

public class SortVersusSetDemo {
    public static void main(String[] args) {
        List<String> source = List.of(
                "pear", "apple", "pear", "banana", "apple");

        List<String> sorted = new ArrayList<>(source);
        sorted.sort(Comparator.naturalOrder());

        TreeSet<String> uniqueSorted = new TreeSet<>(source);

        System.out.println("Original: " + source);
        System.out.println("Sorted List: " + sorted);
        System.out.println("TreeSet: " + uniqueSorted);
        System.out.println("Original size: " + source.size());
        System.out.println("TreeSet size: " + uniqueSorted.size());
        System.out.println("Stream distinct then sorted: "
                + source.stream().distinct().sorted().toList());

        TreeMap<String, Integer> counts = new TreeMap<>();
        for (String word : source) {
            counts.merge(word, 1, Integer::sum);
        }
        System.out.println("Sorted frequencies: " + counts);

        List<String> spellings =
                List.of("Java", "java", "JAVA", "Kotlin");
        TreeSet<String> ignoreCase =
                new TreeSet<>(String.CASE_INSENSITIVE_ORDER);
        ignoreCase.addAll(spellings);

        System.out.println("Case-sensitive equals: "
                + "Java".equals("java"));
        System.out.println("Case-insensitive compare zero: "
                + (String.CASE_INSENSITIVE_ORDER
                        .compare("Java", "java") == 0));
        System.out.println("Case-insensitive TreeSet: " + ignoreCase);
        System.out.println("Case-insensitive TreeSet size: "
                + ignoreCase.size());
        System.out.println("Case-insensitive sorted List: "
                + spellings.stream()
                        .sorted(String.CASE_INSENSITIVE_ORDER)
                        .toList());

        BigDecimal a = new BigDecimal("1.0");
        BigDecimal b = new BigDecimal("1.00");
        System.out.println("BigDecimal equals: " + a.equals(b));
        System.out.println("BigDecimal compareTo zero: "
                + (a.compareTo(b) == 0));

        Set<BigDecimal> hash = new HashSet<>(List.of(a, b));
        Set<BigDecimal> tree = new TreeSet<>(List.of(a, b));
        System.out.println("BigDecimal HashSet size: " + hash.size());
        System.out.println("BigDecimal TreeSet size: " + tree.size());
    }
}
```

Compile and run with JDK 17 or higher:

```bash
javac SortVersusSetDemo.java
java SortVersusSetDemo
```

Deterministic output:

```text
Original: [pear, apple, pear, banana, apple]
Sorted List: [apple, apple, banana, pear, pear]
TreeSet: [apple, banana, pear]
Original size: 5
TreeSet size: 3
Stream distinct then sorted: [apple, banana, pear]
Sorted frequencies: {apple=2, banana=1, pear=2}
Case-sensitive equals: false
Case-insensitive compare zero: true
Case-insensitive TreeSet: [Java, Kotlin]
Case-insensitive TreeSet size: 2
Case-insensitive sorted List: [Java, java, JAVA, Kotlin]
BigDecimal equals: false
BigDecimal compareTo zero: true
BigDecimal HashSet size: 2
BigDecimal TreeSet size: 1
```

**Explanation:**

1. `sorted` preserves all 5 elements of `source`, simply arranging them by `String`'s natural ordering. Both `apple`s and both `pear`s remain intact.
2. `new TreeSet<>(source)` retains only one copy of each duplicate string under natural ordering, leaving 3 elements.
3. `source.stream().distinct().sorted()` yields the same result as `TreeSet` **in the string example with natural ordering**, because `String.equals` and `String.compareTo` are consistent. The two approaches must not be assumed equivalent for every comparator.
4. `TreeMap<String,Integer>` uses each string as a key and sums occurrences; the result has ascending key order, **without losing frequencies**.
5. `String.CASE_INSENSITIVE_ORDER.compare("Java","java") == 0` whereas `"Java".equals("java")` is `false`. `TreeSet` using this comparator retains only one representative element for the `Java/java/JAVA` group. Since `"Java"` was added first, it is the representative kept in the example; `"Kotlin"` is the second group.
6. `spellings.stream().sorted(String.CASE_INSENSITIVE_ORDER)` sorts by the same comparator yet **keeps all four elements**. With an ordered stream from a `List`, strings comparing as `0` preserve their initial relative order.
7. The two `BigDecimal` values have equal numeric value under `compareTo` yet different `scale`, so `equals` returns `false`. Thus `HashSet` (by `equals`/`hashCode`) keeps 2 elements, whereas `TreeSet` (by `compareTo`) keeps 1.

## 5. `equals()` and `compareTo()`: two equivalence relations that can diverge

In Java, `Set` commonly evokes “contains no two `equals`-equal elements”. However, `TreeSet` uses its comparison relation to perform all element-identification operations. Therefore, for a `SortedSet` to fully satisfy the `Set` contract in the sense of `equals`, the sort order should be **consistent with `equals`**:

```java
// Desired rule when saying ordering is consistent with equals:
(a.compareTo(b) == 0) == a.equals(b)
```

If the two sides differ, `TreeSet`'s internal behavior is still well-defined by the comparator, yet it can be surprising when compared with `HashSet` or `equals`-based set conventions.

**Case 1: `compare(a,b) == 0` even though `a.equals(b)` is `false`.** Two values are merged into one group by `TreeSet`. Examples: case-insensitive `String` comparison, or `BigDecimal("1.0")` and `BigDecimal("1.00")`.

**Case 2: `a.equals(b)` is `true` yet the comparator yields a non-`0` result.** `TreeSet` may retain two elements that `equals` treats as equal, if the comparator uses a different criterion. This is also an inconsistency between the ordering relation and the equality relation.

In particular, never use `hashCode()` to predict how `TreeSet` will deduplicate. `TreeSet` does not distinguish elements by `hashCode`; it uses **comparison order**.

### Comparator comparing only a subset of attributes

Suppose each record has independent `name` and `id`:

```java
record Item(long id, String name) {}

// An example of a name-only comparator:
Comparator<Item> byName = Comparator.comparing(Item::name);
```

This is an **illustrative snippet to be placed in an appropriate class/method**; `record Item` can be declared outside or in a valid local scope. Two `Item`s with different IDs yet the same `name` have `byName.compare(a,b) == 0`, so `TreeSet<>(byName)` will keep only one representative if both are added. That is right if name is the business distinguishing key, yet **wrong** if records with different IDs must both be kept.

If you want to **sort by name while keeping all records**, use a `List<Item>` and `sort(byName)`. If you want each ID unique in `TreeSet` ordered primarily by name, you can use a comparator with an appropriate *tie-breaker*:

```java
Comparator<Item> byNameThenId = Comparator
        .comparing(Item::name)
        .thenComparingLong(Item::id);
```

When `id` is unique and also determines equality, this comparator avoids merging two records merely because their names match. However, if the class's `equals` uses another rule, consistency must still be checked; adding `id` does not automatically solve every model.

## 6. When to use `Stream.distinct()`, and what to remember?

`Stream.distinct()` returns elements distinct according to **`Object.equals`**, and does not accept a comparator to define grouping. For a stream with encounter order (such as `List.stream()`), it retains the **first** appearing element in each `equals`-group. Afterward you can sort:

```java
// Keep one copy per equals-equivalent value, then sort:
List<String> result = source.stream()
        .distinct()
        .sorted()
        .toList();
```

This is an easy-to-understand pipeline when the deduplication rule is `equals` and the sort criterion is natural ordering. However:

- `distinct()` **does not deduplicate by an arbitrary comparator**. For `"Java"` and `"java"`, `distinct()` treats them as two different strings because `String.equals` is case-sensitive.
- `sorted(comparator).distinct()` still deduplicates by `equals`, **not switching to the comparator-returns-`0` rule**. The order of those two operations can affect the representative/encounter order in different cases; define semantics first.
- If deduplication **by a business key** is needed, you can group by key in a `Map`, or use an appropriate comparator in `TreeSet`, though you must clearly specify which representative is kept. Do not assume an API randomly picks “the newest copy” or “the best copy”.
- For ordered parallel streams, `distinct` can require stateful processing and considerable cost; performance matters less than correctness of the deduplication rule.

`distinct()` also relies on a contract-compliant `equals`/`hashCode`. If a custom class implements value-based `equals` yet forgets `hashCode`, hash-based deduplication can yield wrong results. For `TreeSet`, the corresponding requirement is that `compareTo`/`Comparator` must express the desired equivalence properly.

## 7. If you need both ordering and counts of duplicate values

You do not necessarily have to choose between “losing duplicates” and “not sorting”. Several suitable patterns exist:

| Need | Tool | What to remember |
| --- | --- | --- |
| Sort and keep every record | `ArrayList.sort`, `List.sort`, `Stream.sorted` | Multiple equal elements can be present |
| Keep one representative per comparison group and maintain order | `TreeSet` | Duplicates when comparator returns `0` |
| Deduplicate by `equals`, then sort | `stream().distinct().sorted(...)` | `distinct`'s deduplication rule is not the comparator |
| Count frequencies by ordered key | `TreeMap<K,Integer>` accumulating | Count data preserves total occurrences |
| Count frequencies by `equals` then present in a separate order | `HashMap<K,Integer>` then sort entries | Counting rule and display rule can differ |
| Deduplicate while preserving first-seen order | `LinkedHashSet` or ordered `Stream.distinct` | Input order, not sorted order |

`TreeMap` also uses comparator/`compareTo` to identify **equivalent keys**. If a comparator merges two different strings, `merge` into `TreeMap` will sum counts of the same comparator group, no longer counting each distinct `equals` value separately. That may be intentional for a case-insensitive report; otherwise, it is a grouping bug.

If an **ordered multiset** (retaining multiple copies of each element) is required, the Java Collections Framework has no built-in standard `TreeMultiset` class. A `TreeMap<K,Integer>` storing counts is a simple implementation; to keep each detailed record, a sorted `List` is usually more suitable. `PriorityQueue` can hold duplicate values and retrieve the priority element with `poll`, yet **iterator traversal of the queue is not guaranteed to be in sorted order**, so it does not directly replace a sorted list.

## 8. Common misconceptions

1. **“`TreeSet` only sorts, it does not delete data.”** False. It has set semantics, eliminating elements equivalent under the comparator.
2. **“`List.sort` automatically drops duplicate records.”** False. A list retains all occurrences.
3. **“`TreeSet` always uses `equals` to detect duplicates.”** False. `compareTo == 0` or `Comparator.compare == 0` is the condition defining the same element by order.
4. **“`TreeSet` matches `HashSet` in results.”** Not necessarily. `HashSet` uses `equals`/`hashCode`; `TreeSet` uses ordering comparison.
5. **“`sorted(comparator).distinct()` deduplicates by the comparator.”** False. `distinct` still uses `equals`.
6. **“A name-only comparator still keeps everyone with the same name.”** False if placed into a `TreeSet`, because comparing as `0` merges the group.
7. **“You can freely mutate sort fields after adding to `TreeSet`.”** Unsafe. The tree structure depends on ordering; mutating fields participating in comparator/`compareTo` while an element is in the set can break lookup, removal, and traversal expectations.
8. **“You can use `Set` to count occurrences.”** `Set` stores only one representative per group; to track frequencies, count separately or use `Map<K,Integer>`.
9. **“Equal hashes mean `TreeSet` merges elements.”** No. `TreeSet` does not use hash codes to distinguish elements.
10. **“Comparator returning `0` just means two elements sit next to each other.”** In `TreeSet`, `0` also means they **cannot coexist as two separate entries**.

## 9. Checklist before choosing a data structure

- **Do duplicate records matter?** If yes, avoid using `Set` as a default sorting step.
- **Which rule defines duplicates?** `equals`, business ID key, or a comparator (e.g., case-insensitive)?
- **Which representative should a duplicate group keep?** First copy, newest copy, highest-priority copy, or total frequency?
- **When is ordering needed?** Immediately upon inserting elements (`TreeSet`, `TreeMap`) or only when outputting results (`List.sort`)?
- **Is your custom class consistent between `equals` and `compareTo`?** If not, clearly understand the difference between `HashSet` and `TreeSet`.
- **Are fields determining order immutable?** An element inside `TreeSet` must not be mutated in a way that alters its logical position.
- **After processing, should element count equal input count or unique group count?** This is a quick check that helps catch unintended deduplication.

**Takeaway:** **Sorting** is not synonymous with **deduplicating**. Use `List.sort`/`Stream.sorted` when all elements must be preserved and only order changes; use `TreeSet` when you genuinely need a set of unique elements **under the comparison relation**; use `TreeMap<K,Integer>` when you need frequencies by sorted key. Before putting objects into `TreeSet`, always check whether `compare(a,b) == 0` is truly the “duplicate” criterion business logic intends.
