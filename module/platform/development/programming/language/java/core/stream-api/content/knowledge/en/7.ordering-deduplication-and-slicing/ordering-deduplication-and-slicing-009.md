# Impact of Operation Order on Results and Cost

In the Java Stream API, changing the position of `filter`, `map`, `distinct`, `sorted`, `skip`, or `limit` does not merely make code look different. Some swaps **preserve the result while changing the cost**, while other swaps **change the actual data selected**. This matters greatly when selecting top N items, paginating, removing duplicate records, processing very large sources, or switching to parallel streams.

This lesson belongs to the **Ordering, Deduplication, and Slicing** chapter of the `JAVA_STREAM_API` module. We examine the interaction among lazy pipelines, `filter`, `map`, `reduce`, `collect`, *encounter order*, stateful operations, short-circuiting operations, and CPU/memory cost. The goal is to know **when two operations can be reordered, why, and how to verify it**.

Examples use `List.of(...)` (Java 9+); on Java 8 you can substitute `Arrays.asList(...)`. Core operations such as `filter`, `map`, `sorted`, `distinct`, `skip`, and `limit` have existed since Java 8; examples using `takeWhile`/`dropWhile` require Java 9+.

## 1. Distinguishing Encounter Order from Operation Order

A pipeline describes a sequence of transformations:

```text
source → filter(...) → distinct() → sorted(...) → skip(...) → limit(...) → collect(...)
           │               │             │          │           │
     filter elements   deduplicate     sort     skip head   take up to N
```

Two concepts are easy to confuse:

- **Operation order** is the placement of `filter`, `distinct`, `sorted`, `limit`, etc., within the pipeline. Changing operation order can change the meaning of the computation.
- **Encounter order** is the logical order the source and operations commit to maintaining. `List.stream()` normally follows list order; `HashSet.stream()` makes no such guarantee. `sorted()` creates order by comparator, whereas `unordered()` drops the encounter-order constraint for subsequent steps.

Do not equate encounter order with the **execution order of individual lambdas**. In a parallel pipeline, elements may be processed across multiple threads in a different order from the output order. Even sequential pipelines include operations like `sorted` that must collect many elements before emitting results.

An orientation table:

| Operation | Primary effect | Key characteristics to watch |
| --- | --- | --- |
| `filter` | Retains or discards each element | Stateless, lazy; may need to scan many inputs to find enough matches |
| `map` | Transforms each element's value | Stateless, lazy; may collapse distinct elements into equal ones |
| `distinct` | Removes duplicate elements by `equals` | Stateful; on ordered Streams, retains the first occurrence |
| `sorted` | Sorts by natural order or comparator | Stateful; generally needs to inspect the entire finite source |
| `skip(n)` | Discards the first `n` elements in encounter order | Stateful; depends on preceding operations |
| `limit(n)` | Keeps at most the first `n` elements | Stateful, short-circuiting; may stop early depending on pipeline |
| `takeWhile` / `dropWhile` | Takes/drops a **contiguous prefix** matching a condition | Java 9+; strongly dependent on encounter order |
| `unordered` | Drops the encounter-order constraint | Does not shuffle elements; affects selection and optimizations |

Terminal operations such as `collect`, `count`, `findFirst`, or `anyMatch` trigger the pipeline. Chaining intermediate operations alone does not start traversal; however, the presence of `sorted` or `distinct` can prevent a terminal operation from taking advantage of early stopping.

## 2. `filter` and `limit`: Picking N Qualifying Results vs Inspecting Only N Inputs?

Given an ordered list:

```java
import java.util.List;
import java.util.stream.Collectors;

List<Integer> numbers = List.of(7, 2, 9, 4, 6);

List<Integer> a = numbers.stream()
        .filter(n -> n % 2 == 0)
        .limit(2)
        .collect(Collectors.toList());

List<Integer> b = numbers.stream()
        .limit(2)
        .filter(n -> n % 2 == 0)
        .collect(Collectors.toList());

System.out.println(a); // [2, 4]
System.out.println(b); // [2]
```

- **`filter(...).limit(2)`** means finding **at most two elements satisfying the condition** across the entire source. The pipeline may have to inspect rejected elements before collecting two matches.
- **`limit(2).filter(...)`** means inspecting only the **first two source elements**, then filtering them. The result may have fewer than two elements even if valid items exist later.

You cannot push `limit` before `filter` just to process less data: doing so usually changes the business requirement.

When using `findFirst`, placing `filter` before `findFirst` finds the **first element matching the condition**; if you want to inspect only the very first element of the source, express that limit explicitly.

## 3. `sorted` and `limit`: Global Top N vs Sorting the First N Inputs

```java
List<Integer> scores = List.of(9, 2, 8, 1, 7);

List<Integer> smallestGlobal = scores.stream()
        .sorted()
        .limit(3)
        .collect(Collectors.toList());

List<Integer> sortedPrefix = scores.stream()
        .limit(3)
        .sorted()
        .collect(Collectors.toList());

System.out.println(smallestGlobal); // [1, 2, 7]
System.out.println(sortedPrefix);   // [2, 8, 9]
```

`sorted().limit(3)` finds the **three smallest values across the entire dataset**. On a source without pre-established order, `sorted` must typically examine all `N` elements, use significant memory, and pay a typical `O(N log N)` sorting cost before emitting results.

`limit(3).sorted()` keeps only the **first three elements**, then sorts them. Sorting cost is smaller, but it answers a different query.

Similarly, to find the top three largest:

```java
import java.util.Comparator;

List<Integer> top3 = scores.stream()
        .sorted(Comparator.reverseOrder())
        .limit(3)
        .collect(Collectors.toList());

System.out.println(top3); // [9, 8, 7]
```

For very large datasets where only a handful of top items are needed, you may want a **bounded size-K heap top-K algorithm**, or push sorting/limiting down to an indexed data source instead of always calling `sorted().limit(k)`. Never arbitrarily switch to `limit(k).sorted()` to save CPU, because the result will differ.

## 4. `distinct` and `limit`: N Distinct Elements vs Deduplicating the First N?

```java
List<Integer> ids = List.of(1, 1, 2, 3, 4);

List<Integer> uniqueFirst = ids.stream()
        .distinct()
        .limit(3)
        .collect(Collectors.toList());

List<Integer> limitedFirst = ids.stream()
        .limit(3)
        .distinct()
        .collect(Collectors.toList());

System.out.println(uniqueFirst);  // [1, 2, 3]
System.out.println(limitedFirst); // [1, 2]
```

On a Stream **with encounter order**, `distinct` keeps the **first element** in each equal group. After deduplicating, `limit(3)` gathers three distinct values if the source has at least three distinct values. Swapping them caps raw records before deduplicating, so you might not get three values.

`distinct()` normally requires a structure tracking seen values. Memory footprint depends on the number of distinct values seen (`U`); average hashing cost generally scales with the amount of data inspected. On an ordered parallel stream, preserving the first-seen element can make `distinct` require more coordination and buffering.

**Infinite source hazard:** `Stream.generate(() -> 1).distinct().limit(2)` can never find two distinct values; do not run this example because the terminal operation may never finish. Placing `limit` at the end of a pipeline does not guarantee the entire pipeline terminates.

## 5. `map` and `distinct`: Post-Transformation Values Determine Duplication

`map` can turn two initially distinct values into the same value. Thus swapping `map` and `distinct` easily introduces bugs:

```java
import java.util.Locale;

List<String> names = List.of("An", "AN", "Binh");

List<String> normalizeThenUnique = names.stream()
        .map(name -> name.toLowerCase(Locale.ROOT))
        .distinct()
        .collect(Collectors.toList());

List<String> uniqueThenNormalize = names.stream()
        .distinct()
        .map(name -> name.toLowerCase(Locale.ROOT))
        .collect(Collectors.toList());

System.out.println(normalizeThenUnique); // [an, binh]
System.out.println(uniqueThenNormalize); // [an, an, binh]
```

With `map(...).distinct()`, duplicates are decided **after normalization**. With `distinct().map(...)`, duplicates are decided **before normalization**, so two initially different elements can turn into two identical copies in the output.

The condition for safely reordering them is not just that the `map` function is pure and stateless: you must also check whether the function **preserves equality relationships**. If mapping collapses distinct values into equal ones, swapping is unsafe. For objects, `distinct()` relies on `equals`/`hashCode` of the **type present at that stage**, and does not automatically know "business ID duplication".

If you want to deduplicate by key, express the rule explicitly with a suitable structure, such as mapping IDs to records with a deterministic merge function; calling `distinct` on the whole object may violate business requirements.

## 6. `filter` and `distinct`: Usually Same Result, Different Cost

When `filter` uses a fixed, side-effect-free predicate whose outcome does not depend on other elements, and equality is checked consistently, filtering before or after deduplicating usually yields the exact same sequence of values:

```java
List<Integer> values = List.of(2, 2, 3, 3, 4, 4, 5);

List<Integer> filterThenDistinct = values.stream()
        .filter(n -> n % 2 == 0)
        .distinct()
        .collect(Collectors.toList());

List<Integer> distinctThenFilter = values.stream()
        .distinct()
        .filter(n -> n % 2 == 0)
        .collect(Collectors.toList());

System.out.println(filterThenDistinct); // [2, 4]
System.out.println(distinctThenFilter); // [2, 4]
```

Moving `filter` earlier can reduce the number of elements fed into the deduplication structure. If the predicate is cheap and drops most elements, this is usually beneficial. Yet it does not always save work: if the predicate is expensive and the source contains heavy duplication, deduplicating first can reduce predicate evaluations.

For instance: with one million records containing only ten distinct IDs, a network check per ID (though I/O generally should not be performed in a predicate) behaves very differently from `n % 2`. A practical solution might collect the IDs first and batch-process them, rather than mechanically optimizing `filter` placement.

**Crucial precondition:** if the predicate depends on mutable state, time, or side effects, moving it can alter results. In the Stream API, behavioral functions should be stateless and non-interfering; consider reordering only when that contract holds.

## 7. `filter`, `map`, and Transformation Cost

An expensive transformation should be applied to **as few elements as possible**, provided filtering remains accurate.

```java
List<Integer> raw = List.of(-2, 0, 1, 5, 8);

// "Preparation" here is just an example of a computation with cost.
List<String> result = raw.stream()
        .filter(n -> n > 0)
        .map(n -> "item-" + n)
        .collect(Collectors.toList());

System.out.println(result); // [item-1, item-5, item-8]
```

Placing `filter(n -> n > 0)` before `map` avoids building strings for invalid numbers. However, if the filter condition is defined on the **transformed result**, you cannot arbitrarily move it earlier:

```java
List<String> codes = List.of(" A ", " ", "B", "  C ");

// Filter after normalizing, because the condition checks the trimmed string.
List<String> cleaned = codes.stream()
        .map(String::trim)
        .filter(s -> !s.isEmpty())
        .collect(Collectors.toList());

System.out.println(cleaned); // [A, B, C]
```

Distinguish transformations that **change data type**, **change data meaning**, or **increase/decrease cardinality**. Moving `filter` earlier is only worth considering when an equivalent predicate can be expressed on the original input and the mapping function is safe and stateless.

## 8. `skip`, `limit`, and Pagination: Order Determines Which Page

Use `skip(offset).limit(pageSize)` to slice a window from a sequence with an established order:

```java
List<String> rows = List.of("A", "B", "C", "D", "E", "F");

List<String> page = rows.stream()
        .skip(2)
        .limit(3)
        .collect(Collectors.toList());

System.out.println(page); // [C, D, E]
```

Reversing to `limit(3).skip(2)` retains only the first three elements and discards two of them: result `[C]`. The two pipelines are not equivalent.

The placement of `skip` relative to `filter` also matters greatly:

```java
List<Integer> data = List.of(1, 2, 3, 4, 5, 6);

List<Integer> filteredPage = data.stream()
        .filter(n -> n % 2 == 0)
        .skip(1)
        .collect(Collectors.toList());

List<Integer> rawPage = data.stream()
        .skip(1)
        .filter(n -> n % 2 == 0)
        .collect(Collectors.toList());

System.out.println(filteredPage); // [4, 6]
System.out.println(rawPage);      // [2, 4, 6]
```

If the requirement is "paginate **records matching the condition**", the standard order is:

```text
source → filter(condition) → sorted(stable order) → skip(offset) → limit(pageSize)
```

When `skip`/`limit` comes before `sorted`, you are only sorting one slice of the source data, not producing "page N in global order".

**Reliable pagination requires consistent ordering.** If the comparator lets two records tie on the sort key, their order may not be deterministic enough for stable paging across reads, especially if the source or data changes. Add a unique secondary key (such as an ID) and consider *keyset pagination* for large datasets instead of continually increasing `skip`.

## 9. `takeWhile` and `dropWhile` Are Not Like `filter`

Since Java 9, `takeWhile` and `dropWhile` operate on a **contiguous prefix** of a Stream **with encounter order**.

```java
List<Integer> measures = List.of(1, 2, 5, 4, 3);

System.out.println(
        measures.stream()
                .filter(n -> n < 5)
                .collect(Collectors.toList())
); // [1, 2, 4, 3]

System.out.println(
        measures.stream()
                .takeWhile(n -> n < 5)
                .collect(Collectors.toList())
); // [1, 2]

System.out.println(
        measures.stream()
                .dropWhile(n -> n < 5)
                .collect(Collectors.toList())
); // [5, 4, 3]
```

- `filter(predicate)` tests each element independently and keeps **all** matching elements.
- `takeWhile(predicate)` takes the **longest prefix** continuously satisfying the condition and then stops taking.
- `dropWhile(predicate)` discards the **longest prefix** continuously satisfying the condition, then keeps the entire remainder (even elements that match again).

Putting `sorted` before `takeWhile` or `dropWhile` changes which prefix is selected:

```java
List<Integer> unsorted = List.of(1, 2, 5, 4, 3);

List<Integer> afterSorting = unsorted.stream()
        .sorted()
        .takeWhile(n -> n < 5)
        .collect(Collectors.toList());

System.out.println(afterSorting); // [1, 2, 3, 4]
```

On an unordered Stream, `takeWhile`/`dropWhile` do not preserve prefix semantics in original list order; by contract, the subset kept or dropped may not match your expectation. If the requirement is "all values less than 5", use `filter`.

## 10. Encounter Order, `unordered`, and Parallel Streams

`unordered()` is not a randomizer like `shuffle`. It notifies downstream stages that encounter order **does not need to be respected**. Depending on the source and terminal operation, this can let some operations run more efficiently in parallel while dropping guarantees about "first".

```java
List<Integer> numbers = List.of(4, 1, 4, 3, 2, 3, 5);

// Preserves the List's encounter order and first occurrences.
List<Integer> ordered = numbers.parallelStream()
        .distinct()
        .limit(3)
        .collect(Collectors.toList());

System.out.println(ordered); // [4, 1, 3]
```

If you add `unordered()`, you cannot assert which three distinct elements will be retained:

```java
List<Integer> someThree = numbers.parallelStream()
        .unordered()
        .distinct()
        .limit(3)
        .collect(Collectors.toList());

// Contains at most three distinct values; membership and order
// are not guaranteed to match [4, 1, 3].
```

For the pipeline above, there are at least three distinct values, so `limit` yields three elements if execution completes normally. Do not expect them to be the **first three values** or the **three smallest values**. Placing `sorted()` **after** `limit(3)` does not fix the wrong "global top three" semantics, because elements were already sliced before sorting.

In an ordered parallel pipeline, `skip`, `limit`, and `distinct` often pay coordination overhead to preserve the "first element" constraint. Use `unordered()` only when business logic genuinely **does not care which elements are selected**. `sorted()` before `limit()` has a different meaning, so `unordered()` cannot replace it for top-N queries.

### `forEach` and `forEachOrdered`

```java
List.of(10, 20, 30).parallelStream()
        .forEach(System.out::println); // Print order is not guaranteed.

List.of(10, 20, 30).parallelStream()
        .forEachOrdered(System.out::println); // 10, 20, 30
```

`forEachOrdered` preserves encounter-order execution of actions when the Stream is ordered. Do not treat `peek` print order or shared-variable mutation in `map` as proof of result ordering.

## 11. Laziness, Short-Circuiting, and Two Kinds of Cost

Operation order determines **how many elements must flow through a stage**, yet you cannot predict lambda invocation counts using a rigid formula for every source and terminal operation.

In a sequential pipeline:

```java
import java.util.stream.IntStream;

long found = IntStream.rangeClosed(1, 1_000_000)
        .filter(n -> n % 1_000 == 0)
        .limit(2)
        .count();

System.out.println(found); // 2
```

To find the first two numbers divisible by 1,000, the pipeline may inspect up to 2,000, without traversing all one million numbers. Thus `limit(2)` **bounds the output count**, not the input count checked to just two elements.

Conversely:

```java
long top = IntStream.rangeClosed(1, 1_000_000)
        .boxed()
        .sorted(Comparator.reverseOrder())
        .limit(2)
        .count();

System.out.println(top); // 2
```

Putting `sorted` before `limit` can force the pipeline to inspect the entire input to find the largest elements, even though only two elements are returned. However, do not infer that **one million comparator calls actually happened** from this snippet alone: the Stream API lets certain terminal operations (especially `count` on sized pipelines) optimize away traversal when the count is unaffected. To inspect the top two values, use `collect` instead of `count`.

### Infinite Streams and `limit` Placement

```java
import java.util.stream.Stream;

List<Long> firstFiveSorted = Stream.iterate(0L, n -> n + 1)
        .limit(5)
        .sorted()
        .collect(Collectors.toList());

System.out.println(firstFiveSorted); // [0, 1, 2, 3, 4]
```

Here `limit(5)` turns an infinite source into a finite slice so `sorted` can complete. Flipping it to `Stream.iterate(...).sorted().limit(5)` can cause the pipeline **never to emit a first element**, because `sorted` needs to establish order before emitting from a non-terminating source. This is an example of a reordering that breaks both termination and memory safety.

### Stateful Intermediate Operations

| Operation | Typical cost (finite source) | Early-stopping capability |
| --- | --- | --- |
| `map` / `filter` | Proportional to elements actually inspected; usually no global buffer | Can short-circuit with `limit`, `findFirst`, or `anyMatch` |
| `distinct` | Proportional to elements seen and distinct keys encountered; may buffer key set | `distinct().limit(k)` can stop once k distinct values arrive, if enough exist |
| `sorted` | Typically `O(N log N)` time and `O(N)` memory | Usually cannot emit elements until required order is established |
| `skip(n)` | Must discard n elements in encounter order | Can optimize on sized/splittable sources |
| `limit(n)` | Emits at most n elements downstream | Short-circuiting, unless an upstream stateful step blocks it |

These are **design heuristics**, not rigid internal-algorithm guarantees across every JDK. Operations may be optimized or executed differently depending on the source, `Spliterator` characteristics, terminal operation, and parallelism.

## 12. Checklist for Deciding Whether Reordering Is Safe

Before moving an operation earlier to make it "faster", ask in sequence:

1. **Which elements are required?** Do `limit`, `skip`, `takeWhile`, or `findFirst` depend on encounter order?
2. **Do elements change identity/value after `map`?** If `map` normalizes, rounds, or extracts a key, `distinct` before and after may deduplicate different groups.
3. **Is the predicate independent of other data?** Only swap pure, stateless, side-effect-free functions that preserve meaning.
4. **Is global sorting required?** `sorted().limit(k)` and `limit(k).sorted()` solve two different problems.
5. **Is the source finite or infinite?** `sorted` and some uses of `distinct` may never finish when placed before a short-circuit.
6. **Does the source have an encounter order?** If not, "first" may be unspecified; adding `unordered` permits picking different elements.
7. **Where is the bottleneck?** Filtering early shrinks data flowing into expensive stages, yet may increase calls to an expensive predicate if placed before `distinct`.
8. **Have you measured on real data?** Measure CPU, memory, returned record count, source read time, and result stability.

A quick example table:

| Swap | Usually same result? | Reason |
| --- | --- | --- |
| `filter` ↔ `limit` | **No** | Filtering N matches differs from inspecting N inputs |
| `sorted` ↔ `limit` | **No** | Global top N differs from sorting the first N elements |
| `distinct` ↔ `limit` | **No** | Distinct count after slicing may be less than N |
| `skip` ↔ `limit` | **No** | Changes the sliced window |
| `filter` ↔ `skip` | **No** | Skips elements before vs after filtering |
| `map` ↔ `distinct` | **No, if map alters equality** | Duplication is tested on two different types/values |
| `filter` ↔ `distinct` | **Usually yes**, when predicate is pure and consistent with equality | Filtering/hashing cost may differ |
| `filter` ↔ `sorted` | **Usually yes**, if predicate is pure, comparator fits, and only sorted filtered output is needed | Filtering first usually reduces sorting volume |
| `takeWhile` ↔ `sorted` | **No** | Prefix condition is applied to a different order |

## 13. Comprehensive Example: Selecting Top Three Product Scores by Business Rules

Suppose a list of product scores may contain duplicates, scores below a threshold, and unsorted entries. The task is to **get the three highest distinct scores after removing scores below 8**.

```java
import java.util.Comparator;
import java.util.List;
import java.util.stream.Collectors;

List<Integer> scores = List.of(6, 10, 10, 8, 12, 5, 12, 9);

List<Integer> topDistinct = scores.stream()
        .filter(score -> score >= 8)
        .distinct()
        .sorted(Comparator.reverseOrder())
        .limit(3)
        .collect(Collectors.toList());

System.out.println(topDistinct); // [12, 10, 9]
```

The order here has clear meaning:

1. `filter(score >= 8)` drops unqualified data right at the start.
2. `distinct()` keeps one occurrence per score; in this problem, duplication is based on **score value**.
3. `sorted(reverseOrder())` orders all distinct valid scores from highest to lowest.
4. `limit(3)` picks the top three distinct values, if enough exist.

A seemingly "cheaper" version that changes meaning:

```java
List<Integer> wrong = scores.stream()
        .filter(score -> score >= 8)
        .limit(3)
        .distinct()
        .sorted(Comparator.reverseOrder())
        .collect(Collectors.toList());

System.out.println(wrong); // [10, 8]
```

This version examines only the first three valid scores `[10, 10, 8]`, missing `12` and `9` later in the list. That is a business logic bug, not just a performance difference.

If you want a page of product records rather than scores, use a comparator with a stable tie-breaker key, clarify what "duplicate" means (product ID, variant, or score), and consider pushing sorting/pagination down to the data source to avoid loading everything into memory.

## 14. Self-Check Questions

1. Given `[7, 2, 9, 4, 6]`, why does `filter(even).limit(2)` differ from `limit(2).filter(even)`? **Because** one selects two valid values while the other filters only among the first two inputs.
2. Do `sorted().limit(3)` and `limit(3).sorted()` perform the same job? **No**: one finds the first three values in global sorted order, while the other sorts the first three source values.
3. On `["An", "AN"]`, why does `map(lowercase).distinct()` produce one element while `distinct().map(lowercase)` produces two? **Because** normalization changes the equality relation.
4. Does `Stream.generate(() -> 1).distinct().limit(2)` terminate? **No**, because two distinct values can never be found.
5. Does `unordered()` randomly shuffle a `List`? **No**; it drops the encounter-order commitment, allowing downstream stages to select or execute differently.
6. When paginating filtered and sorted records, where should `skip`/`limit` go? **After** the filtering and sorting required by business logic.
7. Why is `takeWhile(x < 5)` not equivalent to `filter(x < 5)` on an unsorted sequence? **Because** `takeWhile` only takes the contiguous matching prefix.
8. To evaluate the cost of `sorted` on a large source, why should you not rely solely on `count()` to infer how many elements were actually sorted? **Because** the JDK can optimize `count` when size is known without traversing the pipeline.

**Application rule:** First specify accurately **which elements to retain** and **which order must be guaranteed**, then optimize. Push simple filters before expensive operations when safe, keep `sorted` before `limit` when global top N is required, and never move `distinct` or `skip` across `map`/`filter` when doing so changes meaning. Measure cost on real data and your target JDK, especially for parallel pipelines or infinite sources.
