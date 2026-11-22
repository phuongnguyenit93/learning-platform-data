# Statefulness Cost of `sorted()` and `distinct()` in Java Streams

In the Java Stream API, not every intermediate operation can process elements one by one without storing anything extra. Two common operations, **`sorted()`** and **`distinct()`**, need information from **multiple elements**, so they are classified as *stateful intermediate operations*. Understanding the cost of maintaining state helps predict memory usage, time to first result, early termination capability, and the impact of running streams in parallel.

Consider a pipeline:

~~~text
List<T> / data source
      |
      v
filter(...)       -- typically stateless: per-element decision
      |
      v
distinct()        -- stateful: remembers seen values
      |
      v
sorted(...)       -- stateful: needs to organize multiple elements to determine order
      |
      v
limit(3)          -- takes at most 3 results at this position
      |
      v
toList()          -- terminal: requests the result
~~~

**Key takeaway:** both `sorted` and `distinct` are intermediate operations and remain *lazy* when constructing the pipeline, but **lazy does not mean zero memory cost**, nor does it guarantee that placing `limit` downstream will make all preceding steps cheaper. Actual cost depends on input size, number of distinct values, whether the source is ordered, operation placement, and sequential/parallel execution.

## 1. Stateless vs. Stateful in a Pipeline

**Stateless** operations (e.g., `map`, `filter`) typically only need the current element and the function provided by the caller. In a simple sequential pipeline, an element can pass through multiple stateless steps to the terminal operation without needing to build a full list after each step.

**Stateful** operations need to retain state related to other elements:

- `sorted()` or `sorted(comparator)` must determine element positions according to a shared order.
- `distinct()` needs to know whether an equivalent element has already appeared so it does not emit it again.
- `limit()` also maintains a counter; it is a *short-circuiting stateful intermediate operation*, though its state is usually smaller than sorting the entire input. Distinguish **how much state must be retained** from **whether an operation is stateful**.

A conceptual example:

~~~java
List<String> result = List.of("B", "A", "B", "C").stream()
        .filter(s -> !s.isEmpty())
        .distinct()
        .sorted()
        .toList();
// [A, B, C]
~~~

Requires importing `java.util.List`; the snippet is placed inside a method. `filter` checks each value. `distinct` must remove the second occurrence of `"B"`. `sorted` produces ascending order. `toList()` is the terminal operation that triggers pipeline evaluation.

A stateful intermediate operation **does not necessarily always buffer the entire source**: `distinct` can remember the set of seen keys and forward non-duplicate elements incrementally; conversely, `sorted` typically must consume the entire finite input before emitting sorted elements. This is an important difference in **when results can start appearing**.

## 2. `sorted()`: Why Does It Usually Need to Buffer Everything?

`Stream.sorted()` sorts according to the natural order of elements; `Stream.sorted(Comparator<? super T>)` uses the caller-provided comparator. It is a **stateful intermediate operation**, not a terminal one, and it **does not sort the source collection directly**. For a `List`, if you want to sort the list in place, use `list.sort(comparator)`.

~~~java
List<Integer> descending = List.of(4, 1, 3, 2).stream()
        .sorted(Comparator.reverseOrder())
        .toList();
// [4, 3, 2, 1]
~~~

Requires importing `List` and `Comparator`. For a finite but unsorted input, `sorted` generally needs to know all elements to guarantee which element comes before which: the smallest value might only appear at the very end of the source.

### Typical Cost

If there are **n input elements**:

| Resource | Typical Trend |
| --- | --- |
| Time | General comparison-based sorting is typically around `O(n log n)` comparisons/cost |
| Working memory | Usually requires `O(n)` references/auxiliary buffer to collect and order the elements |
| Latency to first element | May have to wait until the entire finite source is read before emitting sorted results |
| Result | Elements ordered by comparator or natural order, without mutating the source |

This is a **useful analytical model**, not a guaranteed complexity or fixed allocation amount in the Stream API specification. The implementation, whether the source is already ordered, known size, element type, JDK version, and sorting algorithm all affect performance. The cost of the comparator itself also matters: if the comparator performs heavy string processing or expensive property extraction, actual cost increases with the number of comparisons.

For `IntStream`, `LongStream`, or `DoubleStream`, which have their own primitive `sorted()`, per-element boxing is avoided compared to `Stream<Integer>`. However, sorting many values still has a cost.

### Stability and Ordering

For an **ordered** stream, `sorted()` guarantees stability (*stable*): two elements considered equal by the comparator preserve their relative encounter order. For an **unordered** stream, the specification provides no such stability guarantee.

~~~java
record Task(String id, int priority) {}

List<Task> tasks = List.of(
        new Task("A", 1),
        new Task("B", 1),
        new Task("C", 2)
);
List<Task> ordered = tasks.stream()
        .sorted(Comparator.comparingInt(Task::priority))
        .toList();
// Task A comes before Task B because they have the same priority and the List source is ordered.
~~~

This is an illustrative snippet inside a method, requiring `List` and `Comparator`; `record Task` is placed at class scope or near the appropriate method. **A comparator returning 0 does not mean two objects are equal according to `equals`.** `sorted` sorts; it does not deduplicate.

## 3. `distinct()`: Needing to Remember Seen Elements

`Stream.distinct()` removes duplicate elements based on `Object.equals(Object)`. On an ordered stream, the result **preserves the first occurrence** of each `equals`-equivalent value; on an unordered stream, there is no guarantee which representative element is kept if elements are equal yet differ in other aspects.

~~~java
List<String> names = List.of("Binh", "An", "Binh", "Chi", "An", "Dung");
List<String> unique = names.stream().distinct().toList();
// [Binh, An, Chi, Dung]
~~~

To recognize that the second `"Binh"` is a duplicate, a typical implementation needs to store a `Set`-like structure of seen values. If there are **n input elements** and **u distinct values**:

| Resource | Typical Trend |
| --- | --- |
| Memory | Around `O(u)` state to recognize seen values |
| Time | With a standard hash-based set and reasonable `hashCode`/`equals`, around `O(n)` on average for duplicate checks |
| Worst case | Hash collisions, expensive `equals`, or special sources can significantly increase cost |
| Latency | In a suitable sequential pipeline, distinct elements can be emitted as they are found without necessarily waiting for the whole source |

`O(u)` is a general algorithmic analysis guideline, **not an exact allocation formula for every JDK or parallel mode**. When `u` is close to `n` (most elements are distinct), the state set can be nearly as large as the entire input. When many elements are duplicates, `u` is significantly smaller than `n`.

`distinct` does not accept a comparator or key extractor. If you want to deduplicate by an `id` field rather than the object's full `equals`, you need to **design a key-mapping transformation**, use a map/collector by key, or use a deduplication mechanism with an explicit contract. Do not assume `sorted(comparator).distinct()` will remove elements for which the comparator returns 0: `distinct` still uses `equals`.

### The `equals` and `hashCode` Contract

For custom classes used in value comparisons, `equals` and `hashCode` must be designed consistently: if `a.equals(b)`, then `a.hashCode() == b.hashCode()`. A `record` provides appropriate component-based comparison methods by default.

~~~java
record Entry(String id, int version) {}

List<Entry> entries = List.of(
        new Entry("A", 1),
        new Entry("A", 1),
        new Entry("A", 2)
);
List<Entry> distinctEntries = entries.stream().distinct().toList();
// The two Entry("A", 1) instances merge into one; Entry("A", 2) remains separate.
~~~

The snippet above is illustrative only and placed in a context where `List` is imported. If you need only one element per `id`, `distinct` on a record that includes `version` does not meet the requirement — you must define the version-selection rule and use an appropriate collector/map.

Do not mutate fields involved in `equals`/`hashCode` while elements are being checked through a hash structure: doing so can break the consistency of duplicate detection.

## 4. Operation Ordering: Same Correctness or Different Cost

With the same steps, changing their order can change the **result values**, the **number of elements processed**, and **memory usage**.

### `filter` Before `sorted`

~~~java
List<Integer> result = List.of(5, 1, 4, 2, 3).stream()
        .filter(n -> n % 2 == 0)
        .sorted()
        .toList();
// [2, 4]
~~~

`sorted` receives only two even numbers instead of processing all five numbers and filtering afterward. When the filter condition is cheap and independent of order, placing `filter` early usually reduces the number of elements fed into the stateful operation. However, do not reorder if the predicate depends on earlier normalization steps or changes semantics.

### `distinct` Before `sorted` When Sorting Unique Values

~~~java
List<String> uniqueSorted = names.stream()
        .distinct()
        .sorted()
        .toList();
// [An, Binh, Chi, Dung]
~~~

In this example, `distinct` reduces six input elements to four values, so `sorted` has fewer elements to sort. `distinct` still pays the cost of retaining the seen set; this is a trade-off between remembering unique values and reducing the number of elements to sort.

~~~java
List<String> sortedUnique = names.stream()
        .sorted()
        .distinct()
        .toList();
// [An, Binh, Chi, Dung]
~~~

The two pipelines above produce the same result **on this String data**. Do not apply this swap blindly to every comparator, encounter order, or representative-element requirement: `sorted` by a comparator and `distinct` by `equals` are two different concepts.

### `sorted().limit(k)` Differs from `limit(k).sorted()`

~~~java
List<String> smallestThree = names.stream()
        .sorted()
        .limit(3)
        .toList();
// [An, An, Binh]
~~~

Because we need the three smallest elements of the **entire source**, `sorted` comes first and can process all elements before `limit(3)` receives data.

~~~java
List<String> sortedFirstThree = names.stream()
        .limit(3)
        .sorted()
        .toList();
// [An, Binh, Binh]
~~~

Here only the **first three elements from the source** (`Binh, An, Binh`) are passed into `sorted`. This is usually cheaper, but the answer is "sort the first three elements", **not** "the three smallest elements of the entire source".

**Note:** using `limit(k)` *after* `sorted` does not mean the Java API guarantees only `O(k)` memory is needed. If the problem's real goal is finding the top-k out of n values where k is much smaller than n, consider a dedicated top-k algorithm (e.g., a priority queue of size k) instead of sorting everything and then limiting.

### `distinct().limit(k)` Can Read More Than k Source Elements

~~~java
List<String> firstThreeUnique = names.stream()
        .distinct()
        .limit(3)
        .toList();
// [Binh, An, Chi]
~~~

The source must advance past the second `Binh` to find `Chi` (which is the third distinct element). Swapping the order:

~~~java
List<String> uniqueWithinFirstThree = names.stream()
        .limit(3)
        .distinct()
        .toList();
// [Binh, An]
~~~

The second approach inspects only the first three values and yields two distinct values. If the goal is to cap the **data-reading budget** before deduplication, put `limit` first. If the goal is to find k distinct elements, put `distinct` before `limit`, while accounting for the possibility that the source might not contain k distinct values.

## 5. Short-Circuiting and Infinite Sources: Real Termination Conditions

Two examples intentionally **not meant to be run**:

~~~java
// Does not terminate in the sense of producing finite output:
// Stream.iterate(1, n -> n + 1)
//       .sorted()
//       .limit(3)
//       .toList();

// Infinite source of all 1s, with only a single distinct value:
// Stream.generate(() -> 1)
//       .distinct()
//       .limit(2)
//       .toList();
~~~

First case: `sorted` comes before `limit`; it needs to process an unbounded source to know the full order. Second case: `distinct` emits only the first `1`, while `limit(2)` keeps waiting for a second distinct element that never arrives.

Place a finite limit upstream:

~~~java
List<Integer> topThreeOfHundred = Stream.iterate(1, n -> n + 1)
        .limit(100)
        .sorted(Comparator.reverseOrder())
        .limit(3)
        .toList();
// [100, 99, 98]
~~~

These are the **three largest numbers among the first one hundred values**, not the three largest numbers of the infinite increasing sequence. If a source may be infinite while the question asks for a finite sample set, explicitly bound the sample scope before sorting.

~~~java
List<Integer> uniqueSample = Stream.generate(() -> 1)
        .limit(10)
        .distinct()
        .toList();
// [1]
~~~

`limit(10)` before `distinct` lets the pipeline terminate without needing to find a specific number of distinct values. That changes the meaning from "find k distinct values" to "deduplicate within m samples".

Additionally, a stateful operation **after** `limit` may process the bounded number of elements, but this does not guarantee that the `Supplier` will not block or that no exception will occur in a mapper/predicate.

## 6. Complete Java 17+ Example and Verified Stdout

Save the file **`SortedDistinctCostDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class SortedDistinctCostDemo {
    public static void main(String[] args) {
        List<String> names = List.of("Binh", "An", "Binh", "Chi", "An", "Dung");

        System.out.println("sorted=" + names.stream().sorted().toList());
        System.out.println("distinct=" + names.stream().distinct().toList());
        System.out.println("distinctThenSorted=" +
                names.stream().distinct().sorted().toList());
        System.out.println("sortedThenDistinct=" +
                names.stream().sorted().distinct().toList());
        System.out.println("sortedThenLimit=" +
                names.stream().sorted().limit(3).toList());
        System.out.println("limitThenSorted=" +
                names.stream().limit(3).sorted().toList());
        System.out.println("distinctThenLimit=" +
                names.stream().distinct().limit(3).toList());
        System.out.println("limitThenDistinct=" +
                names.stream().limit(3).distinct().toList());

        List<String> parallelDistinct = names.parallelStream().distinct().toList();
        System.out.println("parallelDistinct=" + parallelDistinct);

        List<String> byLength = List.of("aa", "bb", "c").stream()
                .sorted(Comparator.comparingInt(String::length))
                .distinct()
                .toList();
        System.out.println("lengthSortedDistinct=" + byLength);

        List<String> mutable = new ArrayList<>(names.stream().distinct().toList());
        mutable.add("E");
        System.out.println("mutableSize=" + mutable.size());
    }
}
~~~

Run commands (JDK 17 or higher):

~~~bash
javac SortedDistinctCostDemo.java
java SortedDistinctCostDemo
~~~

**Exact stdout:**

~~~text
sorted=[An, An, Binh, Binh, Chi, Dung]
distinct=[Binh, An, Chi, Dung]
distinctThenSorted=[An, Binh, Chi, Dung]
sortedThenDistinct=[An, Binh, Chi, Dung]
sortedThenLimit=[An, An, Binh]
limitThenSorted=[An, Binh, Binh]
distinctThenLimit=[Binh, An, Chi]
limitThenDistinct=[Binh, An]
parallelDistinct=[Binh, An, Chi, Dung]
lengthSortedDistinct=[c, aa, bb]
mutableSize=5
~~~

Analysis:

1. `sorted` produces ascending lexicographical order and **does not automatically remove duplicates**.
2. `distinct` removes duplicate values, while on an ordered `List` it preserves first-appearance order: `Binh, An, Chi, Dung`.
3. Both combinations `distinct→sorted` and `sorted→distinct` yield the same result **on this dataset**; the state retained and the number of elements processed can differ.
4. Placing `limit` before/after a stateful operation changes its input set and can change the answer.
5. `parallelStream().distinct()` still preserves the first occurrence for an ordered `List` source; however, the coordination cost to preserve order can be high.
6. `sorted(Comparator.comparingInt(String::length)).distinct()` still keeps both `"aa"` and `"bb"` because they are **not equal according to `equals`**, even though the length comparator returns 0. `"c"` comes first because it is shorter.
7. `Stream.toList()` produces a list that does not support structural modification; `new ArrayList<>(...)` in the example explicitly creates a mutable copy before adding `"E"`.

With JDK 17, the entire program compiles with `javac --release 17` and the output above was verified by actual execution.

## 7. Parallel Streams: Why Are Stateful Operations Often More Expensive?

**Parallel streams** split processing into subtasks. Stateless `map`/`filter` operations are generally well suited to splitting, whereas `sorted` and `distinct` require **coordination across parts**.

### Parallel `sorted()`

To produce the final sorted order, partitions need to be merged according to the comparator. This can create intermediate buffers, partition data, and merge them back. Multi-core CPUs can help on sufficiently large sources, but the overhead of allocation, task splitting, synchronization, and merging can outweigh the benefits on small datasets.

For sources with an encounter order, `sorted` implies a stable sort. The comparator must be consistent, non-mutating, and ideally side-effect-free. Avoid assuming comparator calls happen sequentially or in a fixed order during parallel execution.

### Parallel `distinct()` on Ordered Sources

When preserving the **first occurrence** in a stream with an encounter order, workers cannot always decide independently which element is the first representative without coordination. That can require significant synchronization/buffering. The Javadoc for `distinct` also warns that parallel processing on ordered sources can be expensive due to the requirement to preserve stability.

If the problem **does not care about the order of representative elements**, and only needs the set of distinct values:

~~~java
List<String> result = names.parallelStream()
        .unordered()
        .distinct()
        .toList();
~~~

This is an illustrative snippet using the `names` variable from the example program. `unordered()` removes the pipeline's encounter-order constraint, which can allow parallel `distinct` to execute more efficiently; however, the result has **no guaranteed order**. Do not apply `unordered()` when the application needs to "keep the first-seen record" or display a fixed order.

Do not claim `parallelStream()` is always faster: measure with sufficiently large data, appropriate JVM settings, and a realistic execution environment. For reliable benchmarking, use JMH to control warm-up, JIT optimization, and measurement; do not run `System.nanoTime()` once and generalize it into a rule.

## 8. Cost Planning from Input Size and Selectivity

Suppose there are `n` source elements, `m` elements passing `filter`, and `u` distinct elements among those `m`:

| Pipeline | Expected Impact |
| --- | --- |
| `filter(p).sorted()` | `sorted` has to process roughly `m` elements instead of `n` |
| `filter(p).distinct().sorted()` | `distinct` inspects `m` elements and remembers roughly `u` keys; `sorted` processes roughly `u` elements |
| `sorted().filter(p)` | `sorted` may have to process all `n` elements before `filter` reduces them to `m` |
| `limit(k).sorted()` | Sorts at most `k` elements passed down from the source |
| `sorted().limit(k)` | Typically still has to sort the entire input before taking `k` elements |
| `limit(k).distinct()` | Deduplicates at most `k` sampled elements |
| `distinct().limit(k)` | May have to read more than `k` elements, or even fail to terminate if an infinite source lacks enough distinct values |

The table describes processing trends, not exact operation counts or allocated bytes. The **selectivity** of the predicate determines `m`; the **diversity** of the data determines `u`. Both quantities often have a major impact on cost, so measure with representative data rather than relying solely on a toy dataset with a few elements.

In a multi-step pipeline, the Stream engine may apply optimizations. For example, some terminal operations like `count()` on a sized source can compute the result without executing every intermediate operation, provided the required result is preserved. Therefore, **do not rely on side effects in `peek`, `map`, comparators, or predicates to infer how many times they are called**. To observe cost, measure allocation/heap and time for a real business task rather than making measurements depend on printing inside the pipeline.

## 9. Alternatives for Large Datasets

### Filter and Reduce Data Before Stateful Operations

If `filter` can be pushed earlier without changing semantics, eliminate unnecessary data before `sorted` or `distinct`. Similarly, if only a small slice of a very large source is needed, define a **finite source scope** upfront (time range, record count, partition key, window).

### Use an Appropriate Top-k Algorithm When You Only Need Top-k

`sorted(comparator).limit(k)` is concise and correct for finite sources, but it usually sorts everything. If `k` is much smaller than `n`, using a **priority queue of size k** can achieve roughly `O(n log k)` time and `O(k)` memory for top-k, and then sort the final k results. This is an **alternative algorithm** that must be implemented with the right comparison rules; the Stream API's `sorted` does not promise to turn into a top-k algorithm when it sees `limit`.

~~~java
// Illustrates the structure inside a method:
// Keep the k largest values using a min-heap, then sort in descending order.
PriorityQueue<Integer> heap = new PriorityQueue<>();
int k = 3;
for (int value : values) {
    if (heap.size() < k) {
        heap.add(value);
    } else if (value > heap.peek()) {
        heap.poll();
        heap.add(value);
    }
}
List<Integer> top = new ArrayList<>(heap);
top.sort(Comparator.reverseOrder());
~~~

This is an **illustrative snippet**, requiring `java.util.PriorityQueue`, `List`, `ArrayList`, `Comparator`, and a defined finite `Iterable<Integer> values`; it is not a standalone runnable program. For k equal to 0, handle it separately before the loop; for k larger than the number of elements, only that many values are collected. A heap does not deduplicate unless additional rules are added.

### When `distinct` Is Needed on Too Large a Source

**Exact deduplication across an entire infinite source that may contain infinitely many distinct values** cannot default to bounded state using `distinct()`. You can redefine the problem as per-batch/window deduplication, key-based partitioning, or storing state in an external system. If using a Bloom filter or approximate technique, you must accept the risk of mistakenly dropping unseen values (*false positive*), and do not call that exact `distinct`.

### When You Only Need the Count of Distinct Values

`stream.distinct().count()` expresses the intent cleanly on a finite source, but it can still consume memory to track distinct keys. Do not assume that just because the terminal `count()` returns a single number, the preceding pipeline uses `O(1)` memory. You can switch to approximate counting if the business domain allows it, but the error margin must be stated clearly.

## 10. Common Pitfalls and Correctness Checks

**Confusing a comparator with equality:** `sorted(comparator)` uses a comparator; `distinct()` uses `equals`. Two strings of the same length are not duplicates just because a length comparator returns 0. To deduplicate by a key, build a key-based algorithm/collector with a record-selection policy.

**Placing `limit` after `sorted` on an infinite stream:** sorting an infinite stream cannot complete as a full sort. Bound the dataset before sorting or redefine the requirement.

**Placing `limit` after `distinct` when there are not enough distinct values:** an infinite source of all 1s with `distinct().limit(2)` will wait forever. If you need to cap the number of reads, put `limit` before `distinct`, accepting that the number of distinct output values may be less than k.

**Assuming `distinct` needs no memory because streams are lazy:** it must recognize seen keys. The more distinct values in the data, the larger the state.

**Assuming `sorted` always needs little memory when `limit(10)` follows it:** `limit` after sort does not remove the requirement to order the entire input.

**Assuming every parallel stream improves performance:** ordered `distinct` needs to preserve the first occurrence, and `sorted` needs coordination/merging; parallel execution can be slower and consume more memory.

**Abusing side effects to measure a pipeline:** `peek(System.out::println)` is not a reliable measurement tool; the optimizer may skip traversal when the terminal result allows it. Use proper benchmarks, heap profilers/JFR, or JMH when drawing performance conclusions.

**Mutating the source during processing:** non-interference is a key principle. Do not add/remove elements of a `List` while a Stream is traversing it; avoid mutating keys involved in comparator/`equals` while sorting/deduplication is running.

**Assuming `toList()` output is mutable:** since Java 16, `Stream.toList()` returns a list that does not support modification. If you need to modify it further, create `new ArrayList<>(stream.toList())`.

**Equating sorting with output stability:** an unordered source makes no commitment to an initial order, so do not expect "keep the first element" from `distinct` without a meaningful encounter order.

## 11. Application Checklist

1. Determine the source size `n`, whether the data is finite or potentially infinite, and whether all data is needed or only a finite sample.
2. Estimate the pass-through ratio of filters and the number of distinct keys `u`: if `u≈n`, `distinct` may retain large state.
3. Verify semantics when placing `filter`, `distinct`, `sorted`, and `limit` in different orders; do not optimize by changing the answer.
4. Check whether the requirement needs **encounter order**, **stable sort**, or "the first record". If not, an unordered source may allow certain optimizations.
5. For parallel pipelines, choose them only with representative benchmarks; do not expect stateful steps to always distribute efficiently.
6. If top-k with small k is needed, consider a priority queue instead of sorting everything; if unbounded deduplication is needed, define a window/batch/external-state policy.
7. Test with data having many duplicates and almost no duplicates, large sources, comparators with tied keys, and ordered/unordered inputs.

**Summary:** `sorted()` maintains state to establish order and usually requires memory proportional to the number of elements to sort; `distinct()` retains information about seen keys, so its cost depends on the number of distinct values. Both are lazy intermediate operations when building a pipeline, yet they can be very expensive when the terminal operation demands results. To reduce cost, remove unneeded data from the pipeline early, place limits in the right position, leverage ordering contracts, and use specialized algorithms when the requirement is top-k or large-scale deduplication.