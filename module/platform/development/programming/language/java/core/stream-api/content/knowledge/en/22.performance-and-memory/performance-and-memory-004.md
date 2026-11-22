# Estimating Memory of `sorted`, `distinct`, `groupingBy`, and `collect`

The Java Stream API lets you express data processing as declarative, *lazy* pipelines with steps like `filter`, `map`, `sorted`, `distinct`, `reduce`, and `collect`. However, **lazy does not mean a pipeline always uses constant memory**. Some operations must remember previously seen elements or group many elements before producing output. Typical examples are `sorted`, `distinct`, `groupingBy`, and forms of `collect` that retain all elements.

This lesson belongs to the **Performance and Memory** chapter of the **JAVA_STREAM_API** module. The goal is to know how to **estimate additional memory**, distinguish peak memory from retained result memory, identify the dominant factor for each operation, evaluate the impact of `Spliterator` and parallel streams, and choose an appropriate design for large datasets. This knowledge connects directly to grouping, custom collectors, parallel processing, and resource limits; advanced transformations like Stream Gatherers must follow the same principles regarding state and output.

> **Rule:** Never conclude a pipeline uses `O(1)` memory just because it has no explicit loop or returns a `Stream`. You must examine **every operation**, the **terminal operation**, and the **size of retained results**.

## 1. Distinguish the types of memory to account for

Before stating “this pipeline uses X MB”, clarify **what you are counting**:

| Component | Example | Should it be included in estimates? |
|---|---|---|
| **Pre-existing source** | `ArrayList<Order>` holding one million objects | Yes in **total application heap**; can be separated from **pipeline-added memory** |
| **Intermediate state** | Sorting buffer, hash table of `distinct` | Yes; may stay live while the pipeline runs |
| **Collector state** | Map of groups, lists per group | Yes; often becomes part of the final result |
| **Retained output** | `List` from `collect(toList())` | Yes; remains live after the terminal operation finishes |
| **Temporary objects** | Wrappers, iterators, entries, mapper outputs | Can increase allocation rate and GC pressure even when short-lived |
| **Parallel execution memory** | Per-branch state, fork/join queues, merge buffers | Yes; varies by splitting strategy and parallelism |
| **Off-heap resources** | File handles, native buffers, direct memory | Must be managed; not fully reflected by collector heap figures |

### 1.1. Retained memory, added memory, and peak memory

Let:

- `B_source`: size of the existing source that remains referenced.
- `B_state(t)`: intermediate state live at time `t`.
- `B_result(t)`: created result data live at time `t`.
- `B_misc(t)`: buffers, auxiliary objects, and temporary data live at `t`.

Estimate of **peak live heap** for the task:

\[
B_{\text{peak}}\;\approx\; B_{\text{source}}\;+\;
\max_t\bigl(B_{\text{state}}(t)+B_{\text{result}}(t)+B_{\text{misc}}(t)\bigr)
\]

This is an **estimation model**, not an exact equality for the JVM heap. GC timing, internal allocations, when references are released, and implementation details can make the actual peak differ from a simple sum. Do not sum every buffer that ever existed as if all were simultaneously live.

**Retained memory after `collect`** can be much smaller than peak memory: a `sorted` buffer may be freed, while the resulting `List` or `Map` remains held by the caller. Conversely, a pipeline like `sorted().limit(5).toList()` can **return only 5 elements yet still have needed a large buffer** during sorting.

### 1.2. Notation used throughout this lesson

| Symbol | Meaning |
|---|---|
| `n` | Number of elements actually reaching the operation under consideration |
| `u` | Number of **distinct** elements by `equals/hashCode` after `distinct`, `u ≤ n` |
| `k` | Number of distinct **group keys** in `groupingBy`, `k ≤ n` |
| `m` | Number of elements actually retained in a result collection |
| `p` | Number of accumulators or intermediate branches that may coexist, **not necessarily equal to thread count** |
| `L` | Total character/content length when joining into a String |

These symbols describe **memory complexity** in terms of elements or groups; converting to bytes requires accounting for object layout, references, and the target JVM implementation.

## 2. Memory complexity overview table

For finite sources where operations must actually traverse and build full required results, the table below gives directional estimates:

| Operation | Typical extra state | Retained result with matching terminal | Common misconception |
|---|---|---|---|
| `map`, `filter` | Usually `O(1)` on a simple sequential pipeline | Depends on terminal operation | Lazy does not mean zero object allocation |
| `sorted` | Usually **`O(n)`** to sort elements reaching this step | If `collect(toList())`: `O(n)` output references | Placing `limit` **after** `sorted` does not automatically shrink sort memory |
| `distinct` | Usually **`O(u)`** for tracking seen elements | If keeping all distinct values: `O(u)` | `u` depends on content and `equals/hashCode` |
| `groupingBy(key, counting())` | Usually **`O(k)`** | Map of `k` groups with counts | Only counts, does not keep individual elements |
| `groupingBy(key, toList())` | Usually **`O(k+n)`** | Map and Lists holding `n` references total | May retain all input objects |
| `groupingBy(key, toSet())` | Usually **`O(k+\sum u_i)`** | Map with distinct Set per group | Each group has its own hash table |
| `collect(toList())` | Usually **`O(m)`** | List of `m` elements | Holding references does not mean referenced objects take 0 space |
| `collect(toSet())` | Usually **`O(u)`** | Set of `u` elements | Adds hash table bucket/node overhead |
| `collect(toMap(...))` | Usually **`O(k)`** for the Map; values can be larger | Map of `k` keys | If values are Lists, add the sizes of all Lists |
| `count()`, `sum()` | Usually **`O(1)`** on a simple source | A single number | Buffers may still appear in steps **before** the terminal |
| `summarizingLong(...)` | **`O(1)`** for one statistics object | `LongSummaryStatistics` | Does not retain all input numbers |

**This table is not an implementation guarantee.** Certain execution paths may optimize already-sorted sources, sized sources, or special operation chains. Conversely, parallel streams may need extra buffers and local containers. Safe analysis must start from **required semantics**, then verify on the target JVM via profiling.

## 3. `sorted`: why does it easily require `O(n)` memory?

`Stream.sorted()` sorts elements in natural order; `sorted(comparator)` uses the supplied comparator. To emit the **smallest element first**, a general sorting algorithm must inspect the relevant elements of the source, because the very last element could be smaller than everything seen earlier.

```java
List<Integer> sorted = Stream.of(9, 1, 7, 3, 2)
        .sorted()
        .collect(Collectors.toList());

System.out.println(sorted); // [1, 2, 3, 7, 9]
```

For a finite source not already known to be sorted as required, the library typically **buffers the elements to sort** and sorts them. Therefore, intermediate state can scale with the **`n` elements reaching the `sorted` step**, i.e., `O(n)` references or boxed values depending on the Stream type/implementation.

### 3.1. Calculating bytes at the model level

Assume:

- `n = 1_000_000` `Sale` objects already exist in a List.
- A 64-bit JVM using compressed references (*compressed ordinary object pointers*) of **4 bytes** each.
- A reference array holding exactly one million elements, **excluding the `Sale` objects themselves**.

The element payload of that reference array alone is:

\[
1\,000\,000 \times 4 = 4\,000\,000\ \text{bytes}
\approx 3{,}81\ \text{MiB}
\]

That is only the **reference payload** of a hypothetical array, **not the total memory of `sorted`**. You must add array headers, alignment, spare capacity, auxiliary buffers or temporary arrays used by the implementation, newly allocated mapper objects, and the final result. If the JVM uses 8-byte references, one million references alone are roughly **7.63 MiB**.

### 3.2. `sorted().limit(10)` can still cost `O(n)`

```java
List<Sale> cheapestTen = sales.stream()
        .sorted(Comparator.comparingLong(Sale::getCents))
        .limit(10)
        .collect(Collectors.toList());
```

Suppose `sales` has one million records. `limit(10)` only requests the **first 10 results**, but to know which ones are cheapest, general sorting still needs to inspect all records. Do not infer from `limit(10)` that the upstream buffer has a maximum size of 10.

If you only need the **single smallest element**, use:

```java
Optional<Sale> cheapest = sales.stream()
        .min(Comparator.comparingLong(Sale::getCents));
```

`min` is a reduction needing very little state and does not build a sorted List. If multiple records share the same price, specify a tie-breaker (such as order ID) so the selection is deterministic under business rules.

If you need the **top-K** smallest records where `K` is tiny compared to `n`, a bounded heap of size `K` can use only **`O(K)`** extra memory and typically **`O(n log K)`** time. Java Stream’s `sorted().limit(K)` does not promise such a bounded-memory top-K algorithm.

### 3.3. The order of `filter` and `sorted` matters

```java
// Filter first: only sort matching elements.
List<Sale> activeSorted = sales.stream()
        .filter(Sale::isActive)
        .sorted(Comparator.comparingLong(Sale::getCents))
        .collect(Collectors.toList());

// Sort first: may have to buffer the entire source to sort.
List<Sale> sameContent = sales.stream()
        .sorted(Comparator.comparingLong(Sale::getCents))
        .filter(Sale::isActive)
        .collect(Collectors.toList());
```

When the predicate is side-effect-free and the comparator is valid, both pipelines can produce the same elements in price order (given appropriate stability/tie-breaker constraints). However, the first pipeline can shrink `n` for sorting from total records down to `active` records.

Do not reorder operations mechanically if the predicate depends on position/source or there are special ordering requirements; it is best to keep functions pure and verify result equivalence.

### 3.4. `sorted` on infinite or parallel sources

- On an infinite Stream without a bound, requesting the **entire sorted sequence** generally cannot complete. For example, `Stream.generate(...).sorted().findFirst()` is not a safe way to find the minimum of an infinite source.
- On a **parallel stream**, `sorted` may require extra buffers/arrays and merge phases. Complexity remains `O(n)`, yet **constants and peak memory** can increase.
- If the source already carries the `SORTED` characteristic matching the desired order, certain execution paths may avoid redundant sorting. Do not rely on that when budgeting memory for unknown sources.
- `sorted().count()` or pipelines needing only count information may be optimized without actually sorting every element. **Only analyze a sorting buffer when semantic output truly requires sorted order to be materialized**.

## 4. `distinct`: state scales with distinct value count

`distinct()` deduplicates using `Object.equals` (and hash structures generally rely on `hashCode`). For sources not guaranteed to be sorted by value, to tell whether the current element has already appeared, implementations typically maintain **a set of seen elements or keys**.

```java
List<String> skus = Arrays.asList(
        "P01", "P02", "P01", "P03", "P02");

List<String> unique = skus.stream()
        .distinct()
        .collect(Collectors.toList());

System.out.println(unique); // [P01, P02, P03]
```

If there are `n` rows but only `u` distinct SKUs, **state for duplicate detection typically scales with `u`**, not necessarily `n`. Still, in the worst case `u = n`, so `distinct` can require memory growing linearly with the entire source.

### 4.1. Estimating the hash table

With illustrative assumptions:

- `n = 1_000_000` SKU codes.
- `u = 100_000` distinct SKU codes.
- JVM with 4-byte references, structure similar to `HashMap` or `HashSet`.

A hash table typically has:

1. **A bucket array** with capacity larger than the element count due to load factor and resizing rules.
2. **Nodes/entries** for retained distinct elements.
3. References to **keys** and sometimes the key objects themselves if newly created.

As an **illustrative** example, if one node occupies roughly 32 bytes:

\[
100\,000 \times 32 \approx 3{,}2\ \text{MB}
\]

This is only the hypothetical node portion, **excluding the bucket array, String keys, or other overhead**. Actual object size depends on JVM version, alignment, collection implementation, heap settings, and data.

### 4.2. The gap between `u` and `n` determines the benefit

| Data | `n` | `u` | Interpretation |
|---|---:|---:|---|
| One million transactions across 100 SKUs | 1,000,000 | 100 | Distinct state memory can be small relative to source |
| One million transactions with unique SKUs | 1,000,000 | 1,000,000 | Seen set can approach element count |
| Ten thousand values, all identical | 10,000 | 1 | Distinct state is very small |
| Source with unknown cardinality | Unknown | Unknown | Cannot budget solely by `n` without inspecting distribution |

**Note:** if a mapper creates a new String per record before `distinct`, those temporary Strings also incur allocation/GC cost. `distinct` may only retain representatives of distinct values, yet still has to process every candidate value created.

### 4.3. `distinct` on an already `sorted` source

In a sequence **already sorted in an order consistent with duplicate identity**, equal records sit adjacent to one another. A sequential scan only needs to remember the previous element to remove duplicates. Some implementations can exploit the `SORTED` characteristic.

However, **do not claim that every `sorted(comparator).distinct()` in every JDK uses `O(1)` distinct state**. A comparator may be inconsistent with `equals`; source characteristics, ordering, and implementation strategy affect optimizations. Treat `O(u)` as the conservative assumption for general sources.

### 4.4. `distinct` and parallel processing

In a parallel stream **with encounter order**, `distinct` must keep the representative matching the **first occurrence** of a value, which can require coordination, buffering, and merging across branches. With an unordered Stream, the framework has more freedom and can use concurrent hash table techniques.

```java
Set<String> uniqueSkus = sales.parallelStream()
        .map(Sale::getSku)
        .unordered()
        .collect(Collectors.toSet());
```

If the goal is **only a Set of SKUs**, the pipeline above may **not need a separate `distinct()`**: `toSet()` already deduplicates. `unordered()` is only valid when business logic does not care about encounter order. Do not drop order if you need “the first SKU appearing in the source”.

## 5. `groupingBy`: memory depends on group count AND downstream

`Collectors.groupingBy(classifier, downstream)` creates a `Map<K, D>`. Memory cost is not merely “having `k` keys”, it also depends on the data type `D` accumulated in each group.

```java
Map<String, Long> countByRegion = sales.stream()
        .collect(Collectors.groupingBy(
                Sale::getRegion,
                Collectors.counting()));
```

With one million records across only five regions, the result only needs a Map of roughly five keys, each with a count. Structurally retained state is typically **`O(k)`**, not `O(n)`.

### 5.1. `groupingBy` with `counting`

```java
Map<String, Long> countBySku = sales.stream()
        .collect(Collectors.groupingBy(
                Sale::getSku,
                Collectors.counting()));
```

The result stores one counter per SKU. In terms of **retained memory**, this is typically `O(k)`. However, how a counting collector implements updates can produce **temporary objects** or boxing; thus **total bytes allocated during execution** can be much higher than final Map size.

If the goal is summing a numeric field:

```java
Map<String, Long> centsByRegion = sales.stream()
        .collect(Collectors.groupingBy(
                Sale::getRegion,
                Collectors.summingLong(Sale::getCents)));
```

`summingLong` keeps a small sum state per group. Note that `long` sums can overflow; choose an appropriate numeric type and overflow policy for large data.

### 5.2. `groupingBy` with `toList`

```java
Map<String, List<Sale>> salesByRegion = sales.stream()
        .collect(Collectors.groupingBy(
                Sale::getRegion,
                Collectors.toList()));
```

Suppose all `n` records belong to one of `k` groups. Then:

\[
\sum_{i=1}^{k} |\text{list}_i| = n
\]

Therefore, memory for the result includes:

- A Map with roughly `k` entries.
- Roughly `k` List objects and each List’s backing array.
- **A total of `n` references to `Sale` records** (excluding spare capacity).
- The original `Sale` objects, if they stay live because the Lists/Map reference them.

**Retained** structural memory is typically `O(k+n)`. If `n = 1_000_000` with 4-byte references, **just the references inside the Lists** are around **4 MB**, excluding other structures.

**Objects are not duplicated by default**: group Lists can hold references to the original `Sale` instances, rather than cloning a million objects. Even so, it prevents the original objects from **being garbage-collected** as long as the result stays referenced.

### 5.3. `groupingBy` with `mapping`/`toSet`

```java
Map<String, Set<String>> skusByRegion = sales.stream()
        .collect(Collectors.groupingBy(
                Sale::getRegion,
                Collectors.mapping(
                        Sale::getSku,
                        Collectors.toSet())));
```

If group `i` has `u_i` distinct SKUs, retained state is typically on the order of:

\[
O\left(k + \sum_{i=1}^{k}u_i\right)
\]

The same SKU appearing in two regions will generally have **two Set membership slots**, one per region. If the goal is a **system-wide** Set of SKUs, `map(Sale::getSku).collect(toSet())` can need fewer structures.

### 5.4. Multi-level `groupingBy`

```java
Map<String, Map<String, Long>> counts =
        sales.stream().collect(
                Collectors.groupingBy(
                        Sale::getRegion,
                        Collectors.groupingBy(
                                Sale::getSku,
                                Collectors.counting())));
```

Here there is an outer Map by region and a sub-Map by SKU for **each** region. Estimate by the number of key pairs that actually appear, not just global SKU count:

\[
O\left(k_{\text{region}} +
\#\{(\text{region},\text{sku})\text{ appearing}\}\right)
\]

If the two grouping criteria are nearly unique per element, the number of pairs can approach `n`. If many records repeat pairs, the pair count can be very small.

### 5.5. `groupingBy` does not create groups with zero elements

If a region does not appear in the source, `groupingBy` does not automatically create a key for that region. If data was `flatMap`ped from orders to line items, orders with no line items may **no longer be counted**. That is a **semantic** issue, not just memory. Do not optimize by dropping groups required for reporting.

## 6. `collect`: there is no single universal memory complexity

`collect` is a terminal operation. Memory depends on the **Collector** passed to it:

| Collector / terminal | Data meaning | Typical result/state memory |
|---|---|---|
| `toList()` / `toCollection(ArrayList::new)` | Keep all elements | `O(n)` references and collection |
| `toSet()` | Keep distinct elements | `O(u)` entries/buckets and keys |
| `toMap(key, value, merge)` | Keep one value per key | `O(k)` if values are small; more if values are complex |
| `counting()` | Element count | `O(1)` for a standalone collector |
| `summingLong(...)` | Sum of a field | `O(1)` |
| `averagingDouble(...)` | Average | `O(1)` arithmetic state |
| `summarizingLong(...)` | Count/sum/min/max/avg | `O(1)` |
| `joining(delimiter)` | One output String | At least proportional to total output length `L` |
| `groupingBy(key, downstream)` | One result per group | `O(k)` plus downstream state |
| Custom Collector | Determined by `supplier`/`accumulator`/`combiner` | Must analyze the custom state design |

### 6.1. `collect(toList)` and `toList` are not “streaming into a List” with `O(1)` RAM

```java
List<String> names = source.stream()
        .map(Person::getName)
        .collect(Collectors.toList());
```

When the terminal operation finishes, the list must hold all `n` returned name values. If the mapper creates a new String, the List also retains those Strings. `map` may process one element at a time, but **the terminal collector dictates result size**.

Java 16 added `Stream.toList()`, returning an unmodifiable List; **switching APIs does not turn an `n`-element output into `O(1)` memory**. If the caller needs a mutable List, choose an appropriate contract, e.g., `Collectors.toCollection(ArrayList::new)`.

### 6.2. `collect(toMap)`: few keys, large values

```java
Map<String, List<Sale>> bySku = sales.stream()
        .collect(Collectors.groupingBy(Sale::getSku));
```

A Map may have only a few dozen keys, yet **each value is a List holding records**. Never estimate `O(k)` purely from Map key count. For a Map whose values are nested structures, compute:

\[
B_{\text{map result}}
\;\approx\;
B_{\text{map structure}}
\;+\;\sum_{\text{key}} B_{\text{value(key)}}
\]

Replacing value Lists with counts/sums can drastically reduce retained memory, but you also **lose access to individual records** in the report. That is a business-requirement choice, not just a technical optimization.

### 6.3. `collectingAndThen`, `teeing`, and finishers

`Collectors.collectingAndThen(downstream, finisher)` typically has memory depending on `downstream`. The finisher can create a **copy** or sort the result, increasing peak memory:

```java
List<String> immutable = names.stream()
        .collect(Collectors.collectingAndThen(
                Collectors.toList(),
                list -> Collections.unmodifiableList(list)));
```

This example creates an **unmodifiable view** over the collected List without guaranteeing a new copy of the data. If the finisher uses `new ArrayList<>(list)` or `List.copyOf(list)`, extra memory may be needed while copying. `List.copyOf` was introduced in Java 10 and rejects null elements.

`Collectors.teeing` (Java 12+) runs two downstream collectors over the same data; accumulated memory depends on **both states** and the final merger, so you cannot assume `O(1)` if either branch retains all elements.

### 6.4. Custom collectors: analyze every field

Example custom accumulator:

```java
final class Stats {
    long count;
    long sum;
    long min = Long.MAX_VALUE;
    long max = Long.MIN_VALUE;
}
```

If `supplier` creates one `Stats`, `accumulator` only updates those fields, and `combiner` merges numbers, then state for **one collector** is `O(1)`. If you add `Map<String, Stats> bySku`, state grows with **SKU count `k`**. If you add `List<Sale> allSales`, state grows with **`n`**. Calling `Collector.of(...)` provides no “automatic complexity”.

## 7. Memory budget illustration with one million records

Suppose a service has:

- `n = 1_000_000` sale records in an existing `ArrayList`.
- `u = 100_000` distinct SKUs.
- `k = 500` regions/categories.
- 4-byte references on a suitably configured 64-bit JVM.
- `Sale` objects already exist, **not counting their own size in the extra-memory column**.

| Approach | Additional data that may be held | Initial estimate |
|---|---|---|
| `sales.stream().count()` | One counter or source-size optimization | Very small relative to `n` |
| `sales.stream().min(cmp)` | One extremum candidate and comparator | Very small relative to `n` |
| `sales.stream().sorted(cmp).toList()` | `O(n)` sort buffer + `O(n)` result List | Each **million references** is already ~**4 MB**, potentially multiple buffers |
| `sales.stream().map(Sale::getSku).distinct().toList()` | State for `u` values + List of `u` references | Hash state is much larger than just one `u × 4` array |
| `groupingBy(region, counting())` | Map of `k` keys, counting state | Scales primarily with `k = 500` |
| `groupingBy(region, toList())` | Map of `k` keys and `n` List references total | At least several MB just for backing arrays |
| `groupingBy(sku, summingLong(...))` | Map of roughly `u` keys and sums | Scales with `u = 100_000` |

**Do not use this table to promise exact MB numbers in production.** The table only identifies the **dominant component**. Changing JVM flags, reference size, String size, hash tables, resize counts, parallel splits, and heap limits can make real measurements differ significantly.

### 7.1. Rough calculation for references

\[
B_{\text{refs}} \approx m \times B_{\text{ref}}
\]

For example, with `m = 1_000_000`:

- `B_ref = 4` bytes: **4,000,000 bytes ≈ 3.81 MiB**.
- `B_ref = 8` bytes: **8,000,000 bytes ≈ 7.63 MiB**.

This is only the **hypothetical reference array**, excluding headers, spare capacity, hash tables, or referenced objects. Confusing **MB** (10^6 bytes) with **MiB** (2^20 bytes) can also skew estimates.

### 7.2. Preliminary formula for `groupingBy(toList)`

If every `Sale` already exists and only extra Map/List structures are counted:

\[
B \approx B_{\text{map buckets}}
 + k \cdot B_{\text{map entry}}
 + \sum_{i=1}^{k}
   \bigl(B_{\text{list object},i}
   + \text{capacity}_i \cdot B_{\text{ref}}\bigr)
\]

Since `\sum_i \text{size}_i = n` while `capacity_i` can exceed `size_i`, backing array bytes are usually **greater than or equal to** `n × B_ref`. If the result is cached long-term, it also keeps the `Sale` objects alive along with it.

## 8. Complete Java 8 example: comparing result sizes

The following program generates data itself so it can run without external files. Its goal is to **observe cardinality and result shapes**, not to replace a profiler with console numbers.

Save as `StreamMemoryEstimationDemo.java` and run with JDK 8 or higher:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.LongSummaryStatistics;
import java.util.Map;
import java.util.Optional;
import java.util.PriorityQueue;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class StreamMemoryEstimationDemo {
    static final class Sale {
        private final int id;
        private final String region;
        private final String sku;
        private final long cents;
        private final boolean active;

        Sale(int id, String region, String sku,
                long cents, boolean active) {
            this.id = id;
            this.region = region;
            this.sku = sku;
            this.cents = cents;
            this.active = active;
        }

        int getId() { return id; }
        String getRegion() { return region; }
        String getSku() { return sku; }
        long getCents() { return cents; }
        boolean isActive() { return active; }
    }

    // Find K smallest records using a K-bounded max-heap.
    // Illustrative example with k > 0 and an existing List source.
    static List<Sale> smallestK(
            List<Sale> source,
            int k,
            Comparator<Sale> ascending) {
        if (k <= 0) {
            throw new IllegalArgumentException("k must be positive");
        }
        PriorityQueue<Sale> heap =
                new PriorityQueue<>(k, ascending.reversed());

        for (Sale sale : source) {
            if (heap.size() < k) {
                heap.offer(sale);
            } else if (ascending.compare(sale, heap.peek()) < 0) {
                heap.poll();
                heap.offer(sale);
            }
        }

        List<Sale> result = new ArrayList<>(heap);
        result.sort(ascending);
        return result;
    }

    public static void main(String[] args) {
        final int n = 100_000;
        final String[] regions = {
                "BAC", "NAM", "TRUNG", "TAY"
        };
        final String[] skus = IntStream.range(0, 100)
                .mapToObj(i -> "SKU-" + i)
                .toArray(String[]::new);

        List<Sale> sales = IntStream.range(0, n)
                .mapToObj(i -> new Sale(
                        i,
                        regions[i % regions.length],
                        skus[i % skus.length],
                        (long) (i % 500) * 100L,
                        i % 5 != 0))
                .collect(Collectors.toList());

        Comparator<Sale> byCentsThenId =
                Comparator.comparingLong(Sale::getCents)
                        .thenComparingInt(Sale::getId);

        // A. sorted().limit(5): 5 results, but sort may have
        // to buffer n elements before returning.
        List<Sale> fiveSorted = sales.stream()
                .sorted(byCentsThenId)
                .limit(5)
                .collect(Collectors.toList());

        // B. Min: only needs a single extremum candidate.
        Optional<Sale> oneMin = sales.stream()
                .min(byCentsThenId);

        // C. Top-K via heap: keeps at most K candidates,
        // without sorting all n elements.
        List<Sale> fiveHeap = smallestK(
                sales, 5, byCentsThenId);

        // D. distinct: returns only 100 distinct SKUs.
        List<String> uniqueSkus = sales.stream()
                .map(Sale::getSku)
                .distinct()
                .collect(Collectors.toList());

        // E. groupingBy + counting: keeps four counts.
        Map<String, Long> counts = sales.stream()
                .collect(Collectors.groupingBy(
                        Sale::getRegion,
                        Collectors.counting()));

        // F. groupingBy + toList: keeps n record references.
        Map<String, List<Sale>> allByRegion = sales.stream()
                .collect(Collectors.groupingBy(
                        Sale::getRegion,
                        Collectors.toList()));

        // G. groupingBy + summingLong: keeps only group totals.
        Map<String, Long> totals = sales.stream()
                .collect(Collectors.groupingBy(
                        Sale::getRegion,
                        Collectors.summingLong(Sale::getCents)));

        // H. LongSummaryStatistics: one statistics object
        // instead of keeping every cents value.
        LongSummaryStatistics stats = sales.stream()
                .collect(Collectors.summarizingLong(
                        Sale::getCents));

        int keptInGroupLists = allByRegion.values().stream()
                .mapToInt(List::size)
                .sum();

        System.out.println("source size      = " + sales.size());
        System.out.println("sorted top 5     = " + fiveSorted.size());
        System.out.println("heap top 5       = " + fiveHeap.size());
        System.out.println("same top 5 IDs   = "
                + IntStream.range(0, 5).allMatch(i ->
                        fiveSorted.get(i).getId()
                                == fiveHeap.get(i).getId()));
        System.out.println("min ID           = "
                + oneMin.orElseThrow(IllegalStateException::new)
                        .getId());
        System.out.println("distinct SKUs    = " + uniqueSkus.size());
        System.out.println("region count     = " + counts.size());
        System.out.println("grouped references = "
                + keptInGroupLists);
        System.out.println("grouped totals keys = "
                + totals.size());
        System.out.println("statistics count = "
                + stats.getCount());
    }
}
```

**Key output to observe:**

```text
source size      = 100000
sorted top 5     = 5
heap top 5       = 5
same top 5 IDs   = true
min ID           = 0
distinct SKUs    = 100
region count     = 4
grouped references = 100000
grouped totals keys = 4
statistics count = 100000
```

The program does not print “sorted used X MB” because those figures must be **measured in a real runtime**. It demonstrates an important distinction: two `Map` results both have **4 keys**, yet `groupingBy(counting())` keeps four counts, while `groupingBy(toList())` keeps **100,000 record references** across Lists.

### 8.1. Analyzing `smallestK`

`PriorityQueue` in the example is configured as a **max-heap** by reversing the ascending comparator, so the **largest of the K current candidates** sits at the head of the heap. For each new record:

1. If the heap has fewer than K elements, insert it.
2. If the heap is full and the new record is **smaller** than the largest currently kept, remove the largest and insert the new record.
3. Finally, sort the remaining K candidates to return in ascending order.

Extra memory complexity is typically **`O(K)`** for the heap and result List; time is **`O(n log K + K log K)`**. Results match `sorted(...).limit(K)` if the comparator defines a consistent total order (for example, including `id` as a tie-breaker) and there are no unhandled nulls.

### 8.2. The data source also consumes memory

In this program, `sales` has 100,000 `Sale` objects created **before** the Stream operations. They and the backing reference array stay on the heap while the program runs. When a profiler reports total heap usage, not all of it is the cost of `sorted`, `distinct`, or collectors.

To separate costs, measure **allocation**, **retained size**, and **peak live set** per phase; do not look only at a single `Runtime.totalMemory() - Runtime.freeMemory()` reading at the end of the program.

## 9. Impact of pipeline order on memory

Two pipelines with the same business meaning can use very different amounts of memory when operations are reordered.

### 9.1. `filter` before `sorted`

```java
// Sort only active records.
List<Sale> a = sales.stream()
        .filter(Sale::isActive)
        .sorted(byCentsThenId)
        .collect(Collectors.toList());

// Sort all records first, then drop inactive ones.
List<Sale> b = sales.stream()
        .sorted(byCentsThenId)
        .filter(Sale::isActive)
        .collect(Collectors.toList());
```

If the predicate is pure and the comparator has a deterministic tie-breaker, results can be equivalent; however, the first pipeline puts only active records into the sorting buffer, while the second may put all records into the buffer.

### 9.2. `distinct` before `sorted`

```java
List<String> a = sales.stream()
        .map(Sale::getSku)
        .distinct()
        .sorted()
        .collect(Collectors.toList());

List<String> b = sales.stream()
        .map(Sale::getSku)
        .sorted()
        .distinct()
        .collect(Collectors.toList());
```

With `String` and natural order, both pipelines return the same ascending list of distinct SKUs. However:

- Approach A may only need to **sort `u` SKUs** after deduplication, though it still needs distinct state.
- Approach B may have to **sort `n` values** first, even though the final result has only `u` SKUs.

When `u ≪ n`, deduplicating **before** sorting is often worth considering for shrinking sort input. However, with data where equality and comparator are inconsistent, or when retaining a specific representative record is required, never reorder a pipeline without verifying semantics.

### 9.3. `groupingBy` before and after mapping

```java
// Keep Sale objects in each group's List.
Map<String, List<Sale>> detailed = sales.stream()
        .collect(Collectors.groupingBy(Sale::getRegion));

// Keep only counts per group.
Map<String, Long> summary = sales.stream()
        .collect(Collectors.groupingBy(
                Sale::getRegion,
                Collectors.counting()));
```

The `summary` approach generally keeps much less memory because it **does not need to retain references to each `Sale` in the result**. Yet if the report requires viewing individual transactions per region, a summary does not satisfy the business requirement.

## 10. Parallel streams: how do they multiply intermediate state?

When calling `parallel()`, the framework can split the source via `Spliterator`, accumulate across multiple branches, and merge results. Memory impact depends on each operation:

| Operation | Memory risk under parallelism |
|---|---|
| `sorted` | Buffers/arrays supporting sorting and merging can increase peak memory |
| `distinct` | Distinct set, combining structures, or order-preservation mechanisms can cost extra |
| `groupingBy` | Multiple intermediate Maps may coexist before the combiner merges them |
| `groupingByConcurrent` | Can reduce merging multiple Maps in some cases, yet introduces contention and concurrent structure overhead |
| `toList` | Multiple local buffers/collections may exist before assembling the final result |
| `count` / `sum` | Per-branch state is small, though task management overhead still exists |

### 10.1. Do not equate thread count with exact accumulator count

If there are `p` intermediate containers, each holding roughly `k` Map entries, the cost of **replicated state across branches** can reach `O(p × k)` for group structures in a worst-case model. However, **`p` is not necessarily equal to thread count**: the framework may create more tasks/branches than workers, and each branch normally sees only its own partition of data.

With `groupingBy(toList())`, total element references across local containers still relate to `n` before merging, while during combiner merging there may exist **temporary arrays/lists or spare capacity**, increasing peak memory.

### 10.2. Concurrent collectors do not automatically save RAM

```java
ConcurrentMap<String, Long> counts = sales.parallelStream()
        .collect(Collectors.groupingByConcurrent(
                Sale::getRegion,
                Collectors.counting()));
```

`groupingByConcurrent` can allow multiple workers to accumulate into a concurrent structure under favorable conditions, reducing some intermediate Map merging overhead. Yet if all elements share the same key, contention can be high. A concurrent map also carries its own synchronization/structural overhead. **There is no guarantee** that it uses less RAM or runs faster than `groupingBy`.

### 10.3. Shared state outside the pipeline is not an optimization

```java
Map<String, List<Sale>> shared = new HashMap<>();

sales.parallelStream().forEach(sale ->
        shared.computeIfAbsent(
                sale.getRegion(), key -> new ArrayList<>())
                .add(sale));
// WRONG: HashMap/ArrayList are unsafe when mutated concurrently by multiple workers.
```

Wanting to save “multiple local Maps” does not justify a data race. Use a collector with the right contract, or design a thread-safe concurrent mechanism and measure it in practice if truly needed.

## 11. JVM factors that make byte estimates differ from reality

### 11.1. Headers, alignment, boxing, and reference size

An object contains more than just its field data:

- Object header and alignment padding.
- References to child objects.
- Backing arrays with headers and capacity that may exceed `size()`.
- Entries/nodes of `HashMap`, `HashSet`, `TreeMap`, and other collections.
- Wrappers like `Integer` or `Long` when boxing or stored as Map values.
- Strings and their backing arrays, sometimes shared, sometimes newly created by a mapper.

For instance, `Collectors.toList()` may hold one million **references** to source objects; if preceded by `map(s -> new DTO(s))`, it also holds one million **new DTOs**. Estimating solely from `list.size()` while ignoring the object graph often severely undercounts reality.

### 11.2. Hash tables have capacity and load factors

With `distinct`, `toSet`, `toMap`, and `groupingBy`, the count `u` or `k` does not equal the exact bucket count. Hash tables resize according to load thresholds; resizing can allocate a new array before the old one is reclaimed. Peak memory can therefore be **larger than** the steady-state retained memory of the result.

### 11.3. Cumulative allocation differs from live memory

Suppose a mapper allocates temporary objects a million times without retaining them. **Total allocated bytes** can be huge, while live heap at the end of the pipeline is small. GC can reclaim short-lived objects, yet allocation and collection still consume CPU and affect latency.

Therefore, distinguish:

1. **Allocation rate / allocated bytes**: how many bytes were allocated.
2. **Peak live heap**: peak volume of live objects.
3. **Retained size**: how much remains referenced by results/sources.
4. **GC pause/throughput**: collection cost and impact on performance.

Do not optimize based solely on a single memory snapshot after the pipeline completes.

## 12. Reliable ways to measure memory

### 12.1. Choosing a practical measurement path

Common tools in the Java ecosystem:

| Tool | Useful for observing |
|---|---|
| **Java Flight Recorder (JFR)** | Allocations, GC, CPU, runtime events |
| **Java Mission Control (JMC)** | Analyzing JFR recordings |
| **VisualVM** | Heap, classes/instances, and memory usage trends |
| **Heap dump / heap analyzers** | Retained size, dominator trees, and reference retention chains |
| **JMH with GC profiler** | Microbenchmarking, allocation rates, and comparing alternatives |

When precision about environment, version, and scale matters, specify JDK, VM flags, parallelism, GC, heap limits, hardware, and input data. Do not compare a JDK with compressed references against another configuration and attribute the difference entirely to the Stream API.

### 12.2. Profiling workflow for each alternative

1. **Define correct output**: element count, order, groups, totals, min/max must be equivalent across alternatives.
2. **Keep sources/fixtures stable**: do not change distributions of `u`, `k`, or size `n` between runs.
3. **Measure each pipeline separately**: `sorted`, `distinct`, `groupingBy(counting)`, `groupingBy(toList)`, etc.; avoid retaining previous runs’ results unless intentionally measuring concurrency.
4. **Separate pre-existing sources from added memory**: know how many source objects were created prior to measurement.
5. **Measure both allocation and retained heap**: track GC, peak live set, and which objects the result keeps alive.
6. **Test sequential and parallel** if the system genuinely uses both.
7. **Repeat with varying `n`, `u`, `k`**: double `n` while keeping `k` fixed, then increase `k` to find what drives memory growth.
8. **Verify off-heap resource impact** if data comes from files, databases, or networks.

### 12.3. Why `Runtime.totalMemory - freeMemory` is only a rough indicator

`Runtime.getRuntime().totalMemory() - freeMemory()` gives a point-in-time snapshot influenced by committed heap regions, GC timing, other threads, and uncollected temporary objects. It does not fully reflect **the peak during sorting**, because you may sample after the buffer was already released.

Even calling `System.gc()` does not yield a precise measurement, may not execute as expected in the runtime, and should not be part of production algorithms. Use a proper profiler instead of a single “before/after” formula.

## 13. Choosing an approach based on the business problem

| Need | Typically suitable approach | Memory benefit |
|---|---|---|
| Need only the cheapest record | `min(comparator)` | Avoids storing a full sorted list |
| Need K smallest records, K small | Top-K with bounded heap | Keeps roughly K candidates instead of n |
| Need only distinct SKU count/set | `map(Sale::getSku).collect(toSet())` | Avoids `distinct().toList()` if only a Set is needed |
| Need order counts by region | `groupingBy(region, counting())` | Keeps one counter per key |
| Need revenue totals by region | `groupingBy(region, summingLong(...))` | Does not retain every order in each group |
| Need to inspect every order per region | `groupingBy(region, toList())` | Must accept retaining references to each order |
| Need all data sorted | `sorted(...).toList()` | Accept memory proportional to output/sort data |
| Need only count/sum/min/max/avg | `summarizingLong(...)` | A single small statistics state |
| Need multiple KPIs with complex rules | Custom collector with minimal state | Avoids unnecessary data materialization |

**The best choice is not always the fewest bytes.** If a full, ordered detail report must be exported, a large List may be unavoidable. Conversely, if only counts/totals are needed, keeping a million records in a Map of Lists only to call `size()` is avoidable waste.

## 14. Common misconceptions and mistakes

| Claim or practice | Why it is wrong | How to fix |
|---|---|---|
| “Streams are lazy so they always use `O(1)` RAM.” | `sorted`, `distinct`, and collectors keep state | Analyze both intermediate and terminal steps |
| “`sorted().limit(5)` only keeps 5 elements.” | Sorting usually must inspect and buffer much of the input | Use `min` or a top-K algorithm when appropriate |
| “`distinct` must keep all `n` elements.” | State usually scales with distinct values `u` | Measure `u` and hash table overhead |
| “A Map has 5 keys so `groupingBy` is always small.” | Downstream `toList` can hold `n` references | Inspect the value structure inside each group |
| “`collect` always costs `O(n)`.” | `counting` and `summingLong` have small state | Classify by the chosen Collector |
| “`toSet` is always cheaper than `toList`.” | Hash tables have bucket/node overhead | Compare by `u`, `n`, and semantic requirements |
| “`parallel()` reduces peak heap.” | Multiple buffers/containers can coexist | Benchmark and profile parallel execution separately |
| “`groupingByConcurrent` is always faster and uses less RAM.” | Concurrent maps have contention and overhead | Compare against `groupingBy` under real key distribution |
| “List size is enough to compute exact bytes.” | Headers, capacity, object graphs, and boxing matter | Use a model and verify with a profiler |
| “You can replace a List of transactions with a count without affecting the API.” | Loses detail data | Preserve the business contract |
| “Measuring heap after `collect` is enough.” | Sort buffers and temporary objects may already be dead | Measure allocations and peak live heap |
| “Reading `Files.lines` and collecting closes the file automatically.” | Terminal operations do not replace `close` | Use `try-with-resources` |

## 15. Practice exercises with answers

### Exercise 1. Memory of `sorted` and `limit`

**Problem:** One million objects enter `sorted(comparator).limit(10).toList()`. Can you conclude that `sorted`'s state holds only ten elements?

**Answer:** No. On an unsorted source, sorting generally needs to inspect and buffer all relevant input before knowing the first ten elements. The final result has 10 elements, yet **peak state** can scale with one million. If only top-10 is needed, consider a bounded heap algorithm of size 10.

### Exercise 2. `distinct` and cardinality

**Problem:** There are 500,000 rows containing only 200 distinct SKUs. Should `distinct` state be modeled around 500,000 or 200?

**Answer:** With standard hash-table techniques, state tracks roughly **`u = 200`** distinct elements, aside from other buffers/overhead. Do not treat 200 as a byte count, since each entry also involves nodes, buckets, and keys. If every row has a different SKU, `u` approaches `n`.

### Exercise 3. Choosing the right downstream collector

**Problem:** One million orders belong to 4 regions. The report only needs the **order count per region**. Should you pick `groupingBy(region, toList())` or `groupingBy(region, counting())`?

**Answer:** `groupingBy(region, counting())`. It keeps a Map of four groups with counts instead of keeping one million references in Lists, assuming business logic does not need individual orders back.

### Exercise 4. Rough reference array calculation

**Problem:** Assume each reference takes 4 bytes. A List needs a backing array of exactly 2,000,000 references, excluding headers/spare capacity. How much do the references alone occupy?

**Answer:**

\[
2\,000\,000 \times 4
= 8\,000\,000\ \text{bytes}
\approx 7{,}63\ \text{MiB}
\]

This is not the total heap of the List or of the objects the List references.

### Exercise 5. Sort first or deduplicate first?

**Problem:** You have one million SKU strings with only 100 distinct SKUs. If you need a **distinct, ascending** list of SKUs, which order should you consider?

**Answer:** `stream.distinct().sorted().toList()` usually feeds only about 100 distinct values into `sorted`, rather than sorting one million strings before deduplicating. Apply when SKU equality and ordering match intended semantics.

### Exercise 6. Parallel grouping and Map count

**Problem:** Why can `parallelStream().collect(groupingBy(region, counting()))` have higher peak memory than the sequential version?

**Answer:** The framework may allocate **multiple intermediate Maps and accumulator containers** across branches before merging; these states can coexist during processing. Container count is not simply equal to thread count. `groupingByConcurrent` uses a different strategy but does not guarantee less RAM.

### Exercise 7. Retained heap vs. temporary objects

**Problem:** A pipeline creates many DTOs in `map`, then only counts them with `count()`. At the end, result memory is tiny. Can you claim the pipeline did not allocate many objects?

**Answer:** No. It **may** have allocated many temporary DTOs, or it may have been optimized to skip executing the mapper when the count is already known. You must measure actual allocations; small retained size does not prove small total allocations.

### Exercise 8. Reviewing a keyed report

**Problem:** A service only needs total revenue per SKU, yet currently uses `groupingBy(sku, toList())` and iterates each List to sum amounts. How can memory be reduced?

**Answer:** Use `groupingBy(sku, summingLong(Sale::getCents))` if `long` arithmetic fits and transaction details are unnecessary. If overflow detection is required, design a collector summing with `Math.addExact` or use a larger numeric type. The resulting Map will hold one sum per SKU instead of Lists of transactions.

### Exercise 9. Distinguishing MB and MiB

**Problem:** Why is 4,000,000 bytes not equal to 4 MiB?

**Answer:** `1 MB = 1,000,000 bytes`, whereas `1 MiB = 1,048,576 bytes`. Therefore 4,000,000 bytes equals **4 MB** but only about **3.81 MiB**. Always specify units when comparing heap budgets.

## 16. Checklist before optimizing Stream memory

1. **Have you defined which memory to measure?** Total heap, added memory, peak during execution, or retained result?
2. **Do you know `n`, `u`, and `k`?** Datasets with high duplication behave differently from mostly unique keys.
3. **Is `sorted` present?** Is the entire sorted result really needed, or only min/top-K?
4. **Is `distinct` present?** Does the output need an ordered List or just a Set of distinct values?
5. **Which downstream is `groupingBy` using?** `counting`, `summingLong`, `toList`, and `toSet` have very different memory footprints.
6. **How many elements does `collect` retain?** If `n` results must exist, lazy `map` alone cannot give `O(1)` RAM.
7. **Can data be reduced before stateful operations?** Filter properly before `sorted`; consider `distinct` before `sorted`.
8. **Are temporary objects or boxing increasing?** Measure allocations and GC, not just retained heap.
9. **Is it parallel?** Check buffers, local Maps, contention, and combiner cost.
10. **Have you measured under the real JVM configuration?** Reference size, headers, load factors, and GC differ.
11. **Are I/O sources closed?** Heap cost and file descriptors are separate concerns.
12. **Do all optimizations preserve exact correctness?** Never drop records, required ordering, or queryability required by the business.

**Conclusion:** When estimating Java Stream memory, do not assign one single complexity to the whole pipeline. **`sorted` typically needs state proportional to `n`**, **`distinct` typically scales with `u`**, **`groupingBy` scales with `k` plus downstream state**, and **`collect` depends entirely on the Collector and result size**. Distinguish intermediate buffers, retained data, source objects, temporary allocations, and peak live heap; then validate your model by profiling on the real JVM and real data. This approach enables grounded optimization without trading off correctness or business requirements around order, detail, and resources.
