# Pushing Filtering and Short-Circuiting to the Right Position

In the **Java Stream API**, performance often depends more on **the order of steps in the pipeline** than on the number of lines of code. `filter` removes unnecessary data, while short-circuiting operations such as `limit`, `findFirst`, or `anyMatch` avoid processing elements once enough results have been found. However, only reorder steps when **the semantics of the problem remain unchanged**.

This lesson belongs to the **Performance and Memory** chapter of the **JAVA_STREAM_API** module. It connects declarative, lazy pipeline writing with `map`, `reduce`, and `collect`, while pointing out effects on sorting, grouping, state, resources, and parallel streams.

## 1. Mechanisms to understand before optimizing

A Stream pipeline typically has three parts:

```text
Source (List, file, ...) → intermediate operations → terminal operation
                           filter / map / sorted     findFirst / collect / count
```

- Intermediate operations like `filter`, `map`, `sorted`, `distinct`, and `limit` are **lazy**: calling them only builds the pipeline without traversing the source immediately.
- Terminal operations like `toList`, `collect`, `reduce`, `count`, or `findFirst` trigger processing. In a typical sequential pipeline, stateless operations like `filter` and `map` are fused to process element by element, rather than creating an intermediate list after each step.
- Some stateful operations (`sorted`, `distinct`, and certain uses of `limit`, `skip`) may need to buffer data or coordinate across multiple elements. This is where reducing the number of elements **before** an expensive operation often brings noticeable benefits.
- Short-circuiting is the **ability** to stop once enough information is gathered, not a promise that predicate invocations will always equal the exact number of initial elements needed. Parallel pipelines or preceding stateful operations may process extra elements.

For example, the following pipeline does not create three intermediate lists:

```java
List<Integer> result = numbers.stream()
    .filter(n -> n > 0)
    .map(n -> n * 2)
    .limit(3)
    .toList();
```

In a sequential, ordered stream without operations that block short-circuiting, the pipeline can finish after finding **3 positive numbers**, instead of reading the entire source.

## 2. Placing `filter` before expensive operations

Suppose you have a list of orders and need the 20 **paid** orders with the highest value. Both approaches below give the same result when the comparator and predicate are pure, but the amount of data that needs sorting differs.

```java
record Order(long id, boolean paid, int totalCents) {}

Comparator<Order> byValueDescending =
    Comparator.comparingInt(Order::totalCents).reversed();

// Sort everything first, then filter.
List<Order> slower = orders.stream()
    .sorted(byValueDescending)
    .filter(Order::paid)
    .limit(20)
    .toList();

// Filter first to shrink the set that needs sorting.
List<Order> better = orders.stream()
    .filter(Order::paid)
    .sorted(byValueDescending)
    .limit(20)
    .toList();
```

If the source has `n` orders and only `m` are paid (`m` much smaller than `n`), typical sorting cost drops from roughly `O(n log n)` to `O(m log m)`. `sorted` still must prepare the set to be sorted before emitting the first element, so placing `limit(20)` after `sorted` **does not** make the sort look at only 20 orders. Working memory for sorting also depends on the number of elements reaching `sorted`.

Practical rule: place filters that are **cheap, highly selective, and independent of later steps** before `sorted`, `distinct`, expensive mappings, and grouping collectors. For instance, filtering valid orders before `collect(groupingBy(...))` reduces the amount of data inserted into groups.

### Filtering before `map` when possible

```java
// Need to build reports for up to 50 paid orders meeting the threshold.
List<Report> reports = orders.stream()
    .filter(Order::paid)
    .filter(o -> o.totalCents() >= 100_000)
    .limit(50)
    .map(this::buildReport)
    .toList();
```

Here `buildReport` is assumed to be a side-effect-free, expensive transformation that does not change element count. Placing `limit` before `map` avoids building reports beyond the 50 orders needed. If you must filter by an **attribute that only appears after mapping**, you cannot arbitrarily pull the predicate earlier; you must prove or rewrite an equivalent predicate on the original data.

A small but useful detail: for independent conditions, it is usually better to check the cheap condition before the expensive one. For example, `.filter(o -> o.paid() && expensiveCheck(o))` leverages short-circuiting of the `&&` operator. Changing order can alter behavior if functions have side effects or throw exceptions; predicates in a Stream should be pure and non-interfering with the source.

## 3. `limit` before vs. after `filter` are two different problems

Consider four orders in exact encounter order:

```java
List<Order> sample = List.of(
    new Order(1, false, 900),
    new Order(2, true,  500),
    new Order(3, true, 1000),
    new Order(4, true,  700)
);

List<Long> firstTwoPaid = sample.stream()
    .filter(Order::paid)
    .limit(2)
    .map(Order::id)
    .toList(); // [2, 3]

List<Long> paidAmongFirstTwo = sample.stream()
    .limit(2)
    .filter(Order::paid)
    .map(Order::id)
    .toList(); // [2]
```

- `filter(...).limit(2)` means **find at most two elements matching the condition**.
- `limit(2).filter(...)` means **examine only the first two elements from the source and then filter them**.

Neither is universally “faster while giving the same answer”; you must choose based on business requirements. Likewise, moving `limit` before `sorted` turns “the 20 largest orders” into “sort the first 20 orders”, which is completely different.

Conversely, for a pure, one-to-one, order-preserving `map`, you can consider pushing `limit` before it to avoid mapping redundant elements:

```java
// When only the first 20 records after filtering are needed:
List<String> labels = orders.stream()
    .filter(Order::paid)
    .limit(20)
    .map(o -> "Order #" + o.id())
    .toList();
```

Do not apply this reasoning to `flatMap` if each input element produces a varying number of output elements: `limit` before `flatMap` counts **parent elements**, whereas `limit` after `flatMap` counts **child elements**.

## 4. Choosing the right short-circuiting operation for the goal

| Goal | Appropriate terminal/intermediate operation | Termination condition |
| --- | --- | --- |
| Only need to know if at least one element matches | `anyMatch(predicate)` | One `true` result found |
| Check whether all elements match | `allMatch(predicate)` | Encounter a `false` element |
| Check whether no elements match | `noneMatch(predicate)` | Encounter a `true` element |
| Get the first element by encounter order | `findFirst()` | First element determined |
| Get any single element | `findAny()` | One suitable element found |
| Get at most `k` elements | `limit(k)` | At most `k` output elements produced |
| Get contiguous prefix matching a condition | `takeWhile(predicate)` | First non-matching element reached, on an ordered stream |

For example, if you only need to check whether a large, paid order exists, do not build a result list and check emptiness:

```java
boolean exists = orders.stream()
    .anyMatch(o -> o.paid() && o.totalCents() >= 100_000);
```

`.filter(...).findFirst().isPresent()` can also short-circuit, but `anyMatch` directly expresses the “exists or not” intent. `allMatch` and `noneMatch` both return `true` on an empty stream by logical convention; handle that separately if the problem requires at least one element to exist.

When you need **the first order**, choose `findFirst` if source order matters. `findAny` can reduce coordination overhead in parallel streams when **any** element is acceptable. Do not promise `findAny` is always faster, and do not assume stable results across runs.

## 5. Distinguishing `filter` from `takeWhile` and `dropWhile`

Since Java 9, `takeWhile` and `dropWhile` support prefix-based stream processing; they **do not** replace `filter` in all cases.

```java
List<Integer> values = List.of(2, 4, 7, 6, 8);

List<Integer> filtered = values.stream()
    .filter(n -> n % 2 == 0)
    .toList(); // [2, 4, 6, 8]

List<Integer> prefix = values.stream()
    .takeWhile(n -> n % 2 == 0)
    .toList(); // [2, 4]

List<Integer> remainder = values.stream()
    .dropWhile(n -> n % 2 == 0)
    .toList(); // [7, 6, 8]
```

`takeWhile` is especially suited when **data is ordered** and the condition describes a prefix, such as events sorted by timestamp taking only up to a cutoff. If data is not sorted as assumed, `takeWhile` stops at the first violating element and may skip valid elements later. On an unordered stream, the subset taken by `takeWhile`/`dropWhile` differs from a deterministic prefix; do not use them instead of `filter` to compute position-exact results.

## 6. “Barriers” that can negate short-circuiting benefits

A lazy pipeline does not mean every step can process one element at a time and emit immediately:

```java
// Must sort matching elements before knowing which is smallest.
Optional<Order> smallestPaid = orders.stream()
    .filter(Order::paid)
    .sorted(Comparator.comparingInt(Order::totalCents))
    .findFirst();
```

If you only need the **minimum value**, use a dedicated reduction operation, which typically avoids sorting the whole set:

```java
Optional<Order> smallestPaid = orders.stream()
    .filter(Order::paid)
    .min(Comparator.comparingInt(Order::totalCents));
```

`min` still must inspect matching candidates to ensure the right result; the main benefit is not needing to sort the entire set. For finite data, `min` typically takes `O(n)` comparisons and minimal extra memory, whereas `sorted` usually costs `O(n log n)` plus a sorting buffer.

Common barriers:

- `sorted` requires substantial state; a trailing `limit` does not guarantee avoiding sorting earlier elements.
- `distinct` tracks previously seen elements; for sources with high cardinality, state can grow significantly.
- `skip(k)` and `limit(k)` on **ordered** parallel streams can require coordination to preserve exact positions.
- `collect`/`groupingBy` normally must receive elements through the end of the pipeline; pass only genuinely needed elements into the collector. For some source/terminal combinations, the JDK can optimize counting or skip intermediate steps that do not affect the result, so do not use side effects in `peek` to deduce exactly how many elements were processed.

If you want **top K** over a very large source under strict memory limits, consider a heap algorithm of size K or a specialized collector instead of `sorted(...).limit(k)`; that is an algorithmic change requiring careful handling of comparators, ties, ordering, and collector associativity.

## 7. Prove that reordering preserves the result

| Reordering | Recommended? | Conditions to consider |
| --- | --- | --- |
| `filter → sorted` instead of `sorted → filter` | Usually beneficial | Predicate does not depend on position/rank; comparator and predicate are pure; tie handling remains preserved |
| `filter → map` instead of `map → filter` | Conditional | An equivalent predicate exists on the input, and mapping need not run on discarded elements |
| `limit → map` instead of `map → limit` | Conditional | Map is pure, one-to-one, order-preserving, and does not need to run on dropped elements |
| `limit → filter` instead of `filter → limit` | Usually wrong | Changes “up to K matching elements” to “filter within the first K elements” |
| `limit → sorted` instead of `sorted → limit` | Usually wrong | Changes global top K to top K of the initial slice |
| `filter ↔ distinct` | Inspect carefully | Predicate must yield the same result for elements considered equal; representative selection and order may affect the outcome |
| `takeWhile` instead of `filter` | Only when intended | Requires a contiguous prefix, usually relying on a suitable encounter order |

For example, `filter` and `distinct` are not always safely interchangeable: two objects considered equal by `equals` that differ in the filtered property can cause `distinct().filter(...)` to keep a non-matching representative, while `filter(...).distinct()` keeps another element. Similarly, if calling `map`, predicates, or comparators causes side effects, throws data-dependent exceptions, or depends on external state, reordering can also alter observable effects. The Stream API encourages **stateless, non-interfering** functions (do not modify the source being traversed).

## 8. Sequential streams, parallel streams, and encounter order

For an ordered list, `filter(...).limit(10)` expresses “the first 10 matching elements”. In a sequential pipeline, it typically allows pulling from the source to stop early. In `parallelStream()`, guaranteeing **first** may require threads to coordinate, buffer, or process extra elements. Depending on source, data size, predicate cost, and `Spliterator` characteristics (`ORDERED`, `SIZED`, `SUBSIZED`, ...), the parallel version can be slower than sequential.

```java
// Only use if requirements allow taking any 10 matching orders.
List<Order> anyTen = orders.parallelStream()
    .unordered()
    .filter(Order::paid)
    .limit(10)
    .toList();
```

`unordered()` drops the encounter order requirement for downstream steps; it **does not** shuffle data in any predictable way. This sometimes helps `limit`/`findAny` run more efficiently in parallel, but is unsuitable when you need “the first 10 orders”, “first chronologically”, or reproducible fixed results. Do not enable `parallel()` just because data is large; measure with real workloads and data access patterns.

If you use a stateful custom `Gatherer` or collector, separately examine its short-circuiting capability, retained data volume, and combining rules under parallel execution. Do not assume optimizations of a simple `filter/map` chain apply identically to these stateful steps.

## 9. Short-circuiting with resource-holding sources

Reading a file line by line is a case where short-circuiting saves both time and I/O:

```java
Path path = Path.of("events.log");

try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    List<String> firstHundredNonBlank = lines
        .filter(line -> !line.isBlank())
        .limit(100)
        .toList();

    // Use firstHundredNonBlank within the required scope.
}
```

Use `try-with-resources` to close the stream and file even when `limit` stops reading before EOF, or when a terminal operation throws an error. Do not store the stream and use it after closing; do not read the whole file with `readAllLines` if the goal is just the first few matching lines. Actual short-circuiting on real sources also depends on buffering mechanisms, `Spliterator` characteristics, and preceding steps.

## 10. Measuring and deciding in real projects

1. **State the required result clearly**: “first K matching elements”, “K largest elements”, “exists”, or “all elements match”. These goals lead to different pipelines.
2. **Identify expensive or stateful steps**: object-creating `map`, I/O calls, `sorted`, `distinct`, `groupingBy`, and custom collectors. Place independent `filter` operations before them if semantics remain identical.
3. **Verify semantics with edge cases**: empty source, fewer than K matches, many duplicates, first element failing, data not in assumed order; also check any side effects that should be eliminated.
4. **Measure after getting a correct solution**: use JMH for microbenchmarking, warm up the JVM, keep input data and result consumption equivalent; observe throughput, allocation, and GC, considering both large/small datasets and sequential/parallel execution. Do not rely on a single `System.nanoTime()` measurement to draw conclusions.
5. **Measure holistically before complicating code**: if the predicate is very cheap or the source is small, gains may be negligible. Readability, business correctness, and maintainability remain key criteria.

### Self-check exercise

With the sample order list in section 3, predict the results of the following three pipelines and run them to verify:

```java
sample.stream().filter(Order::paid).limit(2).map(Order::id).toList();
sample.stream().limit(2).filter(Order::paid).map(Order::id).toList();
sample.stream().filter(Order::paid)
    .sorted(Comparator.comparingInt(Order::totalCents).reversed())
    .limit(2).map(Order::id).toList();
```

**Answer:** `[2, 3]`, `[2]`, and `[3, 4]`, respectively. The last pipeline sorts, so the answer reflects the two highest-value paid orders rather than the first two paid orders encountered.

**Takeaway when designing pipelines:** filter early when conditions are independent, short-circuit according to the exact goal, and always check stateful steps/encounter order before reordering. With Streams, performance optimization is only valid when **the observable result remains correct**.
