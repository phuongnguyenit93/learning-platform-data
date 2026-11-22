# Multi-Criteria Sorting with Comparator

> **Chapter:** Ordering, Deduplication, and Slicing  
> **Module:** JAVA_STREAM_API  
> **Goal:** Build multi-level comparators with `Comparator`, apply them to `Stream.sorted(...)`, control ascending/descending order, handle ties, and safely combine them with `distinct`, `skip`, and `limit`.

When processing data with the **Java Stream API**, sorting requirements are rarely just "by name ascending". A candidate list may need **highest score first**, if tied then **department alphabetically**, if still tied then **earliest registration order**, and finally **ID** so the order is deterministic. For orders, you might prioritize status, total amount, and then creation date. These requirements are **multi-criteria sorting**.

In the declarative pipelines of the **JAVA_STREAM_API** module, `sorted(comparator)` is a stateful intermediate operation. To use it properly, you must understand the contract of `Comparator`, *encounter order*, lazy behavior, and performance implications—especially when combining filtering, pagination, result collection, or parallel processing. These skills are also essential when working with grouping, custom collectors, `Spliterator`, and advanced Stream transformations.

## 1. From Business Requirements to a Chain of Criteria

Suppose there are five candidate profiles to rank:

| Profile ID | Name | Score | Team | Registration Order |
| --- | --- | ---: | --- | ---: |
| U04 | An | 90 | Backend | 100 |
| U02 | Binh | 95 | Mobile | 103 |
| U03 | Chi | 95 | Backend | 101 |
| U01 | Dung | 95 | Backend | 101 |
| U05 | Em | 95 | Mobile | 101 |

Sorting rules:

1. **Score descending**: higher scores come first.
2. **Team ascending** in lexicographical order: Backend before Mobile.
3. **Registration order ascending**: earlier registration comes first.
4. **Profile ID ascending** to eliminate ties when multiple elements share the first three keys.

Expected result:

```text
U01  Dung  95  Backend  101
U03  Chi   95  Backend  101
U05  Em    95  Mobile   101
U02  Binh  95  Mobile   103
U04  An    90  Backend  100
```

We can visualize how order is decided between two profiles:

```text
Compare score:
  different? -> decide (higher score comes first)
       |
     equal
       v
Compare team:
  different? -> decide (team A-Z)
       |
     equal
       v
Compare registration order:
  different? -> decide (smaller number first)
       |
     equal
       v
Compare ID:
  different? -> decide (ID A-Z)
       |
     equal
       v
Two profiles are equivalent across all sort keys
```

**Principle:** earlier criteria have higher priority. The next criterion **is only evaluated when the previous comparison returns 0**.

## 2. How Does `Comparator` Work?

`Comparator<T>` is a functional interface in `java.util` with the method:

```java
int compare(T left, T right);
```

Meaning of the result's sign:

| `compare(a, b)` | Sort relationship |
| --- | --- |
| Negative (`< 0`) | `a` comes before `b`. |
| Equal to `0` | `a` and `b` are equivalent **under the comparison criterion**. |
| Positive (`> 0`) | `a` comes after `b`. |

The return value **does not have to be** `-1`, `0`, or `1`; Java only uses its sign.

Example:

```java
import java.util.Comparator;

Comparator<Integer> ascending = Integer::compare;
Comparator<Integer> descending = (a, b) -> Integer.compare(b, a);

System.out.println(ascending.compare(2, 9) < 0);  // true
System.out.println(descending.compare(2, 9) > 0); // true
```

A valid comparator must satisfy key properties:

- **Antisymmetric sign:** the sign of `compare(a,b)` is opposite to `compare(b,a)`.
- **Transitivity:** if `a` precedes `b` and `b` precedes `c`, then `a` must precede `c`.
- **Consistency under Comparator equality:** if `compare(a,b) == 0`, comparing `a` and `b` against any `c` must yield the same sign.
- Keys used in comparisons must remain stable during sorting; do not mutate them between `compare` calls.

Violating this contract can cause sorting algorithms to return unreliable results or throw `IllegalArgumentException` in certain cases.

### 2.1. `Comparator` vs `Comparable`

- `Comparable<T>` defines a type's **natural order** via `compareTo`, such as `String`, `Integer`, and `LocalDate`.
- `Comparator<T>` is an **externally supplied order** that can be customized per requirement and combined across multiple criteria without modifying the data class.

Parameterless `Stream.sorted()` uses natural order; elements must be mutually comparable. `Stream.sorted(comparator)` uses the provided comparator.

```java
List<String> names = List.of("Chi", "An", "Binh");

List<String> natural = names.stream()
    .sorted()
    .toList(); // [An, Binh, Chi]

List<String> byLength = names.stream()
    .sorted(Comparator.comparingInt(String::length))
    .toList(); // [An, Chi, Binh]
```

If elements lack an appropriate `Comparable`, calling `sorted()` can throw `ClassCastException` when the pipeline executes. For records or business objects, passing an explicit `Comparator` is recommended.

## 3. Creating the Primary Criterion with `comparing`

`Comparator` provides factory methods and combinators to express sorting directly:

| Method | Meaning |
| --- | --- |
| `Comparator.comparing(keyExtractor)` | Compares by the extracted key using the key's natural order. |
| `Comparator.comparing(keyExtractor, keyComparator)` | Compares the key using the specified Comparator. |
| `Comparator.comparingInt(...)` | Compares an `int` key without boxing during key extraction. |
| `Comparator.comparingLong(...)` | Compares a `long` key. |
| `Comparator.comparingDouble(...)` | Compares a `double` key. |
| `Comparator.naturalOrder()` | Natural order. |
| `Comparator.reverseOrder()` | Reverses natural order. |

Using a record for illustration (Java 16+):

```java
record Candidate(
    String id,
    String name,
    int score,
    String team,
    long registeredOrder
) {}
```

Sort by score ascending:

```java
Comparator<Candidate> byScoreAsc =
    Comparator.comparingInt(Candidate::score);
```

Sort by score descending:

```java
Comparator<Candidate> byScoreDesc =
    Comparator.comparingInt(Candidate::score).reversed();
```

Sort by name:

```java
Comparator<Candidate> byName =
    Comparator.comparing(Candidate::name);
```

For primitive types, prefer `comparingInt`, `comparingLong`, or `comparingDouble` when applicable. This makes the key type explicit and avoids creating wrapper objects solely for comparison.

### 3.1. Avoid Subtraction in `compare`

Do not write integer comparators by arbitrarily subtracting values:

```java
Comparator<Integer> unsafe = (a, b) -> a - b;
```

For example, with `a = Integer.MAX_VALUE` and `b = -1`, subtraction overflows `int` and flips the sign. That breaks the ordering semantics.

Use:

```java
Comparator<Integer> safe = Integer::compare;

// Or for Candidate:
Comparator<Candidate> byScore =
    Comparator.comparingInt(Candidate::score);
```

Similarly for `long`, use `Long.compare` or `comparingLong`.

## 4. Chaining Multiple Criteria with `thenComparing`

This is the core technique of this lesson. `thenComparing` accepts a secondary Comparator; it is only consulted if the preceding Comparator returns `0`.

### 4.1. Complete Four-Level Example

```java
Comparator<Candidate> ranking = Comparator
    .comparingInt(Candidate::score)
    .reversed()
    .thenComparing(Candidate::team)
    .thenComparingLong(Candidate::registeredOrder)
    .thenComparing(Candidate::id);
```

Reading from top to bottom:

- `comparingInt(Candidate::score).reversed()`: higher score first.
- `thenComparing(Candidate::team)`: on equal scores, team in natural order.
- `thenComparingLong(Candidate::registeredOrder)`: on equal score and team, earlier registration first.
- `thenComparing(Candidate::id)`: final key makes the order deterministic if IDs are unique.

Applying it:

```java
List<Candidate> sorted = candidates.stream()
    .sorted(ranking)
    .toList();
```

`sorted(ranking)` is an **intermediate operation**. Only at `toList()` is the Stream evaluated and returned as a list in the new order. `candidates` is not sorted in place.

### 4.2. What Overloads Does `thenComparing` Have?

| Form | Purpose |
| --- | --- |
| `thenComparing(Comparator<? super T>)` | Chains an existing secondary Comparator. |
| `thenComparing(keyExtractor)` | Sorts by an object key using its natural order. |
| `thenComparing(keyExtractor, keyComparator)` | Sorts by an object key using a custom Comparator. |
| `thenComparingInt(keyExtractor)` | Compares a secondary `int` key. |
| `thenComparingLong(keyExtractor)` | Compares a secondary `long` key. |
| `thenComparingDouble(keyExtractor)` | Compares a secondary `double` key. |

Example reusing named Comparators:

```java
Comparator<Candidate> byTeam =
    Comparator.comparing(Candidate::team);

Comparator<Candidate> byTime =
    Comparator.comparingLong(Candidate::registeredOrder);

Comparator<Candidate> byId =
    Comparator.comparing(Candidate::id);

Comparator<Candidate> ranking = Comparator
    .comparingInt(Candidate::score).reversed()
    .thenComparing(byTeam)
    .thenComparing(byTime)
    .thenComparing(byId);
```

Extracting variables is helpful when a criterion has complex logic, needs reuse, or requires isolated unit testing.

## 5. Reversing Individual Criteria: A Common `reversed()` Bug

`Comparator.reversed()` reverses the **entire current Comparator**, not just the comparison step written immediately next to it in the fluent chain.

Suppose you want **score descending**, but **name ascending**.

**Correct:**

```java
Comparator<Candidate> correct = Comparator
    .comparingInt(Candidate::score)
    .reversed()                        // Reverses only the score comparator.
    .thenComparing(Candidate::name);   // Name stays ascending.
```

**Wrong if the goal is only to reverse score:**

```java
Comparator<Candidate> wrong = Comparator
    .comparingInt(Candidate::score)
    .thenComparing(Candidate::name)
    .reversed(); // Reverses BOTH score AND name.
```

When you want to reverse **only the second criterion**, create a sub-comparator and reverse it:

```java
Comparator<Candidate> scoreAscNameDesc = Comparator
    .comparingInt(Candidate::score)
    .thenComparing(
        Comparator.comparing(Candidate::name).reversed()
    );
```

Or provide a dedicated Comparator for the key:

```java
Comparator<Candidate> scoreAscNameDesc2 = Comparator
    .comparingInt(Candidate::score)
    .thenComparing(
        Candidate::name,
        Comparator.reverseOrder()
    );
```

Both approaches sort by **score ascending, name descending**.

### 5.1. When Both Criteria Are Descending

```java
Comparator<Candidate> scoreDescNameDesc = Comparator
    .comparingInt(Candidate::score)
    .reversed()
    .thenComparing(
        Comparator.comparing(Candidate::name).reversed()
    );
```

Explicitly specifying the direction of each level helps prevent unintended changes when business requirements are updated later.

### 5.2. Comparators for Dates and Times

`LocalDate`, `Instant`, and many `java.time` types have natural ordering. For example, prioritizing the earliest due date:

```java
record Task(String id, int priority, java.time.LocalDate dueDate) {}

Comparator<Task> byPriorityDescDueAsc = Comparator
    .comparingInt(Task::priority)
    .reversed()
    .thenComparing(Task::dueDate)
    .thenComparing(Task::id);
```

If the latest date needs to come first:

```java
Comparator<Task> byPriorityDescDueDesc = Comparator
    .comparingInt(Task::priority)
    .reversed()
    .thenComparing(
        Task::dueDate,
        Comparator.reverseOrder()
    )
    .thenComparing(Task::id);
```

Consistent mental model: each level has a **key** and a **direction**. Do not rely on intuition from placing `reversed` at the end of the chain.

## 6. Standalone Runnable Java Example

The following example uses Java 17+ and implements the exact four criteria introduced at the start. Save it as `MultiCriteriaSortDemo.java`:

```java
import java.util.Comparator;
import java.util.List;

public class MultiCriteriaSortDemo {
    record Candidate(
        String id,
        String name,
        int score,
        String team,
        long registeredOrder
    ) {}

    public static void main(String[] args) {
        List<Candidate> candidates = List.of(
            new Candidate("U04", "An", 90, "Backend", 100),
            new Candidate("U02", "Binh", 95, "Mobile", 103),
            new Candidate("U03", "Chi", 95, "Backend", 101),
            new Candidate("U01", "Dung", 95, "Backend", 101),
            new Candidate("U05", "Em", 95, "Mobile", 101)
        );

        Comparator<Candidate> ranking = Comparator
            .comparingInt(Candidate::score).reversed()
            .thenComparing(Candidate::team)
            .thenComparingLong(Candidate::registeredOrder)
            .thenComparing(Candidate::id);

        List<Candidate> ranked = candidates.stream()
            .filter(candidate -> candidate.score() >= 90)
            .sorted(ranking)
            .toList();

        ranked.forEach(candidate -> System.out.printf(
            "%s | %-4s | %d | %-7s | %d%n",
            candidate.id(),
            candidate.name(),
            candidate.score(),
            candidate.team(),
            candidate.registeredOrder()
        ));
    }
}
```

Output:

```text
U01 | Dung | 95 | Backend | 101
U03 | Chi  | 95 | Backend | 101
U05 | Em   | 95 | Mobile  | 101
U02 | Binh | 95 | Mobile  | 103
U04 | An   | 90 | Backend | 100
```

Because profile IDs are unique, the final criterion distinguishes every pair of profiles. This is a practical way to guarantee consistent order across repeated runs on the same dataset, especially when paginating.

If you only want the profile IDs after sorting:

```java
List<String> rankedIds = candidates.stream()
    .sorted(ranking)
    .map(Candidate::id)
    .toList();

// [U01, U03, U05, U02, U04]
```

In general, place `sorted` before `map` if mapping discards information needed for sorting. If mapping produces an object that still retains enough keys and satisfies the same rule, a different order may be designed; the key is preserving semantic equivalence.

## 7. Handling `null` in Sort Keys and in Elements Themselves

### 7.1. Nullable Keys

`Comparator.comparing(Candidate::team)` uses `String`'s natural order by default and cannot handle a `null` key when comparing it against another key.

If the requirement is "unknown team goes last", write:

```java
Comparator<Candidate> byNullableTeam = Comparator.comparing(
    Candidate::team,
    Comparator.nullsLast(Comparator.naturalOrder())
);
```

If "unknown team goes first":

```java
Comparator<Candidate> byNullableTeamFirst = Comparator.comparing(
    Candidate::team,
    Comparator.nullsFirst(Comparator.naturalOrder())
);
```

You can chain this into the sequence:

```java
Comparator<Candidate> rankingWithNullTeam = Comparator
    .comparingInt(Candidate::score).reversed()
    .thenComparing(
        Candidate::team,
        Comparator.nullsLast(Comparator.naturalOrder())
    )
    .thenComparing(Candidate::id);
```

Here `nullsLast(...)` applies to the **`team` key value**, not the entire `Candidate`.

### 7.2. Whole Elements That May Be `null`

If the Stream contains `null` elements (for example, from a source that permits them), wrap the element-level comparator:

```java
Comparator<Candidate> nonNullComparator =
    Comparator.comparing(Candidate::name);

Comparator<Candidate> wholeElementComparator =
    Comparator.nullsLast(nonNullComparator);

List<Candidate> sorted = candidatesWithNulls.stream()
    .sorted(wholeElementComparator)
    .toList();
```

`candidatesWithNulls` is an illustrative list that must exist in a program using this snippet.

Two distinct cases:

- `Candidate` exists, but `candidate.team() == null`: handle a **nullable key**.
- The `Candidate` element itself is `null`: handle a **nullable element**.

Do not wrap the outer comparator in `nullsLast` and expect it to automatically handle nullable keys inside the object.

### 7.3. Reversing and `null` Position

`Comparator.nullsLast(Comparator.reverseOrder())` means **non-null values descending, `null` stays last**. However, calling `reversed()` on the **entire** Comparator created with `nullsLast` also flips `null` to the front.

Example:

```java
Comparator<String> descendingButNullLast =
    Comparator.nullsLast(Comparator.reverseOrder());
```

Choose the `null` policy according to business rules first, then choose the sort direction for non-null values.

## 8. Comparator Returning 0, Stability, and Encounter Order

Two elements are considered **equal by a Comparator** if `compare(a,b) == 0`. That **does not mean** `a.equals(b)` is `true`.

For example, sorting only by score:

```java
Comparator<Candidate> byScoreOnly =
    Comparator.comparingInt(Candidate::score);
```

Both `U01` and `U03` have score 95, so `byScoreOnly.compare(u01, u03) == 0`, even though their IDs, names, and object instances differ.

### 8.1. Is `sorted` Stable?

By the `Stream.sorted(...)` contract:

- On an **ordered stream**, sorting is **stable**: elements that compare equal under the Comparator retain their relative source order.
- On an **unordered stream**, there is **no stability guarantee** for elements with equal keys.

Example:

```java
record Item(String id, int score) {}

List<Item> items = List.of(
    new Item("A", 5),
    new Item("B", 2),
    new Item("C", 5)
);

List<String> ids = items.stream()
    .sorted(Comparator.comparingInt(Item::score))
    .map(Item::id)
    .toList();

// [B, A, C] — A and C tie on score, preserving relative List order.
```

If elements come from a source with no guaranteed order, such as a `HashSet`, do not rely on source position to decide which tied element comes first.

### 8.2. Add a Tie-Breaker for Deterministic Results

Add a secondary key:

```java
Comparator<Item> byScoreThenId = Comparator
    .comparingInt(Item::score)
    .thenComparing(Item::id);
```

With a unique and immutable `id` during sorting, distinct elements are separated. Ranking then does not depend on source ordering among equal keys.

This is especially important for user-facing results, reproducible statistics, and pagination. If IDs are not unique, use a final key capable of distinguishing records per business requirements.

### 8.3. `Comparator` Differs from `distinct` and `equals`

`Stream.distinct()` removes duplicates based on `Object.equals`, **not using the Comparator passed to `sorted`**.

```java
record Entry(String id, int score) {}

List<Entry> entries = List.of(
    new Entry("A", 5),
    new Entry("B", 5)
);

List<Entry> result = entries.stream()
    .sorted(Comparator.comparingInt(Entry::score))
    .distinct()
    .toList();

// Keeps both A and B: the two records are distinct under equals.
```

A `TreeSet` or `TreeMap`, on the other hand, uses the Comparator (or natural order) to determine key equivalence; if the Comparator returns 0 for two keys that differ under `equals`, those structures treat them as the same key. Therefore, **do not replace `distinct()` with `collect(toCollection(() -> new TreeSet<>(byScoreOnly)))`** if your goal is to keep records with different IDs and equal scores.

## 9. Sorting Strings: Case Sensitivity, Normalization, and Locale

`Comparator.comparing(Candidate::name)` relies on `String.compareTo`, comparing UTF-16 code units. That is not always the natural display order in Vietnamese.

### 9.1. Case-Insensitive Comparison

```java
Comparator<Candidate> byNameIgnoringCase = Comparator.comparing(
    Candidate::name,
    String.CASE_INSENSITIVE_ORDER
);
```

If names differ only in letter case (for instance `"an"` and `"An"`), this Comparator may return 0. When a consistent order for both is needed:

```java
Comparator<Candidate> byNameIgnoringCaseThenId = Comparator
    .comparing(Candidate::name, String.CASE_INSENSITIVE_ORDER)
    .thenComparing(Candidate::id);
```

### 9.2. Locale-Sensitive Comparison

To sort names by local language rules, consider `java.text.Collator`:

```java
import java.text.Collator;
import java.util.Comparator;
import java.util.Locale;

Collator viCollator = Collator.getInstance(
    Locale.forLanguageTag("vi-VN")
);

Comparator<Candidate> byVietnameseName = Comparator.comparing(
    Candidate::name,
    viCollator
);
```

`Collator` provides locale-specific collation rules and allows configuring strength levels. Exact results depend on configuration, data, and environment. In parallel pipelines, note that `Collator` holds mutable configuration state; do not share a mutated instance across threads.

Any normalization rule (trimming, case conversion, Unicode normalization) must match business requirements. **Do not arbitrarily strip Vietnamese diacritics** if the system must distinguish different names.

## 10. Combining `sorted` with `filter`, `skip`, and `limit`

A common pipeline for search listings:

```java
List<Candidate> page = candidates.stream()
    .filter(c -> c.score() >= 90)
    .sorted(ranking)
    .skip(2)
    .limit(2)
    .toList();
```

Reading in logical order:

1. `filter` selects qualifying records.
2. `sorted` establishes multi-criteria ranking order.
3. `skip(2)` skips the first two records **in the sorted order**.
4. `limit(2)` takes at most the next two records.
5. `toList()` evaluates and returns the result.

With the dataset in section 6, `page` contains `U05` followed by `U02`.

### 10.1. Swapping `sorted` and `limit` Can Change the Result

```java
// Take the first two profiles from the source, then sort them:
List<Candidate> firstTwoSorted = candidates.stream()
    .limit(2)
    .sorted(ranking)
    .toList();
```

The result can only choose from the first two source elements (`U04` and `U02`); the highest-ranked profile `U01` cannot appear.

Conversely:

```java
// Rank everything, then take the top two profiles:
List<Candidate> topTwo = candidates.stream()
    .sorted(ranking)
    .limit(2)
    .toList();

// [U01, U03] by profile ID.
```

If the requirement is the **global top N**, you must sort by the criteria before slicing, or use a dedicated top-K algorithm that preserves the exact result.

### 10.2. Stable Pagination Requires a Final Tie-Breaker Key

If multiple records share the same score, team, and registration time and the source has no stable order, paginating with `skip` and `limit` can place tied records onto different pages across queries. Adding a unique key criterion to the Comparator determines the order among them.

However, **even a complete Comparator cannot guarantee consistent pagination if the dataset changes between page loads**. In continuously updated systems, use an appropriate strategy such as snapshots or *keyset pagination* at the data source.

## 11. Performance: `sorted` Is a Stateful Operation

`filter` and `map` can typically process one element at a time as needed. `sorted` is **stateful**: to know the first element in global sort order, it normally must examine the entire finite input and retain the data needed to sort.

Suppose:

```java
long count = candidates.stream()
    .filter(c -> c.score() >= 90)
    .sorted(ranking)
    .count();
```

Because only the count is needed and sorting does not change the element count, the Stream implementation may optimize away the actual sort in some cases. **Do not rely on side effects inside a Comparator as mandatory behavior**.

### 11.1. Typical Costs

For `n` finite elements:

- General comparison sorting typically has time complexity around `O(n log n)`.
- Stream sorting typically requires an `O(n)` buffer to establish global order.
- Each comparison may re-extract keys, especially when using expensive computed methods.
- A `thenComparing` chain usually avoids computing secondary keys for pairs that already differ on the primary key, but does not guarantee each key is extracted only once per element.

There is no blanket rule that Streams are faster or slower than every other sort: `List.sort(comparator)` may fit better when mutating the collection's order in place, whereas `stream().sorted(...).toList()` fits when producing a new result combined with filtering/mapping.

### 11.2. Choosing the Right Operation Order

Usually, filtering before sorting reduces the amount of data to process:

```java
List<Candidate> eligible = candidates.stream()
    .filter(c -> c.score() >= 90)
    .sorted(ranking)
    .toList();
```

If the filter condition does not depend on order, this produces the same result set as sorting then filtering and often reduces sorting work. You cannot, however, freely reorder `limit` or `skip` as illustrated earlier.

In particular, on a potentially **infinite** source, a global `sorted()` cannot generally emit results because there is no moment when collecting elements finishes. Bound the source per the problem requirements **before** sorting, or use a specialized streaming algorithm.

### 11.3. When You Need Top K on Large Datasets

`stream().sorted(comparator).limit(k)` is readable and well suited to medium-sized datasets. If `n` is very large while `k` is small, a structure such as a **size-K priority queue** can reduce complexity to roughly `O(n log k)` with `O(k)` memory, provided the criteria and tie-breaking are implemented properly.

That is a different algorithmic choice, not merely swapping `sorted` and `limit`. Only optimize that way when data scale and benchmarks show it is needed.

## 12. Parallel Sorting and Encounter Order

`sorted(comparator)` works on both sequential and parallel Streams:

```java
List<Candidate> rankedInParallel = candidates.parallelStream()
    .sorted(ranking)
    .toList();
```

With an ordered `List` source, the output order must still obey the Comparator, and tied elements remain stable per the `sorted` contract. However:

- Sorting is stateful; splitting/merging work and buffering carry overhead.
- The Comparator must **not cause side effects that mutate data** and must be consistent across calls.
- The Comparator may be invoked multiple times with no guarantees on call count, order, or executing thread.
- For an unordered Stream, `sorted` does not guarantee stability for elements the Comparator treats as equal.
- `forEach` in parallel does not guarantee print order; if encounter-order output is required, consider `forEachOrdered` or collecting a list with `toList()`.

Example to avoid confusion:

```java
// Do not rely on the print order of forEach on a parallel stream:
candidates.parallelStream()
    .sorted(ranking)
    .forEach(c -> System.out.println(c.id()));

// Collect results and iterate the List to preserve order:
List<Candidate> ranked = candidates.parallelStream()
    .sorted(ranking)
    .toList();

ranked.forEach(c -> System.out.println(c.id()));
```

Parallel execution **does not automatically guarantee a speedup**. Consider dataset size, comparison cost, `Spliterator` characteristics, memory bandwidth, core count, and actual workload.

## 13. How to Test a Multi-Level Comparator

For a ranking comparator, test at least three cases: **different primary key**, **equal primary key but different secondary key**, and **all keys equal except the final key**.

For example, alongside `record Candidate` and `Comparator<Candidate> ranking` from section 6:

```java
Candidate a = new Candidate("U10", "A", 95, "Backend", 101);
Candidate b = new Candidate("U11", "B", 90, "Backend", 101);
Candidate c = new Candidate("U12", "C", 95, "Mobile", 101);
Candidate d = new Candidate("U13", "D", 95, "Backend", 102);
Candidate e = new Candidate("U14", "E", 95, "Backend", 101);

assert ranking.compare(a, b) < 0; // Higher score first.
assert ranking.compare(a, c) < 0; // Same score, Backend before Mobile.
assert ranking.compare(a, d) < 0; // Same score/team, earlier registration first.
assert ranking.compare(a, e) < 0; // Prior keys equal, smaller id first.
```

In Java, `assert` is disabled by default; run with `-ea` if you want `assert` statements evaluated. In real automated tests, use your testing framework's assertions.

Additionally, for custom Comparator logic, check transitivity and edge cases: negative numbers, large values, `null` keys, case differences in strings, and unordered sources. A Comparator composed from standard factory methods is generally more readable and less error-prone than a hand-written multi-branch comparison algorithm.

## 14. Common Mistakes

| Mistake | Why it is wrong or risky | How to fix |
| --- | --- | --- |
| Using `(a,b) -> a.score() - b.score()` | Can overflow integers. | `comparingInt(Candidate::score)` or `Integer.compare`. |
| Writing `.thenComparing(...).reversed()` when only reversing the primary key | Reverses the entire chain built so far. | Call `reversed()` before `thenComparing`, or reverse only the sub-comparator. |
| Sorting only by score when stable pagination is required | Tied records have undetermined order if the source is unordered. | Add a deterministic final key such as a unique ID. |
| Using `limit(k).sorted(...)` to get the global top K | Drops elements beyond the first `k` source elements. | `sorted(...).limit(k)` or a dedicated top-K algorithm. |
| Thinking `distinct()` uses `sorted`'s Comparator | `distinct` is based on `equals`. | Separate deduplication rules from sorting rules. |
| Using `TreeSet` with a score-only Comparator | Distinct elements with equal scores can be treated as duplicates. | Use a complete Comparator with identity, or choose a suitable structure. |
| Ignoring nullable keys | Can throw `NullPointerException`. | `nullsFirst` / `nullsLast` at the key comparator level. |
| Writing a Comparator that depends on state mutated during sorting | Inconsistent ordering relation. | Keep keys and comparison rules stable. |
| Logging or counting inside `compare` and relying on call count | Call count and execution path are algorithm-dependent and may be optimized away. | Separate business logic from the Comparator. |
| Assuming `parallelStream().sorted(...)` is always faster | Splitting/merging and buffering overhead can outweigh gains. | Benchmark on realistic data. |
| Sorting an infinite source with `sorted()` then `limit()` | `sorted()` needs global order before emitting elements. | Limit input elements first or change algorithms. |

## 15. Practice Exercises

**Exercise 1 – Employee ranking.** Given `Employee(String id, String department, int performance, long joinedAt)`. Sort by performance descending, department ascending, join date ascending, and ID ascending. Build the Comparator using `comparingInt` and `thenComparing` overloads.

**Exercise 2 – Controlling secondary direction.** Starting from Exercise 1's comparator, change the department rule to **descending** while keeping performance descending and the remaining criteria ascending. Explain why putting `reversed()` at the very end of the chain is wrong.

**Exercise 3 – Missing data.** Given `Ticket(String id, Integer severity, String owner)`, where `owner` may be `null`. Sort by `severity` descending, then `owner` ascending with `null` last, and finally by `id`. Also handle the case where `severity` may be `null` if required.

**Exercise 4 – Taking the top N.** From 10,000 records, filter for valid status and take the 5 records with the highest score. Write the correct pipeline and explain why `limit(5).sorted(...)` does not meet the requirement.

**Exercise 5 – Comparator and duplicates.** Create two distinct records with the same score, then compare the result of `sorted(...).distinct()` against collecting into a `TreeSet` that compares only by score. Explain why the element counts can differ.

Hint for Exercise 1:

```java
Comparator<Employee> ranking = Comparator
    .comparingInt(Employee::performance).reversed()
    .thenComparing(Employee::department)
    .thenComparingLong(Employee::joinedAt)
    .thenComparing(Employee::id);
```

This snippet assumes `Employee` is the record defined in the exercise; if `department` can be `null`, add a nullable-key comparator as shown in section 7.

## 16. Summary of Key Points to Remember

- **`Comparator<T>` determines order by the sign of `compare(a,b)`**. A valid order must be consistent and transitive.
- **`comparing(...)`, `comparingInt(...)`, `comparingLong(...)`, `comparingDouble(...)`** build the primary criterion; **`thenComparing(...)`** adds lower-priority criteria.
- **`reversed()` reverses the entire Comparator at the point where it is called**; to reverse a single key, reverse that key's Comparator before chaining.
- **`nullsFirst` and `nullsLast`** handle `null` values; distinguish a nullable key from a nullable element.
- **`Stream.sorted(comparator)` is stateful and lazy**. On ordered streams, sorting is stable for tied elements; on unordered streams, stability is not guaranteed.
- **`sorted(...).skip(...).limit(...)`** expresses pagination after ranking; **`limit(...).sorted(...)`** is a different problem. Add a unique identifier key when deterministic order is required.
- **A Comparator does not define `distinct()`'s rule**; deduplication relies on `equals`, whereas some sorted sets/maps use the Comparator to distinguish keys.
- **The cost of `sorted` can be substantial**, especially with large datasets, infinite sources, and parallel processing. Measure and choose algorithms according to real needs.
- Understanding ordering, `Spliterator` source characteristics, lambda purity, and `collect` behavior will help you use other techniques in **JAVA_STREAM_API** effectively, from grouping to custom collectors and Stream Gatherers.
