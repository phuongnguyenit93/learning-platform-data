# Collecting in Sorted Order with TreeSet

An application often needs to collect data into a set that is **both deduplicated and deterministically ordered**: an alphabetical list of product codes, ascending price tiers, or a multi-criteria ranking table. In the **Java Stream API**, the clear way to express this requirement is `collect(Collectors.toCollection(TreeSet::new))`.

`TreeSet` is a `NavigableSet` backed by an ordered tree structure. When collecting elements into a `TreeSet`, Java uses **natural ordering (`Comparable`)** or a provided **`Comparator`** to sort the elements. Notably, this comparison also determines **which elements are considered duplicates**.

This lesson belongs to the **Collecting into Collections** chapter of the **JAVA_STREAM_API** module. After this lesson, you will know how to collect a Stream into a `TreeSet`, define custom ordering, distinguish `TreeSet` from `sorted()`, `distinct()`, and `Collectors.toSet()`, and recognize risks related to `Comparator`, `null`, mutable data, parallel Streams, resources, and performance. This knowledge lays the groundwork for custom collectors, grouping, `Spliterator`, and Stream Gatherers.

## 1. Practical Problem: Needing Both Sorting and Deduplication

Suppose a system receives technology codes selected by users:

~~~text
java, kotlin, java, go, stream, kotlin
~~~

The output requirement is that **each code appears only once** and is **sorted in ascending order**. We can write:

~~~java
import java.util.List;
import java.util.TreeSet;
import java.util.stream.Collectors;

public class TreeSetOverview {
    public static void main(String[] args) {
        List<String> technologies = List.of(
            "java", "kotlin", "java", "go", "stream", "kotlin"
        );

        TreeSet<String> result = technologies.stream()
            .collect(Collectors.toCollection(TreeSet::new));

        System.out.println(result); // [go, java, kotlin, stream]
        System.out.println(technologies.size()); // 6: source remains unchanged
    }
}
~~~

In this example, `TreeSet` uses the natural ordering of `String` (`String.compareTo`). Two strings that compare equal under that comparison are kept only once. The source list has 6 elements, whereas the resulting `TreeSet` has 4 elements and iterates in ascending order.

`TreeSet` **does not depend on the appearance order** of elements for sorting. If `"api"` is appended to the end of the source, it will appear at the beginning of the resulting set.

> This example uses `List.of` (Java 9+). `TreeSet` and `Collectors.toCollection` themselves work since Java 8; if Java 8 is needed, replace `List.of(...)` with `Arrays.asList(...)`.

## 2. What Kind of Collection Is TreeSet?

`java.util.TreeSet<E>` implements `NavigableSet<E>` and follows the sorting behavior of `SortedSet<E>`. Key properties:

| Property | Meaning when used with Stream |
|---|---|
| Does not store duplicates per comparison rule | When `compare(a, b) == 0` or `a.compareTo(b) == 0`, `TreeSet` treats `a` and `b` as the same element |
| Elements are sorted | Iterates over the set according to the comparator or natural ordering |
| Range and threshold element access | Supports `first`, `last`, `lower`, `floor`, `ceiling`, `higher`, and subset views |
| Modifiable | Allows calling `add`, `remove`, `clear` on the resulting `TreeSet` |
| Not thread-safe by default | Do not mutate the same `TreeSet` concurrently from multiple threads without proper synchronization |
| Balanced-tree-based cost | Basic operations like `add`, `remove`, `contains` have guaranteed logarithmic time complexity in the set size |

A `TreeSet` created with `new TreeSet<>()` uses **natural ordering**. Therefore, elements must be **mutually comparable**, usually by implementing `Comparable`. If elements lack an appropriate natural ordering, provide a `Comparator`.

~~~mermaid
flowchart LR
    A["Stream: 7, 3, 7, 5, 3"] --> B["collect(toCollection(TreeSet::new))"]
    B --> C["TreeSet: 3, 5, 7"]
    C --> D["Iterate in ascending order"]
~~~

The data flow still follows the Stream model: `stream()` creates the source, `filter`/`map` are lazy intermediate steps if present, and `collect(...)` is the **terminal operation** producing the result.

## 3. Mechanism of Collectors.toCollection(TreeSet::new)

`Collectors.toCollection` has the general signature:

~~~java
static <T, C extends Collection<T>>
Collector<T, ?, C> toCollection(Supplier<C> collectionFactory)
~~~

The `collectionFactory` argument is a `Supplier` that creates the target collection. Passing `TreeSet::new` instructs the collector to create a **new `TreeSet`** and insert processed elements into it.

~~~java
TreeSet<Integer> numbers = java.util.stream.Stream.of(5, 1, 2, 5, 3)
    .collect(java.util.stream.Collectors.toCollection(TreeSet::new));

System.out.println(numbers); // [1, 2, 3, 5]
~~~

Conceptually, when running sequentially:

1. The collector calls the supplier to obtain an empty `TreeSet`.
2. Each element from the Stream is inserted via `add`.
3. `TreeSet` uses the comparator or natural ordering to find its position and detect duplicates.
4. `collect` returns the resulting set.

With a parallel Stream, the collector may create multiple containers, accumulate branches independently, and then merge them. Do not assume the supplier is called only once or that calls occur in a fixed thread order.

### 3.1. Why Not Just Use Collectors.toSet()?

~~~java
List<Integer> source = List.of(5, 2, 5, 1, 3);

java.util.Set<Integer> unspecified = source.stream()
    .collect(java.util.stream.Collectors.toSet());

TreeSet<Integer> ascending = source.stream()
    .collect(java.util.stream.Collectors.toCollection(TreeSet::new));

System.out.println(ascending); // [1, 2, 3, 5]
~~~

`Collectors.toSet()` creates a `Set`, but **guarantees neither the implementation type nor result iteration order**. Even if a run prints in ascending order, never rely on that.

`Collectors.toCollection(TreeSet::new)` states the requirement explicitly: **create an actual `TreeSet`** and follow that set type's ordering.

### 3.2. Why Not Just Call sorted()?

~~~java
List<Integer> values = List.of(5, 2, 5, 1, 3);

List<Integer> sortedButDuplicated = values.stream()
    .sorted()
    .collect(java.util.stream.Collectors.toList());

TreeSet<Integer> sortedAndUnique = values.stream()
    .collect(java.util.stream.Collectors.toCollection(TreeSet::new));

System.out.println(sortedButDuplicated); // [1, 2, 3, 5, 5]
System.out.println(sortedAndUnique);     // [1, 2, 3, 5]
~~~

`sorted()` **sorts without deduplicating**; `TreeSet` both sorts and deduplicates **according to the set's comparison**.

## 4. Natural Ordering: Comparable

For `Integer`, `Long`, `String`, and many standard types implementing `Comparable`, `TreeSet::new` usually works out of the box.

~~~java
import java.util.List;
import java.util.TreeSet;
import java.util.stream.Collectors;

List<Integer> scores = List.of(8, 6, 10, 6, 9, 8);

TreeSet<Integer> orderedScores = scores.stream()
    .collect(Collectors.toCollection(TreeSet::new));

System.out.println(orderedScores); // [6, 8, 9, 10]
System.out.println(orderedScores.first()); // 6
System.out.println(orderedScores.last());  // 10
~~~

**Keep in mind:** `String.compareTo` compares using Java's natural string ordering, which is case-sensitive. It **does not automatically** apply language-specific alphabetical rules such as Vietnamese collation or natural-language rules.

For example, `"Java"` and `"java"` are two distinct values in a `TreeSet<String>` using natural ordering. When normalizing codes or sorting by locale, define the business rule explicitly.

### 4.1. What About Objects Without Comparable?

~~~java
record Product(String sku, long price) {}

List<Product> products = List.of(
    new Product("SP02", 200L),
    new Product("SP01", 100L)
);

// No natural ordering exists for the Product record.
// products.stream().collect(Collectors.toCollection(TreeSet::new));
~~~

A `record` automatically generates `equals` and `hashCode`, **not `Comparable`**. A `TreeSet` using natural ordering can throw `ClassCastException` when inserting non-comparable objects. The proper approach is to supply a `Comparator<Product>`, as shown in the next section.

## 5. Specifying a Comparator When Collecting

`TreeSet` has a constructor taking a `Comparator<? super E>`. Because `Collectors.toCollection` requires a supplier, use a lambda to construct the set with a comparator:

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.TreeSet;
import java.util.stream.Collectors;

List<Integer> scores = List.of(8, 6, 10, 6, 9);

TreeSet<Integer> descendingScores = scores.stream()
    .collect(Collectors.toCollection(
        () -> new TreeSet<>(Comparator.reverseOrder())
    ));

System.out.println(descendingScores); // [10, 9, 8, 6]
~~~

If you need ascending order for objects implementing `Comparable`, you can use `Comparator.naturalOrder()`. For descending order, `Comparator.reverseOrder()` is concise. When the object type is not naturally comparable, provide a comparator specifying the exact sort fields.

### 5.1. Sorting Objects by a Field

Complete runnable example on **Java 17+**:

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.TreeSet;
import java.util.stream.Collectors;

public class ProductOrderDemo {
    record Product(String sku, String name, long priceVnd) {}

    public static void main(String[] args) {
        List<Product> products = List.of(
            new Product("SP03", "Pen",  30_000L),
            new Product("SP01", "Notebook",  80_000L),
            new Product("SP02", "Exercise Book",  30_000L)
        );

        Comparator<Product> byPriceThenSku =
            Comparator.comparingLong(Product::priceVnd)
                .thenComparing(Product::sku);

        TreeSet<Product> ordered = products.stream()
            .collect(Collectors.toCollection(
                () -> new TreeSet<>(byPriceThenSku)
            ));

        ordered.forEach(p ->
            System.out.println(p.sku() + ": " + p.priceVnd())
        );
    }
}
~~~

Output:

~~~text
SP02: 30000
SP03: 30000
SP01: 80000
~~~

`comparingLong(Product::priceVnd)` sorts price in **ascending order**. When two prices are equal, `thenComparing(Product::sku)` uses the product SKU to break ties, so `SP02` precedes `SP03`.

### 5.2. Descending Sort with Multiple Criteria

If you want descending price, and ascending SKU on ties:

~~~java
Comparator<Product> byPriceDescThenSku =
    Comparator.comparingLong(Product::priceVnd)
        .reversed()
        .thenComparing(Product::sku);

TreeSet<Product> descending = products.stream()
    .collect(Collectors.toCollection(
        () -> new TreeSet<>(byPriceDescThenSku)
    ));
~~~

The snippet above uses `Product` and `products` from the previous example. `reversed()` only reverses the comparator built up to that point; `thenComparing(Product::sku)` then continues sorting SKUs in **ascending** order when prices tie.

**Avoid subtracting integers to compare them**, such as `(a, b) -> (int) (a.priceVnd() - b.priceVnd())`. Subtraction can overflow, and casting `long` to `int` loses information. `Comparator.comparingLong` and `Long.compare` are safer for comparisons.

## 6. TreeSet Deduplicates by compare() == 0, Not Simply by equals()

This is the most critical point of the lesson.

With `Stream.distinct()`, two objects are considered duplicates by `equals()` (and must obey the `hashCode()` contract). With `TreeSet`, two elements are considered duplicates when **the comparator returns 0**, or `compareTo` returns 0 under natural ordering.

Example with `BigDecimal`:

~~~java
import java.math.BigDecimal;
import java.util.List;
import java.util.TreeSet;
import java.util.stream.Collectors;

List<BigDecimal> amounts = List.of(
    new BigDecimal("1.0"),
    new BigDecimal("1.00"),
    new BigDecimal("2.0")
);

System.out.println(amounts.get(0).equals(amounts.get(1)));    // false
System.out.println(amounts.get(0).compareTo(amounts.get(1))); // 0

long byEquals = amounts.stream().distinct().count();

TreeSet<BigDecimal> byOrdering = amounts.stream()
    .collect(Collectors.toCollection(TreeSet::new));

System.out.println(byEquals);        // 3
System.out.println(byOrdering.size()); // 2
~~~

`BigDecimal.equals` also checks `scale`, so `1.0` and `1.00` differ; `BigDecimal.compareTo` considers them numerically equal. Thus `distinct()` keeps both, whereas `TreeSet` using natural ordering keeps only one representative.

### 6.1. A Price-Only Comparator Can Drop Records

Returning to `Product`:

~~~java
Comparator<Product> onlyPrice =
    Comparator.comparingLong(Product::priceVnd);

TreeSet<Product> byPrice = products.stream()
    .collect(Collectors.toCollection(
        () -> new TreeSet<>(onlyPrice)
    ));

System.out.println(byPrice.size()); // 2, even though source has 3 products
~~~

Both `SP02` and `SP03` cost 30,000 and are treated as **duplicates by the comparator**, even though they have different SKUs. If the goal is to **sort while keeping both products**, you need a comparator that distinguishes them via a secondary criterion, such as `thenComparing(Product::sku)`.

If you need to guarantee the comparator distinguishes all `Product` records with different components, you can also include `name` as a tie-breaker:

~~~java
Comparator<Product> byPriceSkuName =
    Comparator.comparingLong(Product::priceVnd)
        .thenComparing(Product::sku)
        .thenComparing(Product::name);
~~~

In the example with non-null fields, this comparator distinguishes by all three record fields, aligning more closely with the record's default `equals`.

### 6.2. What Does a Comparator Consistent with equals Mean?

A comparator is **consistent with equals** when `compare(a, b) == 0` is equivalent to `a.equals(b)` for the relevant objects. This is a **recommended property** if you want `TreeSet` to fully uphold the general `Set` expectations for equality.

If a comparator is inconsistent with `equals`, `TreeSet` still behaves deterministically per its sorting rule, but may **violate the general `Set` contract for equality**. This easily leads to surprises when combining the set with APIs that use `equals` and `hashCode`.

Choose the comparator according to **business goals**:

- If you need a set of **unique products** sorted by price: the comparator should have tie-breakers to distinguish different products.
- If you need **unique price levels**: map to `priceVnd` first, then collect `TreeSet<Long>`.
- If you need **one representative product per code**, define the representative-selection rule explicitly, then collect by code with transparent duplicate handling.

Do not pick a comparator on a single field and accidentally discard records that differ in other fields.

### 6.3. Case-Insensitive Strings

~~~java
import java.util.List;
import java.util.TreeSet;
import java.util.stream.Collectors;

List<String> languages = List.of("Java", "java", "Kotlin", "kotlin");

TreeSet<String> caseInsensitive = languages.stream()
    .collect(Collectors.toCollection(
        () -> new TreeSet<>(String.CASE_INSENSITIVE_ORDER)
    ));

System.out.println(caseInsensitive); // [Java, Kotlin] in sequential example
~~~

`String.CASE_INSENSITIVE_ORDER` treats `"Java"` and `"java"` as equivalent for sorting and deduplication. In an ordered sequential pipeline like above, the first representative added in the group is `"Java"`. With unordered sources or when a specific record must be chosen by policy, **normalize the data or design a dedicated representative-selection rule** rather than relying on which casing happens to be kept.

If the goal is **canonical technical codes**, calling `map(value -> value.toLowerCase(Locale.ROOT))` before collecting into a `TreeSet` is usually clearer than relying solely on a case-insensitive comparator.

## 7. Normalizing and Filtering Data Before Collecting

Suppose user input contains `null`, whitespace, and empty values. The pipeline should define normalization steps before collecting:

~~~java
import java.util.Arrays;
import java.util.Locale;
import java.util.Objects;
import java.util.TreeSet;
import java.util.stream.Collectors;

public class NormalizedTreeSetDemo {
    public static void main(String[] args) {
        var raw = Arrays.asList(
            " Java ", null, "kotlin", "JAVA", "", " Go "
        );

        TreeSet<String> normalized = raw.stream()
            .filter(Objects::nonNull)
            .map(String::trim)
            .filter(s -> !s.isEmpty())
            .map(s -> s.toLowerCase(Locale.ROOT))
            .collect(Collectors.toCollection(TreeSet::new));

        System.out.println(normalized); // [go, java, kotlin]
    }
}
~~~

The step order has a purpose:

1. `filter(Objects::nonNull)` removes `null` before calling `trim`.
2. `map(String::trim)` strips leading/trailing whitespace.
3. `filter(s -> !s.isEmpty())` discards values that become empty after normalization.
4. `toLowerCase(Locale.ROOT)` standardizes code casing according to technical rules.
5. `collect(toCollection(TreeSet::new))` creates a sorted, deduplicated set.

Here `TreeSet` deduplicates based on the **normalized strings**. If we collected before normalizing, the raw strings might be treated as distinct, failing to meet the requirement.

Note: this example only shows technical code normalization rules. For personal names, Vietnamese text, or multilingual keywords, collation/Unicode rules must be defined by context instead of defaulting to `String.compareTo`.

## 8. When Should You Not Use TreeSet?

Some requirements look like "ordered collection" but actually call for a different Collection type.

| Practical need | Approach | Reason |
|---|---|---|
| Need all elements, including duplicates, sorted | `stream.sorted(comparator).collect(toList())` | `List` retains duplicate elements |
| Need unique elements per `equals`, order does not matter | `collect(toSet())` | Does not require a tree structure |
| Need unique elements per `equals`, preserving **appearance order** | `collect(toCollection(LinkedHashSet::new))` | `LinkedHashSet` is hash-based and preserves insertion order |
| Need unique elements per comparator, always iterated sorted | `collect(toCollection(() -> new TreeSet<>(comparator)))` | `TreeSet` combines comparator-based sorting and deduplication |
| Need to keep the "best" record per business key | Collect into `Map` with an explicit merge function | Allows controlling representative-selection policy |
| Only need the first few results in computed order | Consider `sorted` + `limit` or a dedicated top-k algorithm | Avoids storing the whole set unnecessarily |

Direct comparison example:

~~~java
import java.util.LinkedHashSet;
import java.util.List;
import java.util.TreeSet;
import java.util.stream.Collectors;

List<Integer> input = List.of(3, 1, 3, 2);

List<Integer> sortedAll = input.stream()
    .sorted()
    .collect(Collectors.toList());
// [1, 2, 3, 3]

LinkedHashSet<Integer> insertionOrder = input.stream()
    .collect(Collectors.toCollection(LinkedHashSet::new));
// [3, 1, 2]

TreeSet<Integer> naturalOrder = input.stream()
    .collect(Collectors.toCollection(TreeSet::new));
// [1, 2, 3]
~~~

`LinkedHashSet` keeps first-insertion order; `TreeSet` iterates according to the comparator. Two sets may have the same element count yet differ in ordering and **differ in duplicate semantics** when the data type exhibits a discrepancy between `equals` and the comparator.

Another option to both sort and deduplicate by `equals` is:

~~~java
LinkedHashSet<Integer> sortedUniqueByEquals = input.stream()
    .sorted()
    .collect(Collectors.toCollection(LinkedHashSet::new));
// [1, 2, 3]
~~~

This approach fits when equality must rely on `equals` while ordering must rely on `sorted`. When a comparator is inconsistent with `equals`, the result can differ from collecting into a `TreeSet`.

## 9. Using TreeSet as a NavigableSet After collect

The benefit of `TreeSet` does not stop at sorted printing. It also supports finding values near a threshold.

~~~java
import java.util.List;
import java.util.TreeSet;
import java.util.stream.Collectors;

TreeSet<Integer> thresholds = List.of(10, 20, 30, 40).stream()
    .collect(Collectors.toCollection(TreeSet::new));

System.out.println(thresholds.first());      // 10
System.out.println(thresholds.last());       // 40
System.out.println(thresholds.lower(20));    // 10: less than 20
System.out.println(thresholds.floor(20));    // 20: less than or equal to 20
System.out.println(thresholds.ceiling(25));  // 30: greater than or equal to 25
System.out.println(thresholds.higher(30));   // 40: greater than 30
~~~

Navigation methods table:

| Method | Meaning under ascending order |
|---|---|
| `lower(x)` | Greatest element **strictly less than** `x` |
| `floor(x)` | Greatest element **less than or equal to** `x` |
| `ceiling(x)` | Least element **greater than or equal to** `x` |
| `higher(x)` | Least element **strictly greater than** `x` |
| `first()` / `last()` | First/last element per comparator |
| `descendingSet()` | View iterating in reverse order |
| `headSet` / `tailSet` / `subSet` | Views representing ranges of the set |

Subset examples:

~~~java
System.out.println(thresholds.headSet(30));    // [10, 20]
System.out.println(thresholds.tailSet(30));    // [30, 40]
System.out.println(thresholds.subSet(20, 40)); // [20, 30]
System.out.println(thresholds.descendingSet());// [40, 30, 20, 10]
~~~

In the two-argument / single-argument overloads above, `headSet(to)` and `subSet(from, to)` **exclude the upper bound**, while `tailSet(from)` **includes the lower bound**. Other overloads accept boolean flags to specify whether bounds are inclusive.

**Be careful:** many subset methods and `descendingSet()` return **views backed by the original TreeSet**, not independent copies. Modifying the view can reflect on the original set and vice versa. If you want a snapshot, copy the elements.

### 9.1. Empty Sets and null in Navigation Results

On an empty `TreeSet`, `first()` and `last()` throw `NoSuchElementException`. Methods such as `lower`, `floor`, `ceiling`, and `higher` may return `null` when no matching element exists, yet `null` could also be a valid element if the comparator allows it; hence appropriate data rules are needed.

If you only want to check whether the set has elements:

~~~java
TreeSet<Integer> empty = java.util.stream.Stream.<Integer>empty()
    .collect(Collectors.toCollection(TreeSet::new));

if (!empty.isEmpty()) {
    System.out.println(empty.first());
}
~~~

## 10. Handling null and Appropriate Comparators

With a `TreeSet` using natural ordering, inserting `null` typically causes `NullPointerException`. When source data may contain null, the usual approach is to **filter out null** before collecting:

~~~java
import java.util.Arrays;
import java.util.Objects;
import java.util.TreeSet;
import java.util.stream.Collectors;

TreeSet<String> safe = Arrays.asList("Kotlin", null, "Java")
    .stream()
    .filter(Objects::nonNull)
    .collect(Collectors.toCollection(TreeSet::new));

System.out.println(safe); // [Java, Kotlin]
~~~

If business logic **requires keeping null as a distinct element**, you can use a null-safe comparator:

~~~java
import java.util.Arrays;
import java.util.Comparator;
import java.util.TreeSet;
import java.util.stream.Collectors;

Comparator<String> nullableOrder =
    Comparator.nullsFirst(Comparator.naturalOrder());

TreeSet<String> withNull = Arrays.asList("Kotlin", null, "Java")
    .stream()
    .collect(Collectors.toCollection(
        () -> new TreeSet<>(nullableOrder)
    ));

System.out.println(withNull); // [null, Java, Kotlin]
~~~

`Comparator.nullsFirst` places null before non-null values and retains only **one null** because two nulls compare equal under the comparator. Using `nullsLast` puts null at the end.

Allowing null in a set can make some navigation operations or business logic hard to distinguish between "not found" and "the null element". In systems needing explicit representation of missing data, consider normalizing inputs or using a status type instead of storing null as a set member.

## 11. Avoid Mutating Comparison Fields While an Object Is in a TreeSet

A `TreeSet` relies on the ordering relationship of elements to organize its tree. If you mutate fields used by the comparator **after adding the object**, the tree structure may no longer match the new ordering.

Unsafe design example:

~~~java
class MutableScore {
    int score;

    MutableScore(int score) {
        this.score = score;
    }
}

java.util.Comparator<MutableScore> byScore =
    java.util.Comparator.comparingInt(item -> item.score);

TreeSet<MutableScore> ranking = java.util.stream.Stream.of(
        new MutableScore(10),
        new MutableScore(20)
    )
    .collect(java.util.stream.Collectors.toCollection(
        () -> new TreeSet<>(byScore)
    ));

// Do not mutate score of an element already inside ranking.
// ranking.first().score = 99;
~~~

When the comparison key changes, `contains`, `remove`, `first`, or subsequent insertions may not behave as expected. This is the **mutable key** bug, similar to mutating a field affecting `hashCode` while the object is inside a `HashSet`.

Safe practices:

- Prefer **records** or objects with immutable sort fields.
- If a sort attribute changes, **remove the element from the set, update it, and re-insert it** per proper design, or build a new set from updated data.
- The comparator should remain consistent over time while a TreeSet uses it; avoid depending on mutable external state.

## 12. Parallel Collection and Correctness Requirements

`Collectors.toCollection(TreeSet::new)` is not a `CONCURRENT` collector. Yet it can still be used in `parallelStream()` because the framework can create **multiple independent TreeSets** and combine them:

~~~java
import java.util.List;
import java.util.TreeSet;
import java.util.stream.Collectors;

List<Integer> values = List.of(7, 3, 9, 3, 1, 7, 5);

TreeSet<Integer> result = values.parallelStream()
    .collect(Collectors.toCollection(TreeSet::new));

System.out.println(result); // [1, 3, 5, 7, 9]
~~~

In this example, correctness relies on the natural ordering rule of `Integer` and the collector mechanism, independent of thread completion order. However, `TreeSet` is **not thread-safe** when multiple threads directly mutate the same set object outside the pipeline.

Snippet to avoid:

~~~java
TreeSet<Integer> shared = new TreeSet<>();

// Dangerous: multiple threads mutating shared concurrently.
// values.parallelStream().forEach(shared::add);
~~~

Similarly, the **supplier** in `toCollection` must create a new collection each time it is called. Returning a shared `TreeSet` from an outer variable breaks the collector's independent accumulation mechanism.

### 12.1. The Comparator Must Be Pure and Consistent

A comparator must not:

- Depend on an incrementing counter, current time, or random values.
- Change comparison outcomes while building the set.
- Have side effects that mutate the source or elements while they are being compared.

If the same two objects are compared again and their relative order changes, the tree structure can become inconsistent; with parallel processing, bugs become even harder to reproduce.

### 12.2. Do Not Assume Parallel Is Faster

When merging TreeSets from branches, the framework may have to insert elements from one branch into another branch's set, incurring comparison and tree-balancing costs. For small sets, sequential execution is usually simpler. For large sets, measure timing, memory allocation, comparator cost, and number of unique values in a real environment before deciding.

## 13. Complexity, Memory, and Infinite Sources

`TreeSet` is backed by a balanced tree structure, so basic operations `add`, `remove`, and `contains` have **O(log k)** complexity for `k` current elements. When collecting `n` elements into a TreeSet with `k` distinct values, the cost is typically viewed as **O(n log k)**, depending on comparator cost. Memory retained by the result grows with the number of unique elements.

Comparison overview:

| Option | Result properties | Notable costs |
|---|---|---|
| `collect(toSet())` | Unique per `equals/hashCode`; order not guaranteed | Often favorable when sorting is unnecessary |
| `sorted().collect(toList())` | Ordered, retains duplicates | Must sort and retain all output elements |
| `collect(toCollection(TreeSet::new))` | Ordered per comparator and deduplicated by comparison | Tree insertion cost and storing distinct values |
| `sorted().collect(toCollection(LinkedHashSet::new))` | Sort first, then deduplicate by `equals/hashCode` | Sorting cost plus hashing and insertion structures |

No option is universally optimal. If you only need the **minimum element**, `stream.min(comparator)` can be much better than collecting the whole source into a TreeSet just to call `first()`. If you only need the **first few smallest elements**, consider data requirements, scale, and an appropriate top-k algorithm.

### 13.1. Collecting an Entire Infinite Source Will Not Terminate

~~~java
// Do not run: infinite source, collecting everything into a TreeSet.
// java.util.stream.IntStream.iterate(0, n -> n + 1)
//     .boxed()
//     .collect(Collectors.toCollection(TreeSet::new));
~~~

When processing an unbounded source, there must be a **stopping condition** or **finite limit** before the terminal operation:

~~~java
TreeSet<Integer> firstFive = java.util.stream.IntStream
    .iterate(0, n -> n + 1)
    .limit(5)
    .boxed()
    .collect(Collectors.toCollection(TreeSet::new));

System.out.println(firstFive); // [0, 1, 2, 3, 4]
~~~

`limit(5)` ensures only five elements are taken from this sequential `iterate` source. Note that `sorted()` or `distinct()` may require state and increase processing cost; placing a limit in the wrong position can prevent termination or alter results.

## 14. Creating an Unmodifiable Result Set

A `TreeSet` returned from the collector is **mutable**:

~~~java
TreeSet<String> languages = java.util.stream.Stream
    .of("Java", "Go", "Kotlin")
    .collect(Collectors.toCollection(TreeSet::new));

languages.add("Scala"); // Valid.
~~~

If the application needs to publish a read-only set to callers, create a snapshot and wrap it with an unmodifiable wrapper:

~~~java
import java.util.Collections;
import java.util.SortedSet;
import java.util.TreeSet;

SortedSet<String> snapshot =
    Collections.unmodifiableSortedSet(new TreeSet<>(languages));

// snapshot.add("Rust"); // Throws UnsupportedOperationException.
~~~

`new TreeSet<>(languages)` creates a **copy of the current state**; `unmodifiableSortedSet` blocks modifications through the wrapper. If you merely wrap the original `TreeSet` without copying, the wrapper remains a **view** and can reflect changes made elsewhere holding a reference to the original set.

Do not confuse this with `Collectors.toUnmodifiableSet()`: that collector produces an unmodifiable set, but **does not promise sorted order or a TreeSet implementation**.

## 15. Practice Exercise: Product Price Catalog

A store needs to retrieve **distinct selling prices in ascending order** from a product list. Negative prices are invalid entries and must be excluded; additionally, it needs to find the closest price **not less than 50,000 VND**.

**Requirement:** build a declarative pipeline using `filter`, `mapToLong` or `map`, and `Collectors.toCollection`. Do not use `forEach(sharedSet::add)`.

Reference solution (Java 17+):

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.TreeSet;
import java.util.stream.Collectors;

public class PriceLevelsPractice {
    record Product(String sku, long priceVnd) {}

    public static void main(String[] args) {
        List<Product> products = List.of(
            new Product("SP01", 70_000L),
            new Product("SP02", 40_000L),
            new Product("SP03", 70_000L),
            new Product("SP04", -1L),
            new Product("SP05", 90_000L)
        );

        TreeSet<Long> priceLevels = products.stream()
            .map(Product::priceVnd)
            .filter(price -> price >= 0L)
            .collect(Collectors.toCollection(TreeSet::new));

        System.out.println(priceLevels);        // [40000, 70000, 90000]
        System.out.println(priceLevels.ceiling(50_000L)); // 70000

        TreeSet<Long> descending = products.stream()
            .map(Product::priceVnd)
            .filter(price -> price >= 0L)
            .collect(Collectors.toCollection(
                () -> new TreeSet<>(Comparator.reverseOrder())
            ));

        System.out.println(descending); // [90000, 70000, 40000]
    }
}
~~~

In this exercise, `map(Product::priceVnd)` converts products into **price levels**, and then `TreeSet<Long>` automatically deduplicates prices. This accurately expresses the requirement "distinct price levels". Collecting `Product` directly into a TreeSet sorted by price would merge different products that share the same price, losing product information.

**Self-Check:**

1. Does `Collectors.toSet()` guarantee creating a `TreeSet`? — **No**.
2. Does `stream.sorted().collect(toList())` remove duplicate elements? — **No**.
3. What does `TreeSet` use to treat two elements as duplicates? — **Comparison returning 0** from the comparator or `compareTo`.
4. Why can `new TreeSet<Product>()` fail for a `Product` record without a comparator? — Records **do not implement `Comparable` by default**.
5. When is `thenComparing` needed? — When the primary comparator may treat distinct objects as tied while business rules require keeping them separate.
6. Does a `TreeSet` using natural order automatically accept `null`? — **Do not rely on that**; filter out null or intentionally use a null-supporting comparator.
7. Can `add` be called on a `TreeSet` returned from `collect`? — **Yes**, it is a mutable collection.
8. Should you mutate the comparison field of an element already inside a TreeSet? — **No**, as it can corrupt the tree's ordering invariant.
9. Can `parallelStream().collect(toCollection(TreeSet::new))` be used? — **Yes**, provided the collector and comparator obey their contracts; do not infer that it will run faster.

## 16. Key Takeaways When Choosing TreeSet in Java Stream API

**`collect(Collectors.toCollection(TreeSet::new))`** is the explicit way to collect elements into a set that is **sorted** and **deduplicated by comparison**. When a non-natural order is needed, provide a `Comparator` inside the supplier: `() -> new TreeSet<>(comparator)`.

Before choosing TreeSet, answer three questions: **does the data truly need sorting**, **is "duplicate" defined by `equals` or by the comparator**, and **do distinct records sharing a sort field need to be kept**? If all elements must be retained, use `sorted` with a `List`; if appearance order and equality are needed, consider `LinkedHashSet`; if selecting a representative per key is needed, define an explicit rule with a collector.

Finally, ensure **a consistent comparator**, **stable comparison fields**, **appropriately bounded data sources**, and **never share an unsynchronized mutable TreeSet**. These principles ensure safe Stream API usage when scaling to grouping, custom collectors, `Spliterator`, parallel processing, and Stream Gatherers.
