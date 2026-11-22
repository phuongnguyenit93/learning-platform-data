# Handling Sum and Average on Empty Sources

In the Java Stream API, a pipeline may produce no elements at all: the input list is already empty, `filter` discards every record, or a transformation step retains only valid values and finds none. In such cases, **sum** and **average** do not share the same meaning or result type. On primitive Streams, `sum()` returns **0** on an empty source, whereas `average()` returns **`OptionalDouble.empty()`**. Knowing this distinction clearly prevents division by zero and avoids mistaking “no data” for “an actual average of 0”.

This lesson belongs to the **Numeric Aggregation Accuracy** chapter of the **JAVA_STREAM_API** module. This topic builds on declarative, lazy pipelines, `filter`, `map`, `reduce`, and `collect`, and is useful when aggregating by group, designing custom collectors, processing in parallel, or controlling rounding errors, numeric overflow, and resources. The main examples target Java 8 and later unless another version is explicitly noted.

## 1. Why Is an Empty Source a Mandatory Case to Handle?

Suppose an application has a list of invoices, and today **no invoices have been paid**. Two business questions sound similar:

- “Total amount paid today?”: typically **0 dong**, because no transaction contributes to the sum.
- “Average value of each paid invoice today?”: **undefined**, because no invoice exists to compute an average.

The arithmetic mean of `n` values is:

\[
\overline{x}=\frac{x_1+x_2+\dots+x_n}{n},\quad n>0
\]

When `n = 0`, the denominator is 0; you cannot infer an average merely from a sum of 0. Java reflects this through two categories of APIs:

| Operation | Non-empty source | Empty source |
|---|---|---|
| `IntStream.sum()` | Sum of type `int` | `0` |
| `LongStream.sum()` | Sum of type `long` | `0L` |
| `DoubleStream.sum()` | Sum of type `double` | `0.0` |
| `IntStream.average()` | `OptionalDouble` containing the average | `OptionalDouble.empty()` |
| `LongStream.average()` | `OptionalDouble` containing the average | `OptionalDouble.empty()` |
| `DoubleStream.average()` | `OptionalDouble` containing the average | `OptionalDouble.empty()` |
| `IntStream.count()` (likewise `LongStream`, `DoubleStream`) | Element count | `0L` |

**Key point:** A sum of 0 **does not tell you** that the source is empty. A source containing the element `0`, or the values `-5` and `5`, can also have a sum of 0.

## 2. Sum: Why Does sum() Return 0 on an Empty Stream?

Addition has an **identity element** of `0`: for any number `a`, `a + 0 = 0 + a = a`. Therefore, the sum over zero elements can reasonably be defined as the identity element, analogous to `reduce(0, ...)`.

```java
import java.util.stream.IntStream;
import java.util.stream.LongStream;
import java.util.stream.DoubleStream;

System.out.println(IntStream.empty().sum());    // 0
System.out.println(LongStream.empty().sum());   // 0
System.out.println(DoubleStream.empty().sum()); // 0.0
System.out.println(IntStream.empty().count());  // 0
```

If you already have a list of numbers, primitive Streams support summing directly:

```java
import java.util.Arrays;
import java.util.List;

List<Integer> amounts = Arrays.asList(100, 200, -300);

int total = amounts.stream()
        .mapToInt(Integer::intValue)
        .sum();

System.out.println(total); // 0, even though there are three elements.
```

### 2.1. Filtering Out All Elements Also Produces an Empty Source for the Terminal Operation

```java
List<Integer> amounts = Arrays.asList(100, 200, 300);

int emptySum = amounts.stream()
        .filter(value -> value < 0)
        .mapToInt(Integer::intValue)
        .sum();

System.out.println(emptySum); // 0
```

Intermediate operations such as `filter` are typically **lazy**. Having no elements after filtering only surfaces when `sum` actually traverses the pipeline; no exception is thrown simply because the filtered result is empty.

### 2.2. mapToInt/mapToLong Before sum

For `Stream<Order>` or `Stream<Product>`, you must map objects to numbers:

```java
long totalCents = orders.stream()
        .filter(Order::isPaid)
        .mapToLong(Order::getAmountCents)
        .sum();
```

This snippet assumes an `Order` type with `isPaid()` returning `boolean` and `getAmountCents()` returning `long`. After filtering, if there are no paid orders, `totalCents` equals `0L`.

Never assume integer sums are always safe in magnitude: `IntStream.sum()` can **overflow `int`**, and `LongStream.sum()` can **overflow `long`** when the true sum exceeds the value range. See the accuracy section below for more details.

## 3. Average: OptionalDouble Represents the Potential Absence of a Result

The `average` operation on all primitive Streams returns `OptionalDouble`:

```java
import java.util.OptionalDouble;
import java.util.stream.IntStream;

OptionalDouble averageOfThree = IntStream.of(10, 20, 30)
        .average();
System.out.println(averageOfThree); // OptionalDouble[20.0]

OptionalDouble averageOfNothing = IntStream.empty()
        .average();
System.out.println(averageOfNothing); // OptionalDouble.empty
```

Do not call `getAsDouble()` without first confirming that a value is present:

```java
OptionalDouble average = IntStream.empty().average();

// WRONG: throws NoSuchElementException when OptionalDouble is empty.
// double value = average.getAsDouble();

if (average.isPresent()) {
    System.out.println("Average = " + average.getAsDouble());
} else {
    System.out.println("No data available to compute average");
}
```

You can handle this more concisely with `ifPresent`, `orElse`, or `orElseGet`:

```java
OptionalDouble average = IntStream.of(10, 20).average();

average.ifPresent(value -> System.out.println("Avg = " + value));

double displayValue = average.orElse(0.0);
System.out.println(displayValue); // 15.0
```

However, choosing `orElse(0.0)` is an **application policy**, not the mathematical definition of an empty average. Only default to 0 when users or business rules **accept** equating “no data” with displaying the number 0.

### 3.1. Distinguishing Three Cases

| Data | `sum()` | `average()` | Interpretation |
|---|---:|---|---|
| `[]` | `0` | Empty | No measurements yet |
| `[0]` | `0` | Present with `0.0` | One measurement actually equal to 0 |
| `[-5, 5]` | `0` | Present with `0.0` | Two measurements canceling each other out |

If the system needs to report **“whether data exists yet”**, keep `OptionalDouble` or the pair `count` and `sum`, instead of storing only a single `double`.

## 4. reduce With Identity and Without Identity

`sum()` is a specialized tool, whereas `reduce` makes it clear why a sum can return 0 on an empty source.

### 4.1. With Identity: Always Produces a Result

```java
import java.util.stream.Stream;

int total = Stream.<Integer>empty()
        .reduce(0, Integer::sum);

System.out.println(total); // 0
```

The `reduce(identity, accumulator)` overload returns `identity` itself when there are no elements. For addition, the identity must be `0`. Using `100` as the initial value turns an empty sum into `100`, and can also produce an incorrect sum during parallel execution if it violates the combiner contract.

### 4.2. Without Identity: Returns Optional

```java
import java.util.Optional;
import java.util.stream.Stream;

Optional<Integer> totalIfPresent = Stream.<Integer>empty()
        .reduce(Integer::sum);

System.out.println(totalIfPresent); // Optional.empty
```

With a non-empty source:

```java
Optional<Integer> total = Stream.of(4, -4)
        .reduce(Integer::sum);

System.out.println(total); // Optional[0]
```

`reduce(BinaryOperator<T>)` is appropriate when you want to distinguish the sum of **zero elements** from the sum of **a set of elements that add up to 0**. Conversely, if business rules define an empty sum as 0 and do not need that distinction, `sum()` or `reduce(0, ...)` is the clearer choice.

Note: the combining operation in `reduce` must satisfy *associativity* if you want correct results when a Stream splits work in parallel. With floating-point numbers, different addition orders can produce different rounding errors; do not equate “correct according to the formula” with “bit-identical results every time”.

## 5. Collectors May Handle Empty Sources Differently from average()

Inside `collect`, Java provides `Collectors.summingInt`, `summingLong`, `summingDouble`, `averagingInt`, `averagingLong`, and `averagingDouble`. These collectors follow a contract that returns a concrete numeric value, **not `OptionalDouble`**, for the average.

```java
import java.util.Collections;
import java.util.List;
import java.util.stream.Collectors;

List<Integer> empty = Collections.emptyList();

int sum = empty.stream()
        .collect(Collectors.summingInt(Integer::intValue));

double avg = empty.stream()
        .collect(Collectors.averagingInt(Integer::intValue));

System.out.println(sum); // 0
System.out.println(avg); // 0.0
```

This is an important difference:

| Calculation | Empty source | Distinguishes “no data”? |
|---|---|---|
| `IntStream.empty().sum()` | `0` | No, if looking only at the sum value |
| `IntStream.empty().average()` | `OptionalDouble.empty()` | Yes |
| `empty.stream().collect(summingInt(...))` | `0` | No, if looking only at the sum value |
| `empty.stream().collect(averagingInt(...))` | `0.0` | No, if looking only at the average value |
| `empty.stream().reduce(Integer::sum)` | `Optional.empty()` | Yes |
| `empty.stream().count()` | `0L` | Can be used to detect an empty source |

**Do not replace `average()` with `Collectors.averagingInt` expecting both to return “undefined” on an empty source.** When you need that distinction, retain the element count or apply a custom collector that returns a result type carrying a data-presence flag.

### 5.1. summaryStatistics: Getting count, sum, and average Together

If a report needs multiple summary metrics, you can use `summaryStatistics()`:

```java
import java.util.IntSummaryStatistics;
import java.util.stream.IntStream;

IntSummaryStatistics stats = IntStream.empty()
        .summaryStatistics();

System.out.println(stats.getCount());   // 0
System.out.println(stats.getSum());     // 0
System.out.println(stats.getAverage()); // 0.0
```

`getAverage()` on statistics returns `0.0` when `count == 0`. Therefore, to represent **no average**, check the count:

```java
import java.util.OptionalDouble;

OptionalDouble avgFromStats = stats.getCount() == 0
        ? OptionalDouble.empty()
        : OptionalDouble.of(stats.getAverage());
```

On an empty `IntSummaryStatistics`, `getMin()` starts at `Integer.MAX_VALUE` and `getMax()` starts at `Integer.MIN_VALUE`; you should **not** display them as actual extrema when `getCount() == 0`. `LongSummaryStatistics` and `DoubleSummaryStatistics` must likewise be handled according to their respective contracts.

The advantage of statistics is counting and accumulating in a **single pass**. This is especially useful for single-use Stream sources; you do not need to create the same Stream and call `sum()` and then `average()` on an already-consumed Stream object.

## 6. Complete Java 8 Example: Invoices With No Matching Records

The following example has three order statuses and an `amountCents` field of type `long`, representing monetary amounts in the smallest currency unit. The application computes the sum and average of paid orders, then attempts to compute them for a status that **does not exist** in the data.

```java
import java.util.Arrays;
import java.util.List;
import java.util.LongSummaryStatistics;
import java.util.OptionalDouble;
import java.util.stream.Collectors;

public class EmptyAggregationDemo {
    static final class Order {
        private final String status;
        private final long amountCents;

        Order(String status, long amountCents) {
            this.status = status;
            this.amountCents = amountCents;
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
                new Order("PAID", 10_000L),
                new Order("PENDING", 50_000L),
                new Order("PAID", 30_000L)
        );

        // Each terminal operation requires a new Stream from the list.
        long paidTotal = orders.stream()
                .filter(order -> "PAID".equals(order.getStatus()))
                .mapToLong(Order::getAmountCents)
                .sum();

        OptionalDouble paidAverage = orders.stream()
                .filter(order -> "PAID".equals(order.getStatus()))
                .mapToLong(Order::getAmountCents)
                .average();

        System.out.println("Total PAID: " + paidTotal); // 40000
        System.out.println("Avg PAID: " + paidAverage.orElse(-1)); // 20000.0

        // There are no REFUNDED orders in the list.
        long refundedTotal = orders.stream()
                .filter(order -> "REFUNDED".equals(order.getStatus()))
                .mapToLong(Order::getAmountCents)
                .sum();

        OptionalDouble refundedAverage = orders.stream()
                .filter(order -> "REFUNDED".equals(order.getStatus()))
                .mapToLong(Order::getAmountCents)
                .average();

        System.out.println("Total REFUNDED: " + refundedTotal); // 0
        System.out.println("Has REFUNDED avg? " + refundedAverage.isPresent());
        // false

        // If count/sum/average are needed together, collect once.
        LongSummaryStatistics stats = orders.stream()
                .filter(order -> "REFUNDED".equals(order.getStatus()))
                .collect(Collectors.summarizingLong(Order::getAmountCents));

        System.out.println("REFUNDED count: " + stats.getCount()); // 0
        System.out.println("Total REFUNDED: " + stats.getSum()); // 0

        if (stats.getCount() == 0) {
            System.out.println("Avg REFUNDED: no data yet");
        } else {
            System.out.println("Avg REFUNDED: " + stats.getAverage());
        }
    }
}
```

Key takeaway: the same set of orders can yield a **sum of 0** and an **empty average** for the `REFUNDED` group. Using `"REFUNDED".equals(order.getStatus())` also avoids a null-dereference error if an order's `status` can be null; the example assumes the `Order` elements themselves are non-null.

If you need to report both sum and average over a **single-use source** (such as a data-reading stream), choose `summarizingLong` or another collector that retains full statistics, rather than creating a Stream once and trying to reuse it after a terminal operation has been called.

## 7. Empty Groups: groupingBy and partitioningBy Behave Differently

In grouped aggregations, “a group with no records” can be represented either by **the absence of the key** or by **having the key with a default result**. You must distinguish these two cases when designing reports.

### 7.1. groupingBy Does Not Automatically Create Absent Groups

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

List<String> statuses = Arrays.asList("PAID", "PAID", "PENDING");

Map<String, Long> counts = statuses.stream()
        .collect(Collectors.groupingBy(
                status -> status,
                Collectors.counting()));

System.out.println(counts.get("PAID"));      // 2
System.out.println(counts.containsKey("REFUNDED")); // false
```

Without any elements belonging to the `REFUNDED` group, `groupingBy` does not add that key on its own. If a report must always include every prescribed status, the reporting layer should actively populate missing groups while still distinguishing **no records generated** from **an average of 0 from actual data**.

### 7.2. partitioningBy Always Has Two Boolean Keys

```java
import java.util.Collections;
import java.util.Map;
import java.util.stream.Collectors;

Map<Boolean, Double> averages = Collections.<Integer>emptyList()
        .stream()
        .collect(Collectors.partitioningBy(
                number -> number >= 0,
                Collectors.averagingInt(Integer::intValue)));

System.out.println(averages.get(true));  // 0.0
System.out.println(averages.get(false)); // 0.0
```

`partitioningBy` creates both `true` and `false` groups even when the input is completely empty; with the downstream collector `averagingInt`, both receive `0.0`. **This is the collector's default value**, not proof that each group had a measurement equal to 0. You can also collect `count` for each group to identify empty cases before presenting results.

## 8. Computing Average Manually: Guard Against Division by Zero

An error-prone way to write it is:

```java
long sum = values.stream().mapToLong(Long::longValue).sum();
long count = values.size();

// WRONG if count == 0: with long/long division, throws ArithmeticException.
// long mean = sum / count;
```

Even when `count > 0`, `sum / count` with two integer operands **truncates the fractional part**, rather than producing an exact floating-point average. If the data suits floating-point arithmetic, use:

```java
OptionalDouble average = values.stream()
        .mapToLong(Long::longValue)
        .average();
```

If you need to preserve absence with a manual calculation:

```java
long count = values.size();
long sum = values.stream().mapToLong(Long::longValue).sum();

OptionalDouble average = count == 0
        ? OptionalDouble.empty()
        : OptionalDouble.of((double) sum / count);
```

Both snippets assume `values` is a `List<Long>` containing non-null elements, and that `sum` does not overflow `long`. The Stream `average()` method is recommended for ordinary average calculations; the manual division example merely illustrates separating the **empty rule** from the **computation**.

### 8.1. Avoid Using NaN Implicitly as an Empty Marker

In `double`, `0.0 / 0.0` evaluates to `NaN` rather than throwing `ArithmeticException`. However, `NaN` does not serve as a drop-in replacement with the same contract as `OptionalDouble.empty()`: `NaN` can also arise from invalid input data or arithmetic with infinity. If you need to distinguish an empty source from data containing `NaN`, check `count` or retain `OptionalDouble`.

## 9. Precision: Having Data Does Not Guarantee a Valid Average

`OptionalDouble.isPresent()` only indicates that **elements were fed into the computation**; it does not by itself guarantee that the average is finite, exact, or business-valid.

### 9.1. Floating-Point Rounding Errors

`double` uses a finite binary representation, so decimal numbers such as `0.1` and `0.2` are usually not stored with absolute precision.

```java
import java.util.stream.DoubleStream;

double sum = DoubleStream.of(0.1, 0.2).sum();
OptionalDouble average = DoubleStream.of(0.1, 0.2).average();
```

Do not compare floating-point numbers by requiring the resulting bits to match an ideal decimal representation. `DoubleStream.sum()` may use compensated summation techniques to improve accuracy, but that does not mean every floating-point calculation is exact or that summation orders across parallel configurations always yield identical results.

### 9.2. NaN and Infinity

`DoubleStream.average()` returns `OptionalDouble.empty()` on an **empty** source. If the source is non-empty and contains `NaN`, the result can be an `OptionalDouble` **holding `NaN`**; these two states must be kept distinct.

```java
import java.util.OptionalDouble;
import java.util.stream.DoubleStream;

OptionalDouble result = DoubleStream.of(Double.NaN, 10.0)
        .average();

System.out.println(result.isPresent()); // true
System.out.println(Double.isNaN(result.getAsDouble())); // true
```

If the requirement is to aggregate only finite numbers, you can filter intentionally:

```java
OptionalDouble finiteAverage = DoubleStream
        .of(10.0, Double.NaN, Double.POSITIVE_INFINITY, 20.0)
        .filter(Double::isFinite) // Java 8+
        .average();

System.out.println(finiteAverage.orElse(Double.NaN)); // 15.0
```

Filtering out invalid values means changing the dataset used to compute the average; the system may need to record the count of discarded records so readers understand the full data quality picture.

### 9.3. Integer Overflow

`int` and `long` do not automatically widen when a sum exceeds their range. For example:

```java
import java.util.stream.IntStream;

int overflowed = IntStream.of(Integer.MAX_VALUE, 1).sum();
System.out.println(overflowed); // -2147483648 (int overflow)
```

If input values are `int` and the sum may exceed `int`, choose `mapToLong` to widen the result range. `IntStream.mapToLong` expects an `IntToLongFunction` taking `int`; use a primitive-converting lambda:

```java
long widened = IntStream.of(Integer.MAX_VALUE, 1)
        .mapToLong(value -> (long) value)
        .sum();
System.out.println(widened); // 2147483648
```

Converting to `long` resolves the case above but **does not** eliminate the possibility of `long` overflow. For sums that can even exceed the `long` range, use `BigInteger` or `BigDecimal` according to the domain, and choose an appropriate rounding mode for averages.

## 10. Monetary Amounts: Exact Sums With BigDecimal, Average Only When count > 0

For currency or values requiring controlled rounding, `BigDecimal` represents decimal numbers exactly as entered. Summing can use `reduce(BigDecimal.ZERO, BigDecimal::add)`, while averaging should divide only when elements are present.

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Optional;

List<BigDecimal> amounts = Arrays.asList(
        new BigDecimal("0.10"),
        new BigDecimal("0.20"));

BigDecimal total = amounts.stream()
        .reduce(BigDecimal.ZERO, BigDecimal::add);

Optional<BigDecimal> average = amounts.isEmpty()
        ? Optional.empty()
        : Optional.of(total.divide(
                BigDecimal.valueOf(amounts.size()),
                2,
                RoundingMode.HALF_UP));

System.out.println(total);   // 0.30
System.out.println(average); // Optional[0.15]

List<BigDecimal> none = Collections.emptyList();
BigDecimal emptyTotal = none.stream()
        .reduce(BigDecimal.ZERO, BigDecimal::add);
Optional<BigDecimal> emptyAverage = none.isEmpty()
        ? Optional.empty()
        : Optional.of(emptyTotal.divide(
                BigDecimal.valueOf(none.size()),
                2,
                RoundingMode.HALF_UP));

System.out.println(emptyTotal);   // 0
System.out.println(emptyAverage); // Optional.empty
```

This example assumes a list containing no `null` elements. If the elements being summed come from a filtering pipeline, you must count **the filtered elements themselves**, not `amounts.size()` of the original list. If the source can only be consumed once, collect both the sum and the count with an appropriate collector before computing the average.

Prefer `new BigDecimal("0.10")` over `new BigDecimal(0.10)` to avoid introducing `double` representation error before constructing the `BigDecimal`.

## 11. Designing Business Policies for Empty Sources

An API returning `OptionalDouble.empty()` **preserves information**; the presentation layer then decides what to display when a result is missing.

| Requirement | Recommended policy |
|---|---|
| Total revenue for a day with no transactions | Return `0` in the corresponding currency unit |
| Average invoice value for a day with no transactions | Keep “no average”; display “No data yet” |
| Dashboard forced to display only a number | May use `orElse(0)` if business rules allow it; should also keep `count` or an empty flag |
| Average value must exist for a downstream step | Validate the data; reject or handle with an appropriate business exception |
| Computing averages by group | Check whether the group exists and the per-group record count; avoid misreading `averaging...() == 0.0` |
| Financial reports requiring exact sum and average | Use `BigDecimal`/smallest currency unit and specify a rounding mode |

There is no single default value that fits every system. What must stay consistent is **separating an empty data state from the numeric value 0** whenever the business cares about that difference.

## 12. Practice Exercises With Solutions

### Exercise 1: Sum and Average Results

```java
int sum = java.util.stream.IntStream.of(4, -4).sum();
java.util.OptionalDouble avg =
        java.util.stream.IntStream.of(4, -4).average();
```

**Answer:** `sum == 0`, `avg.isPresent() == true`, and `avg.getAsDouble() == 0.0`. There are two actual numbers, so the average is defined.

### Exercise 2: Source Emptied by filter

```java
java.util.OptionalDouble avg =
        java.util.stream.IntStream.of(1, 3, 5)
                .filter(n -> n % 2 == 0)
                .average();
```

**Answer:** `OptionalDouble.empty()`, because there are no even numbers after `filter`.

### Exercise 3: Comparing Two Ways to Compute Average

```java
List<Integer> empty = java.util.Collections.emptyList();

java.util.OptionalDouble a =
        empty.stream().mapToInt(Integer::intValue).average();

double b = empty.stream().collect(
        java.util.stream.Collectors.averagingInt(Integer::intValue));
```

**Answer:** `a` is empty; `b == 0.0`. You cannot rely on `b` alone to distinguish an empty source from a source containing a single `0`.

### Exercise 4: Initial summaryStatistics Values

```java
java.util.IntSummaryStatistics stats =
        java.util.stream.IntStream.empty().summaryStatistics();
```

**Answer:** `stats.getCount() == 0`, `stats.getSum() == 0`, `stats.getAverage() == 0.0`. Do not display `stats.getMin()` and `stats.getMax()` as meaningful extrema when count is 0.

### Exercise 5: Designing a Report Result

A reporting API needs to return the total amount, order count, and average order amount; when there are no orders, it must preserve the “no average yet” signal. Should it return three `double` values, or return count, total, and an optional value?

**Answer:** Return **count + total + an optional average** (for example `OptionalDouble` if rounding error is acceptable, or `Optional<BigDecimal>` for money). When count is 0, the total can be 0, but the average must be marked absent if that is a business requirement.

## 13. Key Takeaways

`sum()` on an empty `IntStream`, `LongStream`, and `DoubleStream` returns **0**, whereas `average()` returns **`OptionalDouble.empty()`**. `reduce` with an identity returns the identity on an empty source, whereas `reduce` without an identity returns an empty `Optional`. The `averagingInt`/`averagingLong`/`averagingDouble` collectors and summary statistics produce `0.0` when there are no elements, so you need `count` if you want to distinguish missing data from a genuine average of 0. When computing sums and averages, always consider three factors: **whether the source has elements, whether the value range can overflow, and whether the numeric type meets your precision requirements**.
