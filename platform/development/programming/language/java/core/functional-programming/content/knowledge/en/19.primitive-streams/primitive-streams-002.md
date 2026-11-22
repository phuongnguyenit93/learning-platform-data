# `range()` and `rangeClosed()` in Java Primitive Streams

## 1. Problem and Objectives

In Java programming, we often need a sequence of consecutive integers to assign sequence numbers, iterate over array indices, generate test codes, loop through integer days/values, or sum an interval. Writing a `for` loop is a familiar approach, but since Java 8, **`IntStream` and `LongStream`** provide factory methods dedicated to generating number sequences: `range()` and `rangeClosed()`.

The core difference lies in the **upper bound**:

- `range(startInclusive, endExclusive)`: includes the start point, **excludes** the end point, corresponding to the interval **[start, end)**.
- `rangeClosed(startInclusive, endInclusive)`: includes **both** endpoints when start is not greater than end, corresponding to the interval **[start, end]**.

Example:

~~~java
IntStream.range(2, 6);       // 2, 3, 4, 5
IntStream.rangeClosed(2, 6); // 2, 3, 4, 5, 6
~~~

These are two expressions that return a Stream, **not a standalone program**. They do not print anything to the console yet; a terminal operation such as `toArray()`, `sum()`, `count()`, `forEach(...)`, or `boxed().toList()` is needed to collect or observe the results.

After this lesson, learners should be able to:

1. Correctly read the parameters `startInclusive`, `endExclusive`, and `endInclusive`.
2. Distinguish between `IntStream.range`, `IntStream.rangeClosed`, `LongStream.range`, and `LongStream.rangeClosed`.
3. Accurately predict cases with equal bounds, reversed bounds, and negative numbers.
4. Choose a **half-open** range to iterate indices `0` to `length - 1`, and choose a **closed** range when the business logic includes the last value.
5. Combine with `map`, `filter`, `mapToObj`, `sum`, `count`, `boxed`, and `parallel`.
6. Distinguish a sequence with a **step of 1** from a sequence requiring a step other than 1.
7. Avoid off-by-one errors, assuming a range counts down automatically, integer overflow, collecting excessively large sequences into memory, and relying on the order of `parallel().forEach`.
8. Compile and run standalone examples using JDK 17.

## 2. Package and Return Types

Both methods are **static factory methods** located on the two primitive stream interfaces:

| API | Parameter types | Return type | Meaning |
| --- | --- | --- | --- |
| `IntStream.range(int startInclusive, int endExclusive)` | `int, int` | `IntStream` | `start <= n < end` |
| `IntStream.rangeClosed(int startInclusive, int endInclusive)` | `int, int` | `IntStream` | `start <= n <= end` |
| `LongStream.range(long startInclusive, long endExclusive)` | `long, long` | `LongStream` | `start <= n < end` |
| `LongStream.rangeClosed(long startInclusive, long endInclusive)` | `long, long` | `LongStream` | `start <= n <= end` |

Commonly used imports:

~~~java
import java.util.stream.IntStream;
import java.util.stream.LongStream;
~~~

There is no equivalent `DoubleStream.range(...)` or `DoubleStream.rangeClosed(...)` in the standard Java 17 API. For a sequence of `double` values with a clear step, you can generate sequence numbers with `IntStream.range(...)` and then `mapToDouble(...)`; for floating-point numbers, you must pay attention to representation error and should not control the termination condition by arbitrary floating-point accumulation.

### Why Primitive Streams?

`IntStream` holds elements as primitive `int`, and `LongStream` holds `long`. Unlike `Stream<Integer>`/`Stream<Long>`, these primitive pipelines can reduce boxing/unboxing and provide arithmetic terminal operations such as `sum()`, `average()`, and `summaryStatistics()`.

When an API requires objects, convert from primitive to object intentionally:

~~~java
List<Integer> numbers = IntStream.range(1, 5)
        .boxed()
        .toList(); // [1, 2, 3, 4]
~~~

This snippet is placed inside a method with `import java.util.List;`. `boxed()` converts each `int` into an `Integer` and returns `Stream<Integer>`; boxing is unnecessary if the pipeline only computes a sum or a count.

## 3. `range()` — Half-Open Interval `[start, end)`

### 3.1. Lower Bound Included, Upper Bound Excluded

~~~java
int[] values = IntStream.range(2, 6).toArray();
System.out.println(java.util.Arrays.toString(values));
~~~

Output:

~~~text
[2, 3, 4, 5]
~~~

The number `2` appears because `startInclusive = 2`. The number `6` does not appear because `endExclusive = 6`. This can be understood via a traditional loop:

~~~java
for (int n = 2; n < 6; n++) {
    System.out.println(n);
}
~~~

Both representations produce the same sequence of values `2, 3, 4, 5` in ascending order. With the `for` loop, each print statement runs directly; with `IntStream.range`, we create a source and optionally process it with a pipeline. The two snippets above illustrate the same boundary conditions, not a claim that all execution approaches have the same cost.

### 3.2. Why Is a Half-Open Interval Convenient?

In Java, arrays, `List`, `String`, and many index-slice APIs use **inclusive start, exclusive end**:

~~~text
array length = 4
valid indices: 0, 1, 2, 3
IntStream.range(0, 4) --> 0, 1, 2, 3
~~~

Using `range(0, array.length)` lets you write the exact boundary without subtracting 1. For a sequence from 0 to `n - 1`, the number of elements is `n` if `n >= 0`.

If `start < end` and the difference `end - start` is computed without overflowing the numeric domain under consideration, the mathematical number of elements is `end - start`. If `start >= end`, the result is empty. **Do not manually compute the size using `int` subtraction when the two bounds may lie at extreme limits** because the difference can overflow; `count()` returns `long` and avoids many manual size-calculation bugs.

### 3.3. Example with Negative Numbers

~~~java
int[] values = IntStream.range(-2, 3).toArray();
System.out.println(java.util.Arrays.toString(values));
~~~

Output:

~~~text
[-2, -1, 0, 1, 2]
~~~

`range` is not restricted to positive numbers or starting at 0. The condition is a sequence **increasing by 1** from the lower bound, excluding the upper bound. Use it when iterating over relative offsets, adjusted indices, or a mathematical number domain.

## 4. `rangeClosed()` — Closed Interval `[start, end]`

### 4.1. Both Bounds Are Present

~~~java
int[] values = IntStream.rangeClosed(2, 6).toArray();
System.out.println(java.util.Arrays.toString(values));
~~~

Output:

~~~text
[2, 3, 4, 5, 6]
~~~

This is semantically equivalent to:

~~~java
for (int n = 2; n <= 6; n++) {
    System.out.println(n);
}
~~~

Note that a `for` loop with a `<=` condition on `int` **can overflow** if the upper bound is `Integer.MAX_VALUE` and the loop body allows the variable to increment past the limit. `IntStream.rangeClosed` is designed by its API contract to include the last value without requiring the caller to write `end + 1`. Therefore, **do not** mechanically replace `rangeClosed(a,b)` with `range(a,b+1)`.

### 4.2. When Should You Use an Inclusive Upper Bound?

- Iterating over sequence numbers from `1` to `n`, including `n`.
- Summing integers from `1` to `10`: `IntStream.rangeClosed(1,10).sum()` returns `55`.
- Testing all integer values from a low threshold to a high threshold, including both endpoints.
- Generating multiplication tables, levels, or counters with the convention "from A **to** B, inclusive".

Example:

~~~java
int sum = IntStream.rangeClosed(1, 5).sum();
System.out.println(sum); // 15
~~~

The number of elements in a closed interval with `start <= end` is `end - start + 1` **mathematically**. As with half-open intervals, computing the formula directly with `int` can overflow for very large or very small bounds.

## 5. Equal Bounds, Reversed Bounds, and Empty Intervals

This comparison table applies to both `IntStream` and `LongStream` (with appropriate bound values):

| Call | Resulting sequence | Why |
| --- | --- | --- |
| `range(2, 6)` | `2, 3, 4, 5` | Excludes `6` |
| `rangeClosed(2, 6)` | `2, 3, 4, 5, 6` | Includes `6` |
| `range(3, 3)` | Empty | `3 <= n < 3` has no solution |
| `rangeClosed(3, 3)` | `3` | Both bounds coincide and are included |
| `range(6, 2)` | Empty | Lower bound is greater than upper bound |
| `rangeClosed(6, 2)` | Empty | Does not count down automatically |
| `range(-2, 3)` | `-2, -1, 0, 1, 2` | Contains negative numbers, 0, and positive numbers below `3` |
| `rangeClosed(-2, 3)` | `-2, -1, 0, 1, 2, 3` | Includes `3` |
| `range(0, 0)` | Empty | Useful when input size is 0 |
| `rangeClosed(0, 0)` | `0` | Inappropriate if you want to represent 0 iterations |

Pay special attention: `range(0, n)` runs **n times if n is non-negative**, whereas `rangeClosed(0, n)` runs **n + 1 times** when `n >= 0`. For array index iteration, using `rangeClosed(0, array.length)` usually causes an out-of-bounds access on the last element.

### No Negative Step

Both factory methods produce a **sequence increasing by 1** in natural order. Calling `rangeClosed(5, 1)` does not produce `5, 4, 3, 2, 1`; it produces an empty Stream. If you need to count down, you must express a transformation or use an appropriate `IntStream.iterate` (see section 10).

## 6. Complete Java 17 Program

This program demonstrates half-open intervals, closed intervals, equal/reversed bounds, array traversal, summing, a step other than 1, and collecting results from a parallel Stream.

Create the file **`RangeDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.stream.IntStream;
import java.util.stream.LongStream;

public class RangeDemo {

    static void show(String label, IntStream values) {
        System.out.println(
                label + "=" + Arrays.toString(values.toArray()));
    }

    public static void main(String[] args) {
        show("range", IntStream.range(2, 6));
        show("rangeClosed", IntStream.rangeClosed(2, 6));
        show("same-open", IntStream.range(3, 3));
        show("same-closed", IntStream.rangeClosed(3, 3));
        show("reverse", IntStream.rangeClosed(6, 2));

        int[] scores = {4, 7, 9};
        List<String> indexed = IntStream
                .range(0, scores.length)
                .mapToObj(i -> i + ":" + scores[i])
                .toList();

        System.out.println("indexed=" + indexed);
        System.out.println(
                "sum=" + LongStream.rangeClosed(1, 10).sum());

        show("step2", IntStream.iterate(
                1, n -> n < 9, n -> n + 2));

        List<Integer> parallel = IntStream.range(0, 6)
                .parallel()
                .boxed()
                .toList();
        System.out.println("parallel=" + parallel);
    }
}
~~~

Run from the directory containing `RangeDemo.java` with JDK 17+:

~~~bash
javac -encoding UTF-8 RangeDemo.java
java RangeDemo
~~~

**Exact stdout:**

~~~text
range=[2, 3, 4, 5]
rangeClosed=[2, 3, 4, 5, 6]
same-open=[]
same-closed=[3]
reverse=[]
indexed=[0:4, 1:7, 2:9]
sum=55
step2=[1, 3, 5, 7]
parallel=[0, 1, 2, 3, 4, 5]
~~~

### Line-by-Line Explanation

1. `range(2,6)` excludes `6`, whereas `rangeClosed(2,6)` includes `6`.
2. When both bounds equal `3`, the half-open interval is empty; the closed interval has exactly one element `3`.
3. With start bound `6` greater than end bound `2`, `rangeClosed` returns empty and does not count backward.
4. `range(0, scores.length)` generates indices `0,1,2`, then `mapToObj` uses the index to fetch the value and form the strings `0:4`, `1:7`, `2:9`.
5. `LongStream.rangeClosed(1,10).sum()` returns a `long` with the value `55`.
6. `IntStream.iterate(1, n -> n < 9, n -> n+2)` produces `1,3,5,7`: used when the step is different from `1`.
7. `parallel()` allows the pipeline to execute in parallel, but the `range(0,6)` source still has an **encounter order**. `boxed().toList()` preserves this order in the result, so it prints from `0` to `5`.

The program uses small sequences to avoid memory pressure. Each `show` call consumes the Stream exactly once via `toArray()`; it does not reuse a Stream that has already been consumed.

## 7. Traversing Array and List Indices with `range()`

### 7.1. Reading Elements by Array Index

~~~java
String[] names = {"An", "Binh", "Chi"};

List<String> numbered = IntStream.range(0, names.length)
        .mapToObj(i -> i + " - " + names[i])
        .toList();

System.out.println(numbered);
~~~

Output:

~~~text
[0 - An, 1 - Binh, 2 - Chi]
~~~

This is a **code snippet inside a method** with `java.util.List` and `IntStream` imported. Given `names.length = 3`, `range(0,3)` produces `0,1,2`. Index `3` is absent; therefore it cannot cause an `ArrayIndexOutOfBoundsException` from the range bounds.

If the array is empty, `range(0,0)` returns an empty Stream and `toList()` returns an empty list. This is an advantage of half-open intervals in collection processing.

### 7.2. Traversing a List When You Actually Need the Index

~~~java
List<String> items = List.of("red", "green", "blue");

List<String> labels = IntStream.range(0, items.size())
        .mapToObj(i -> i + "=" + items.get(i))
        .toList();

System.out.println(labels);
~~~

Output:

~~~text
[0=red, 1=green, 2=blue]
~~~

If you only need the values, `items.stream().map(...)` is usually clearer; use `IntStream.range` when **the index carries meaning** (numbering, zipping two same-sized structures, checking positions). For certain `List` implementations without efficient random access like `LinkedList`, repeated `get(i)` calls can be much more expensive than sequential iteration. Do not assume the Stream style is faster than a loop by default.

### 7.3. Valuable Use Cases for `mapToObj`

On `IntStream`, `mapToObj` transforms each `int` into an object; `boxed()` only converts `int` to `Integer`. Compare:

~~~java
List<Integer> indices = IntStream.range(0, 3)
        .boxed()
        .toList();

List<String> tags = IntStream.range(0, 3)
        .mapToObj(i -> "item-" + i)
        .toList();
~~~

`indices` receives `[0,1,2]`, while `tags` receives `["item-0","item-1","item-2"]`. If the goal is purely numeric computation, use `IntStream` directly to avoid unnecessary object creation.

## 8. When to Choose `rangeClosed()` Instead of `range()`

### 8.1. Summing Integers in an Interval Including the Upper Bound

~~~java
int total = IntStream.rangeClosed(1, 10).sum();
System.out.println(total); // 55
~~~

This is appropriate when the mathematical requirement is the sum from `1` **through `10`**. Using `range(1,10)` would only sum `1..9` and return `45`, which is wrong due to an off-by-one error.

### 8.2. Multiplication Table

~~~java
int multiplier = 7;
List<String> table = IntStream.rangeClosed(1, 3)
        .mapToObj(n -> multiplier + " x " + n
                + " = " + (multiplier * n))
        .toList();

table.forEach(System.out::println);
~~~

Output:

~~~text
7 x 1 = 7
7 x 2 = 14
7 x 3 = 21
~~~

This is a code snippet inside a method. `multiplier` is effectively final locally, so the lambda is allowed to use it. If you want up to `10`, change the bound `3` to `10`.

### 8.3. When Both Endpoints Matter, Yet a Half-Open Interval Is Preferred

In many interval-partitioning algorithms, half-open intervals are more logical: two adjacent segments `[0,5)` and `[5,10)` do not overlap and are easy to merge and compute sizes for. You do not necessarily have to use `rangeClosed` just because a problem statement uses the word "to"; you must understand **whether the data includes the endpoint or not**.

For example, "valid indices of an array with length = 10" should use `range(0,10)`, even though people often say "from 0 to 9". Conversely, "integers from 1 to 10, inclusive" should use `rangeClosed(1,10)`.

## 9. `LongStream` and Numeric Limits

### 9.1. `long` Sequences

~~~java
long[] ids = LongStream.range(100L, 104L).toArray();
System.out.println(java.util.Arrays.toString(ids));
~~~

Output:

~~~text
[100, 101, 102, 103]
~~~

`LongStream.rangeClosed(100L,104L)` also includes `104`. Use `LongStream` when the values to represent exceed the `int` range (−2^31 to 2^31−1) or when the domain uses `long` for integer IDs/offsets/timestamps. Simply switching `IntStream` to `LongStream` does not change inclusive/exclusive bound semantics.

### 9.2. `rangeClosed` Is Safe at the Endpoint, Not Against Pipeline Size

~~~java
long max = Long.MAX_VALUE;
long[] tail = LongStream.rangeClosed(max - 1, max)
        .toArray();

System.out.println(java.util.Arrays.toString(tail));
~~~

Output:

~~~text
[9223372036854775806, 9223372036854775807]
~~~

`rangeClosed` does not require writing `max + 1`, which would overflow to `Long.MIN_VALUE`. However, **never** call `toArray()`, `boxed().toList()`, or `forEach(...)` carelessly on a huge range: a Stream only represents the sequence, it does not eliminate processing and storage costs.

### 9.3. Counting Elements and Overflow

`count()` returns `long`, not `int`:

~~~java
long count = IntStream.rangeClosed(1, 5).count();
System.out.println(count); // 5
~~~

An `int` interval can have more than `Integer.MAX_VALUE` elements. For example, mathematically `rangeClosed(Integer.MIN_VALUE,Integer.MAX_VALUE)` contains **2^32 elements**, which cannot be counted accurately in an `int` variable. Use a `long` result when you need the element count. However, do not create collections materializing billions of values just to demonstrate a formula.

With `LongStream` at extreme bounds, even the theoretical element count can exceed the representable range of `long`. Do not assume that `count()`, `sum()`, or every algorithm can accurately represent an arbitrarily wide `long` range; you must determine the valid domain of your application and potentially use `BigInteger` or split the range if the problem requires exact counting of extremely large quantities.

### 9.4. `sum()` and Overflow

`IntStream.sum()` returns `int`; `LongStream.sum()` returns `long`. There is no mathematical guarantee of "no overflow." For example, the sum of `1..100000` exceeds the `int` limit:

~~~java
long sum = IntStream.rangeClosed(1, 100_000)
        .mapToLong(n -> n)
        .sum();

System.out.println(sum); // 5000050000
~~~

Here `mapToLong` enables computing in `long`; the result `5,000,050,000` does not fit in `int`. For very large `long` sums, you still need to consider `long` overflow or use `BigInteger`/exact arithmetic according to the business domain.

## 10. Sequences with Step Other Than 1 or Counting Down

`range` and `rangeClosed` always advance by **1 unit at a time**. They do not accept a `step` argument. If you need even numbers, odd numbers, or a descending sequence, there are two basic options.

### 10.1. Transforming or Filtering an Interval

~~~java
int[] evens = IntStream.rangeClosed(1, 10)
        .filter(n -> n % 2 == 0)
        .toArray();

System.out.println(java.util.Arrays.toString(evens));
~~~

Output:

~~~text
[2, 4, 6, 8, 10]
~~~

This approach is easy to understand and reasonable for small ranges. However, it generates/inspects elements of the original sequence and then discards unwanted values. For large steps or wide ranges, it can be more efficient to generate only the desired values.

### 10.2. `IntStream.iterate` with a Predicate and Step

Since Java 9, `IntStream.iterate(seed, hasNext, next)` can generate a sequence with a condition and an update rule:

~~~java
int[] odds = IntStream.iterate(1,
        n -> n < 9,
        n -> n + 2)
        .toArray();

System.out.println(java.util.Arrays.toString(odds));
~~~

Output:

~~~text
[1, 3, 5, 7]
~~~

Descending sequence:

~~~java
int[] backward = IntStream.iterate(5,
        n -> n >= 1,
        n -> n - 1)
        .toArray();

System.out.println(java.util.Arrays.toString(backward));
~~~

Output:

~~~text
[5, 4, 3, 2, 1]
~~~

You must **ensure the predicate eventually terminates**. If the update step overflows, the condition may change unexpectedly or fail to stop as intended; guard extreme bounds. For simple linear countdowns, a `for` loop is often still more readable and safer.

### 10.3. Generating a Sequence with Step `k` by Mapping Indices

~~~java
int start = 10;
int step = 3;
int count = 4;

int[] values = IntStream.range(0, count)
        .map(i -> start + i * step)
        .toArray();

System.out.println(java.util.Arrays.toString(values));
~~~

Output:

~~~text
[10, 13, 16, 19]
~~~

This code represents `count` positions and maps them to domain values; it is convenient when the number of elements is known in advance. However, the expression `start + i * step` can overflow `int`; for large numbers, use `long`, `Math.multiplyExact`/`Math.addExact`, or appropriate input bounds.

## 11. Combining `range` with Primitive Stream Operations

### 11.1. `filter` and `map`

~~~java
int[] squares = IntStream.rangeClosed(1, 6)
        .filter(n -> n % 2 == 0)
        .map(n -> n * n)
        .toArray();

System.out.println(java.util.Arrays.toString(squares));
~~~

Output:

~~~text
[4, 16, 36]
~~~

Order: generate `1..6`, keep `2,4,6`, square them into `4,16,36`. The `filter`/`map` operations in this example process `int` directly without boxing.

### 11.2. `sum`, `average`, `min`, `max`

~~~java
int sum = IntStream.range(1, 5).sum();      // 10
long n = IntStream.range(1, 5).count();     // 4
double average = IntStream.range(1, 5)
        .average().orElse(0.0);             // 2.5
~~~

These are **independent pipelines**, each line creating a new Stream. `average()` returns `OptionalDouble` because an empty Stream has no average value. Choosing `orElse(0.0)` is merely the policy of this example; it does not mean the average of an empty set is mathematically `0`.

For `min()`/`max()`, the result is `OptionalInt` or `OptionalLong`; you must handle the empty-interval case properly.

### 11.3. `summaryStatistics`

~~~java
IntSummaryStatistics stats =
        IntStream.rangeClosed(1, 5).summaryStatistics();

System.out.println(stats.getCount()); // 5
System.out.println(stats.getMin());   // 1
System.out.println(stats.getMax());   // 5
~~~

This snippet requires importing `java.util.IntSummaryStatistics`. `summaryStatistics` is useful when you need multiple statistics from the same pipeline; you cannot reuse a consumed Stream to call `sum()` and then `max()` one after another.

### 11.4. Do Not Reuse a Consumed Stream

~~~java
IntStream stream = IntStream.range(1, 5);
long count = stream.count();
// int sum = stream.sum(); // Wrong: the stream has already been consumed.
~~~

To compute two results, create two new Stream sources or use `summaryStatistics()`. After a terminal operation runs, do not call further terminal/intermediate operations on the same Stream as if it were a list that can be traversed multiple times.

### 11.5. Lazy Execution and `count()`

`range` creates a Stream source that can be processed by a lazy pipeline. Intermediate operations such as `map` and `filter` do not necessarily run at declaration time. `count()` or `toArray()` are terminal operations.

However, `count()` can be optimized to compute the element count directly when the source size is known and intermediate steps do not change the number of elements. **Do not rely on side effects in `map` to count lambda invocations**; this is an anti-pattern because optimizations may skip executing transformations that are not needed to compute the result.

## 12. `parallel()` and Ordering

`IntStream.range` and `LongStream.range` produce sequences with a natural ascending order. You can call `parallel()`:

~~~java
List<Integer> numbers = IntStream.range(0, 6)
        .parallel()
        .boxed()
        .toList();

System.out.println(numbers); // [0, 1, 2, 3, 4, 5]
~~~

`parallel()` changes the execution strategy; it **does not remove the inherent encounter order** of the source. `toList()` collects results in encounter order when the Stream is ordered.

However:

~~~java
IntStream.range(0, 6)
        .parallel()
        .forEach(System.out::println);
~~~

**Do not assume a fixed stdout for this snippet.** With a parallel Stream, `forEach` does not guarantee the execution order of side effects; numbers may print out of sequence order. If you must perform actions in encounter order, use `forEachOrdered`, while considering the cost of enforcing ordering.

Use parallel Streams only when there is evidence of benefit; for short intervals, the overhead of splitting work may outweigh the benefit. Avoid mutating a shared `ArrayList` inside `parallel().forEach(list::add)`; if you want to collect results, use an appropriate collector or `toList()`.

## 13. Common Mistakes to Avoid

| Mistake | Consequence | Correct approach |
| --- | --- | --- |
| Using `range(1,10)` to sum 1 to 10 inclusive | Misses 10 | Use `rangeClosed(1,10)` |
| Using `rangeClosed(0,array.length)` to access an array | Last element has an out-of-bounds index | `range(0,array.length)` |
| Thinking `rangeClosed(5,1)` counts down | Empty sequence | Use `iterate` or an appropriate `for` loop |
| Using `range(0,0)` expecting a single value 0 | Empty Stream | `rangeClosed(0,0)` if you want a single 0 |
| Manually writing `range(start,end+1)` to include end | Can overflow when end is at the maximum | Use `rangeClosed(start,end)` |
| Computing length with `int length = end-start+1` for extreme bounds | `int` overflow | `count()` returning `long` when the domain fits, or compute with a sufficiently wide type |
| Calling `toArray()` on a range of billions of elements | Consumes too much memory | Limit the size or process via aggregation |
| Assuming `IntStream.sum()` does not overflow | Sum can be wrong | Convert to `long` or an appropriate numeric type |
| Wanting step 2 and thinking `range(start,end,2)` exists | No step overload exists | `iterate` or index `map` |
| Reusing a Stream after `count()` | Stream lifecycle error | Create a new source or use statistics |
| Relying on `parallel().forEach` to print in order | Side-effect order is not guaranteed | `forEachOrdered` or `toList()` |
| Repeatedly indexing a `LinkedList` with `get(i)` | Can be slow | Iterate directly with Iterator/Stream |
| Using `boxed()` unnecessarily in numeric computations | Creates intermediate objects | Keep a primitive pipeline |
| Thinking `range` executes immediately upon declaration | Stream pipeline is lazy | Call a terminal operation when needed |
| Mutating a local variable inside a lambda to accumulate a sum | Violates effectively final or causes side effects | Use `sum()`/`reduce` |

### Special Warning for Extreme Bounds

Example:

~~~java
int last = Integer.MAX_VALUE;
int[] tail = IntStream.rangeClosed(last - 1, last)
        .toArray();
~~~

This is a valid sequence containing only the last two numbers of the `int` range. Meanwhile, `IntStream.range(last - 1, last + 1)` is **not equivalent** because `last + 1` overflows.

Similarly, `LongStream.rangeClosed(Long.MAX_VALUE - 1, Long.MAX_VALUE)` has the last two elements of the `long` range; do not replace it with `range(..., Long.MAX_VALUE + 1)`. For intervals with extremely large element counts, summing/counting/materializing still requires considering data limits—do not confuse "valid factory" with "every terminal operation has enough resources."

## 14. Guided Exercises

### Exercise 1 — Reading the Upper Bound

Predict:

~~~java
System.out.println(
    java.util.Arrays.toString(IntStream.range(4, 8).toArray())
);
System.out.println(
    java.util.Arrays.toString(IntStream.rangeClosed(4, 8).toArray())
);
~~~

**Answer:** `[4, 5, 6, 7]` and `[4, 5, 6, 7, 8]`. Explain using the condition `n < 8` for `range` and `n <= 8` for `rangeClosed`.

### Exercise 2 — Empty Intervals

Test `range(5,5)`, `rangeClosed(5,5)`, `range(7,2)`, and `rangeClosed(7,2)`. State the number of elements in each Stream and explain why the result is not a countdown sequence.

**Answer:** `0, 1, 0, 0` elements respectively.

### Exercise 3 — Safe Index Retrieval

Given `int[] data = {9, 3, 5, 8};`. Use `IntStream.range(0, data.length).mapToObj(i -> i + ":" + data[i]).toList()` to produce `[0:9,1:3,2:5,3:8]`. Try an empty array and explain why no invalid index access occurs.

### Exercise 4 — Summing Integers Including the Upper Bound

Write a pipeline to compute `1 + 2 + ... + 100` using `rangeClosed(1,100)`. The result is `5050`. Try switching to `range(1,100)` and point out that `100` is omitted.

### Exercise 5 — Step Size

Generate the sequence `3,6,9,12` using `IntStream.rangeClosed(1,4).map(n -> n*3)` and using `IntStream.iterate(3, n -> n <= 12, n -> n+3)`. Compare expressing this when the element count is known versus when the stopping condition is known.

### Exercise 6 — `LongStream`

Generate the values `1_000_000_000_000L` through `1_000_000_000_003L` using `LongStream.rangeClosed`. Use `count()` to verify there are 4 elements. Explain why these values do not fit in `int`.

### Exercise 7 — Overflow When Summing

Compute the sum `1..100_000` using `IntStream.rangeClosed(1,100_000).sum()` and using `mapToLong(n -> n).sum()`. Explain why only the `long` version produces the mathematical result `5_000_050_000`.

### Exercise 8 — Parallelism and Ordering

Compare `IntStream.range(0,10).parallel().boxed().toList()` with `IntStream.range(0,10).parallel().forEach(System.out::println)`. Explain why the List has a reliable order, whereas the lines printed by `forEach` have no guaranteed order.

### Exercise 9 — Iterating Negative Numbers

Generate `[-3,-2,-1,0,1]` using `range(-3,2)` and `[-3,-2,-1,0,1,2]` using `rangeClosed(-3,2)`. Verify the element count and the last value.

### Exercise 10 — From Problem to API Choice

Given three requirements: (a) iterate over all indices of an array of length `n`, (b) number players from `1` to `n`, (c) generate odd numbers from `1` to `19`. Choose one of `range`, `rangeClosed`, `iterate`, or index `map`; explain the upper bound and the reason.

## 15. Checklist Before Using `range`

1. Is the upper bound value needed? If **no**, `range`; if **yes**, `rangeClosed`.
2. Are the start and end bounds equal or reversed? Predict empty/single-element results.
3. Are you iterating over array/List indices? Usually `range(0,length)` is more accurate.
4. Does the sequence increment by `1`? If not, consider `iterate` or `map`.
5. Does the data need `int` or `long`? Is there a risk of bounds or calculations exceeding the range?
6. Are you computing a size with an `int` formula that could overflow? Check the numeric type of the result.
7. Could the terminal operation materialize a huge amount of data in memory?
8. Do you need a return value or only a side effect? Prefer `sum`/`map`/`toList` when there is output data.
9. Are you using `parallel`? Do not rely on the call order of parallel `forEach`.
10. Are you reusing a consumed Stream or recomputing too many times on the same source?
11. Have edge cases `0`, equal bounds, negative bounds, `Integer.MAX_VALUE`, and `Long.MAX_VALUE` been checked appropriately?

## 16. Summary and References

**`range(startInclusive,endExclusive)` generates a sequence increasing by 1 with an inclusive left bound and an exclusive right bound. `rangeClosed(startInclusive,endInclusive)` generates a sequence increasing by 1 including both bounds.** When the two bounds are equal, `range` is empty while `rangeClosed` contains one element; when the start bound is greater than the end bound, both are empty and do not count down automatically.

Use `IntStream.range(0,array.length)` for indices; use `IntStream.rangeClosed(1,n)` for numbers from 1 to n inclusive. When integer values exceed `int`, use `LongStream` appropriately, while still controlling size, overflow risk when summing, and memory when materializing data. For steps other than 1, use `iterate` or index transformation; there is no `range(start,end,step)` overload.

**Official documentation:** Java SE 17 Javadoc for `java.util.stream.IntStream` and `java.util.stream.LongStream` (the `range`, `rangeClosed`, `iterate`, `mapToObj`, `sum`, `count` methods), `java.util.stream.BaseStream` and `java.util.stream.Stream` (ordering, pipelines, and terminal operations).
