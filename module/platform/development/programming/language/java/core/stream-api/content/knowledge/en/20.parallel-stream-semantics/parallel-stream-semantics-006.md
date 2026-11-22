# Costs of sorted, distinct, skip, limit, takeWhile, and dropWhile

> **Chapter:** Parallel Processing Semantics  
> **Module:** JAVA_STREAM_API  
> **Focus:** Identifying the costs of *stateful* intermediate operations and prefix-selecting operations in the Java Stream API, especially when switching a pipeline from `stream()` to `parallelStream()` or calling `parallel()`. Finding ways to optimize **without breaking the result contract**.

## Learning objectives

After this lesson, you will be able to:

1. Explain why `sorted`, `distinct`, `skip`, `limit`, `takeWhile`, and `dropWhile` cannot be evaluated like an independent per-element `map`.
2. Distinguish **stateful intermediate operations**, **short-circuiting intermediate operations**, and **encounter order**.
3. Predict results on ordered Streams and understand the freedom of result selection on unordered Streams.
4. Identify costs involving buffering, cross-partition coordination, element traversal, and synchronization in parallel execution.
5. Understand the difference between `filter` and `takeWhile`/`dropWhile`, including on unsorted data.
6. Propose ordering of `filter`, `distinct`, `sorted`, and `limit` per requirements while avoiding reorderings that change results.
7. Use `unordered()`, `SIZED`, `SUBSIZED`, and well-splittable sources appropriately.
8. Write correctness test suites and real performance measurements before deciding to use a parallel stream.

Examples use Java 17+. `sorted`, `distinct`, `skip`, `limit`, and `parallelStream` have existed since Java 8; `takeWhile` and `dropWhile` were added in **Java 9**; `Stream.toList()` was added in Java 16. Examples apply generally to `Stream<T>` and, where explicitly noted, primitive Streams such as `IntStream`/`LongStream`.

---

## 1. The problem: parallel processing is not just splitting elements evenly

A pipeline with only stateless transformations is usually easy to partition:

~~~java
import java.util.List;

List<Integer> source = List.of(2, 3, 4, 5, 6);

List<Integer> result = source.parallelStream()
        .filter(n -> n % 2 == 0)
        .map(n -> n * n)
        .toList();

System.out.println(result); // [4, 16, 36]
~~~

`filter` and `map` on independent elements do not need to know the outcome of **every other element** to decide whether to keep or transform the current element.

In contrast:

- `sorted` must establish a **global order**, not just sort each partition.
- `distinct` must know whether an element has appeared elsewhere.
- `skip`/`limit` must determine which elements fall into the **skipped region** or **kept region**.
- `takeWhile`/`dropWhile` on an ordered Stream depend on the first **prefix** boundary matching or failing the predicate.

~~~text
ORDERED source: [a, b, c, d, e, f, g, h]
                     |
                 parallel()
                     |
           +---------+---------+
           |                   |
        [a,b,c,d]           [e,f,g,h]
           |                   |
     process one branch  process other branch
           \                   /
            +--- coordination -+
                     |
                     v
              contract result
~~~

Merely splitting the source is not enough to complete operations with global constraints. They may require temporary memory, data exchange, a merge pass, or ordering coordination across branches.

**There is no rule that "parallel is always faster."** Coordination costs can outweigh multi-CPU gains, especially on small sources, I/O sources, or pipelines with multiple stateful operations.

## 2. Three concepts to distinguish before measuring

### 2.1. Stateful vs. stateless

| Kind | Examples | Depends on other elements? |
|---|---|---|
| Stateless intermediate | `map`, `filter` | Typically no, if lambdas obey stateless/non-interfering rules |
| Stateful intermediate | `sorted`, `distinct` | Yes: global order or previously seen values |
| Stateful slicing | `skip`, `limit` | Yes: position/bounds of the result slice |
| Stateful prefix | `takeWhile`, `dropWhile` | Yes: prefix boundary determined by predicate |

Stateful operations are still **intermediate operations**: calling them only configures the pipeline; a terminal operation such as `toList`, `count`, `findFirst`, or `sum` is what triggers source consumption.

### 2.2. Short-circuiting does not mean free

Two operations in this group are specified as **short-circuiting intermediate operations**:

- `limit(n)` can terminate the pipeline once `n` elements have been taken.
- `takeWhile(P)` can terminate once the required prefix has been determined.

`skip(n)` and `dropWhile(P)` are not general short-circuiting operations: after dropping the prefix, downstream may still require all remaining elements. `sorted()` must determine order before emitting sorted elements; `distinct()` must track seen values.

A downstream `findFirst` or `limit` can stop the **entire pipeline** in specific scenarios, but you should not infer that every upstream operation will inspect fewer elements or avoid buffering.

### 2.3. Encounter order is not thread execution order

A `List`, array, or `IntStream.range(...)` source has a defined encounter order. An ordinary `HashSet` source **does not guarantee** an encounter order.

~~~java
import java.util.List;

List<String> values = List.of("A", "B", "C", "D");

values.parallelStream().forEach(System.out::println);
// Print order is not guaranteed.

List<String> collected = values.parallelStream().toList();
System.out.println(collected); // [A, B, C, D]
~~~

`toList()` preserves encounter order when the Stream is ordered, even though prior operations may execute concurrently. Parallel `forEach` does not guarantee execution order; `forEachOrdered` is for cases where the terminal action must run in encounter order.

### 2.4. Ordered vs. unordered: a question about the result contract

`unordered()` drops the encounter order constraint at the Stream level; it **does not actively shuffle** data. If the result can be *any* valid subset without needing the "first" element, relaxing the order constraint can open optimization opportunities. If business logic requires "the first 10 elements," "skip the first 10 elements," or "the leading log entries up to an error," do not drop order.

---

## 3. Overview cost table

The table below describes **tendencies**, not time/memory guarantees of a specific JDK.

| Operation | Core semantics | Typical cost on sequential source | Challenge on parallel ordered |
|---|---|---|---|
| `sorted()` | Sorts all elements by natural order | May need to hold `n` elements; sorting is typically O(n log n) | Merging sorted parts; needs global order and memory |
| `distinct()` | Keeps each value once by `equals` | Tracks seen values; memory grows with unique value count | Coordinating deduplication **and** keeping first occurrence |
| `skip(n)` | Drops the first `n` elements in encounter order | Traverses skipped prefix unless source supports efficient skipping | Pinpointing exact boundary across partitions |
| `limit(n)` | Takes at most the first `n` elements | Can stop early once enough values are collected | Selecting the true prefix and coordinating/canceling work |
| `takeWhile(P)` | Takes the longest prefix satisfying `P` | Can stop at the first non-matching element | Detecting the first global boundary across order |
| `dropWhile(P)` | Drops the longest prefix satisfying `P` | Scans to the first non-matching element, then forwards the rest | Identifying the dropped prefix across multiple partitions |

Two important notes:

1. **Memory cost is not always O(n)** across all implementations; `distinct` may use hash structures, `sorted` may choose an appropriate algorithm/partitioning, and `skip/limit` may leverage size metadata and `Spliterator`. The table describes causes, not internal algorithms.
2. Processing cost depends on **operation position in the pipeline**, source traits, `SIZED`/`SUBSIZED`, result size, and the terminal operation. Do not judge solely from the method name.

## 4. sorted: the cost of global ordering

`sorted()` (or `sorted(comparator)`) is a **stateful intermediate operation**. To ensure the first emitted element is truly the smallest by the comparator, a general sort typically must observe all of a finite input before emitting the complete sorted output.

~~~java
import java.util.List;

List<Integer> values = List.of(9, 1, 7, 3, 5);

List<Integer> sorted = values.parallelStream()
        .sorted()
        .toList();

System.out.println(sorted); // [1, 3, 5, 7, 9]
~~~

No particular sorting algorithm is guaranteed. For general sources and data, comparison sorting typically takes **O(n log n)** comparisons and additional memory; parallel execution may sort chunks and coordinate/merge them to establish global order.

### 4.1. sorted is stable when the Stream has encounter order

On an ordered `Stream<T>`, `sorted` guarantees a **stable sort**: elements considered equal by the comparator preserve their original relative order. On an unordered Stream, stability is not guaranteed.

~~~java
import java.util.Comparator;
import java.util.List;

record Row(String code, int priority) {}

List<Row> rows = List.of(
        new Row("A", 2),
        new Row("B", 1),
        new Row("C", 2)
);

List<Row> sorted = rows.parallelStream()
        .sorted(Comparator.comparingInt(Row::priority))
        .toList();

System.out.println(
        sorted.stream().map(Row::code).toList()
); // [B, A, C]
~~~

`A` precedes `C` because both rows have `priority = 2` and the `List` source has encounter order.

If you want a **fully deterministic order independent of arrival order on ties**, add a tie-breaker:

~~~java
Comparator<Row> byPriorityThenCode =
        Comparator.comparingInt(Row::priority)
                  .thenComparing(Row::code);
~~~

### 4.2. sorted on an infinite source cannot emit a first element in general

~~~java
import java.util.stream.Stream;

// Do not run: an infinite source has no guarantee
// that sorted() can ever determine the smallest element to emit.
// Stream.iterate(0, n -> n + 1)
//         .sorted()
//         .findFirst();
~~~

Conversely, placing a limit **before** `sorted` can yield a finite input set:

~~~java
import java.util.List;
import java.util.stream.Stream;

List<Integer> result = Stream.iterate(10, n -> n - 1)
        .limit(5)
        .sorted()
        .toList();

System.out.println(result); // [6, 7, 8, 9, 10]
~~~

However, `limit(5).sorted()` does not have the same meaning as `sorted().limit(5)` on a general source.

### 4.3. sorted early or late?

If the requirement is simply keeping valid values and sorting them, it is usually beneficial to **filter before sorting**:

~~~java
import java.util.List;

List<Integer> values = List.of(9, -1, 7, -3, 5, 2);

List<Integer> result = values.parallelStream()
        .filter(n -> n >= 0)
        .sorted()
        .toList();

System.out.println(result); // [2, 5, 7, 9]
~~~

`filter` shrinks the input fed into `sorted`. With an independent pure predicate and an appropriate comparator, moving `filter` earlier preserves the sorted dataset. If the predicate depends on **position** or **mutable state**, or if `limit/skip/takeWhile` sits in between, do not swap them arbitrarily.

### 4.4. Be careful with sorting just to take a few elements

~~~java
import java.util.Comparator;
import java.util.List;

List<Integer> values = List.of(9, 1, 7, 3, 5);

List<Integer> topThree = values.stream()
        .sorted(Comparator.reverseOrder())
        .limit(3)
        .toList();

System.out.println(topThree); // [9, 7, 5]
~~~

This is the right result for **the three largest elements**. Yet general `sorted` may have to process the entire source before `limit` takes three elements. For huge datasets and very small `k`, a top-K algorithm using a heap of size `k` or an appropriate collector can lower costs, provided comparator, tie-break, and data semantics are designed accurately.

**Do not** change it to `limit(3).sorted(reverseOrder())` if the goal is still a global top-K.

---

## 5. distinct: deduplication and the cost of tracking seen values

`distinct()` uses `Object.equals` (or equivalent semantics for primitive streams) to retain each unique value once.

~~~java
import java.util.List;

List<Integer> values = List.of(2, 1, 2, 3, 1, 4);

System.out.println(values.stream().distinct().toList());
// [2, 1, 3, 4]

System.out.println(values.parallelStream().distinct().toList());
// [2, 1, 3, 4]
~~~

On a Stream with encounter order, `distinct` is **stable**: among equal elements, it retains the **first** occurrence in encounter order. `Integer` in the example makes the ordering easy to see.

### 5.1. The more distinct values in the source, the larger distinct's state can grow

A typical deduplication implementation stores seen values, so memory can grow with the number of unique elements. With `n` elements and `u` unique values, tracking state can scale with `u` (in addition to other pipeline overhead).

If values have well-distributed `hashCode` implementations, hash-based approaches are typically efficient; however, do not assign an absolute time complexity to every implementation or every object class.

### 5.2. Why can ordered parallel distinct be expensive?

To preserve the **first occurrence**, the framework must know whether a value in a later partition already appeared in an earlier partition.

~~~text
ORDERED source:
[ A, B, A ] | [ C, B, D ] | [ D, E ]

Required result:
[ A, B, C, D, E ]

Not only must it know "B was seen":
it must know which partition holds the first B.
~~~

On an ordered parallel stream, `distinct` may require a *full barrier*, temporary buffers, and coordination between partitions. This is a classic example where preserving encounter order increases parallel overhead.

### 5.3. When "first record" is not needed, the order constraint can be dropped

~~~java
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

List<Integer> values = List.of(2, 1, 2, 3, 1, 4);

Set<Integer> unique = values.parallelStream()
        .unordered()
        .distinct()
        .collect(Collectors.toSet());

System.out.println(unique.equals(Set.of(1, 2, 3, 4))); // true
~~~

`unordered()` relieves `distinct` from keeping the first element in encounter order. Yet **never use this approach** if the user needs the earliest-appearing record in the list.

If the final goal is simply a `Set` and no intermediate logic depends on order, `collect(Collectors.toSet())` is also a direct option; `distinct().collect(toSet())` is sometimes redundant.

### 5.4. DISTINCT is by equals, not by business key

~~~java
import java.util.List;

record Product(long id, String name) {}

List<Product> products = List.of(
        new Product(7L, "Bút cũ"),
        new Product(7L, "Bút mới")
);

System.out.println(products.stream().distinct().count()); // 2
~~~

The two `record` instances differ in `name`, so `equals` returns `false`. `distinct` does not merge by `id`.

If the requirement is "for each ID, keep the record with the highest revision," use a `toMap` collector with an explicit business merge function instead of expecting `distinct` to resolve duplicate keys.

### 5.5. Avoid mutable objects changing equals/hashCode during traversal

`distinct` may rely on `equals` and `hashCode`. If state involved in those two methods mutates while the pipeline is running, results can be wrong or unstable.

Stream behavioral functions must be **non-interfering** and **stateless**; source data must also be managed properly. Never mutate an object to "mark as seen" inside `distinct` or an earlier `peek`.

---

## 6. skip: dropping a prefix by position

`skip(n)` discards the **first n elements** of a Stream with encounter order. If the source has fewer than `n` elements, the result is empty.

~~~java
import java.util.List;

List<String> values = List.of("A", "B", "C", "D", "E");

List<String> result = values.parallelStream()
        .skip(2)
        .toList();

System.out.println(result); // [C, D, E]
~~~

`skip` is a stateful intermediate operation, yet **not** a general short-circuiting operation. After discarding two elements, downstream may still consume all remaining elements.

### 6.1. Cost of skip on sequential sources

With a forward-only `Iterator`, skipping `n` elements may require advancing the iterator n times. With sources supporting efficient indexing/splitting, Stream can leverage that metadata to skip entire segments without processing them.

Thus you cannot assume `skip(n)` always processes every skipped element; cost depends on the `Spliterator` and pipeline.

### 6.2. Cost of skip on parallel ordered streams

To discard **the exact first n elements** in global order, processing chunks must jointly locate the boundary:

~~~text
ORDERED source:
     [A, B, C] | [D, E, F] | [G, H]
skip(4):
     drop A,B,C,D
     keep E,F,G,H
~~~

If exact partition sizes are known, locating the boundary can be efficient. If the source lacks known sizes or splits unevenly, the framework may need more coordination and buffering.

### 6.3. Skip on an unordered stream

If encounter order is dropped:

~~~java
import java.util.List;

List<Integer> source = List.of(10, 20, 30, 40, 50);

List<Integer> result = source.parallelStream()
        .unordered()
        .skip(2)
        .toList();

System.out.println(result.size()); // 3
// Cannot predict exactly which three values are kept.
~~~

On a Stream without encounter order, `skip(2)` is permitted to drop **any two elements** from a source of at least two elements. That semantics differs from "drop the first two elements in the List."

### 6.4. Skip and offset pagination

~~~java
import java.util.List;

List<String> rows = List.of("A", "B", "C", "D", "E", "F");

int pageNumber = 1; // 0-indexed
int pageSize = 2;

List<String> page = rows.stream()
        .skip((long) pageNumber * pageSize)
        .limit(pageSize)
        .toList();

System.out.println(page); // [C, D]
~~~

The result page is stable only if **data ordering is stable**. If the source comes from a query without explicit sorting, or the list is updated between reads, `skip/limit` cannot guarantee consistent pagination.

For very large offsets or database-backed sources, do not load the entire dataset into Java only to skip millions of rows; prefer source-side pagination or keyset pagination. That is a source-architecture decision, not just a Stream question.

---

## 7. limit: taking at most n elements and potentially short-circuiting

`limit(n)` selects at most the first `n` elements in encounter order, if the Stream is ordered.

~~~java
import java.util.List;

List<Integer> values = List.of(2, 4, 6, 8, 10, 12);

List<Integer> firstThree = values.parallelStream()
        .limit(3)
        .toList();

System.out.println(firstThree); // [2, 4, 6]
~~~

`limit` is a **short-circuiting stateful intermediate operation**. Once enough elements are determined, downstream no longer needs the rest, though in parallel execution other branches may have already started work.

### 7.1. Limit does not mean the mapper runs only n times

~~~java
import java.util.List;

List<Integer> result = List.of(1, 2, 3, 4, 5, 6)
        .parallelStream()
        .map(n -> n * 10)
        .limit(2)
        .toList();

System.out.println(result); // [10, 20]
~~~

The result contains the exact first two elements in encounter order. Yet `parallel` may have already begun processing elements beyond the retained prefix, so do not count mapper invocations as business data. Permitted Stream optimizations may also skip certain pipeline lambdas when they do not affect the result.

### 7.2. Unordered limit relaxes constraints but changes meaning

~~~java
import java.util.List;

List<Integer> values = List.of(10, 20, 30, 40, 50);

List<Integer> sample = values.parallelStream()
        .unordered()
        .limit(2)
        .toList();

System.out.println(sample.size()); // 2
// There is no guarantee that sample is [10, 20].
~~~

If the requirement is "pick any two records" and element position does not matter, this can be a valid option. If the requirement is "the first two records chronologically," dropping order is a business bug.

### 7.3. Should limit come before or after sorted?

~~~java
import java.util.Comparator;
import java.util.List;

List<Integer> values = List.of(2, 9, 4, 7, 1);

List<Integer> largestTwo = values.stream()
        .sorted(Comparator.reverseOrder())
        .limit(2)
        .toList();

List<Integer> largestAmongFirstTwo = values.stream()
        .limit(2)
        .sorted(Comparator.reverseOrder())
        .toList();

System.out.println(largestTwo);          // [9, 7]
System.out.println(largestAmongFirstTwo); // [9, 2]
~~~

**The two pipelines have different meanings.** Swapping `limit` and `sorted` can lower sorting cost, yet it changes the problem from "global top-K" to "sort the first K records of the source."

### 7.4. limit(0) and negative n

~~~java
import java.util.stream.IntStream;

System.out.println(IntStream.range(0, 100).limit(0).count()); // 0

// Throws IllegalArgumentException:
// IntStream.range(0, 100).limit(-1);
~~~

`skip` also requires a non-negative count. If `pageNumber * pageSize` risks `int` overflow, compute in `long` and validate inputs before passing as an offset.

---

## 8. takeWhile: taking the longest prefix matching a condition

`takeWhile(P)` (Java 9+) is not the same as `filter(P)`.

On a source **with encounter order**, it selects **the longest contiguous prefix at the start of the Stream** matching the predicate. Once the first non-matching element is encountered, the result ends.

~~~java
import java.util.List;

List<Integer> values = List.of(2, 4, 7, 8, 10);

List<Integer> prefix = values.stream()
        .takeWhile(n -> n % 2 == 0)
        .toList();

List<Integer> allEven = values.stream()
        .filter(n -> n % 2 == 0)
        .toList();

System.out.println(prefix);  // [2, 4]
System.out.println(allEven); // [2, 4, 8, 10]
~~~

`takeWhile` can stop when it hits `7`; `filter` must keep checking later elements to find other even numbers, unless downstream has its own short-circuiting operation.

### 8.1. Sequential takeWhile cost

With a sequential source and a simple predicate, determining the prefix usually evaluates the matching elements plus **the first non-matching element** (if any). After that, it does not need to continue reading the source for this operation.

If every element of a finite source matches, it must traverse to the end to prove the prefix spans the entire source. On an **infinite source where every element matches**, collecting everything into a List will never terminate.

~~~java
import java.util.stream.IntStream;

List<Integer> finite = IntStream.iterate(0, n -> n + 1)
        .takeWhile(n -> n < 5)
        .boxed()
        .toList();

System.out.println(finite); // [0, 1, 2, 3, 4]
~~~

### 8.2. Why can ordered parallel takeWhile be very expensive?

Suppose the source is split into branches:

~~~text
ORDERED: [1, 2, 3, 4] | [5, 6, 7, 8] | [9, 10]
Predicate: n < 7

Required result: [1, 2, 3, 4, 5, 6]

The right branch may run first, yet the "longest prefix"
result can only be decided after knowing earlier branches.
~~~

To preserve the longest prefix in **encounter order**, the framework must locate the globally first non-matching position. That synchronization/coordination constraint can make ordered parallel `takeWhile` much costlier than running sequentially.

### 8.3. takeWhile on an unordered stream has a different contract

On a Stream **without encounter order**, `takeWhile` may take **any subset of elements matching the predicate**; it is not required to keep the longest prefix of an original source order. Even if every element matches, the subset taken does not necessarily include all elements.

~~~java
import java.util.List;

List<Integer> values = List.of(1, 2, 3, 4, 5, 6);

List<Integer> selected = values.parallelStream()
        .unordered()
        .takeWhile(n -> n < 4)
        .toList();

// Every selected element must satisfy n < 4.
// Do not expect selected to equal [1, 2, 3].
System.out.println(selected);
~~~

If you need **all** elements satisfying `n < 4` regardless of position, use `filter(n -> n < 4)`. Dropping order before `takeWhile` does not turn it into `filter`.

### 8.4. takeWhile does not sort data automatically

~~~java
import java.util.List;

List<Integer> values = List.of(1, 3, 8, 5, 6);

System.out.println(values.stream()
        .takeWhile(n -> n < 7).toList()); // [1, 3]
~~~

Elements `5` and `6` are still less than 7, yet they sit **after** `8`, so they are not part of the longest prefix. If you want to test "every number under 7 anywhere," use `filter`. If you want a threshold cutoff on a sorted sequence, verify that the source truly has the appropriate ordering.

---

## 9. dropWhile: dropping the longest prefix, keeping the rest

`dropWhile(P)` (Java 9+) discards the **longest prefix** of an ordered Stream whose contiguous leading elements satisfy the predicate.

~~~java
import java.util.List;

List<Integer> values = List.of(2, 4, 7, 8, 10);

List<Integer> remaining = values.stream()
        .dropWhile(n -> n % 2 == 0)
        .toList();

List<Integer> onlyOdd = values.stream()
        .filter(n -> n % 2 != 0)
        .toList();

System.out.println(remaining); // [7, 8, 10]
System.out.println(onlyOdd);   // [7]
~~~

`dropWhile` does not remove every element matching `P`: once the first non-matching element is encountered, all remaining elements are kept **intact along the stream**.

### 9.1. Sequential dropWhile cost

`dropWhile` must find the boundary at the start of the source, then typically **continue forwarding all remaining elements** downstream. Thus it is **not a short-circuiting intermediate operation** in the sense that `takeWhile` is.

~~~java
import java.util.List;

List<Integer> values = List.of(1, 2, 7, 3, 4);

List<Integer> afterBoundary = values.stream()
        .dropWhile(n -> n < 5)
        .toList();

System.out.println(afterBoundary); // [7, 3, 4]
~~~

Elements `3` and `4` satisfy `n < 5`, yet because they appear after the prefix-breaking element `7`, they are retained.

### 9.2. Parallel ordered requires locating the global boundary

If multiple partitions are processed concurrently, the framework cannot arbitrarily drop matching elements in the middle or end. It must identify all elements belonging to the **prefix** to drop and keep every element after the first boundary.

This constraint can cause buffering, partition coordination, or reduced useful parallelism — especially when the source size is unknown or splitting is poor.

### 9.3. dropWhile on an unordered stream

On a Stream without encounter order, `dropWhile` may drop **any subset of elements matching the predicate**. It is not required to drop every matching element.

~~~java
import java.util.List;

List<Integer> values = List.of(1, 2, 3, 4, 5);

List<Integer> result = values.parallelStream()
        .unordered()
        .dropWhile(n -> n < 4)
        .toList();

// Elements not matching n < 4, such as 4 and 5,
// are not dropped by dropWhile.
// Elements 1, 2, 3 may be dropped partially or completely.
System.out.println(result);
~~~

If the requirement is "keep every element with n >= 4," use `filter(n -> n >= 4)` to express it, not `unordered().dropWhile(n -> n < 4)`.

### 9.4. Boundary cases: all or no elements match

| Finite ORDERED source | `takeWhile(P)` | `dropWhile(P)` |
|---|---|---|
| Every element matches `P` | Entire source | Empty stream |
| First element fails `P` | Empty stream | Entire source |
| Empty source | Empty stream | Empty stream |

With an **infinite** source where every element satisfies `P`, `dropWhile(P)` may never emit a single element downstream, because the prefix-dropping boundary never appears.

---

## 10. Comparing all six operations on the same dataset

~~~java
import java.util.List;

List<Integer> source = List.of(4, 2, 2, 6, 3, 5, 8);
~~~

| Ordered sequential pipeline | Result | Explanation |
|---|---|---|
| `source.stream().sorted()` | `[2, 2, 3, 4, 5, 6, 8]` | Sorts everything |
| `source.stream().distinct()` | `[4, 2, 6, 3, 5, 8]` | Keeps first occurrence |
| `source.stream().skip(3)` | `[6, 3, 5, 8]` | Drops first three elements |
| `source.stream().limit(3)` | `[4, 2, 2]` | Takes first three elements |
| `source.stream().takeWhile(n -> n % 2 == 0)` | `[4, 2, 2, 6]` | Stops before the first odd number (`3`) |
| `source.stream().dropWhile(n -> n % 2 == 0)` | `[3, 5, 8]` | Drops even prefix, keeps `8` after boundary |

Reference code:

~~~java
import java.util.List;

List<Integer> source = List.of(4, 2, 2, 6, 3, 5, 8);

System.out.println(source.stream().sorted().toList());
System.out.println(source.stream().distinct().toList());
System.out.println(source.stream().skip(3).toList());
System.out.println(source.stream().limit(3).toList());
System.out.println(source.stream().takeWhile(n -> n % 2 == 0).toList());
System.out.println(source.stream().dropWhile(n -> n % 2 == 0).toList());
~~~

This table shows **results for an ordered sequential Stream**; if you add `unordered()`, do not copy prefix-based or first-occurrence outputs as mandatory assertions.

## 11. Why do SIZED and SUBSIZED matter for skip/limit?

`Spliterator` describes the data source to the Stream API.

- `ORDERED`: the source has an encounter order.
- `SIZED`: the remaining element count is known accurately per contract.
- `SUBSIZED`: Spliterators produced via `trySplit` also have exact sizes.

~~~java
import java.util.Spliterator;
import java.util.stream.IntStream;

Spliterator.OfInt source = IntStream.range(0, 100).spliterator();

System.out.println(source.hasCharacteristics(Spliterator.ORDERED));  // true
System.out.println(source.hasCharacteristics(Spliterator.SIZED));    // true
System.out.println(source.hasCharacteristics(Spliterator.SUBSIZED)); // true
~~~

When a source splits into contiguous slices of known size, `skip`/`limit` can compute boundaries without traversing every element in skipped partitions.

~~~text
ORDERED and SUBSIZED:
[0..24] | [25..49] | [50..74] | [75..99]

skip(50).limit(10) can determine:
  skip the first two partitions
  take 50..59 from the third partition
  no need to retain the rest
~~~

This is an **optimization capability**, not a promise that every JDK version executes strictly according to this diagram.

Conversely, an iterator from an I/O source with unknown remaining count typically lacks `SIZED/SUBSIZED`. Jumping to a global offset in parallel ordered mode becomes harder.

### 11.1. Do not attach SIZED/SUBSIZED falsely to force speedup

If you write a custom Spliterator and report inaccurate sizes, the framework may optimize based on false metadata. For instance, with `count()`, a size-guaranteed pipeline might skip traversing elements altogether.

Declare `SIZED` only if `estimateSize()` is exact per contract. Declare `SUBSIZED` only if splitting also preserves that exactness.

### 11.2. An "ordered" source alone does not indicate splittability

A list and a file iterator can both be ordered, yet:

- A list can usually split into index slices of known size.
- A file iterator may only read forward, lack a known end count, or fail to split efficiently.

Two sources that are both `ORDERED` can have vastly different parallel `skip/limit` costs. Do not infer performance solely from `ORDERED`.

---

## 12. Reordering operations: which optimizations preserve meaning?

One rule: **only reorder operations when you can prove the result does not change under the requirements**.

### 12.1. filter before sorted: usually beneficial

~~~java
import java.util.List;

List<Integer> values = List.of(9, -1, 3, -2, 7);

List<Integer> a = values.stream()
        .filter(n -> n >= 0)
        .sorted()
        .toList();

List<Integer> b = values.stream()
        .sorted()
        .filter(n -> n >= 0)
        .toList();

System.out.println(a); // [3, 7, 9]
System.out.println(b); // [3, 7, 9]
~~~

With a pure predicate, the retained element set is order-independent and no position-based operation sits in between, so filtering first reduces the number of elements to sort.

### 12.2. distinct before sorted: can reduce elements to sort

~~~java
import java.util.List;

List<Integer> values = List.of(7, 3, 7, 1, 3, 5);

List<Integer> result = values.stream()
        .distinct()
        .sorted()
        .toList();

System.out.println(result); // [1, 3, 5, 7]
~~~

With `Integer` natural ordering, placing `distinct` before `sorted` usually makes sense if the source has many duplicates. However, deduplication also consumes memory and processing cost; if the comparator is not consistent with `equals` or the problem requires selecting a specific representative among objects, analyze ordering and tie-breaks carefully.

### 12.3. limit before sorted: usually changes the problem

~~~java
import java.util.List;

List<Integer> values = List.of(8, 1, 7, 2, 9);

System.out.println(values.stream()
        .sorted()
        .limit(2)
        .toList()); // [1, 2]

System.out.println(values.stream()
        .limit(2)
        .sorted()
        .toList()); // [1, 8]
~~~

The first selects **the two smallest values in the entire source**; the second sorts **the first two values**. Never optimize purely for speed while ignoring this difference.

### 12.4. skip and distinct do not commute freely

~~~java
import java.util.List;

List<Integer> values = List.of(1, 1, 2, 3);

System.out.println(values.stream()
        .skip(1)
        .distinct()
        .toList()); // [1, 2, 3]

System.out.println(values.stream()
        .distinct()
        .skip(1)
        .toList()); // [2, 3]
~~~

`skip(1)` on the raw data drops one **position**, whereas `skip(1)` after `distinct` drops the **first unique value**. The two questions are not the same.

### 12.5. takeWhile and filter do not commute arbitrarily

~~~java
import java.util.List;

List<Integer> values = List.of(1, 2, 9, 3, 4);

System.out.println(values.stream()
        .takeWhile(n -> n < 5)
        .filter(n -> n % 2 == 0)
        .toList()); // [2]

System.out.println(values.stream()
        .filter(n -> n % 2 == 0)
        .takeWhile(n -> n < 5)
        .toList()); // [2, 4]
~~~

In the second pipeline, `filter` already removed `9` before `takeWhile` evaluated the boundary. That **altered the prefix**.

### 12.6. sorted + takeWhile on sorted data

~~~java
import java.util.List;

List<Integer> values = List.of(7, 1, 3, 9, 5);

List<Integer> small = values.stream()
        .sorted()
        .takeWhile(n -> n < 6)
        .toList();

System.out.println(small); // [1, 3, 5]
~~~

`sorted` puts values below the threshold contiguously at the front, so `takeWhile` behaves similarly to `filter(n -> n < 6)` on ascending sorted data. However, sorting the entire source can be expensive; if you only need **all** values below the threshold without sorting, use `filter`.

---

## 13. unordered(): when is relaxing constraints safe?

`unordered()` is an intermediate operation that is **not a shuffle**. It merely declares that downstream results **do not need to preserve the input's encounter order**.

Cases worth considering:

- You only need a **set of unique values**, regardless of which element appeared first.
- You only need **any n elements** for sampling/testing, with no notion of "first."
- Running parallel `distinct` on large data where ordering has no business meaning.
- The final aggregation is a `Set` or a structure whose order is contractually irrelevant.

Cases where it should **not** be used:

- Fetching the first page of a chronologically sorted list.
- Reading logs from the start up to an error event with `takeWhile`.
- Dropping all records before the first checkpoint with `dropWhile`.
- Keeping the "first record" among duplicates.
- Needing an ordered list output for matching, display, or export.

### 13.1. Unordered does not guarantee speedup

~~~java
import java.util.List;

List<Integer> values = List.of(8, 1, 8, 3, 1, 5);

List<Integer> result = values.parallelStream()
        .unordered()
        .distinct()
        .toList();
~~~

There may be no noticeable speedup on six elements because of parallel overhead. The result still contains the exact unique values by `equals`, with no order guarantee.

Dropping encounter order only **permits** cheaper execution strategies; the framework is under no obligation to pick a particular one.

---

## 14. Real-world problem: filtering and ranking orders

Suppose you have a list of orders and need the **top 5 active orders with the highest total amount**, sorted by descending price and then ascending ID.

~~~java
import java.util.Comparator;
import java.util.List;

record Order(String id, long totalCents, boolean active) {}

List<Order> orders = List.of(
        new Order("O-01", 500, true),
        new Order("O-02", 900, true),
        new Order("O-03", 1200, false),
        new Order("O-04", 700, true),
        new Order("O-05", 400, true),
        new Order("O-06", 1500, true),
        new Order("O-07", 300, true),
        new Order("O-08", 1100, true)
);

Comparator<Order> ranking =
        Comparator.comparingLong(Order::totalCents)
                  .reversed()
                  .thenComparing(Order::id);

List<Order> topFive = orders.parallelStream()
        .filter(Order::active)
        .sorted(ranking)
        .limit(5)
        .toList();

System.out.println(topFive.stream().map(Order::id).toList());
// [O-06, O-08, O-02, O-04, O-01]
~~~

Why does this order make sense?

1. `filter` removes inactive orders before sorting, shrinking the input to `sorted`.
2. `sorted(ranking)` establishes global priority order with an explicit tie-breaker.
3. `limit(5)` selects the exact first five orders **after sorting**.
4. `toList()` returns the list in the ordered Stream's result order.

**Do not** move `limit(5)` before `sorted`, as that would pick five orders by source order instead of top five by ranking criteria.

### 14.1. Should parallel be used here?

Possibly, but not by default. With eight orders, sequential execution is usually enough and parallel overhead can exceed sorting work. With millions of orders, you must also measure sort cost and source splittability.

If top-K is a frequent query on huge datasets, a heap-based K-selection algorithm may fit better than full sorting, though you must verify final order, tie-breaking, duplicate handling, and intermediate merging before designing a custom parallel collector.

---

## 15. Real-world problem: event logs and the first boundary

Suppose `events` is guaranteed to be in **increasing chronological order**. You want all events before the `"STOP"` marker.

~~~java
import java.util.List;

List<String> events = List.of(
        "BEGIN",
        "READY",
        "WORK",
        "STOP",
        "CLEANUP",
        "END"
);

List<String> beforeStop = events.stream()
        .takeWhile(event -> !event.equals("STOP"))
        .toList();

List<String> afterStop = events.stream()
        .dropWhile(event -> !event.equals("STOP"))
        .toList();

System.out.println(beforeStop); // [BEGIN, READY, WORK]
System.out.println(afterStop);  // [STOP, CLEANUP, END]
~~~

`dropWhile` keeps the **STOP marker itself** because the marker is the first element failing the prefix-dropping predicate. If you also want to skip the marker:

~~~java
List<String> afterMarker = events.stream()
        .dropWhile(event -> !event.equals("STOP"))
        .skip(1)
        .toList();

System.out.println(afterMarker); // [CLEANUP, END]
~~~

This is valid only if "drop the first element after dropWhile" is truly the requirement; if no marker exists, the entire Stream is dropped by `dropWhile` and `skip(1)` receives an empty stream.

**Do not add `unordered()`** to these two pipelines: the concepts "before STOP" and "after STOP" **only have meaning when event order is defined**. Ordered parallel execution may require coordination to locate the first boundary; with many log sources that must be read sequentially, sequential execution is often the right and sufficiently fast choice.

---

## 16. Infinite sources and avoiding non-terminating pipelines

Intermediate operations can interact unpredictably with **termination** on infinite sources.

| Pipeline on an infinite source | Risk or behavior |
|---|---|
| `sorted().limit(10)` | May never emit a single element, because sorting needs global order |
| `distinct().limit(10)` | May finish if the source produces at least 10 distinct values over time, though no general guarantee |
| `skip(10).limit(5)` | Can terminate if the source supplies enough elements |
| `takeWhile(P).toList()` | Can terminate once a non-matching element appears; if no boundary appears, it will not |
| `dropWhile(P).limit(5)` | Can terminate if a boundary and enough subsequent elements appear; if P always holds, it will not |
| `limit(10).sorted()` | Feeds finite input to sort; usually terminates if the source supplies enough elements |

Illustrating a finite result produced from a potentially infinite source:

~~~java
import java.util.List;
import java.util.stream.Stream;

List<Integer> values = Stream.iterate(0, n -> n + 1)
        .skip(10)
        .limit(5)
        .toList();

System.out.println(values); // [10, 11, 12, 13, 14]
~~~

When placing `sorted` before `limit` on an infinite source, a downstream short-circuit **does not automatically turn sort into a top-K finder that can emit immediately**.

Infinite sources also raise resource and task-cancellation concerns. Do not build long-running side-effect loops inside a lambda expecting `limit` to always interrupt that loop.

---

## 17. Testing correctness when switching from sequential to parallel

A parallel pipeline is only worth using when it **preserves data semantics**. Test each operation thoroughly rather than comparing two final values on one small dataset.

### 17.1. Dataset intentionally containing duplicates, different order, and mid-stream boundaries

~~~java
import java.util.List;

List<Integer> source = List.of(4, 2, 2, 6, 3, 5, 8);

List<Integer> expectedDistinct = List.of(4, 2, 6, 3, 5, 8);
List<Integer> expectedTopTwo = List.of(8, 6);
List<Integer> expectedPrefix = List.of(4, 2, 2, 6);

List<Integer> distinct = source.parallelStream()
        .distinct()
        .toList();

List<Integer> topTwo = source.parallelStream()
        .sorted(java.util.Comparator.reverseOrder())
        .limit(2)
        .toList();

List<Integer> prefix = source.parallelStream()
        .takeWhile(n -> n % 2 == 0)
        .toList();

if (!expectedDistinct.equals(distinct)
        || !expectedTopTwo.equals(topTwo)
        || !expectedPrefix.equals(prefix)) {
    throw new AssertionError("Kết quả song song sai hợp đồng");
}
~~~

The source is a `List` with encounter order, so expected results in this example are **exact**. With `unordered()`, do not compare specific positional lists if the contract allows multiple valid answers.

### 17.2. Testing unordered pipelines via invariants instead of a fixed order

~~~java
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

List<Integer> source = List.of(1, 1, 2, 3, 4, 5);

Set<Integer> distinct = source.parallelStream()
        .unordered()
        .distinct()
        .collect(Collectors.toSet());

if (!distinct.equals(Set.of(1, 2, 3, 4, 5))) {
    throw new AssertionError("Sai tập giá trị duy nhất");
}

List<Integer> sample = source.parallelStream()
        .unordered()
        .limit(3)
        .toList();

if (sample.size() != 3 || !source.containsAll(sample)) {
    throw new AssertionError("Sai cardinality hoặc giá trị");
}
~~~

On sources with duplicates, `containsAll` checks **set membership** but does not verify occurrence counts. If multiplicity is part of the business contract, verify by **multiset** (frequency map) or design a strong enough check.

### 17.3. Important boundary cases

| Case | What to verify |
|---|---|
| Empty source | `sorted/distinct/skip/limit/takeWhile/dropWhile` produce appropriate empty results |
| `limit(0)` | Result has zero elements |
| `skip(0)` | No elements dropped |
| `skip(n)` with `n > size` | Empty result |
| All duplicates | `distinct` keeps exactly one element per `equals` |
| Comparator with tied values | Does `sorted` preserve relative order when ORDERED? |
| Predicate true for entire source | `takeWhile` takes all, `dropWhile` drops all on finite ORDERED sources |
| Predicate false on first element | `takeWhile` is empty, `dropWhile` keeps everything |
| Predicate flips true → false → true | `takeWhile/dropWhile` act on **a single boundary**, unlike `filter` |
| `unordered()` | Assert only invariants required by contract, not a fixed prefix |
| Large data, many partitions | Correct result and no shared mutable state |
| Sources without `SIZED/SUBSIZED` | Do not assume element-skipping cost is low |
| I/O sources | Ensure resource closing and exception handling |

---

## 18. Measuring performance properly: benchmarks vs. timing printouts

Never rely solely on:

~~~java
long start = System.nanoTime();
// pipeline runs once
long elapsed = System.nanoTime() - start;
~~~

to conclude "parallel is 2x faster." A single run can be skewed by **JIT warm-up**, GC, thread scheduling, machine load, source structure, data size, and how the result is consumed.

### 18.1. Recommended benchmark matrix

| Variable to test | Reference values |
|---|---|
| Size `n` | Small, medium, large (e.g., 100, 100,000, 10,000,000 elements) |
| Source type | `ArrayList`, `IntStream.range`, unknown-size iterator source |
| Ordering state | ORDERED, or `unordered()` if business rules permit |
| Duplicate rate | 0%, low, high |
| `while` boundary position | Beginning, middle, near end, absent |
| `skip/limit` | Drop/take few, moderate, many |
| Sort operation | Natural order, comparators with varying tie-break and cost |
| Mode | `stream()` vs. `parallelStream()` |
| Output | Identical business result or acceptable invariant |

For critical applications, use **JMH** and a proper benchmark design. Ensure results are consumed, input data is equivalent, warm-up is sufficient, and input generation does not accidentally occur inside the timed section if the goal is measuring the pipeline alone.

### 18.2. What to measure?

- **Throughput/latency** of the entire pipeline.
- **Allocation/GC**: many stateful operations require buffers or hash structures.
- **CPU utilization**: are extra cores doing useful work or only increasing contention?
- **Peak memory**: especially `sorted` and `distinct` on large sources.
- **Correctness** of results: with wrong data, any speedup claim is meaningless.

### 18.3. Do not compare speeds of semantically different pipelines

`unordered().limit(100)` can be faster than ordered `limit(100)`, yet **the two pipelines do not guarantee selecting the same 100 elements**. Treat this as an optimization only if business logic genuinely accepts any 100 elements.

Similarly, `filter(P)` and `takeWhile(P)` return different datasets on arbitrarily ordered sources. Benchmarking them as "equivalent" algorithms is methodologically invalid if their outputs do not share the same meaning.

---

## 19. Choosing APIs and safe optimization strategies

| Actual need | Suggested API | Checklist before enabling parallel |
|---|---|---|
| Sort everything | `sorted(comparator)` | Sort/memory cost; stateless comparator; tie-break order |
| Global top-K | `sorted(comparator).limit(k)` or dedicated top-K algorithm | Do not swap to `limit(k).sorted()` |
| Deduplicate keeping first seen | `distinct()` on ORDERED Stream | May have barriers and encounter-order overhead |
| Just a unique value set | `unordered().distinct()` or `toSet()` | Order/representative does not matter |
| Drop first n records | `skip(n)` | Encounter order and `SIZED/SUBSIZED` source |
| Take first n records | `limit(n)` | "First" only makes sense on an ORDERED source |
| Pick any n elements | `unordered().limit(n)` | Business rules genuinely permit any subset |
| Take until first failing element | `takeWhile(P)` | Boundary defined on encounter order |
| Drop elements before boundary | `dropWhile(P)` | Boundary and position of first non-matching element |
| Keep all matching elements | `filter(P)` | Do not replace with `takeWhile` on arbitrary data |
| Remove all matching elements | `filter(P.negate())` | Do not replace with `dropWhile` on arbitrary data |

Optimization workflow:

1. **State the result contract in words.** "First three elements," "three largest elements," and "any three elements" are three distinct requirements.
2. **Identify the source's encounter order** and whether business logic needs order preserved.
3. **Estimate scale and distribution:** element count, duplicate ratio, boundary position, pagination size.
4. **Shrink valid data before expensive steps**, such as pure `filter` before `sorted` when meaning is unchanged.
5. **Choose suitable data and source structures**, leveraging `SIZED/SUBSIZED` when present without false declarations.
6. **Test sequentially first**, establish an independent oracle and boundary cases.
7. **Test in parallel**, verifying the output matches the exact order/subset required by contract.
8. **Try `unordered()` only when the contract allows**, and re-check all downstream operations.
9. **Run controlled benchmarks** and keep parallel mode only when gains outweigh coordination and memory costs.

---

## 20. Reinforcement exercises (with answers)

### Exercise 1. Predict the outputs

~~~java
import java.util.List;

List<Integer> numbers = List.of(5, 2, 5, 3, 2);

System.out.println(numbers.stream().distinct().toList());
System.out.println(numbers.stream().sorted().toList());
System.out.println(numbers.stream().skip(2).toList());
System.out.println(numbers.stream().limit(2).toList());
~~~

**Answer:** Respectively `[5, 2, 3]`, `[2, 2, 3, 5, 5]`, `[5, 3, 2]`, `[5, 2]`. `distinct` preserves the first occurrence on an ordered Stream; `skip/limit` rely on the List's encounter order.

### Exercise 2. takeWhile differs from filter

~~~java
import java.util.List;

List<Integer> values = List.of(2, 4, 7, 8, 10);

System.out.println(values.stream()
        .takeWhile(n -> n % 2 == 0).toList());

System.out.println(values.stream()
        .filter(n -> n % 2 == 0).toList());
~~~

**Answer:** `[2, 4]` and `[2, 4, 8, 10]`. `takeWhile` stops at `7`, whereas `filter` finds all even numbers.

### Exercise 3. Does dropWhile remove every matching element?

~~~java
import java.util.List;

List<Integer> values = List.of(1, 2, 7, 3, 4);

System.out.println(values.stream()
        .dropWhile(n -> n < 5).toList());
~~~

**Answer:** `[7, 3, 4]`. It drops only `1, 2` in the **prefix**. Numbers `3, 4` after the boundary `7` are kept.

### Exercise 4. Should limit and sorted be swapped?

**Prompt:** A problem needs the two highest scores of `[2, 9, 4, 7, 1]`. Can you use `limit(2).sorted(reverseOrder())` to reduce cost?

**Answer:** No, because it only sorts the first two elements `[2, 9]` into `[9, 2]`; the global top two must be `[9, 7]`. Define the right top-K problem before optimizing.

### Exercise 5. Why is ordered parallel distinct expensive?

**Prompt:** The source `[A, B, A] | [C, B, D]` is partitioned in parallel and must preserve first occurrences.

**Answer:** A later partition must not retain `B` if `B` already appeared in an earlier partition. Therefore coordination between partitions is needed to preserve the first representative, potentially increasing buffering and synchronization overhead. If you only need a set of values and do not care about the first representative, consider dropping the order constraint.

### Exercise 6. Does unordered limit guarantee taking the first elements?

**Prompt:** Must `List.of(10,20,30,40).parallelStream().unordered().limit(2).toList()` always return `[10,20]`?

**Answer:** No. It is permitted to choose any two-element subset as long as the source has enough elements; it still respects the count and source elements. Use only when order has no business meaning.

### Exercise 7. Does unordered takeWhile become filter?

**Prompt:** Calling `unordered().takeWhile(n -> n < 10)` on a source with numbers below and above 10 — will it always take all numbers below 10?

**Answer:** No. On a Stream without encounter order, `takeWhile` may select **any subset** of matching elements. If the requirement is taking **all** numbers less than 10, use `filter(n -> n < 10)`.

### Exercise 8. Can skip and distinct be swapped?

~~~java
import java.util.List;

List<Integer> values = List.of(1, 1, 2, 3);
~~~

**Answer:** Not in general. `skip(1).distinct()` returns `[1, 2, 3]`, while `distinct().skip(1)` returns `[2, 3]`. Skipping one **raw element** differs from skipping one **unique value**.

### Exercise 9. Why do SIZED/SUBSIZED help slicing?

**Prompt:** A 100-element source splits into four contiguous slices of 25 elements each. You need `skip(50).limit(10)`.

**Answer:** If the Spliterator knows the exact size of each slice and guarantees ordering, the framework can determine that the first two slices are skipped and take the first 10 elements of the third slice without locating boundaries by counting every element of every slice. This is an optimization capability, not a fixed timing rule.

### Exercise 10. Which infinite source pipeline may never terminate?

**Prompt:** Explain why `Stream.iterate(0,n -> n+1).sorted().limit(5).toList()` is inappropriate.

**Answer:** `sorted` must establish ordering over an infinite source before emitting results in general, so it may never emit the first element. Put `limit(5)` before `sorted` if the real requirement is "sort the first five elements," or change algorithms if the goal is top-K of a potentially infinite source.

### Exercise 11. Is the benchmark meaningful?

**Prompt:** A team measures `limit(100)` and `unordered().limit(100)` on an ordered source and claims the second has "the same result but faster."

**Answer:** They cannot claim the same result contract: the unordered version may select a different 100 elements. They must ask whether business rules accept any 100 elements. Only compare timings when both pipelines satisfy the result requirements.

### Exercise 12. Choosing an approach for log data

**Prompt:** A chronological event list `[OPEN, READY, ERROR, RECOVER, CLOSE]`. You need the events from the start **before ERROR**, excluding ERROR.

**Answer:**

~~~java
import java.util.List;

List<String> events = List.of(
        "OPEN", "READY", "ERROR", "RECOVER", "CLOSE"
);

List<String> beforeError = events.stream()
        .takeWhile(s -> !s.equals("ERROR"))
        .toList();

System.out.println(beforeError); // [OPEN, READY]
~~~

Do not use `unordered()` because the "before ERROR" boundary depends on encounter order.

---

**Takeaway:** `sorted` must establish **global order**, `distinct` must resolve **duplicates across partitions**, `skip/limit` depend on **position**, and `takeWhile/dropWhile` depend on **prefix boundaries**. In parallel execution, preserving encounter order can force buffering and coordination across partitions; `unordered()` is appropriate only when business logic truly does not need ordering. Define the exact result meaning, leverage `SIZED/SUBSIZED` sources when available, verify with boundary cases, and benchmark before choosing a parallel pipeline.
