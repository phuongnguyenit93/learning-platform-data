# Using reduce Without an Initial Value

In the Java Stream API, `reduce` is a *terminal operation* used to **combine multiple elements into a single result** according to a combining rule. A particularly useful form is `reduce(BinaryOperator<T>)`, namely **reduce without passing an initial value** (*identity*). When the source has elements, the result is combined from those elements themselves; when the source is empty, there is no result to return, so the method returns `Optional.empty()`.

This lesson belongs to the chapter **Reduction with reduce** of the **JAVA_STREAM_API** module. The goal is to understand how to choose the `reduce` overload, handle empty sources, write valid combining operations for sequential and parallel Streams, and know when specialized APIs like `sum`, `min`, `max`, or `collect` are more suitable. This knowledge builds on declarative pipelines, laziness, `filter`, and `map`, and extends toward grouping, custom collectors, `Spliterator`, parallel processing, as well as constraints on state, resources, and precision.

## 1. Signature of reduce without identity

For `java.util.stream.Stream<T>`, Java 8 and later define:

```java
Optional<T> reduce(BinaryOperator<T> accumulator);
```

Where:

- `T` is both the Stream's element type and the combined result type.
- `BinaryOperator<T>` is a functional interface in `java.util.function`, representing a function that takes **two `T` values** and returns **one `T` value**. It extends `BiFunction<T, T, T>`.
- `accumulator` describes **how to merge two partial results** into one result.
- `Optional<T>` indicates that **an empty source may yield no result**.

Example:

```java
import java.util.Optional;
import java.util.stream.Stream;

Optional<Integer> total = Stream.of(5, 10, 15)
        .reduce(Integer::sum);

System.out.println(total); // Optional[30]
```

There is no `0` argument or any other value serving as a starting point. With a **sequential and ordered** Stream, we can visualize it as:

```text
Source:      [5, 10, 15]
                 \   /
     combine:     15
                  \    /
     combine:       30
                    |
                 Optional[30]
```

This is a simplified explanatory model. In a parallel Stream, the runtime can split the data into multiple parts, combine locally, and then merge the results. Therefore, correctness must rely on the **operation contract**, not on the invocation-order diagram above.

### 1.1. Cases with 0, 1, and multiple elements

```java
Optional<Integer> none = Stream.<Integer>empty()
        .reduce(Integer::sum);

Optional<Integer> one = Stream.of(42)
        .reduce(Integer::sum);

Optional<Integer> many = Stream.of(8, -8)
        .reduce(Integer::sum);

System.out.println(none); // Optional.empty
System.out.println(one);  // Optional[42]
System.out.println(many); // Optional[0]
```

| Source | Result | Meaning |
|---|---|---|
| `[]` | `Optional.empty()` | No elements to reduce |
| `[42]` | `Optional[42]` | The single element itself is the result; no need to combine with another element |
| `[8, -8]` | `Optional[0]` | Data is present and the actual sum is 0 |

**Key point:** `Optional.empty()` and `Optional[0]` are **different**. This form of `reduce` preserves the “no data” signal; if you immediately default to 0, that information can be lost.

## 2. How to handle Optional after reduce

`Optional<T>` is not `T`. To use the result, you need to decide the **policy for an empty source**.

### 2.1. Use the result if present

```java
Optional<Integer> result = Stream.of(3, 4, 5)
        .reduce(Integer::sum);

result.ifPresent(sum -> System.out.println("Total: " + sum));
// Total: 12
```

If the source is empty, `ifPresent` performs no action. Suitable when “if there is no result, no further step is needed”.

### 2.2. Provide a default value

```java
int totalForDisplay = Stream.<Integer>empty()
        .reduce(Integer::sum)
        .orElse(0);

System.out.println(totalForDisplay); // 0
```

For **summing**, 0 may be a reasonable default. However, if the business logic must distinguish “no transactions yet” from “transactions summing to 0”, keep the `Optional` or include the element count.

`orElseGet(() -> fallback)` evaluates the fallback value only when the Optional is empty. If the fallback value is expensive to compute or has side effects, `orElseGet` may be more appropriate than `orElse`, because the argument expression to `orElse` is evaluated immediately upon invocation.

### 2.3. Require a result to be present

```java
int requiredTotal = Stream.of(1, 2, 3)
        .reduce(Integer::sum)
        .orElseThrow(() ->
                new IllegalStateException("No data available to aggregate"));

System.out.println(requiredTotal); // 6
```

With an empty Stream, this code throws `IllegalStateException` with a business message instead of pretending a result exists. Do not call `get()` directly on an empty Optional: `get()` throws `NoSuchElementException`.

Java 9 added `ifPresentOrElse`, and Java 10 added parameterless `Optional.orElseThrow()`. The examples in this lesson continue using syntax available since Java 8 for easy practice.

## 3. Comparing reduce with and without an initial value

Java provides two common forms:

```java
// Without identity: returns Optional<T>.
Optional<Integer> withoutIdentity = Stream.<Integer>empty()
        .reduce(Integer::sum);

// With identity: returns T.
Integer withIdentity = Stream.<Integer>empty()
        .reduce(0, Integer::sum);

System.out.println(withoutIdentity); // Optional.empty
System.out.println(withIdentity);    // 0
```

| Aspect | `reduce(BinaryOperator<T>)` | `reduce(T identity, BinaryOperator<T>)` |
|---|---|---|
| Initial value | Not passed | Passes `identity` |
| Return type | `Optional<T>` | `T` |
| Empty source | `Optional.empty()` | `identity` itself |
| Single element `x` | `Optional[x]` | `accumulator(identity, x)`, must equal `x` if identity is valid |
| Common problems | Finding extrema, summing only when data exists, combining without an obvious identity element | Sum defaulting to 0 when empty, product defaulting to 1 when empty, combining with a well-defined identity element |

**Identity must be a true identity element of the combining operation.** If `op` is addition, `0` is the identity, not `100`. If `op` is multiplication, `1` is the identity. An arbitrary default value can corrupt the result, especially in a parallel pipeline.

```java
int sum = Stream.of(2, 3, 4)
        .reduce(0, Integer::sum); // 9

int product = Stream.of(2, 3, 4)
        .reduce(1, (a, b) -> a * b); // 24

Optional<Integer> productIfPresent = Stream.<Integer>empty()
        .reduce((a, b) -> a * b); // Optional.empty
```

**Omitting the identity** does not mean “the combining operation does not need to obey a mathematical contract”. Both forms require the accumulator to be associative (*associativity*) for the reduction to be valid when the Stream chooses how to split the work.

## 4. Complete example: total amount and largest order

Suppose an application has paid and unpaid orders. We need to:

1. Compute the total paid amount **if matching orders exist**.
2. Pick a paid order with the largest amount, breaking ties by choosing the larger ID.
3. Distinguish the case of **no refunded orders** from a refund total of 0.

The following standalone example runs on Java 8:

```java
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Optional;

public class ReduceWithoutIdentityDemo {
    static final class Order {
        private final String id;
        private final String status;
        private final long amountCents;

        Order(String id, String status, long amountCents) {
            this.id = id;
            this.status = status;
            this.amountCents = amountCents;
        }

        String getId() {
            return id;
        }

        String getStatus() {
            return status;
        }

        long getAmountCents() {
            return amountCents;
        }
    }

    public static void main(String[] args) {
        List<Order> orders = Arrays.asList(
                new Order("HD01", "PAID", 20_000L),
                new Order("HD02", "PENDING", 70_000L),
                new Order("HD03", "PAID", 30_000L),
                new Order("HD04", "PAID", 30_000L)
        );

        // Only paid orders participate in the calculation.
        Optional<Long> paidTotal = orders.stream()
                .filter(order -> "PAID".equals(order.getStatus()))
                .map(Order::getAmountCents)
                .reduce(Long::sum);

        System.out.println(paidTotal);          // Optional[80000]
        System.out.println(paidTotal.orElse(0L)); // 80000

        // Comparator creates a deterministic tie-breaking rule.
        Comparator<Order> byAmountThenId =
                Comparator.comparingLong(Order::getAmountCents)
                        .thenComparing(Order::getId);

        Optional<Order> largestPaid = orders.stream()
                .filter(order -> "PAID".equals(order.getStatus()))
                .reduce((best, candidate) ->
                        byAmountThenId.compare(best, candidate) >= 0
                                ? best : candidate);

        System.out.println(largestPaid
                .map(Order::getId)
                .orElse("(no order)")); // HD04

        // The REFUNDED status does not exist in the sample data.
        Optional<Long> refundedTotal = orders.stream()
                .filter(order -> "REFUNDED".equals(order.getStatus()))
                .map(Order::getAmountCents)
                .reduce(Long::sum);

        System.out.println(refundedTotal); // Optional.empty
        System.out.println(refundedTotal.isPresent()); // false
    }
}
```

In the example, `map(Order::getAmountCents)` turns `Stream<Order>` into `Stream<Long>`; `reduce(Long::sum)` combines the `Long` elements. For the two orders HD03 and HD04 with the same amount, `thenComparing(Order::getId)` decides HD04 is greater according to the chosen comparison rule.

Selecting the maximum order using `reduce` illustrates how a `BinaryOperator<Order>` merges two candidates. In production code, it is usually easier to read if written as `max(byAmountThenId)`:

```java
Optional<Order> largestPaid = orders.stream()
        .filter(order -> "PAID".equals(order.getStatus()))
        .max(byAmountThenId);
```

For monetary totals, using `long` in the smallest currency unit avoids `double` precision errors as long as it stays within overflow limits. If the total may exceed `long` or requires exact decimal division, consider `BigInteger` or `BigDecimal` according to the data domain.

## 5. Reduce without identity on IntStream, LongStream, and DoubleStream

Primitive Streams have `reduce` overloads that take the corresponding operator and return a specialized Optional:

| API | Parameter | Return type without identity |
|---|---|---|
| `IntStream.reduce(...)` | `IntBinaryOperator` | `OptionalInt` |
| `LongStream.reduce(...)` | `LongBinaryOperator` | `OptionalLong` |
| `DoubleStream.reduce(...)` | `DoubleBinaryOperator` | `OptionalDouble` |
| `Stream<T>.reduce(...)` | `BinaryOperator<T>` | `Optional<T>` |

Example:

```java
import java.util.OptionalDouble;
import java.util.OptionalInt;
import java.util.OptionalLong;
import java.util.stream.DoubleStream;
import java.util.stream.IntStream;
import java.util.stream.LongStream;

OptionalInt max = IntStream.of(4, 9, 1)
        .reduce(Integer::max);          // OptionalInt[9]

OptionalLong total = LongStream.empty()
        .reduce(Long::sum);             // OptionalLong.empty

OptionalDouble product = DoubleStream.of(2.0, 3.0)
        .reduce((a, b) -> a * b);        // OptionalDouble[6.0]

System.out.println(max.orElse(-1));      // 9
System.out.println(total.orElse(0L));    // 0
System.out.println(product.orElse(1.0)); // 6.0
```

Notice the distinction that `IntStream.empty().reduce(Integer::sum)` returns `OptionalInt.empty()`, whereas `IntStream.empty().sum()` returns `0`. This is a decision about **how to represent missing data**; not every operation returning an Optional is faster or more accurate.

When working with very large numbers of primitives, `IntStream`/`LongStream`/`DoubleStream` can avoid the boxing/unboxing cost of `Stream<Integer>`/`Stream<Long>`/`Stream<Double>`. If the true goal is simply summing, `sum()` expresses the intent more clearly than `reduce(Integer::sum)`.

## 6. Associativity determines the correctness of a reduction

With an accumulator denoted `op`, **associativity** means:

\[
(a\ \mathrm{op}\ b)\ \mathrm{op}\ c
=a\ \mathrm{op}\ (b\ \mathrm{op}\ c)
\]

Integer addition (within valid arithmetic semantics and range), multiplication, and selecting a maximum under a consistent order are familiar examples. Subtraction and division in general are **not associative**.

### 6.1. Wrong: using subtraction with reduce

```java
import java.util.stream.Stream;

int sequential = Stream.of(10, 5, 2)
        .reduce((a, b) -> a - b)
        .orElseThrow(() -> new IllegalStateException("Empty"));

System.out.println(sequential); // 3: (10 - 5) - 2
```

However, `(10 - 5) - 2 = 3`, whereas `10 - (5 - 2) = 7`. Changing how terms are grouped changes the result. Do not bring this reducer to `parallelStream()` and expect a stable result or the same business meaning as sequential subtraction.

**Note:** Even if sequential code currently appears to “work”, the `reduce` contract requires an associative operation. If the algorithm is actually sequential step-by-step subtraction in order, a direct loop with a defined starting point can express the requirement more clearly.

### 6.2. Selecting extrema: a valid combining operation when the comparator is consistent

```java
import java.util.Comparator;
import java.util.Optional;
import java.util.stream.Stream;

Comparator<String> byLengthThenText =
        Comparator.comparingInt(String::length)
                .thenComparing(Comparator.naturalOrder());

Optional<String> longest = Stream.of("A", "BBB", "CC")
        .reduce((a, b) ->
                byLengthThenText.compare(a, b) >= 0 ? a : b);

System.out.println(longest.orElse("(empty)")); // BBB
```

A reducer that picks the larger element according to a consistent comparator with specific tie-breaking remains meaningful even when the data is split into sub-parts. To express this requirement more concisely, you can use `stream.max(byLengthThenText)`.

### 6.3. Double has addition-order-dependent error

With `double`, addition is not **bitwise associative** due to representation limits and rounding:

```java
double left = (1.0e16 + -1.0e16) + 1.0; // 1.0
double right = 1.0e16 + (-1.0e16 + 1.0); // 0.0
```

Therefore, a parallel reduction on floating-point numbers can differ from the sequential result due to how additions are grouped, even though addition is associative in real mathematics. When high precision is required, choose an appropriate aggregation method, consider `DoubleStream.sum()` (which can improve precision via compensated summation) or `BigDecimal` for decimal data, and establish an acceptable error tolerance.

## 7. Accumulator must be pure and must not mutate shared data

The accumulator used in `reduce` must be **non-interfering** with the source and **stateless** (no shared mutable state). The function may be called differently between sequential and parallel Streams; it should not depend on invocation count, thread execution order, or side effects.

**Do not** mutate an object and use it as an intermediate result:

```java
// DO NOT: mutate the same StringBuilder returned as the state
// of reduce; the result depends on aliasing and parallel execution.
StringBuilder unsafe = Stream.of("A", "B", "C")
        .parallel()
        .reduce(new StringBuilder(),
                (builder, text) -> builder.append(text),
                (left, right) -> left.append(right));
```

The snippet above uses the **three-parameter overload** to illustrate the risk: branches can share the same mutable identity, violating the assumptions required for parallel reduction to work properly. For string building, use a collector:

```java
import java.util.stream.Collectors;
import java.util.stream.Stream;

String joined = Stream.of("A", "B", "C")
        .parallel()
        .collect(Collectors.joining());

System.out.println(joined); // ABC
```

The reason not to use `reduce(String::concat)` for every string concatenation problem lies in cost: immutable strings can create many intermediate copies. `Collectors.joining()` is specifically designed for string concatenation. If you only join a few elements, `reduce` can still express the meaning, but volume and performance should be considered.

### 7.1. Do not use null as a “skip result” signal

`Optional` cannot hold a null element. Under the contract of `reduce(BinaryOperator)`, **if the result of the reduction is null, a `NullPointerException` may be thrown**; specifically, returning null from a reducer when combining non-empty elements is a bug.

```java
// WRONG: do not use null as the result of a reducer.
// Stream.of(1, 2).reduce((a, b) -> null);

// RIGHT if you want to skip some elements:
Optional<Integer> totalPositive = Stream.of(-1, 2, -3, 4)
        .filter(n -> n > 0)
        .reduce(Integer::sum); // Optional[6]
```

If the source data contains null elements, filter or normalize them **before** reducing. Do not use the reducer to implicitly “swallow” null elements.

## 8. Limitations of reduce without identity when computing multiple quantities

`reduce(BinaryOperator<T>)` accepts two elements **of the same type `T`** and combines them back into `T`. It works well when the result and elements share the same type—for example, summing `Long` values, picking the largest `Order`, or joining a few strings.

If the output has a **different type** or you need to compute **multiple metrics at once**, consider other operations:

- `map` before `reduce` when each input can be transformed into the result type to be combined, e.g. `Stream<Order> -> Stream<Long>`.
- `collect` or `summaryStatistics` when you need count, sum, average, extrema, and mutable accumulators together.
- `Collectors.groupingBy(..., downstream)` when you need results per group rather than a single value for the entire Stream.

For instance, `Collectors.reducing(BinaryOperator<T>)` is the collector counterpart to a reducer without identity, convenient when combining per group:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.stream.Collectors;

List<Integer> numbers = Arrays.asList(3, 7, 2, 10);

Map<String, Optional<Integer>> maxByParity = numbers.stream()
        .collect(Collectors.groupingBy(
                n -> n % 2 == 0 ? "EVEN" : "ODD",
                Collectors.reducing(Integer::max)));

System.out.println(maxByParity.get("EVEN")); // Optional[10]
System.out.println(maxByParity.get("ODD"));  // Optional[7]
```

`groupingBy` only creates group keys that appear in the data. With an empty list, the resulting Map is empty and **has neither an “EVEN” nor an “ODD” key**. The Optionals in the Map represent the reducer result for each group. If you only need the maximum, `Collectors.maxBy(Comparator.naturalOrder())` is a more specialized and readable expression.

### 8.1. Reduce without identity and short-circuiting

`reduce` is a terminal operation, but **it is not a short-circuiting operation** like `findFirst` or `anyMatch`. To know the combined result of a finite source, it typically has to consume all elements after filtering. On an infinite Stream, calling `reduce` may not terminate without a prior limiting mechanism:

```java
import java.util.Optional;
import java.util.stream.Stream;

Optional<Integer> totalFirstFive = Stream.iterate(1, n -> n + 1)
        .limit(5)
        .reduce(Integer::sum); // Optional[15]
```

`limit(5)` bounds the first five elements of the infinite source. Do not confuse having a final `Optional` value with an inherent ability of reduction to stop on its own.

## 9. Choosing the right operation for each situation

| Requirement | Usually clearest choice | When source is empty |
|---|---|---|
| Sum of integers, defaulting to 0 | `IntStream.sum()` or `reduce(0, Integer::sum)` | `0` |
| Sum of integers while preserving no-data signal | `reduce(Integer::sum)` | `Optional.empty()` |
| Minimum/maximum element by comparator | `min(comparator)` / `max(comparator)` | `Optional.empty()` |
| Join strings | `Collectors.joining()` | Empty string `""` |
| Count elements | `count()` | `0L` |
| Average of primitive numbers | `IntStream.average()` | `OptionalDouble.empty()` |
| Compute count, sum, min, max together | `summaryStatistics()` or appropriate collector | Count is 0; check before displaying extrema |
| Combine per group with a custom operation | `groupingBy(..., reducing(op))` | Groups with no data do not appear automatically |

Choose `reduce` without identity **when the absence of elements is a meaningful state** or the natural combining operation lacks a suitable identity. When a specialized terminal operation already exists, using it usually makes the code easier to read, easier to verify, and gives better optimization opportunities.

## 10. Common misconceptions

| Misconception | Correct understanding |
|---|---|
| “Without passing identity, reduce automatically uses 0.” | An empty source returns `Optional.empty()`; `0` is only the identity of addition when explicitly passed or defined by APIs like `sum()`. |
| “An empty Optional means the addition resulted in 0.” | `Optional.empty()` means **no result**; `Optional[0]` means **there is a result equal to 0**. |
| “With one element, the reducer runs once with itself.” | No need to invoke the reducer on a pair; the single element is the result. |
| “Reduce always combines from left to right.” | With a parallel Stream, partitioning and combining can differ; the accumulator must be associative. |
| “Any binary operation can be used with reduce.” | Subtraction/division are generally not associative; mutable state can also violate the requirements. |
| “You can use null to skip elements in a reducer.” | Returning null from a reducer can cause the reduction to fail; filter/normalize beforehand. |
| “Parallel reduce is automatically faster than sequential.” | Work splitting, boxing, combining overhead, and per-element cost can make it slower; you must measure. |
| “Using reduce to build a List is the standard way.” | `collect` is more suitable for mutable accumulation into a List, Set, or Map. |

## 11. Practice exercises with answers

### Exercise 1. Distinguish empty from a sum of 0

```java
Optional<Integer> a = Stream.<Integer>empty()
        .reduce(Integer::sum);
Optional<Integer> b = Stream.of(6, -6)
        .reduce(Integer::sum);
```

**Answer:** `a` is `Optional.empty()`; `b` is `Optional[0]`. Only `b` reflects that two elements were actually added.

### Exercise 2. Source with a single element

```java
Optional<String> result = Stream.of("Java")
        .reduce(String::concat);
```

**Answer:** `Optional[Java]`. There is no need for an initial empty string or concatenating that element with itself.

### Exercise 3. Find the longest element

Find the longest word in `["API", "Stream", "Java"]`. If lengths are equal, pick the one that is greater lexicographically.

```java
Comparator<String> rule = Comparator
        .comparingInt(String::length)
        .thenComparing(Comparator.naturalOrder());

Optional<String> longest = Stream.of("API", "Stream", "Java")
        .reduce((a, b) -> rule.compare(a, b) >= 0 ? a : b);
// Optional[Stream]
```

### Exercise 4. Why is subtraction dangerous?

For the numbers 20, 5, 3, compare `(20 - 5) - 3` and `20 - (5 - 3)`.

**Answer:** The two results are 12 and 18, so subtraction is not associative. Do not use it as a reducer for a pipeline that may execute in parallel.

### Exercise 5. Right decision for reporting

An API needs to return the **total paid amount** and distinguish a day with no transactions from a day whose amounts offset each other to zero. Should it return `long` defaulting to 0 or `Optional<Long>`?

**Answer:** `Optional<Long>` after `map(Order::getAmountCents).reduce(Long::sum)` preserves the no-order signal. If you also need `count` to verify completeness or avoid re-traversing the Stream, use a statistics collector that provides both count and total.

## 12. Key takeaways

`reduce(BinaryOperator<T>)` uses the Stream elements themselves as the basis for combining and returns `Optional<T>` because **an empty source has no result**. It distinguishes `Optional.empty()` from an actual result of 0, and applies to addition, selecting extrema, and many other combining rules. To use it properly, write an accumulator that is **pure, non-interfering with source data, does not rely on shared mutable state, and is associative**; handle `Optional` according to business rules and consider specialized APIs such as `sum`, `max`, `min`, or `collect` when they express the goal more clearly.
