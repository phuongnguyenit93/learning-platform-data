# Selecting Global Top N and Grouped Top N

> **Chapter:** Practical Data Processing Patterns  
> **Module:** JAVA_STREAM_API  
> **Focus:** Use `filter`, `sorted`, `limit`, and `collect` to select top-ranked records by business criteria. Distinguish **dataset-wide top N** from **per-group top N**, design tie-breaking order, and upgrade to a bounded-heap collector when data grows large.

## Learning Objectives

After this lesson, you will be able to:

1. Precisely define a "top N" requirement: selection scope, filter conditions, ranking order, tie-breaking, value of N, and tie-handling policy.
2. Write a global top-N pipeline with `filter(...).sorted(...).limit(n).toList()`.
3. Pair `Collectors.groupingBy` with `collectingAndThen` to select top N **separately per group** without cutting off other groups.
4. Distinguish exact **at most N rows** top N from top N **including all boundary ties**.
5. Analyze full sorting cost versus bounded size-N heap cost: time, memory, and group-count impact.
6. Write a custom top-N collector backed by `PriorityQueue` with contract-compliant `supplier`, `accumulator`, `combiner`, and `finisher`.
7. Test empty sources, N = 0, negative N, N exceeding element count, duplicates, comparators, and null values.
8. Cross-check sequential/parallel outputs, using reference data and invariants to catch wrong ordering, dropped elements, or broken tie rules.
9. Choose appropriately among Streams, custom collectors, specialized top-K algorithms, and data-source limit queries.

Examples use Java 17+, with `record` and `Stream.toList()`. `Comparator`, `groupingBy`, `PriorityQueue`, and `Collector.of` overloads have existed since Java 8. Standalone snippets assume previously introduced types and data exist in the same class/method; complete programs compile independently.

---

## 1. Real-World Problem: Top N of What, by Which Criteria?

Suppose a system processes orders across multiple categories. Users ask for:

- **Global top 3:** the three highest-value paid orders across **all categories**.
- **Per-group top 2:** for **each category**, at most the two highest-value paid orders.

Both requests may share the same data and comparator yet **do not yield the same output structure**.

~~~text
All paid orders
         |
         +------------------------------+
         |                              |
         v                              v
   GLOBAL TOP 3                   GROUPED TOP 2
         |                              |
    Sort all                      Group by category
         |                              |
    Take 3 rows                 BOOK: sort + take 2
         |                      PEN : sort + take 2
         v                      BAG : sort + take 2
   List<Order>                          |
                                        v
                              Map<String,List<Order>>
~~~

A common mistake is calling `limit(2)` **before** `groupingBy` and assuming every group still gets two records. Once a global limit trims the **entire** Stream to two elements, groups absent from those two elements are never seen.

### 1.1. Running Sample Data

~~~java
import java.util.List;

record Order(
        String id,
        String category,
        long totalCents,
        boolean paid
) {}

List<Order> orders = List.of(
        new Order("O-01", "BOOK", 1_000, true),
        new Order("O-02", "PEN",    600, true),
        new Order("O-03", "BOOK", 2_100, true),
        new Order("O-04", "BOOK", 1_800, false),
        new Order("O-05", "PEN",  2_100, true),
        new Order("O-06", "BAG",    900, true),
        new Order("O-07", "BOOK", 2_100, true),
        new Order("O-08", "PEN",    100, false),
        new Order("O-09", "BAG",    500, true),
        new Order("O-10", "BAG",  2_100, true)
);
~~~

Every row has a unique `id`, non-null `category`, monetary amount in **cents** as a `long`, and `paid` indicating eligibility for ranking. In this lesson, **only paid orders** participate in both top-N queries.

| ID | Category | Cents | Paid? |
|---|---|---:|---|
| O-01 | BOOK | 1,000 | Yes |
| O-02 | PEN | 600 | Yes |
| O-03 | BOOK | 2,100 | Yes |
| O-04 | BOOK | 1,800 | No |
| O-05 | PEN | 2,100 | Yes |
| O-06 | BAG | 900 | Yes |
| O-07 | BOOK | 2,100 | Yes |
| O-08 | PEN | 100 | No |
| O-09 | BAG | 500 | Yes |
| O-10 | BAG | 2,100 | Yes |

Expected output:

~~~text
Global top 3, tie-broken by ID:
  [O-03, O-05, O-07]

Per-category top 2:
  BOOK -> [O-03, O-07]
  PEN  -> [O-05, O-02]
  BAG  -> [O-10, O-06]
~~~

Four orders tie at `2_100`. If we select strictly three rows globally, we need a deterministic rule deciding which comes first; we use ascending `id` for tie-breaking.

---

## 2. Define Ordering with a Comparator, Not Guesswork

Ranking is a **comparison contract**, not "the Stream somehow knows which order is better".

In this example, the criteria are:

1. `totalCents` **descending**: higher-value orders come first.
2. On equal cents, `id` **ascending**: lexicographically smaller IDs come first.

~~~java
import java.util.Comparator;

Comparator<Order> BEST_FIRST =
        Comparator.comparingLong(Order::totalCents)
                  .reversed()
                  .thenComparing(Order::id);
~~~

Result of `BEST_FIRST.compare(a,b)`:

- Less than `0`: `a` ranks **before** `b`.
- Equal to `0`: the comparator treats both records as tied on the chosen fields.
- Greater than `0`: `a` ranks **after** `b`.

Because this dataset guarantees unique IDs, the comparator totally orders all distinct records even when amounts match. In production systems, validate unique IDs or append a final tie-breaker such as an immutable sequence/record number when you need a **total, reproducible** order across duplicate IDs.

### 2.1. Never Use Subtraction to Compare Large Numbers

~~~java
// AVOID: can overflow long and break the comparator.
// Comparator<Order> broken =
//         (a, b) -> (int) (b.totalCents() - a.totalCents());
~~~

Two hazards: `long` subtraction can overflow, and casting to `int` truncates high-order bits. Use `Comparator.comparingLong` or `Long.compare`.

~~~java
Comparator<Order> alsoCorrect =
        (a, b) -> {
            int byMoney = Long.compare(
                    b.totalCents(), a.totalCents()
            );
            return byMoney != 0
                    ? byMoney
                    : a.id().compareTo(b.id());
        };
~~~

Both approaches handle the full `long` range safely **without** subtracting two amounts to determine order.

### 2.2. Consistency of Units and Criteria

When `totalCents` is integer cents, exact `long` comparison is clear. Do not convert to `double` to rank money and accept undefined rounding errors.

If the problem ranks by *net revenue after refunds*, *purchase count*, *rating score*, or *creation time*, **compute the meaningful ranking field first** before choosing a comparator. Never pick an arbitrary convenient field that does not match the business rule.

---

## 3. Global Top N with sorted().limit()

The most readable approach is:

~~~java
import java.util.List;

int n = 3;

List<Order> globalTop = orders.stream()
        .filter(Order::paid)
        .sorted(BEST_FIRST)
        .limit(n)
        .toList();

System.out.println(globalTop.stream().map(Order::id).toList());
// [O-03, O-05, O-07]
~~~

Pipeline walkthrough:

1. `filter(Order::paid)` drops unpaid orders.
2. `sorted(BEST_FIRST)` sorts **all** eligible orders by amount descending, then ID ascending.
3. `limit(n)` retains only the **first n elements of the sorted result**.
4. `toList()` returns a list in result order; on Java 16+, this List is structurally unmodifiable via the List API.

`sorted` is a **stateful intermediate operation**. The source is ordered and the output deterministic, yet general-purpose `sorted` must inspect the input set to establish global order; placing `limit` afterward does not make the Stream inspect only three records.

### 3.1. Limiting Before Sorting Solves a Different Problem

~~~java
List<Order> wrongTop = orders.stream()
        .filter(Order::paid)
        .limit(3)
        .sorted(BEST_FIRST)
        .toList();

System.out.println(wrongTop.stream().map(Order::id).toList());
// [O-03, O-01, O-02] — only sorts the first three paid orders in the source
~~~

Calling `limit(3)` first drops `O-05`, `O-07`, and `O-10` even though they have higher values. The query silently changed to **"sort the first three orders"**, not **"the three highest-value orders globally"**.

### 3.2. Where Should Filtering Go?

~~~java
// Matches intent: rank only paid orders.
orders.stream()
        .filter(Order::paid)
        .sorted(BEST_FIRST)
        .limit(3)
        .toList();
~~~

If changed to:

~~~java
// WRONG if you want the 3 highest-value PAID orders:
orders.stream()
        .sorted(BEST_FIRST)
        .limit(3)
        .filter(Order::paid)
        .toList();
~~~

An unpaid order can occupy a top-3 slot **before** being filtered out, leaving fewer than three valid orders or omitting lower-ranked eligible orders. `filter` must normally precede `sorted` when it defines eligibility for ranking.

### 3.3. N Equal to 0 or Larger Than Element Count

~~~java
List<Order> none = orders.stream()
        .filter(Order::paid)
        .sorted(BEST_FIRST)
        .limit(0)
        .toList();

System.out.println(none.isEmpty()); // true

List<Order> allPaid = orders.stream()
        .filter(Order::paid)
        .sorted(BEST_FIRST)
        .limit(100)
        .toList();

// There are 8 paid orders in the sample data.
System.out.println(allPaid.size()); // 8
~~~

`limit` returns at most N elements and **never fabricates dummy elements** when N exceeds the input count. `limit(n)` throws `IllegalArgumentException` if N is negative. In business APIs, validate N at the input boundary for clear error messages.

---

## 4. Grouped Top N: groupingBy + collectingAndThen

Top N per category requires **grouping first**, then sorting and limiting **inside each group**.

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

int n = 2;

Map<String, List<Order>> topByCategory = orders.stream()
        .filter(Order::paid)
        .collect(Collectors.groupingBy(
                Order::category,
                Collectors.collectingAndThen(
                        Collectors.toList(),
                        list -> list.stream()
                                .sorted(BEST_FIRST)
                                .limit(n)
                                .toList()
                )
        ));

System.out.println(
        topByCategory.get("BOOK")
                .stream().map(Order::id).toList()
); // [O-03, O-07]

System.out.println(
        topByCategory.get("PEN")
                .stream().map(Order::id).toList()
); // [O-05, O-02]

System.out.println(
        topByCategory.get("BAG")
                .stream().map(Order::id).toList()
); // [O-10, O-06]
~~~

Processing model:

~~~text
orders.stream()
  |
  +-- filter(Order::paid)
  |
  +-- groupingBy(Order::category,
          collectingAndThen(
             toList(),                   // collect per category
             list -> list.stream()
                         .sorted(...)
                         .limit(2)
                         .toList()        // finalize each group separately
          )
      )
  |
  v
  Map<String, List<Order>>
      BOOK -> [O-03, O-07]
      PEN  -> [O-05, O-02]
      BAG  -> [O-10, O-06]
~~~

**Where `collectingAndThen` sits determines the finishing scope.** Because this collector is the downstream of `groupingBy`, each group receives an **intermediate list**, and the finisher selects top N independently for that group.

### 4.1. Pitfall: limit Before groupingBy

~~~java
// WRONG for "top 2 per category":
Map<String, List<Order>> partial = orders.stream()
        .filter(Order::paid)
        .sorted(BEST_FIRST)
        .limit(2)
        .collect(Collectors.groupingBy(Order::category));
~~~

When `limit(2)` runs **before** `groupingBy`, the entire Stream shrinks to two orders: `O-03` and `O-05`. The Map lacks `BAG`, and each group holds at most one order in this example. That computes **global top 2 then grouped**, not **top 2 per group**.

### 4.2. Outer Map Has No Guaranteed Key Order

Default `groupingBy` makes no guarantee about Map implementation type or iteration order. Never compare `Map.toString()` output directly as a fixed oracle.

If you want **category names ascending**, supply a map factory:

~~~java
import java.util.TreeMap;

Map<String, List<Order>> sortedKeys = orders.stream()
        .filter(Order::paid)
        .collect(Collectors.groupingBy(
                Order::category,
                TreeMap::new,
                Collectors.collectingAndThen(
                        Collectors.toList(),
                        list -> list.stream()
                                .sorted(BEST_FIRST)
                                .limit(2)
                                .toList()
                )
        ));

System.out.println(sortedKeys.keySet());
// [BAG, BOOK, PEN]
~~~

`TreeMap` orders **group keys**, while lists inside each group are ordered by `BEST_FIRST`; these are **two independent orderings**.

### 4.3. Do Not Expose Mutable Lists from Intermediate Steps

Downstream `Collectors.toList()` builds an intermediate list with no immutability guarantee. However, `list.stream().sorted(...).limit(n).toList()` returns a final List that is structurally unmodifiable on Java 16+.

The outer Map from `groupingBy` is not guaranteed unmodifiable. To publish an outer Map that cannot be structurally modified:

~~~java
Map<String, List<Order>> readOnly = Map.copyOf(topByCategory);
~~~

`Map.copyOf` is a **shallow** structural copy and does not deep-copy `Order` objects. Here `Order` is a record of primitives and `String`, so fields used for ranking are already immutable.

---

## 5. How Do Global Top N and Grouped Top N Compare?

With the exact same comparator, these two queries answer different questions.

| Property | Global Top N | Grouped Top N |
|---|---|---|
| Ranking input | All eligible records | Each group of eligible records |
| Result type | `List<Order>` | `Map<Key, List<Order>>` |
| Maximum rows | N | Up to N **per group** |
| Can small groups disappear? | Yes, if they lack globally high candidates | Only if the group has no eligible records or all were filtered out |
| `limit` placement | After Stream-wide `sorted` | Inside the group's downstream collector |
| Map ordering needed? | No Map | Choose a map factory if key order matters |
| When to use? | Overall leaderboards, system-wide top products | Top products per store, top transactions per customer, top logs per service |

For example, with 100 groups and top 3 per group, the result can contain up to **300 rows**, not just 3 rows total.

**Do not optimize the wrong problem:** trimming the Stream to N global rows before grouping can be very fast, yet it fails to preserve top N for groups absent from those N rows.

---

## 6. Ties: Strictly N Rows or Everyone Tied at the Boundary Score?

In the sample data, four paid orders share `2_100` cents:

~~~text
O-03 : 2100
O-05 : 2100
O-07 : 2100
O-10 : 2100
~~~

Two common policies:

- **Strict top N (at most N records):** use tie-breakers to establish a total order. Top 3 is `[O-03, O-05, O-07]`.
- **Top N with all boundary ties:** if the Nth item has `2_100`, include all other items with exact `2_100`. Top 3 **with ties** returns **four** records.

These are not interchangeable: a leaderboard widget may strictly cap at N rows, while an awards/competition API may include more than N due to ties.

### 6.1. Fixed Top N: Add a Meaningful Tie-Breaker

~~~java
Comparator<Order> bestFirst =
        Comparator.comparingLong(Order::totalCents)
                  .reversed()
                  .thenComparing(Order::id);

List<Order> top3 = orders.stream()
        .filter(Order::paid)
        .sorted(bestFirst)
        .limit(3)
        .toList();
~~~

Tie-breaking by ID here is an **example business rule**. If real ranking favors earlier transaction time, review score, or a version field, adjust the tie-breaker accordingly. Never rely on encounter order or thread timing as an implicit rule when reproducible results are required.

### 6.2. Top N *Including Ties* at the Boundary

A clear approach for finite sources:

~~~java
import java.util.List;

static List<Order> topWithTies(
        List<Order> source, int n,
        Comparator<Order> bestFirst) {

    if (n < 0) {
        throw new IllegalArgumentException("n must be >= 0");
    }
    if (n == 0) {
        return List.of();
    }

    List<Order> ranked = source.stream()
            .sorted(bestFirst)
            .toList();

    if (ranked.size() <= n) {
        return ranked;
    }

    // Condition: comparator orders totalCents descending
    // as primary criterion, like BEST_FIRST here.
    long threshold = ranked.get(n - 1).totalCents();

    return ranked.stream()
            .takeWhile(order -> order.totalCents() >= threshold)
            .toList();
}
~~~

Usage:

~~~java
List<Order> paid = orders.stream()
        .filter(Order::paid)
        .toList();

List<Order> top3WithTies = topWithTies(
        paid, 3, BEST_FIRST
);

System.out.println(top3WithTies.stream().map(Order::id).toList());
// [O-03, O-05, O-07, O-10]
~~~

`takeWhile` works correctly here **because the list is already sorted descending by amount as its primary key**. If the comparator prioritizes another criterion or the list is unsorted, you cannot apply a `totalCents` threshold this way.

This helper returns **all rows sharing the Nth item's cent value**, not only rows the full comparator considers equal (since the comparator also checks ID). Specify clearly whether "tied" means **equal on primary score** or **equal on all comparison keys**.

### 6.3. Grouped Top N with Ties

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, List<Order>> withTiesByCategory =
        orders.stream()
                .filter(Order::paid)
                .collect(Collectors.groupingBy(
                        Order::category,
                        Collectors.collectingAndThen(
                                Collectors.toList(),
                                group -> topWithTies(
                                        group, 1, BEST_FIRST
                                )
                        )
                ));

System.out.println(
        withTiesByCategory.get("BOOK")
                .stream().map(Order::id).toList()
); // [O-03, O-07]
~~~

In BOOK, two orders tie at 2,100 cents; "top 1 with ties" returns both. When a group has fewer than N items, the entire group is returned without padding fake records.

---

## 7. Handle N and Input Policies Before Writing the Pipeline

N is an API parameter, not an incidental detail. Specify:

| Case | Policy to Document Clearly |
|---|---|
| `n < 0` | Reject with `IllegalArgumentException` |
| `n == 0` | Return an empty list; for grouped top N, decide whether empty group keys appear |
| `n > eligible count` | Return all eligible items in proper order |
| Very large N | Consider API caps and memory/CPU costs |
| Null group key | Reject or map to an explicit "unknown" key per business rules |
| Missing ranking value | Filter, fail, or define explicit null ordering |
| Duplicate IDs when ID is the tie-breaker | Flag invalid data or add a deterministic secondary field |
| Equal primary scores | Cap strictly at N via tie-breaker or expand per tie policy |

A reusable validation helper:

~~~java
static void requireNonNegative(int n) {
    if (n < 0) {
        throw new IllegalArgumentException(
                "Top N limit must be non-negative: " + n
        );
    }
}
~~~

If an API accepts `long n` to pass into `limit`, validate as `long`. With heap structures, `PriorityQueue` capacity is an `int`, so enforce appropriate size bounds.

### 7.1. Empty Sources and Groups

~~~java
List<Order> empty = List.of();

List<Order> global = empty.stream()
        .sorted(BEST_FIRST)
        .limit(5)
        .toList();

Map<String, List<Order>> grouped = empty.stream()
        .collect(Collectors.groupingBy(
                Order::category,
                Collectors.toList()
        ));

System.out.println(global);       // []
System.out.println(grouped.isEmpty()); // true
~~~

`groupingBy` creates keys only for groups present in the source. It does not synthesize entries for every configured category that currently has zero orders.

If you **always** need zero-order categories included, obtain the category set from a reference source and populate empty lists explicitly. Never infer missing categories from the order Stream alone.

---

## 8. Cost of Global sorted().limit(N)

Given `m` eligible items after filtering:

~~~java
orders.stream()
        .filter(Order::paid)
        .sorted(BEST_FIRST)
        .limit(n)
        .toList();
~~~

This is **easy to read and easy to prove right**. General comparison-based sorting typically costs around **O(m log m)** time and may buffer O(m) elements during sorting.

`limit(n)` after `sorted` does not mean the runtime only inspects the first n elements of the source. An element at the very end of the source can still be the **largest**, so global top N cannot be known by reading an arbitrary n-element prefix.

For small or medium datasets, this is usually a sensible starting point. When `m` is huge and `n` is tiny, you can optimize using a **bounded size-n heap**.

### 8.1. Group Then Sort and Limit per Group

With `g` groups of sizes `m_1, m_2, ..., m_g`, summing to `m = Σ m_i`:

~~~text
groupingBy + collect(toList()) + sort each group:
    grouping time:   approx. O(m) average with hash Map
    per-group sort:  Σ O(m_i log m_i)
    group memory:    O(m)
~~~

If groups are roughly balanced, sorting each group individually can perform fewer comparisons than one global sort. Yet it still buffers all input elements across groups before limiting, which can consume substantial memory when `m` is large.

If you only need the N best records per group, maintain **one size-N heap per group key** instead of buffering full group lists.

---

## 9. Bounded Size-N Heap: Concept Before Writing a Collector

`PriorityQueue` exposes the head element according to a comparator. To maintain the **N best records**, we want `peek()` to return the **worst record among the N currently kept**.

If comparator `BEST_FIRST` puts **better records first** (negative compare result), the heap must use **`BEST_FIRST.reversed()`**, i.e., **worst first**.

~~~text
Goal: top 3 by amount descending + ID ascending

Heap currently holds: [2100/O-03, 1500/O-11, 1000/O-01]
peek() = 1000/O-01    (currently worst in top 3)

Candidate 1800/O-12:
  1800 is better than 1000 -> drop 1000, add 1800

Candidate 500/O-13:
  500 is not better than peek -> ignore
~~~

Algorithm:

1. If N = 0, keep no elements.
2. If the heap holds fewer than N items, add the candidate.
3. If the heap already holds N items, compare the candidate against `peek()` (currently worst).
4. If the candidate ranks better, remove `peek()` and insert the candidate.
5. At the end, extract all items from the heap and **sort them with `BEST_FIRST`** to return the display list in proper order.

`PriorityQueue` **does not iterate in sorted order**. Only the head `peek()` is guaranteed per the comparator. Thus `new ArrayList<>(heap)` **cannot** be treated as an already sorted top-N list.

### 9.1. Complexity

With `m` candidates and small positive N:

- Each insertion/replacement on a size-N heap takes **O(log N)**.
- Scanning m elements takes roughly **O(m log N)** worst-case.
- The heap stores only **O(min(m, N))** elements.
- Finalizing sorts at most N elements in **O(N log N)**.

As N approaches m, this advantage shrinks compared to full sorting. Heaps also carry comparator, allocation, and implementation complexity; benchmark on real data.

---

## 10. Complete Program: Top N Using a Heap and Collector.of

The standalone snippet below uses `Collector.of` to encapsulate bounded-N accumulation. It works with both sequential and parallel Streams because each branch gets its own accumulator.

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.PriorityQueue;
import java.util.stream.Collector;

public class TopNHeapDemo {

    record Order(String id, String category, long totalCents) {}

    // Better records sort earlier.
    static final Comparator<Order> BEST_FIRST =
            Comparator.comparingLong(Order::totalCents)
                      .reversed()
                      .thenComparing(Order::id);

    static final class TopNAccumulator {
        private final int limit;
        private final PriorityQueue<Order> worstFirst;

        TopNAccumulator(int limit) {
            if (limit < 0) {
                throw new IllegalArgumentException("limit < 0");
            }
            this.limit = limit;

            // peek(): the WORST record among those currently retained.
            this.worstFirst =
                    new PriorityQueue<>(BEST_FIRST.reversed());
        }

        void accept(Order candidate) {
            if (limit == 0) {
                return;
            }

            if (worstFirst.size() < limit) {
                worstFirst.offer(candidate);
                return;
            }

            Order worst = worstFirst.peek();

            // compare < 0 means candidate ranks before worst.
            if (BEST_FIRST.compare(candidate, worst) < 0) {
                worstFirst.poll();
                worstFirst.offer(candidate);
            }
        }

        TopNAccumulator merge(TopNAccumulator other) {
            if (this.limit != other.limit) {
                throw new IllegalArgumentException("Differing limits");
            }

            // Merge best candidates from the other branch.
            // Do not retain references to other's heap.
            for (Order candidate : other.worstFirst) {
                accept(candidate);
            }
            return this;
        }

        List<Order> finish() {
            ArrayList<Order> result =
                    new ArrayList<>(worstFirst);
            result.sort(BEST_FIRST);
            return List.copyOf(result);
        }
    }

    static Collector<Order, TopNAccumulator, List<Order>>
    topNCollector(int n) {
        if (n < 0) {
            throw new IllegalArgumentException("n must be >= 0");
        }

        return Collector.of(
                () -> new TopNAccumulator(n),
                TopNAccumulator::accept,
                TopNAccumulator::merge,
                TopNAccumulator::finish
        );
    }

    public static void main(String[] args) {
        List<Order> data = List.of(
                new Order("A", "BOOK", 1_000),
                new Order("B", "PEN", 2_000),
                new Order("C", "BOOK", 2_000),
                new Order("D", "PEN", 500),
                new Order("E", "BAG", 3_000),
                new Order("F", "BOOK", 100)
        );

        List<Order> global = data.parallelStream()
                .collect(topNCollector(3));

        System.out.println(
                global.stream().map(Order::id).toList()
        ); // [E, B, C]
    }
}
~~~

Explanation:

- `supplier` creates a **fresh `TopNAccumulator`** per branch; never share a static `PriorityQueue`.
- `accumulator` retains only the best N candidates observed within that partition.
- `combiner` `merge` folds candidates from the right container into the left container, preserving the best N of the union.
- `finisher` turns the heap into a structurally unmodifiable list in **proper display order**.
- This collector does **not** declare `CONCURRENT`, because `PriorityQueue` is not thread-safe; the Stream uses independent containers and merges them by contract.

### 10.1. Why Merging Two Top-N Heaps Is Correct

Suppose `A` and `B` are two independent partitions. If an element `x` of `A` **is not in `topN(A)`**, then `A` already contains at least N elements ranking strictly ahead of `x` under a total-order comparator. When combined with `B`, those elements still exist. Hence `x` can never suddenly enter `topN(A ∪ B)`.

Therefore:

~~~text
topN(A ∪ B)
    = topN( topN(A) ∪ topN(B) )
~~~

Crucial conditions:

1. Use the **exact same comparator and N** everywhere.
2. The comparator must be stable and free of mutable state.
3. For **strictly N rows**, tie-breaking must select deterministic winners; if distinct objects can tie completely, define representative rules explicitly.
4. Never mutate source elements or ranking fields during collection.

Because "merge candidates and take top N" has the empty set as identity and is associative with respect to ranked results, the collector can combine intermediate states across arbitrary split trees.

### 10.2. N Equal to 0

When `n == 0`, the accumulator inserts nothing into the heap and `finish()` returns an empty list. This works safely without a zero-capacity `PriorityQueue` error because the example constructs the queue with the comparator constructor instead of initial capacity `n`.

### 10.3. Do Not Rely on Heap Iterator Order

~~~java
// WRONG if you want a sorted list:
// return new ArrayList<>(worstFirst);

// CORRECT:
ArrayList<Order> ranked = new ArrayList<>(worstFirst);
ranked.sort(BEST_FIRST);
return List.copyOf(ranked);
~~~

Without the final sort, the list may hold the right top-N elements in an arbitrary order violating the display contract.

---

## 11. Reusing topNCollector for Grouped Top N

The beauty of packaging logic into a collector is plugging it straight into `groupingBy`'s downstream:

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

// Uses Order and topNCollector from TopNHeapDemo.
Map<String, List<Order>> topTwoByCategory = data.parallelStream()
        .collect(Collectors.groupingBy(
                Order::category,
                topNCollector(2)
        ));

System.out.println(
        topTwoByCategory.get("BOOK")
                .stream().map(Order::id).toList()
); // [C, A]

System.out.println(
        topTwoByCategory.get("PEN")
                .stream().map(Order::id).toList()
); // [B, D]

System.out.println(
        topTwoByCategory.get("BAG")
                .stream().map(Order::id).toList()
); // [E]
~~~

Place this snippet **inside `TopNHeapDemo.main`** after `data` is declared. In the heap demo data, BOOK has `C=2,000`, `A=1,000`, `F=100`, so top 2 is `[C, A]`.

In a parallel pipeline, `groupingBy` can create intermediate Maps and merge them by key. For each key, `TopNAccumulator.merge` combines that group's candidates. Never use one **global** heap across all keys when the goal is top N **per group**.

### 11.1. Memory for Grouped Top N

With `g` groups each retaining at most `n` records, the heaps hold at most **O(g·n)** references (or fewer for small groups). Add Map overhead and intermediate containers during parallel execution.

When `n` is small and groups are huge, this saves substantial memory compared to buffering a full `List<Order>` per group. However, if `g` itself is huge (approaching total record count), per-group Maps and heaps still add significant overhead.

### 11.2. Do Not Falsely Mark CONCURRENT

`PriorityQueue` is not safe for concurrent `offer`/`poll` calls on **one instance**. Our top-N collector is a standard non-`CONCURRENT` collector.

That does **not** prevent using `parallelStream()`: the Stream accumulates into separate containers and combines them via the combiner. To build a genuinely concurrent collector, redesign both container and concurrency contract—never just slap on a `Characteristic`.

---

## 12. Comparing Implementations

| Solution | Readability | Typical Extra Memory | Best When |
|---|---|---|---|
| Global `sorted().limit(n)` | Very high | Up to O(m) for sort | Small/medium data, code clarity first |
| `groupingBy(..., collectingAndThen(toList(), sort + limit))` | High | O(m) for all groups | Moderate grouped top-N tasks |
| `collect(topNCollector(n))` | Medium | O(min(m,n)) for heap | Small N, many candidates, memory control needed |
| `groupingBy(..., topNCollector(n))` | Medium | O(g·n) + Map | Small N per group, large groups |
| Top N pushed down to data query | DB/source dependent | Avoids shipping excess rows into Java | Huge sources with indexes, sort/limit, or window functions |
| Other selection algorithms (quickselect, specialized top-K) | Higher complexity | Algorithm dependent | Specialized optimization after profiling |

In this table, `m` is eligible record count and `g` is group count. Complexity expressions are **typical models**, not runtime guarantees across every JDK or `Spliterator` implementation.

**An O(m log n) algorithm is not automatically faster in practice.** Complex comparators, per-group heap allocation, GC pressure, and parallel overhead all require proper benchmarking.

---

## 13. Top N Groups by Aggregated Score vs. Top N Records per Group

Two distinct problems:

1. **Top N records per group:** for each category, pick the N highest-value Orders.
2. **Top N groups by total revenue:** sum revenue per category, then pick the N categories with the highest totals.

The second problem requires **grouping/reduction before ranking groups**, not `topNCollector<Order>` per group.

~~~java
import java.math.BigInteger;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, BigInteger> totalByCategory = orders.stream()
        .filter(Order::paid)
        .collect(Collectors.groupingBy(
                Order::category,
                Collectors.mapping(
                        order -> BigInteger.valueOf(order.totalCents()),
                        Collectors.reducing(
                                BigInteger.ZERO,
                                BigInteger::add
                        )
                )
        ));

Comparator<Map.Entry<String, BigInteger>> groupRanking =
        Map.Entry.<String, BigInteger>comparingByValue(
                        Comparator.reverseOrder()
                )
                .thenComparing(Map.Entry::getKey);

List<Map.Entry<String, BigInteger>> bestGroups =
        totalByCategory.entrySet().stream()
                .sorted(groupRanking)
                .limit(2)
                .toList();

System.out.println(
        bestGroups.stream()
                .map(Map.Entry::getKey)
                .toList()
); // [BOOK, BAG]
~~~

From the opening sample data:

~~~text
BOOK: 1000 + 2100 + 2100 = 5200
BAG :  900 +  500 + 2100 = 3500
PEN :  600 + 2100        = 2700
~~~

Because `BigInteger::add` performs exact integer addition, there is no `long` overflow during aggregation. If you use `Collectors.summingLong`, verify whether totals can exceed `long`.

**Do not confuse them:** top 2 groups by total revenue returns `[BOOK, BAG]`; it does **not** return top 2 orders inside each group.

### 13.1. Using teeing or summarizing When Multiple Metrics Are Needed

When group selection depends on **total revenue, order count, and average**, use a downstream collector capturing all needed metrics. Once each group has its summary object, sort groups according to your **group priority rules**.

This combines `groupingBy`, `reducing`, multi-stage collectors, and summation precision in the Java Stream API.

---

## 14. Nulls, Duplicates, and Immutability

### 14.1. Null category or ID

~~~java
// groupingBy(Order::category) requires classifiers to return non-null keys
// in standard usage.
//
// Comparator.thenComparing(Order::id) also needs an explicit policy
// for null IDs.
~~~

In real datasets, decide whether to:

- **Reject** orders missing a category or ID.
- **Filter out** incomplete records, if the report contract permits.
- **Map to a sentinel key** for unknown categories, kept distinct from valid category names.
- **Order nulls explicitly** via null-friendly comparators when nulls are allowed in rankings.

Avoid arbitrary sentinel strings that could collide with real keys. `groupingBy` forbids null keys by default; `List.copyOf`/`Map.copyOf` also forbid nulls.

### 14.2. distinct() Is Not Equivalent to "Once per ID"

~~~java
record Order(String id, String category, long totalCents, boolean paid) {}
~~~

Two Orders sharing `id` with different `totalCents` are **two distinct records under `equals`**. `stream.distinct()` does not deduplicate by ID alone.

If a source contains multiple versions of the same ID, **deduplicate by ID using version/timestamp rules** before ranking—for example, `Collectors.toMap` with a merge function choosing the latest record. Handle duplicate IDs by explicit policy rather than letting parallel thread scheduling pick one arbitrarily.

### 14.3. Compute Top N Over a Snapshot

If mutable `Order` objects change `totalCents` mid-comparison, the comparator can return inconsistent results, corrupting sort order or evicting wrong items from a heap.

Here `record Order` holds `String`, `long`, and `boolean`, so ranking state is immutable. For mutable database or cache entities, snapshot immutable DTOs before collecting, or ensure no concurrent mutations occur.

`List.copyOf` freezes only **list structure**, not mutable entity contents inside.

---

## 15. Parallel Streams: Correctness First, Speed Second

Top N places notable constraints on parallel execution:

- `sorted` is stateful and requires **global** ordering.
- `limit` on an **ORDERED** Stream must return the exact sorted prefix.
- `groupingBy` may build multiple intermediate Maps and merge them by key.
- A heap collector parallelizes cleanly with a valid `combiner`, though it still allocates and merges multiple heaps.
- `PriorityQueue` not being thread-safe is fine as long as each container is mutated exclusively by one branch and the collector is **not** marked `CONCURRENT`.

~~~java
List<Order> sequential = orders.stream()
        .filter(Order::paid)
        .sorted(BEST_FIRST)
        .limit(3)
        .toList();

List<Order> parallel = orders.parallelStream()
        .filter(Order::paid)
        .sorted(BEST_FIRST)
        .limit(3)
        .toList();

if (!sequential.equals(parallel)) {
    throw new AssertionError("Global top order/result mismatch");
}
~~~

With an ordered List and a total-order comparator, both must return the exact same top 3. Still, **comparing sequential against parallel alone is insufficient**: if the comparator violates business rules, both can fail together. Keep an independent expected dataset.

### 15.1. Can You Drop Encounter Order with unordered()?

For **top N in an explicit ranking order**, `unordered()` is usually unnecessary. `sorted(BEST_FIRST)` establishes a new result order; dropping encounter order **beforehand** can change tie outcomes if the comparator does not break all ties.

If you need **top N with fixed tie-breaking**, write a tie-breaking comparator instead of hoping `unordered()` speeds things up without altering output.

### 15.2. Grouped Top N and Map.equals

~~~java
Map<String, List<Order>> seq = orders.stream()
        .filter(Order::paid)
        .collect(Collectors.groupingBy(
                Order::category,
                Collectors.collectingAndThen(
                        Collectors.toList(),
                        xs -> xs.stream().sorted(BEST_FIRST)
                                .limit(2).toList()
                )
        ));

Map<String, List<Order>> par = orders.parallelStream()
        .filter(Order::paid)
        .collect(Collectors.groupingBy(
                Order::category,
                Collectors.collectingAndThen(
                        Collectors.toList(),
                        xs -> xs.stream().sorted(BEST_FIRST)
                                .limit(2).toList()
                )
        ));

if (!seq.equals(par)) {
    throw new AssertionError("Grouped top mismatch");
}
~~~

`Map.equals` compares mappings by content, independent of Map key iteration order. `List.equals` still verifies element order **within each group**—matching the sorted top-N contract.

---

## 16. Verifying Top N with Invariants

Alongside hand-computed expected outputs, check these invariants:

| Invariant | Check |
|---|---|
| Size | `result.size() == min(n, eligible record count)` for strict top N |
| Eligibility | Every Order in the result satisfies `paid` and all filter rules |
| Order | No adjacent pair `a, b` satisfies `BEST_FIRST.compare(a, b) > 0` |
| Optimality | No excluded eligible record ranks ahead of the last item in top N |
| No loss/duplication | Output contains exact selected source items respecting identity/multiplicity |
| Correct grouping | Every item in `map.get(category)` belongs to that category |
| Per-group cap | Each List holds at most N items, independent of other groups |
| N = 0 | Global top empty; grouped top follows documented key policy |
| Ties | Result obeys strict N or boundary-ties policy |
| Parallelism | Matches sequential/oracle on an immutable snapshot |

### 16.1. Order Verification Helper

~~~java
import java.util.Comparator;
import java.util.List;

static <T> void requireSorted(
        List<T> result, Comparator<? super T> bestFirst) {

    for (int i = 1; i < result.size(); i++) {
        if (bestFirst.compare(
                result.get(i - 1), result.get(i)
        ) > 0) {
            throw new AssertionError(
                    "Wrong order at index " + i
            );
        }
    }
}
~~~

Call it as:

~~~java
requireSorted(globalTop, BEST_FIRST);
for (List<Order> group : topByCategory.values()) {
    requireSorted(group, BEST_FIRST);
}
~~~

This helper verifies output ordering, **not that the right elements were selected**. A List of three low-value items can still be sorted; pair it with an oracle and optimality checks.

### 16.2. Verification Against Hand-Computed Results

On the sample data, we know upfront:

~~~text
Global top 3: [O-03, O-05, O-07]
Top 2 BOOK:   [O-03, O-07]
Top 2 PEN:    [O-05, O-02]
Top 2 BAG:    [O-10, O-06]
~~~

Check exact IDs at each position to catch both wrong tie-breaking and wrong ranking criteria. For Maps, fetch by key instead of trusting iteration order.

### 16.3. Comparing Against an Independent Oracle

For a new heap algorithm, `sorted().limit()` serves as a clean **reference oracle** because it is simple and transparent. Still, validate the comparator independently against business requirements; sharing a buggy comparator across both produces false passes.

Beyond comparing heap vs. sort, add hand-verified cases, boundary values near `long` extremes, and tie cases to prove business correctness.

---

## 17. Complete Program: Global and Grouped Top N

This template separates N validation, global top N, and per-group top N into clean functions. It compiles standalone on Java 17+.

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class TopNStreamDemo {

    record Order(
            String id,
            String category,
            long totalCents,
            boolean paid
    ) {}

    static final Comparator<Order> BEST_FIRST =
            Comparator.comparingLong(Order::totalCents)
                      .reversed()
                      .thenComparing(Order::id);

    static void requireN(int n) {
        if (n < 0) {
            throw new IllegalArgumentException("N must be >= 0");
        }
    }

    static List<Order> globalTop(List<Order> orders, int n) {
        requireN(n);

        return orders.stream()
                .filter(Order::paid)
                .sorted(BEST_FIRST)
                .limit(n)
                .toList();
    }

    static Map<String, List<Order>> topByCategory(
            List<Order> orders, int n) {
        requireN(n);

        Map<String, List<Order>> result = orders.stream()
                .filter(Order::paid)
                .collect(Collectors.groupingBy(
                        Order::category,
                        Collectors.collectingAndThen(
                                Collectors.toList(),
                                group -> group.stream()
                                        .sorted(BEST_FIRST)
                                        .limit(n)
                                        .toList()
                        )
                ));

        // Returned Map and Lists are structurally unmodifiable.
        return Map.copyOf(result);
    }

    static List<String> ids(List<Order> selected) {
        return selected.stream().map(Order::id).toList();
    }

    static void requireIds(
            List<Order> selected, String... expected) {
        List<String> actual = ids(selected);
        List<String> target = List.of(expected);

        if (!actual.equals(target)) {
            throw new AssertionError(
                    "Expected " + target + ", got " + actual
            );
        }
    }

    public static void main(String[] args) {
        List<Order> data = List.of(
                new Order("O-01", "BOOK", 1_000, true),
                new Order("O-02", "PEN",    600, true),
                new Order("O-03", "BOOK", 2_100, true),
                new Order("O-04", "BOOK", 1_800, false),
                new Order("O-05", "PEN",  2_100, true),
                new Order("O-06", "BAG",    900, true),
                new Order("O-07", "BOOK", 2_100, true),
                new Order("O-08", "PEN",    100, false),
                new Order("O-09", "BAG",    500, true),
                new Order("O-10", "BAG",  2_100, true)
        );

        List<Order> global = globalTop(data, 3);
        requireIds(global, "O-03", "O-05", "O-07");

        Map<String, List<Order>> grouped =
                topByCategory(data, 2);
        requireIds(grouped.get("BOOK"), "O-03", "O-07");
        requireIds(grouped.get("PEN"), "O-05", "O-02");
        requireIds(grouped.get("BAG"), "O-10", "O-06");

        if (!globalTop(data, 0).isEmpty()) {
            throw new AssertionError("N=0 must be empty");
        }

        if (globalTop(data, 100).size() != 8) {
            throw new AssertionError("Wrong paid order count");
        }

        if (!globalTop(List.of(), 5).isEmpty()
                || !topByCategory(List.of(), 5).isEmpty()) {
            throw new AssertionError("Empty source must stay empty");
        }

        System.out.println("GLOBAL " + ids(global));
        System.out.println("BOOK   " + ids(grouped.get("BOOK")));
        System.out.println("PEN    " + ids(grouped.get("PEN")));
        System.out.println("BAG    " + ids(grouped.get("BAG")));
        System.out.println("TOP_N_OK");
    }
}
~~~

Expected output:

~~~text
GLOBAL [O-03, O-05, O-07]
BOOK   [O-03, O-07]
PEN    [O-05, O-02]
BAG    [O-10, O-06]
TOP_N_OK
~~~

**Example limitations:** This program assumes trusted data, unique IDs, and non-null categories. In apps ingesting data from APIs or databases, validate/normalize fields and define source update policies before publishing indexes or top-N lists.

---

## 18. Common Mistakes and How to Find Counterexamples

| Mistake | Quick Counterexample | Fix |
|---|---|---|
| `limit(N)` before `sorted` | `[2,9,7]`, N=1: returns 2 instead of 9 | Sort all candidates before limiting |
| `limit(N)` before `groupingBy` | Global 2 rows belong to BOOK/PEN, BAG disappears | Place limit inside the group's downstream |
| `filter(paid)` after `limit` | Unpaid order claims a slot then gets dropped | Filter eligibility before ranking |
| Missing tie-breaker | Multiple orders tie at the cutoff score | Define secondary rule and unique keys |
| Comparator using subtraction | Values near `Long.MAX_VALUE`/`MIN_VALUE` | Use `comparingLong` or `Long.compare` |
| Using `distinct()` to deduplicate IDs | Two records with same ID and different amounts survive | Deduplicate by key/version with `toMap` per policy |
| Forgetting to sort heap output | `PriorityQueue.iterator` does not return priority order | Sort with `BEST_FIRST` in finisher |
| Heap using best-first comparator | `peek()` is the best item; wrong item evicted | Use `BEST_FIRST.reversed()` so `peek()` is worst |
| Combiner returns left heap only | Loses strong candidates from right partition | Merge top N from both branches |
| Sharing one `PriorityQueue` across threads | Race conditions and corrupted state | Fresh supplier per branch, non-CONCURRENT collector |
| Picking strict N when ties are required | 4 rows tie at top score, top3 drops one | Use Nth score threshold, expand results |
| Relying on `HashMap` iteration order | Groups print in varying order | Use `TreeMap` or sort key list |
| Negative or out-of-bounds N | `limit(-1)` throws; bad heap capacity | Validate N at boundaries |
| Mutating source mid-stream | Scores or categories shift mid-calculation | Use immutable snapshots or synchronize source |
| Comparing sequential vs. parallel with no oracle | Both share the same broken comparator | Add hand-verified results and invariants |

---

## 19. Testing with Large Datasets and Parallel Execution

Beyond hand-calculated cases, test patterns likely to expose heap and combiner bugs:

1. **One massive group:** small N, many candidates, forcing frequent `peek()` evictions.
2. **Many tiny groups:** group sizes smaller than N, ensuring all group items are kept.
3. **All scores equal:** tie-breaking comparator must select exact prioritized IDs.
4. **Negative/positive scores and extreme `long` values:** comparator must not overflow.
5. **Reversed input:** highest-value record sits at the end, never prematurely truncated.
6. **N = 0, N = 1, N = size, N > size**.
7. **Empty source and groups with zero paid records**.
8. **Repeated `parallelStream` runs:** output matches oracle regardless of work splitting.
9. **Duplicate or null group keys and IDs:** handled per policy, never silently returning partial results.
10. **Skewed group distributions:** one huge category and one tiny category to stress unbalanced merges.

### 19.1. Cross-Checking Heap Against sorted.limit on Identical Data

In `TopNHeapDemo` (section 10), add this to `main`:

~~~java
List<Order> bySorting = data.stream()
        .sorted(BEST_FIRST)
        .limit(3)
        .toList();

List<Order> byHeap = data.parallelStream()
        .collect(topNCollector(3));

if (!bySorting.equals(byHeap)) {
    throw new AssertionError(
            "Heap differs from sorted oracle"
    );
}
~~~

This cross-checks two structurally different algorithms. Since both share the **same comparator**, still test the comparator independently against small hand-verified cases so both do not share a ranking bug.

### 19.2. Verifying Grouped Top N via Invariants

~~~java
// Uses Map<String,List<Order>> topByCategory from section 4.
for (Map.Entry<String, List<Order>> entry
        : topByCategory.entrySet()) {

    String group = entry.getKey();
    List<Order> ranked = entry.getValue();

    if (ranked.size() > 2) {
        throw new AssertionError("Exceeded N in group " + group);
    }

    for (Order order : ranked) {
        if (!order.paid() || !group.equals(order.category())) {
            throw new AssertionError(
                    "Record does not belong to group " + group
            );
        }
    }

    requireSorted(ranked, BEST_FIRST);
}
~~~

This checks size bounds, record validity, and internal order. To prove **optimality**, also assert that no excluded eligible record in the same group ranks ahead of the last selected item.

### 19.3. Benchmarking the Right Things

Measure using JMH or controlled benchmarks, varying:

| Variable | Values to Test |
|---|---|
| Total candidates m | Small, medium, very large |
| N | 0, 1, 10, 100, close to m |
| Group count g | Few large groups, many small groups |
| Paid ratio | Low and high |
| Score distribution | Mostly unique vs. heavy ties |
| Source type | `ArrayList`, hard-to-split `Spliterator` sources |
| Mode | Sequential and parallel |
| Algorithm | Full sort vs. bounded heap |
| Cost | Runtime, memory allocation, GC, peak memory |

Exclude dataset generation time from the timed region when comparing **top-N selection**. Also never print a single `System.nanoTime()` delta and declare a winner: JIT warm-up, CPU load, GC, and result consumption all skew naive timings.

---

## 20. Foundation Exercises (With Answers)

### Exercise 1. Global Top 2

**Prompt:** Given scores `[40, 90, 60, 90]`, select the two highest scores in descending order.

**Answer:**

~~~java
import java.util.Comparator;
import java.util.List;

List<Integer> top = List.of(40, 90, 60, 90)
        .stream()
        .sorted(Comparator.reverseOrder())
        .limit(2)
        .toList();

System.out.println(top); // [90, 90]
~~~

`90` appears twice because the problem asks for top **record/position values**, not distinct values.

### Exercise 2. Wrong limit Placement

**Prompt:** Given `[40, 90, 60]` and N=1, what does `limit(1).sorted(reverseOrder())` return?

**Answer:** `[40]`, because only the first element is sorted. Global top 1 is `[90]`. `sorted` must precede `limit`.

### Exercise 3. Grouped Top N

**Prompt:** BOOK orders score `[5, 9, 1]`; PEN orders score `[2, 7, 6]`. What is top 2 per group?

**Answer:** BOOK `[9, 5]`, PEN `[7, 6]`. Each group is sorted and limited **independently**; never limit the whole source before grouping.

### Exercise 4. N Equal to 0

**Prompt:** What do `limit(0)` and the lesson's heap collector return?

**Answer:** Both return an empty list. With `groupingBy`, if records are still routed by key before finishing, group keys may exist mapped to empty lists; define the API's expected policy.

### Exercise 5. N Greater Than Element Count

**Prompt:** A group has only three records, and N=10. How many records must be returned?

**Answer:** Return the three records sorted by comparator—do not pad seven dummy records.

### Exercise 6. Overflow-Safe Comparator

**Prompt:** Why is `(int)(b.totalCents() - a.totalCents())` dangerous?

**Answer:** `long` subtraction can overflow, and narrowing to `int` drops bits. Use `Comparator.comparingLong(Order::totalCents).reversed()` or `Long.compare(b.totalCents(), a.totalCents())`.

### Exercise 7. Top N and distinct

**Prompt:** Two transactions share amount `100` but have different IDs. Should you call `distinct()` to keep only one?

**Answer:** No. If the requirement is top N **transactions**, two rows with different IDs are two separate transactions. `distinct()` compares objects via `equals`, rather than "deduplicating equal scores".

### Exercise 8. Boundary Ties

**Prompt:** Scores `[100, 90, 90, 70]`, N=2. How do strict top N and top N with ties differ?

**Answer:** Strict two rows returns `[100, 90]` per tie-breaking; including boundary ties at 90 returns `[100, 90, 90]`, i.e., three rows.

---

## 21. Intermediate Exercises (With Answers)

### Exercise 9. Choosing a Revenue Comparator

**Prompt:** `Order` has `long totalCents` and unique `String id`. Write a comparator for cents descending, ID ascending.

**Answer:**

~~~java
Comparator<Order> bestFirst =
        Comparator.comparingLong(Order::totalCents)
                  .reversed()
                  .thenComparing(Order::id);
~~~

The ID tie-breaker prevents orders with equal cents from being selected based on accidental input order when top N keeps only part of a tie.

### Exercise 10. Why Does a Heap Need Worst-First?

**Prompt:** A size-3 heap currently holds scores 20, 15, and 10. When score 17 arrives, which score must be evicted?

**Answer:** Evict 10 and insert 17. `peek()` should expose 10, the **worst** element in the current top 3. Therefore the heap comparator must be the **reverse** of best-first display order.

### Exercise 11. Can Merging Two Heaps Lose a Good Candidate?

**Prompt:** Partition A has `[100, 90, 10]`, partition B has `[95, 80, 5]`, N=2. What is top 2 per partition and top 2 after merging?

**Answer:** Top A is `[100, 90]`, top B is `[95, 80]`. Merging these candidates and taking top 2 yields `[100, 95]`. Values 10 and 5 can never reach global top 2 because their own partitions already contain two better values.

### Exercise 12. Top 1 per Group Is Not Global Top 1

**Prompt:** BOOK has order 100, PEN has order 90, BAG has order 80. How many records does grouped top 1 return?

**Answer:** Three records across three lists. Global top 1 returns only order 100. Never place `limit(1)` before `groupingBy`.

### Exercise 13. Top Groups by Total Revenue

**Prompt:** BOOK has two orders of 100 and 200; PEN has one order of 250. Rank groups by **total** revenue, not largest single order.

**Answer:** BOOK ranks first with total 300 > PEN's 250, even though PEN's largest individual order (250) beats each BOOK order individually. Use `groupingBy` + `reducing/summing` first, then `sorted` on Map entries.

### Exercise 14. Top 2 with Ties

**Prompt:** Sorted descending by score, the list is `[120/A, 110/B, 110/C, 90/D]`. N=2, including all boundary ties.

**Answer:** Returns `[120/A, 110/B, 110/C]`, because the second-place boundary score is 110. Strict N returns `[120/A, 110/B]` per tie-breaking.

### Exercise 15. Why Not Use PriorityQueue.iterator for Output?

**Answer:** `PriorityQueue` guarantees only that `peek()` is the head per comparator; its iterator is not guaranteed to yield elements in sorted order. Materialize a list and call `sort(BEST_FIRST)` in the finisher.

### Exercise 16. Can a Parallel Collector Share One Static Heap?

**Answer:** No. `PriorityQueue` is not thread-safe; sharing one heap across threads causes races and corrupts top N. `Collector.of` needs a supplier creating fresh containers, an accumulator adding to each branch's container, a combiner merging partitions, and must not falsely declare `CONCURRENT`.

### Exercise 17. Testing Grouped Top N

**Prompt:** A test suite only checks `result.get("BOOK").size() <= 2`. Is that enough to prove top 2 is correct?

**Answer:** No. The list could contain two low-value orders or wrong-category orders while still passing the size check. Verify category, paid status, comparator ordering, and that no better candidate was skipped; compare against hand-computed data or the `sorted().limit()` oracle.

### Exercise 18. Mutable Data Scenario

**Prompt:** An entity inside the heap has its `totalCents` mutated mid-run. Why are results unreliable?

**Answer:** The priority key organizing the heap changed without updating heap positions; the comparator ceased to be stable during execution. Use immutable snapshots/DTOs or guard source updates before ranking.

---

## 22. Production Top-N Implementation Checklist

Before shipping a top-N API, answer:

1. **Global top N or grouped top N?** Define the limiting scope clearly.
2. **What is one record unit?** A transaction, user, product version, or aggregated group?
3. **Eligibility conditions?** Payment status, effective dates, access permissions, error filtering.
4. **Does the comparator break ties completely?** Define ordering when primary criteria tie; avoid overflow and mutable state.
5. **Tie policy?** Strict cap at N or expandable for boundary ties?
6. **N=0, negative N, N exceeding size?** Are errors and results defined?
7. **Should empty groups appear?** `groupingBy` does not synthesize missing keys from the source.
8. **Where are nulls/duplicate IDs handled?** Avoid surprise exceptions or silent drops without policy.
9. **Does the source have encounter order?** Must original order break ties when comparators tie?
10. **Need a snapshot?** Could data mutate during collection or after returning results?
11. **Scale of m, g, N?** Choose full sort, bounded heap, or query pushdown.
12. **Do you have an oracle?** At least one small hand-verified dataset plus invariant checks.
13. **Is a parallel collector contract-compliant?** Fresh supplier, lossless combiner, sorted finisher.
14. **Benchmark before optimizing?** Measure runtime, memory, GC, and grouping/sorting cost on realistic data.

~~~text
Top-N requirement
      |
      v
Global or per-group?
      |                         |
   GLOBAL                   PER-GROUP
      |                         |
filter + sorted + limit      groupingBy(
      |                         downstream topN
      |                         )
      +------------+------------+
                   |
                   v
           Data too large?
             |          |
             | No       | Yes, small N
             v          v
         Keep sort   Consider size-N heap
             \          /
              \        /
            Verify vs oracle
                   |
              Try parallel
                   |
            Real benchmark
                   |
                Publish
~~~

---

## Summary

**Global top N** selects the top N elements after filtering and ranking across the **entire source**; **grouped top N** partitions data by key and limits N **within each group**. The clean baseline to learn and verify is `filter().sorted(comparator).limit(n)` globally, and `groupingBy(classifier, collectingAndThen(toList(), list -> list.stream().sorted(comparator).limit(n).toList()))` per group.

For large sources and small N, a `PriorityQueue` holding the **best N candidates** saves memory. When writing a custom collector, ensure `peek()` exposes the **worst currently retained candidate**, the combiner merges candidates from both partitions properly, and the finisher sorts results before publishing. Such optimizations only matter once **ranking keys, tie-breakers, tie policies, filter conditions, and group scopes** are firmly established.

**Key takeaway:** Never "optimize" by moving `limit(N)` before `sorted` or `groupingBy` when the requirement is still global top N or per-group top N. Verify result semantics first using an oracle and boundary cases, and only then benchmark bounded heaps or parallel Streams in the Java Stream API.
