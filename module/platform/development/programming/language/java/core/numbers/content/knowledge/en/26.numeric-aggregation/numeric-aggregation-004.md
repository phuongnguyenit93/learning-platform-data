# average and Empty-Set Handling Requirements in Java

## 1. Why Is an Empty Set a Special Case?

The arithmetic mean of `n` numbers is their sum divided by the element count:

```text
average = (x1 + x2 + ... + xn) / n
Condition: n > 0
```

For example, `[10, 20, 30]` has sum 60, count 3, and mean 20.0. However, an empty set contains no terms: the conventional sum is 0, the count is 0, and `0 / 0` **has no defined arithmetic mean**.

In Java, **different APIs choose different representations for the empty case**:

| API | On a non-empty set | On an empty set |
| --- | --- | --- |
| `IntStream.average()` | `OptionalDouble` containing value | `OptionalDouble.empty()` |
| `LongStream.average()` | `OptionalDouble` containing value | `OptionalDouble.empty()` |
| `DoubleStream.average()` | `OptionalDouble` containing value | `OptionalDouble.empty()` |
| `Collectors.averagingInt/Long/Double` | `Double` containing mean | `0.0` |
| `IntSummaryStatistics.getAverage()` | `double` containing mean | `0.0` |
| `LongSummaryStatistics.getAverage()` | `double` containing mean | `0.0` |
| `DoubleSummaryStatistics.getAverage()` | `double` containing mean | `0.0` |

The key point: **`0.0` is a valid numeric result**, for example the average of `[-10, 10]`; therefore you cannot tell from the number `0.0` alone whether any data existed. If empty sets are mishandled, a program might report an average score of 0 for a class with no grades yet, or an average response time of 0 ms when no requests have been recorded.

## 2. Primitive Stream average() Returns OptionalDouble

Java provides `average()` on the three primitive streams: `IntStream`, `LongStream`, and `DoubleStream`. Each method returns `java.util.OptionalDouble`, rather than returning `double` directly.

```java
OptionalDouble present = IntStream.of(2, 4, 6).average();
OptionalDouble absent = IntStream.empty().average();

// present.isPresent() == true, present.orElseThrow() == 4.0
// absent.isEmpty() == true
```

The snippet above only illustrates the API inside a method; to use it standalone, import `java.util.OptionalDouble` and `java.util.stream.IntStream`.

`OptionalDouble` represents two states:

- **Present:** for example, `OptionalDouble.of(0.0)` is still a present result, even though the value is zero.
- **Absent:** `OptionalDouble.empty()` indicates the aggregation has no average because elements are missing.

Common handling methods:

| Method | Meaning |
| --- | --- |
| `isPresent()` | Is a result present? |
| `isEmpty()` | Is no result present? (Java 11+) |
| `ifPresent(action)` | Perform action only when a result is present |
| `orElse(defaultValue)` | Return real value or caller-defined default |
| `orElseGet(supplier)` | Compute default value when no result is present |
| `orElseThrow()` | Value required; throws `NoSuchElementException` if absent |
| `orElseThrow(exceptionSupplier)` | Throw domain-specified exception if empty |
| `getAsDouble()` | Read present value; throws `NoSuchElementException` if empty |
| `stream()` | Convert to a `DoubleStream` with 0 or 1 element (Java 9+) |

Calling `average()` on an empty primitive stream **does not throw an exception by itself**; an exception occurs when the caller tries to extract an absent value via `getAsDouble()` or `orElseThrow()`.

## 3. First Java 17+ Program: Present, Absent, and Default Results

Save the following as `AverageEmptyDemo.java`:

```java
import java.util.IntSummaryStatistics;
import java.util.OptionalDouble;
import java.util.stream.Collectors;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class AverageEmptyDemo {
    public static void main(String[] args) {
        OptionalDouble normal = IntStream.of(10, 20, 30).average();
        OptionalDouble zeroMean = IntStream.of(-5, 5).average();
        OptionalDouble missing = IntStream.empty().average();

        System.out.println("Normal: " + normal.orElseThrow());
        System.out.println("Zero mean present: " + zeroMean.isPresent());
        System.out.println("Zero mean value: " + zeroMean.orElseThrow());
        System.out.println("Empty present: " + missing.isPresent());
        System.out.println("Empty fallback: " + missing.orElse(0.0));

        double collectorEmpty = Stream.<Integer>empty()
                .collect(Collectors.averagingInt(Integer::intValue));
        IntSummaryStatistics stats = IntStream.empty().summaryStatistics();

        System.out.println("Collector empty: " + collectorEmpty);
        System.out.println("Summary count: " + stats.getCount());
        System.out.println("Summary average: " + stats.getAverage());
    }
}
```

Compile and run:

```bash
javac AverageEmptyDemo.java
java AverageEmptyDemo
```

Exact stdout:

```text
Normal: 20.0
Zero mean present: true
Zero mean value: 0.0
Empty present: false
Empty fallback: 0.0
Collector empty: 0.0
Summary count: 0
Summary average: 0.0
```

`Zero mean value: 0.0` and `Empty fallback: 0.0` have the same number but **different meanings**: one computation had two numbers, while the other had no value and was *substituted* with 0 by the caller. `Collector empty: 0.0` is the collector's convention, not a mathematical claim that the arithmetic mean of an empty set is 0.

## 4. Three Policies for Empty Sets

### 4.1. Allow Missing Results: Keep OptionalDouble

For reports that may have no transactions, no exam scores, or no sensor samples yet, **having no average** is a normal state.

```java
OptionalDouble average = scores.stream()
        .mapToInt(Integer::intValue)
        .average();
```

This illustration assumes `scores` is a `Collection<Integer>` without `null` elements inside a method. Returning `OptionalDouble` directly from the service lets the presentation layer choose "No data yet" instead of accidentally showing `0`.

### 4.2. Empty Not Allowed: Throw a Business Exception

If at least one value is mandatory, validate and report the cause clearly:

```java
double mean = scores.stream()
        .mapToInt(Integer::intValue)
        .average()
        .orElseThrow(() ->
                new IllegalArgumentException("At least one score is required"));
```

`orElseThrow(Supplier)` provides a contextual exception. This is easier to diagnose than calling `getAsDouble()` unchecked and letting `NoSuchElementException` propagate.

### 4.3. Explicit Default Policy: Use orElse

If the report specification states "display 0 when there are no samples", you can use:

```java
double displayAverage = values.stream()
        .mapToDouble(Double::doubleValue)
        .average()
        .orElse(0.0);
```

Understand clearly: this is a **business-defined fallback value**, not an average computed from an empty set. When you need to distinguish "empty" from "true average of 0", also store the element count or a presence flag.

Do not arbitrarily use `-1`, `NaN`, or `0` as a "missing" sentinel: the domain might legitimately produce those values, and JSON/database handling or subsequent math can change their meaning. `OptionalDouble` or a result carrying a `count` field represents missing data much more clearly.

## 5. Distinguishing Stream.average and Collectors.averaging*

Object `Stream<T>` **does not** have `average()` directly. If you have a `List<Integer>`, you typically convert to a primitive stream:

```java
OptionalDouble average = numbers.stream()
        .mapToInt(Integer::intValue)
        .average();
```

Or use a collector:

```java
double average = numbers.stream()
        .collect(Collectors.averagingInt(Integer::intValue));
```

Both blocks assume `numbers` is a valid `List<Integer>` in the calling scope; they are not standalone Java programs. In the first case, empty yields `OptionalDouble.empty()`. In the second case, empty yields `0.0` because `Collectors.averagingInt` returns `Double` and is defined that way.

`Collectors.averagingLong` and `Collectors.averagingDouble` follow the same policy on empty sets. The difference in return type determines how much information is retained: a collector returning only a number **cannot preserve** the "no elements" state.

When using `groupingBy`, a group appears in the result only if at least one element belongs to that group; a group absent from the map **is not** an entry with an average of 0.0. You must obtain the required list of groups from domain data if empty groups also need to be represented.

## 6. SummaryStatistics: Check count Before Interpreting average

`summaryStatistics()` computes multiple metrics in a single terminal operation. For example:

```java
IntSummaryStatistics statistics = numbers.stream()
        .mapToInt(Integer::intValue)
        .summaryStatistics();

long count = statistics.getCount();
if (count == 0) {
    System.out.println("No observations");
} else {
    System.out.println("Average = " + statistics.getAverage());
}
```

This snippet assumes `java.util.IntSummaryStatistics` is imported and `numbers` is a collection without `null` elements.

For an empty `IntSummaryStatistics`:

- `getCount()` returns `0`.
- `getSum()` returns `0`.
- `getAverage()` returns `0.0`.
- `getMin()` returns `Integer.MAX_VALUE`.
- `getMax()` returns `Integer.MIN_VALUE`.

Therefore, check `count` before presenting average, min, and max as statistics from actual samples. `LongSummaryStatistics` and `DoubleSummaryStatistics` also have a count and default values for empty sets, though the types and numeric bounds of min/max differ.

`summaryStatistics()` is appropriate when you need count together with mean, min, and max. If you only care about the average and presence/absence status, `average()` returning `OptionalDouble` directly is usually simpler.

## 7. Designing APIs to Preserve Empty-Set Semantics

A utility returning `OptionalDouble` lets callers apply their own business rules:

```java
import java.util.Collection;
import java.util.Objects;
import java.util.OptionalDouble;

public class AverageService {
    public static OptionalDouble ofIntegers(Collection<Integer> values) {
        Objects.requireNonNull(values, "values");
        return values.stream()
                .mapToInt(Integer::intValue)
                .average();
    }
}
```

This class compiles as-is without `main`; it provides a utility method to call from other code.

Example:

```java
OptionalDouble x = AverageService.ofIntegers(java.util.List.of(4, 6));
// x.orElseThrow() == 5.0

OptionalDouble y = AverageService.ofIntegers(java.util.List.of());
// y.isEmpty() == true
```

Note: `Objects.requireNonNull` only checks that the **collection** is non-null; it does not check individual elements. If an `Integer` element is `null`, unboxing via `Integer::intValue` throws `NullPointerException`. Decide whether `null` elements are invalid input, missing values to record, or entries to skip, and implement that exact policy.

For JSON APIs, consider a DTO representing `count` and a nullable `average` field, rather than expecting every serialization library to treat `OptionalDouble` as a standard field. Field names and absence rules should be documented clearly.

## 8. Program Illustrating Grouped Data

In per-class statistics, a group with no records normally **has no key** in the `groupingBy` result. Save `GroupAverageDemo.java`:

```java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class GroupAverageDemo {
    record Score(String group, int points) {}

    public static void main(String[] args) {
        List<Score> data = List.of(
                new Score("A", 10),
                new Score("A", 20));

        Map<String, Double> result = data.stream().collect(
                Collectors.groupingBy(
                        Score::group,
                        Collectors.averagingInt(Score::points)));

        System.out.println("A average: " + result.get("A"));
        System.out.println("Has B: " + result.containsKey("B"));
        System.out.println("Group count: " + result.size());
    }
}
```

Run:

```bash
javac GroupAverageDemo.java
java GroupAverageDemo
```

Stdout:

```text
A average: 15.0
Has B: false
Group count: 1
```

There is no key B because the input data contains no `Score` for B. If the report must display B, fetch the list of classes from the domain source and reconcile it with the statistics result; absent classes cannot be inferred from the input stream alone.

## 9. Precision and Arithmetic Pitfalls When Computing average

Handling empty sets is distinct from choosing precision. `average()` returns `double`, even when input data is `int` or `long`. `double` has finite precision, so calculations may be rounded, especially for large datasets. With `DoubleStream`, the result can be `NaN` or infinity depending on the data.

Points to note:

1. `OptionalDouble.of(Double.NaN)` **is not the same as** `OptionalDouble.empty()`. If the application only accepts finite numbers, call `Double.isFinite(value)` after verifying a value is present.
2. When implementing manually with `int sum` and `int count`, `sum / count` is **integer division**. For instance, sum 5 and count 2 produces integer 2 before assignment to `double`. Cast to `double` before dividing: `((double) sum) / count`.
3. When summing manually in integer types, `int` or `long` sums can overflow. Do not assume inputs are small just because each element has type `int`.
4. The addition order of `double` values can affect error. Some Java aggregations use error-compensated summation, though that still does not guarantee exact mathematical real-number results.
5. Do not blindly use `==` to compare floating-point averages computed by different algorithmic pipelines; design an error tolerance and handle `NaN` and infinities according to the problem.
6. For monetary data requiring exact decimal arithmetic and explicit rounding, consider `BigDecimal`.

Additionally, a `Stream` is consumed **once**. Calling `count()` and then `average()` on the same primitive stream is invalid; two terminal operations cannot run on the same consumed stream. Create a fresh stream from the collection, or use `summaryStatistics()` to get count and average in a single pass.

## 10. BigDecimal: Empty Check and Explicit Rounding

For decimal numbers requiring controlled precision and rounding, you can sum with `BigDecimal` and divide by the element count. However, you must check for an empty set before dividing to avoid a zero divisor.

Save `DecimalAverageDemo.java`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

public class DecimalAverageDemo {
    static Optional<BigDecimal> average(List<BigDecimal> values) {
        Objects.requireNonNull(values, "values");
        if (values.isEmpty()) {
            return Optional.empty();
        }

        BigDecimal sum = BigDecimal.ZERO;
        for (BigDecimal item : values) {
            sum = sum.add(Objects.requireNonNull(item, "item"));
        }

        BigDecimal mean = sum.divide(
                BigDecimal.valueOf(values.size()),
                2,
                RoundingMode.HALF_UP);

        return Optional.of(mean);
    }

    public static void main(String[] args) {
        System.out.println("Mean: " + average(List.of(
                new BigDecimal("1.00"),
                new BigDecimal("2.00"),
                new BigDecimal("2.00"))).orElseThrow());
        System.out.println("Empty: " + average(List.of()).isEmpty());
        System.out.println("Zero mean: " + average(List.of(
                new BigDecimal("-1.00"),
                new BigDecimal("1.00"))).orElseThrow());
    }
}
```

Run:

```bash
javac DecimalAverageDemo.java
java DecimalAverageDemo
```

Stdout:

```text
Mean: 1.67
Empty: true
Zero mean: 0.00
```

`5.00 / 3` has a non-terminating decimal expansion, so calling `divide(divisor)` *without specifying a rounding mode* throws `ArithmeticException`. The example chose scale 2 and `HALF_UP`, yielding `1.67`. Scale and rounding mode must come from business requirements; **do not assume every monetary value uses two decimal places**.

When there are no elements, the function returns `Optional.empty()` without dividing. When elements exist and the true mean is 0, it returns `Optional.of(new BigDecimal("0.00"))` matching the computed value and scale.

## 11. Grouped Averages and Weighted Averages

Not every requirement called "average" means the same thing:

- **Simple arithmetic mean:** `sum(values) / count`, defined only when count > 0.
- **Weighted average:** `sum(value × weight) / sum(weight)`; check total weight per contract before dividing.
- **Average of group averages:** differs from the overall average across all elements if groups have unequal sizes.
- **Time-weighted average:** if sampling intervals vary, weighting by duration may be required instead of treating every observation as one equal unit.

For example, group A has one score of 10, and group B has three scores of 20, 20, 20. The average of group averages is `(10 + 20) / 2 = 15`; the average across all four students is `(10 + 20 + 20 + 20) / 4 = 17.5`. Which calculation is appropriate depends on the reporting question.

Empty sets, empty groups, and zero total weight all need explicit rules. Do not treat `Collectors.averagingInt` returning 0.0 as equivalent to a valid weighted average.

## 12. Suggestions for Testing Key Cases

For an averaging utility, cover these cases:

| Input | What to verify |
| --- | --- |
| `[]` | Empty policy: Optional empty, error, or default |
| `[0]` | True average `0.0` with one element |
| `[-5, 5]` | Average `0.0` from two elements, not an empty set |
| `[1, 2]` | Average `1.5`; avoids integer-division bug |
| `[1, 2, 2]` with BigDecimal | Valid rounding policy, e.g., scale 2 gives `1.67` |
| Data containing `null` | Clear policy to accept, reject, or skip |
| Data containing `Double.NaN` or infinity | Do not confuse non-finite numbers with empty Optional |
| Only group A present | Do not assume group B has a real average of 0 |
| Very large list | Watch for integer sum overflow and double precision loss |

You can unit-test an `OptionalDouble` function using `isEmpty()` for the empty case and `orElseThrow()` for present data; there is no need to expose hidden streams inside the test.

## 13. Common Mistakes

| Mistake | Impact | Fix |
| --- | --- | --- |
| Calling `average().getAsDouble()` when empty | `NoSuchElementException` | Check Optional or use contextual `orElseThrow` |
| Using `orElse(0.0)` everywhere | Confuses "no samples" with "average is 0" | Keep Optional/count unless business defines a default |
| Assuming `Collectors.averagingInt` returns Optional | Misunderstands API contract | Check count or use a primitive stream |
| Reading `summaryStatistics.getAverage()` at count=0 as a measurement | Inaccurate reporting | Check `getCount()` |
| Writing `sum / count` with integers | Loses fractional digits | Cast before dividing |
| Reusing a stream after a terminal operation | Stream already consumed | Create a new stream or single-pass summary |
| Passing an empty list to BigDecimal division | Division by 0 | Guard count > 0 before divide |
| Omitting scale/rounding on BigDecimal | Can throw `ArithmeticException` on repeating decimals | Declare decimal policy |
| Treating `Double.NaN` as missing data | Wrong state | Distinguish `isPresent` from `Double.isFinite` |
| Averaging group averages while forgetting group counts | Incorrect overall result | Compute weighted sum and count |

## 14. Self-Check

1. **What does `IntStream.empty().average()` return?** `OptionalDouble.empty()`; `average()` does not throw an error on its own.
2. **Are `OptionalDouble.empty()` and `OptionalDouble.of(0.0)` distinguishable?** Yes; one means missing data, the other holds the value 0.0.
3. **What does `Stream.<Integer>empty().collect(Collectors.averagingInt(Integer::intValue))` return?** `0.0` per the collector's contract.
4. **What does `IntStream.empty().summaryStatistics().getAverage()` return?** `0.0`; check `getCount() == 0` before interpreting it.
5. **If at least one score is required, how should it be handled?** Use `average().orElseThrow(() -> new IllegalArgumentException(...))` or validate input data upfront.
6. **What if having no scores yet is a valid state?** Return Optional or a structure with count; display "No data yet".
7. **Can you use the same stream for `count()` and then `average()`?** No; a terminal operation consumes the stream.
8. **Does an average result of NaN mean the Optional is empty?** No; the Optional can be present and hold NaN.
9. **Why might `BigDecimal` average division require rounding?** Because quotients like 5/3 have infinitely many decimal digits, so scale/rounding must be specified if rounding is allowed.

## 15. Conclusion

When using `average` in Java, the key issue is not only dividing the sum by the count, but also **defining behavior when there are no elements**. `IntStream`, `LongStream`, and `DoubleStream` return `OptionalDouble` to preserve the absent state; `Collectors.averaging*` and `SummaryStatistics.getAverage()` return `0.0` when empty because that is their API contract, not an assertion that the mathematical mean of an empty set is 0.

Choose a concrete policy: keep Optional when missing data is normal, throw a contextual error if non-empty input is mandatory, or use a default only when a clear business rule specifies one. For real-world data, also check `count`, `double` precision, non-finite values, and `BigDecimal` rounding so results remain meaningful and reliable.