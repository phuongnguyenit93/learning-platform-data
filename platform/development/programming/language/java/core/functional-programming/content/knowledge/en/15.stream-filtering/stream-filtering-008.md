# How the Order of Filter and Limit Operations Changes Results in Java Stream

## 1. The Core Problem: Filter First or Limit First?

With Java Stream, two processing chains that look nearly identical can return **completely different** results:

~~~java
numbers.stream().filter(n -> n % 2 == 0).limit(3).toList();

numbers.stream().limit(3).filter(n -> n % 2 == 0).toList();
~~~

The illustrative code above assumes `numbers` is a `List<Integer>`. If the source list is:

~~~text
[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
~~~

then the results are:

| Pipeline | Result | Meaning |
| --- | --- | --- |
| `filter(even).limit(3)` | `[2, 4, 6]` | Take the **first 3 even numbers** in the source |
| `limit(3).filter(even)` | `[2]` | Examine the **first 3 elements**, then keep only even numbers |

**Reason:** the steps in a pipeline are chained in the order they are written. `filter` keeps or discards elements; `limit(n)` limits **the number of elements reaching the `limit` step itself**, not necessarily the number of original elements.

Therefore, `filter(...).limit(n)` may have to examine **more than n source elements** to find enough n matching elements, whereas `limit(n).filter(...)` only lets at most n input elements pass into the subsequent filter step.

This lesson focuses on the impact of **the ordering of filter and limit operations**, while also pointing out cases combined with `skip`, `sorted`, ordered sources, and parallel streams.

## 2. Understanding the Exact Contract of filter and limit

### 2.1. filter(Predicate): keeping elements that satisfy a condition

`Stream<T>.filter(Predicate<? super T>)` produces a Stream consisting of the elements whose predicate test evaluates to `true`. For example:

~~~java
List<Integer> even = numbers.stream()
        .filter(n -> n % 2 == 0)
        .toList();
~~~

This is illustrative code inside a method, requiring `import java.util.List`. With a source from 1 to 10, the result is `[2, 4, 6, 8, 10]`.

For a source with an encounter order such as `List`, `filter` preserves the **relative order** of the remaining elements. It does not sort elements on its own and does not directly modify the source list.

The predicate should be a **stateless** and **non-interfering** function: it does not need external state that changes across invocations and does not modify the source during traversal. Simply testing an element does not require modifying other elements.

### 2.2. limit(maxSize): taking no more than maxSize elements at its position

`Stream<T>.limit(long maxSize)` is a **short-circuiting, stateful** intermediate operation: it produces a Stream of at most `maxSize` elements, counted from the **start of the encounter order** if the Stream has an encounter order.

~~~java
List<Integer> firstThree = numbers.stream()
        .limit(3)
        .toList();
// [1, 2, 3]
~~~

`maxSize` must be **non-negative**; passing a negative number throws `IllegalArgumentException`. `limit(0)` yields an empty pipeline result; `limit(n)` does not add elements when the source has fewer than n elements.

Key terms:

- **At most**, not **always exactly n**: if the source or preceding steps have fewer elements, the output may have fewer than n.
- **At its position**: limit counts the elements that have passed through the preceding steps.
- **Encounter order**: “first” has meaning when the source/pipeline has a defined encounter order. For an unordered source, you must not rely on a specific group of elements.
- **Short-circuit**: a terminal operation may complete without processing the entire source. However, you must not assume an exact number of callbacks across all implementations or in a parallel stream.

### 2.3. Both filter and limit are intermediate operations

The two calls above do not produce a result list by themselves. For example:

~~~java
Stream<Integer> pipeline = numbers.stream()
        .filter(n -> n % 2 == 0)
        .limit(3);
List<Integer> result = pipeline.toList();
~~~

This illustrative snippet requires importing `java.util.stream.Stream` and `java.util.List`. Intermediate steps are normally evaluated on demand when a terminal operation such as `toList()` is invoked. Therefore, saying “filter finishes running on the entire list and then limit runs” is an **oversimplified model**: elements can be processed in a pipelined fashion, and the `limit` operation can cause processing to stop early.

The accurate phrasing is that **the result semantics are equivalent to taking the sequence after each transformation in pipeline order**, rather than every intermediate step necessarily being stored as a list.

## 3. Tracing Element by Element: filter then limit

Suppose the source is ordered from 1 to 10, the condition is “even number”, and the limit is 3:

~~~java
numbers.stream()
        .filter(n -> n % 2 == 0)
        .limit(3)
        .toList();
~~~

Logical trace table on a sequential pipeline:

| Source element | Passes `filter`? | Elements reaching `limit` | Retained result |
| --- | --- | --- | --- |
| 1 | No | 0 | `[]` |
| 2 | Yes | 1 | `[2]` |
| 3 | No | 1 | `[2]` |
| 4 | Yes | 2 | `[2,4]` |
| 5 | No | 2 | `[2,4]` |
| 6 | Yes | 3 | `[2,4,6]` |

Once 3 matching elements have been obtained, producing this result list does not need to examine numbers 7–10. The table is meant to illustrate **logical order**, not a contract on the exact number of predicate invocations in every execution mode.

Conclusion: `limit(3)` limits **the number of elements after filter**, so we get the first three even numbers. This is the right choice for the requirement:

> “Give me the first three elements **that satisfy the condition**.”

### 3.1. What if there are not enough matching elements

For example:

~~~java
List<Integer> result = List.of(1, 3, 5, 6).stream()
        .filter(n -> n % 2 == 0)
        .limit(3)
        .toList();
// [6]
~~~

Only one element passes through filter, so a limit of 3 does not create two extra elements. `limit` has no capability to pad or repeat values to reach the count.

## 4. Tracing the Reverse: limit then filter

With the same source 1 to 10, but reversing the order:

~~~java
numbers.stream()
        .limit(3)
        .filter(n -> n % 2 == 0)
        .toList();
~~~

First, `limit(3)` lets only three elements in encounter order proceed:

~~~text
Source:              [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
After limit(3):      [1, 2, 3]
After filter(even):  [2]
~~~

Because the filter can only discard elements and cannot “go fetch more” source elements that were already blocked by `limit`, the result has only one even number.

This style is right when the requirement is:

> “Examine only the first three elements of the source, then filter those that satisfy the condition.”

Business example: **“Check the payment status of the 10 newest orders”** is different from **“Find the 10 newest paid orders”**. Whether the payment condition comes after or before the limit step changes the question the program answers.

## 5. Two Order Problems That Are Often Confused

Given a list of orders already in the desired business order:

~~~java
record Order(String id, boolean paid) {}

List<Order> orders = List.of(
        new Order("A", false),
        new Order("B", true),
        new Order("C", false),
        new Order("D", true),
        new Order("E", true)
);
~~~

This is an **illustrative snippet**: `record Order` is declared at type level, while the list is inside a method; `import java.util.List` is required. Consider two requirements:

### 5.1. Requirement A: “The first two paid orders”

~~~java
List<String> firstTwoPaid = orders.stream()
        .filter(Order::paid)
        .limit(2)
        .map(Order::id)
        .toList();
// [B, D]
~~~

Process: filter the paid orders `B,D,E`, take the first two `B,D`, extract the order IDs.

### 5.2. Requirement B: “Among the first two orders, which ones are paid?”

~~~java
List<String> paidAmongFirstTwo = orders.stream()
        .limit(2)
        .filter(Order::paid)
        .map(Order::id)
        .toList();
// [B]
~~~

Process: take the first two orders `A,B`, then discard the unpaid order `A`. Only `B` remains. Even though both use the operations `filter`, `limit`, `map`, the program answers a **different** question.

### 5.3. What order must “first” be defined by?

If the source is a list already sorted by time from newest to oldest, then “first” can mean “newest”. But if the source `List` is in an undefined data-loading order, you should not assign the meaning “newest” to `limit`.

To get the newest orders, make sure the order is established, for example after sorting by timestamp:

~~~java
// Illustrative snippet when Order has a timestamp field:
// orders.stream()
//       .sorted(Comparator.comparing(Order::timestamp).reversed())
//       .filter(Order::paid)
//       .limit(2)
//       .toList();
~~~

The syntax in the comment is a design example, **does not match the two-field Order record above**, and must not be treated as a standalone program. Before real use, define the timestamp field, the tie-breaking policy for equal timestamps, and the appropriate comparator. If ordering is a business requirement, make it explicit in the data contract or pipeline.

## 6. Combining skip and limit: Paginating in the Right Place

`skip(n)` discards the first n elements **at the position where it is placed in the pipeline**; `limit(n)` keeps no more than the next n elements. Both rely on encounter order when positional results are needed.

### 6.1. Paginating over the filtered set

~~~java
List<Integer> page = numbers.stream()
        .filter(n -> n % 2 == 0)
        .skip(2)
        .limit(2)
        .toList();
// [6, 8]
~~~

Source from 1 to 10; after filter it is `[2,4,6,8,10]`, skip the first two even numbers `2,4`, take the next two `6,8`.

This is the right design for:

> “Paginate **filtered** results: skip the two previous matches and take the next two matches.”

### 6.2. Filtering only within a pre-selected page from the source

~~~java
List<Integer> page = numbers.stream()
        .skip(2)
        .limit(2)
        .filter(n -> n % 2 == 0)
        .toList();
// [4]
~~~

After `skip(2)` there remain `3,4,5,...`; `limit(2)` selects `[3,4]`; filtering even numbers leaves only `[4]`.

This approach is:

> “Take a two-element window of the source and then filter within that window.”

It is **not** equivalent to paginating over the filtered set. If a pagination API returns results matching a search condition, doing `skip`/`limit` before `filter` can cause pages to have too few results even though matching elements still exist further ahead.

### 6.3. The relative position of skip and limit also matters

~~~java
List<Integer> result = numbers.stream()
        .filter(n -> n % 2 == 0)
        .limit(3)
        .skip(1)
        .toList();
// [4, 6]
~~~

After filtering we have `[2,4,6,8,10]`, limiting to 3 leaves `[2,4,6]`, and skipping the first element leaves `[4,6]`. This differs from `filter(...).skip(1).limit(3)`, which can yield `[4,6,8]`.

**Pagination rule:** if you want page p of results satisfying a condition, you usually need **filter → sort in a stable order (if needed) → skip(offset) → limit(pageSize)**. When data is large and comes from a database, consider pushing filter/sort/pagination down to the query and using appropriate pagination instead of loading all data into memory just to paginate with Stream.

## 7. sorted Also Affects the Meaning of limit

The order of `sorted` and `limit` can change which values are selected:

~~~java
List<Integer> source = List.of(7, 2, 6, 3, 8, 4, 5, 1);

List<Integer> smallestTwoEven = source.stream()
        .filter(n -> n % 2 == 0)
        .sorted()
        .limit(2)
        .toList();
// [2, 4]

List<Integer> firstTwoEvenThenSorted = source.stream()
        .filter(n -> n % 2 == 0)
        .limit(2)
        .sorted()
        .toList();
// [2, 6]
~~~

This snippet requires `import java.util.List`, placed inside a method. Distinguish:

- **Filter → sort → take 2**: select the two smallest values among the valid ones.
- **Filter → take 2 → sort**: select the first two valid values that appear in the source, then sort those two selected values.

Do not “optimize” by moving `limit` before `sorted` if the requirement is top N by score, price, or time. It is only safe when you can prove that ordering does not change the target result set.

### 7.1. filter does not change order, but predicate before/after limit matters

For an ordered source, `filter` removes elements while preserving relative order; `limit` selects a **prefix** of the sequence at the point where it is placed. Therefore, placing `limit` before `filter` restricts the range over which the condition is evaluated, not just the size of the output list.

In some special cases, both pipelines produce the same result, for example when the first three elements all satisfy the predicate. However, matching on a single test dataset **does not prove the two pipelines are equivalent for all data**.

## 8. short-circuit and Its Impact on Execution Work

`limit` is an intermediate operation with **short-circuit** capability. When a terminal operation requests a list of at most n elements, the Stream may not need to evaluate all source elements.

For a sequential pipeline, suppose we need 3 even numbers from the sequence 1 to 10: logically, we can stop once we have found `2,4,6`. If `limit(3)` is placed first, only the three elements `1,2,3` are examined by the filter step.

However, be cautious with such claims:

- **Do not assume an exact number of predicate calls** in every pipeline. The JDK may apply valid optimizations, and different terminal operations may consume data differently.
- **In a parallel stream**, multiple parts of the source may already have been processed by the time enough results are found; you must not conclude that all callbacks stop immediately after the n-th matching element.
- Other intermediate operations such as `sorted()` may need to inspect much or all of the data before providing matching results.
- Where `limit(n)` is placed affects **data selection semantics** before it affects performance. Business correctness is the top priority.

### 8.1. Do not use side effects to observe and draw rigid conclusions

Example to avoid:

~~~java
// Counter-example: do not use the print count as a business contract.
// List<Integer> result = numbers.stream()
//     .filter(n -> {
//         System.out.println("check " + n);
//         return n % 2 == 0;
//     })
//     .limit(3)
//     .toList();
~~~

The `println` line inside the predicate has a side effect. When changing the terminal operation, parallel mode, or optimizations, the invocations may not match assumptions. To measure performance, use an appropriate benchmark/profiler; to verify results, compare the output list.

A pure predicate like `n -> n % 2 == 0` is easier to test and has more independent behavior. Actions such as logging or calling external resources should be intentionally organized at system boundaries.

## 9. Ordered Sources, Unordered Sources, and parallelStream

### 9.1. With a List that has encounter order

`List.of(...)` has an encounter order; the `filter` pipeline preserves that order. Therefore:

~~~java
List<Integer> result = numbers.parallelStream()
        .filter(n -> n % 2 == 0)
        .limit(3)
        .toList();
// [2, 4, 6]
~~~

Even though it may run on multiple worker threads, the **result** must respect the encounter order of an ordered stream when `limit` takes the first elements and `toList()` materializes them in that order. This does not mean the per-element testing callbacks run sequentially.

With an ordered parallel stream, preserving the exact “first n matching elements” can incur coordination overhead and reduce parallelism benefits.

### 9.2. With a source without encounter order

Not every Collection has a guaranteed encounter order; for example, `HashSet` does not promise a logical order by value or insertion order. In a pipeline without encounter order, `limit(n)` can pick **any n elements** satisfying the count requirement, rather than a stably defined “first n elements”.

Therefore:

~~~java
// Illustration: do not predict the exact values selected.
Set<Integer> source = new HashSet<>(List.of(1, 2, 3, 4, 5, 6));
List<Integer> selected = source.parallelStream()
        .filter(n -> n % 2 == 0)
        .limit(2)
        .toList();
~~~

The snippet above requires importing `java.util.Set`, `java.util.HashSet`, and `java.util.List`. You can say `selected` contains at most two even numbers from the source, **without** promising a specific pair or specific order across all implementations.

### 9.3. Is unordered() a “slowness fix”?

`unordered()` indicates that subsequent operations do not need to be constrained by encounter order. It can help some parallel pipelines reduce `limit`/`skip` overhead when the business requirement **does not need the first n elements in source order**.

~~~java
List<Integer> anyTwoEven = numbers.parallelStream()
        .unordered()
        .filter(n -> n % 2 == 0)
        .limit(2)
        .toList();
~~~

With the source in the example, you can only promise that the result has at most two even numbers from the source; you cannot promise `[2,4]`. Writing `unordered()` **changes the ordering contract**, not an optimization that can be applied unconditionally.

If the requirement is “the three newest paid orders”, you must never arbitrarily add `unordered()`, because the meaning of **newest** depends on order.

## 10. Complete Java 17 Example with Exact Stdout

Create the file **FilterLimitOrderDemo.java**. This standalone program compares `filter → limit`, `limit → filter`, `skip`, `sorted`, and the order example.

~~~java
import java.util.List;
import java.util.stream.IntStream;

public class FilterLimitOrderDemo {
    record Order(String id, boolean paid) {}

    public static void main(String[] args) {
        List<Integer> numbers = IntStream.rangeClosed(1, 10).boxed().toList();

        List<Integer> filterThenLimit = numbers.stream()
                .filter(n -> n % 2 == 0)
                .limit(3)
                .toList();

        List<Integer> limitThenFilter = numbers.stream()
                .limit(3)
                .filter(n -> n % 2 == 0)
                .toList();

        List<Integer> filterSkipLimit = numbers.stream()
                .filter(n -> n % 2 == 0)
                .skip(2)
                .limit(2)
                .toList();

        List<Integer> skipLimitFilter = numbers.stream()
                .skip(2)
                .limit(2)
                .filter(n -> n % 2 == 0)
                .toList();

        List<Integer> filterLimitSkip = numbers.stream()
                .filter(n -> n % 2 == 0)
                .limit(3)
                .skip(1)
                .toList();

        System.out.println("filter -> limit: " + filterThenLimit);
        System.out.println("limit -> filter: " + limitThenFilter);
        System.out.println("filter -> skip -> limit: " + filterSkipLimit);
        System.out.println("skip -> limit -> filter: " + skipLimitFilter);
        System.out.println("filter -> limit -> skip: " + filterLimitSkip);

        List<Order> orders = List.of(
                new Order("A", false),
                new Order("B", true),
                new Order("C", false),
                new Order("D", true),
                new Order("E", true)
        );

        List<String> firstTwoPaid = orders.stream()
                .filter(Order::paid)
                .limit(2)
                .map(Order::id)
                .toList();

        List<String> paidAmongFirstTwo = orders.stream()
                .limit(2)
                .filter(Order::paid)
                .map(Order::id)
                .toList();

        System.out.println("first 2 paid: " + firstTwoPaid);
        System.out.println("paid among first 2: " + paidAmongFirstTwo);

        List<Integer> parallelOrdered = numbers.parallelStream()
                .filter(n -> n % 2 == 0)
                .limit(3)
                .toList();
        System.out.println("parallel ordered: " + parallelOrdered);

        List<Integer> sortedInput = List.of(7, 2, 6, 3, 8, 4, 5, 1);
        System.out.println("sorted before limit: " + sortedInput.stream()
                .filter(n -> n % 2 == 0)
                .sorted()
                .limit(2)
                .toList());
        System.out.println("limit before sorted: " + sortedInput.stream()
                .filter(n -> n % 2 == 0)
                .limit(2)
                .sorted()
                .toList());
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac --release 17 FilterLimitOrderDemo.java
java FilterLimitOrderDemo
~~~

**Verified stdout:**

~~~text
filter -> limit: [2, 4, 6]
limit -> filter: [2]
filter -> skip -> limit: [6, 8]
skip -> limit -> filter: [4]
filter -> limit -> skip: [4, 6]
first 2 paid: [B, D]
paid among first 2: [B]
parallel ordered: [2, 4, 6]
sorted before limit: [2, 4]
limit before sorted: [2, 6]
~~~

### 10.1. Result Analysis

- The first two lines differ because `filter` before limit selects 3 **matches**, whereas `limit` before filter examines only 3 **inputs**.
- The three lines with `skip` show that each operation takes data from the pipeline immediately preceding it: `filter → skip → limit` gives a page over the filtered set; `skip → limit → filter` gives matching elements within a window of the source; `filter → limit → skip` selects a small set first and then discards the first element of that small set.
- The two order lines represent two different questions: the first two paid orders `[B,D]` and the paid orders among the first two orders `[B]`.
- The `parallel ordered` line illustrates that with an ordered `List`, parallelism does not break the result contract of `filter(...).limit(3).toList()`.
- The last two lines distinguish top N **by value order** from the first N matching elements **by source order** that are then sorted.

This program uses transformations that do not mutate the source and do not require results to depend on thread scheduling.

## 11. Real-World Scenarios Requiring the Right Order

### 11.1. Finding the first 10 in-stock products in a score-sorted table

**Intent:** preserve the product table's priority-score order and select 10 products that are currently in stock.

~~~java
// Illustrative snippet with Product having an inStock() method:
// products.stream()
//         .filter(Product::inStock)
//         .limit(10)
//         .toList();
~~~

If you place `limit(10)` before `filter`, you may receive fewer than 10 products even though many in-stock products sit beyond the first 10 positions. Only do that when the requirement is truly “check the first 10 prioritized products”.

### 11.2. Paginating filtered search results

**Intent:** the second page of valid orders.

~~~java
// Illustrative snippet with Order having predicate isValid:
// orders.stream()
//       .filter(this::isValid)
//       .skip(pageSize)
//       .limit(pageSize)
//       .toList();
~~~

If you place `skip`/`limit` before `filter`, that is pagination of **all orders before filtering**, not pagination of search results. In addition, a stable order must be guaranteed; paginating continuously changing data may require cursor/keyset pagination instead of offset.

### 11.3. Getting the three earliest alerts in a time-sorted event stream

**Intent:** take the first three events satisfying the alert condition in chronological order.

~~~java
// Illustrative snippet with Event having timestamp and severity:
// events.stream()
//       .filter(Event::isAlert)
//       .limit(3)
//       .toList();
~~~

The condition for the result to truly be “earliest” is that the collection already has chronological encounter order. If the source is unordered, simply writing `limit(3)` does not create chronological meaning.

### 11.4. Selecting the top 5 lowest prices still available

**Intent:** filter eligible items, sort by price, and then select the 5 cheapest products.

~~~java
// Illustrative snippet with Product having price():
// products.stream()
//         .filter(Product::available)
//         .sorted(Comparator.comparing(Product::price))
//         .limit(5)
//         .toList();
~~~

Moving `limit(5)` before `sorted` will only sort and select among the first 5 arriving elements, missing better prices that appear later. If prices can be equal and a stable result is required, add a secondary criterion such as ID to the comparator.

## 12. When Do Both Approaches Produce the Same Result?

The two chains `filter(P).limit(k)` and `limit(k).filter(P)` can coincide on a **specific dataset**. For example:

~~~java
List<Integer> source = List.of(2, 4, 6, 7, 9);
List<Integer> a = source.stream().filter(n -> n % 2 == 0).limit(3).toList();
List<Integer> b = source.stream().limit(3).filter(n -> n % 2 == 0).toList();
// Both are [2, 4, 6].
~~~

However, if you change the source to `[1,2,3,4,5,6]`, the two approaches yield different results again. A proper test must include **at least one non-matching value before subsequent matching values**, in order to catch a misplaced `limit` bug.

General takeaway: never swap two operations just because they look syntactically similar. To transform a pipeline for optimization, you must prove equivalence under **all applicable data and business constraints**.

## 13. Common Mistakes and How to Fix Them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Placing `limit` before `filter` when k matching results are needed | May fall short of results even with plenty of data | Place `filter` before `limit` |
| Placing `skip` before `filter` when paginating filtered results | Empty pages or wrong element counts | Filter first, then `skip`/`limit` |
| Placing `limit` before `sorted` when top N by price/score is needed | Selects the wrong subset of elements | Sort before limiting |
| Assuming `limit(k)` always returns k elements | Misreads cases with few matching elements | Understand it means at most k |
| Assuming every Collection has a stable order | “First” has no deterministic meaning | Choose an ordered source or `sorted` |
| Adding `unordered()` when first elements are required | Results vary due to arbitrary selection | Only drop ordering if business allows |
| Guessing filter call counts from result count | Depends on optimizations, terminal, parallel | Test output; profile separately when needed |
| Using a predicate with side effects | Unpredictable results/side effects | Use stateless checks |
| Using `limit(-1)` | Throws `IllegalArgumentException` | Validate parameter n is non-negative |
| Reusing the same Stream object after `toList()` | Stream has already been consumed | Create a new Stream from the Collection |

### 13.1. Difference from takeWhile

`takeWhile(predicate)` keeps the **contiguous prefix** of an ordered stream that still satisfies the predicate and stops at the first element that does not. It is **not the same** as `filter(predicate)`, which skips non-matching elements and continues with matching elements that follow.

For example:

~~~java
List<Integer> values = List.of(2, 4, 5, 6, 8);
List<Integer> filtered = values.stream()
        .filter(n -> n % 2 == 0).toList(); // [2, 4, 6, 8]
List<Integer> prefix = values.stream()
        .takeWhile(n -> n % 2 == 0).toList(); // [2, 4]
~~~

This is an illustrative snippet inside a method, requiring `import java.util.List`. When combining with `limit`, determine whether you want to **filter all elements** or only **take a contiguous prefix**. For an unordered stream, `takeWhile` has different subset-selection semantics; do not reason in terms of a sequential prefix if encounter order has been discarded.

## 14. Checklist for Placing Operations in the Right Order

Before writing `filter` and `limit`, ask yourself:

1. **Which k elements do I want?** “The first k elements satisfying the condition” or “among the first k elements, which ones satisfy the condition?”
2. **Does the source have the right business encounter order?** If not, you need `sorted`/an ordered source before limiting.
3. **Should the filter be applied to the entire data domain or only to a selected window?** The answer determines where `filter` goes.
4. **Is this pagination?** If so, filter and establish ordering before computing offset/limit per the contract.
5. **Do I want top N by a ranking criterion?** You must sort by that criterion before limiting.
6. **Are exactly k results required?** If there is not enough matching data, you must specify returning fewer, reporting it, or querying another source; `limit` does not pad.
7. **Using parallel/unordered stream?** Check requirements on “first”, output ordering, and coordination cost.
8. **Are the predicate and source stable and free of concurrent mutation?** Ensure predictable behavior before discussing optimization.

## 15. Self-Check Questions

**Question 1.** With `List.of(1,2,3,4,5,6,7,8)`, what do the following two pipelines return?

~~~java
// A
values.stream().filter(n -> n % 2 == 0).limit(2).toList();
// B
values.stream().limit(2).filter(n -> n % 2 == 0).toList();
~~~

**Answer:** A returns `[2,4]`, B returns `[2]` because B only inspects the two elements 1 and 2.

**Question 2.** A list ordered newest → oldest contains 2 unpaid orders at the beginning. To get the 5 newest paid orders, which order of operations should be used?

**Answer:** `filter(Order::paid).limit(5)`, provided the source has newest → oldest encounter order. If the source is unordered, you must sort first.

**Question 3.** Why is `filter(...).skip(10).limit(10)` different from `skip(10).limit(10).filter(...)`?

**Answer:** the first takes a page of 10 results from the **filtered set**; the second takes a window from the entire source and then filters, which may leave very few elements.

**Question 4.** With `[7,2,6,3,8,4,5,1]`, the smallest even numbers are 2 and 4. To get the exact two smallest even numbers, should `sorted` be placed before or after `limit(2)`?

**Answer:** `filter(even).sorted().limit(2)`. If you limit before sorted, it only selects the first two even numbers that appear, which are 2 and 6.

**Question 5.** Can `parallelStream().filter(...).limit(3).toList()` on a `List` preserve the first three results satisfying the predicate?

**Answer:** Yes, for an ordered stream, `limit` selects the first elements in encounter order and `toList()` preserves that order. Callbacks may run at different times.

**Question 6.** Should `unordered()` be added before `limit(3)` to speed things up when the requirement is “the three newest orders”?

**Answer:** No; dropping the ordering constraint destroys the meaning of “newest”. Only use it if all matching elements are equivalent for the requirement.

**Question 7.** What does `limit(5)` do on a Stream that only has two elements?

**Answer:** returns at most the two available elements, without adding any elements.

**Question 8.** Why should you not count predicate invocations using a shared variable to assert how Stream optimizes execution?

**Answer:** a pipeline may be lazy, short-circuit, parallel, and optimized; side effects distort measurements and can also cause race issues. Verify the output and use proper profiling tools.

## 16. Reference Documentation

- [Java SE 17 — Stream.filter(Predicate), Stream.limit(long), Stream.skip(long)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html).
- [Java SE 17 — Stream API on encounter order, short-circuiting, and non-interference](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/package-summary.html).
- [Java SE 17 — Collection.stream() and parallelStream()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html).
- [Java SE 17 — Stream.takeWhile(Predicate)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#takeWhile(java.util.function.Predicate)).

**Conclusion:** **`filter(P).limit(k)` selects at most the first k matching elements**, whereas **`limit(k).filter(P)` examines only the first k elements and keeps the matching ones**. This ordering also governs pagination, top N selection, and behavior on parallel/unordered sources. Decide based on the business question first, and consider performance optimization afterward.
