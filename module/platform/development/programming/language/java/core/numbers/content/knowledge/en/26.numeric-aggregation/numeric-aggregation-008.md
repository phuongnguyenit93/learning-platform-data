# Parallel Reduce and Associativity Requirements in Java Numeric Aggregation

## 1. Goal and Problem

In Java Streams, `reduce` combines multiple elements into a single result: a sum, product, maximum, or a composite object such as a sum and sample count. When processing **in parallel** via `parallel()` or `parallelStream()`, the Stream can split the input into multiple chunks, aggregate each chunk separately, and then merge those partial results. Because **the grouping of operations can change**, the combining operation (*reduction operator*) must obey specific rules.

For ordinary integer addition in a non-overflowing range, every grouping yields the same sum:

```text
(2 + 3) + 5 = 10
2 + (3 + 5) = 10
```

But for subtraction:

```text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
```

That is why **you cannot take a reduction that works sequentially and blindly switch it to parallel**. Parallel results are reliable only when the operation is associative, the initial value is a true identity element, and lambdas neither depend on external state nor interfere with the source.

This lesson focuses on **numeric aggregation** with `reduce`, including sums, products, and statistical values; it explains the API contract, interactions with `int`/`long`/`double`/`BigDecimal`, writing combiners, and alternatives using `sum()` or `collect()`.

## 2. How Does Reduce Work?

Simple form:

```java
int sum = java.util.stream.IntStream.rangeClosed(1, 4)
        .parallel()
        .reduce(0, Integer::sum);

System.out.println(sum); // 10
```

This is an illustrative snippet you can place inside a Java method body. `rangeClosed(1, 4)` produces `1, 2, 3, 4`; `reduce(0, Integer::sum)` uses `0` as the identity value and `Integer::sum` as the combining function.

An **illustrative** split (the Stream does not guarantee picking this exact split):

```text
Data:              1    2    3    4
First group:      (1 + 2)  = 3
Second group:     (3 + 4)  = 7
Combine:           3 + 7  = 10
```

Another execution schedule might group `1 + (2 + (3 + 4))`. Because integer addition is associative, this does not affect the mathematical result. `parallel()` allows the framework to split and merge work; **it does not guarantee thread count, split layout, execution order, or that execution is always faster**.

On `Stream<T>` there are three main `reduce` forms:

| API form | Result | Key point |
| --- | --- | --- |
| `reduce(BinaryOperator<T> accumulator)` | `Optional<T>` | No identity; empty stream yields `Optional.empty()`. |
| `reduce(T identity, BinaryOperator<T> accumulator)` | `T` | Has identity; empty stream yields identity. |
| `reduce(U identity, BiFunction<U,? super T,U> accumulator, BinaryOperator<U> combiner)` | `U` | Result type can differ from element type; combiner merges results across parallel branches. |

For primitive streams, `IntStream.reduce`, `LongStream.reduce`, and `DoubleStream.reduce` avoid unnecessary boxing. When simply summing primitives, `sum()` usually expresses intent more clearly than `reduce(0, Integer::sum)`.

## 3. Associativity Is the Core Requirement

A binary operation `op` is **associative** if for all `a`, `b`, `c` in the valid data domain:

```text
op(op(a, b), c) == op(a, op(b, c))
```

Associativity lets you change parenthesization without changing the result. This is exactly what parallel reduction needs to merge chunks processed in separate groups.

### 3.1. Associative Examples

- Sum of integers within a range where arithmetic satisfies the contract: `(a + b) + c = a + (b + c)`.
- Product of integers similarly: `(a × b) × c = a × (b × c)`, keeping type limits and overflow rules in mind.
- `min(a, b)` or `max(a, b)` with a consistent comparison.
- `BigInteger` addition and **exact** `BigDecimal` addition by numeric value.
- Merging `(sum, count)` pairs by component-wise addition, when the storage types have sufficient range.

### 3.2. Non-Associative Examples

- `a - b`: `(10 - 3) - 2 = 5`, while `10 - (3 - 2) = 9`.
- `a / b`: changing parentheses generally changes the result, even for rational numbers.
- Pairwise average `(a + b) / 2`: three elements receive unequal weights depending on grouping; not equivalent to sum divided by count.
- `double` floating-point addition in rounding machine arithmetic: mathematically addition is associative, yet finite representation means `(a + b) + c` can differ from `a + (b + c)`.
- Decimal addition that rounds at **every intermediate step** using `MathContext` or `setScale`: losing digits in different groups can produce different results.

**Do not confuse associativity with commutativity.** Commutativity is `op(a,b) = op(b,a)`, meaning swapping operand order. An operation like string concatenation is associative but not commutative. On streams with a defined encounter order, an associative reduction can preserve that ordering semantics; on unordered sources/operations, do not rely on merge order to produce a result when the operation is not commutative.

## 4. Identity: The Identity Element Must Be Correct

In `reduce(identity, accumulator)`, `identity` must be an **identity element** for the operation:

```text
op(identity, x) == x
op(x, identity) == x
```

Some examples:

| Reduction | Valid identity | Why |
| --- | --- | --- |
| `int`/`long` addition | `0`/`0L` | `x + 0 = 0 + x = x` |
| Multiplication | `1` | `x × 1 = 1 × x = x` |
| `min` over full `int` range | `Integer.MAX_VALUE` | `min(MAX_VALUE, x) = x` |
| `max` over full `int` range | `Integer.MIN_VALUE` | `max(MIN_VALUE, x) = x` |
| `BigDecimal` addition | `BigDecimal.ZERO` | Equal by **numeric value**; consider scale if output contract requires a specific representation. |
| Merging `(sum,count)` pairs | `(0,0)` | Component-wise addition leaves the pair unchanged. |

A wrong identity easily breaks parallel execution because it may be used as the initial value for multiple partitions:

```java
// Wrong: 10 is not the identity element for addition.
int suspicious = java.util.stream.IntStream.of(1, 2, 3, 4)
        .parallel()
        .reduce(10, Integer::sum);
```

Do not rely on any specific output from this **intentionally wrong** snippet: it violates the identity contract, so stream splitting can cause `10` to be added multiple times. If you truly want to add a fixed offset `10` once, sum starting from `0` and add `10` **outside** the reduction:

```java
int correct = 10 + java.util.stream.IntStream.of(1, 2, 3, 4)
        .parallel()
        .reduce(0, Integer::sum);
System.out.println(correct); // 20
```

A proper identity also matters for **empty streams**: `IntStream.empty().reduce(0, Integer::sum)` returns `0`. In contrast, `IntStream.empty().reduce(Integer::sum)` returns `OptionalInt.empty()`; depending on business logic, an empty sum may be 0 whereas an empty min/max should be represented as "no value".

## 5. Accumulator and Combiner in Three-Argument reduce

General form:

```java
<U> U reduce(
        U identity,
        BiFunction<U, ? super T, U> accumulator,
        BinaryOperator<U> combiner)
```

Here `T` is the input element type and `U` is the result type. `accumulator` folds one `T` element into a `U` result; `combiner` merges **two `U` results** computed from separate partitions.

Example parsing numeric strings into a `long` sum:

```java
long total = java.util.stream.Stream.of("10", "20", "30")
        .parallel()
        .reduce(
                0L,
                (sum, text) -> sum + Long.parseLong(text),
                Long::sum);

System.out.println(total); // 60
```

To be valid for parallel merging, the Java Stream contract requires:

1. `combiner` is **associative**.
2. `identity` is an **identity element** for `combiner`.
3. **Compatibility between accumulator and combiner**: for all valid `u` and `t`,

```text
combiner(u, accumulator(identity, t)) == accumulator(u, t)
```

In the example above: `accumulator(0, "20") = 20`. Given a prior partial sum `u = 10`, `combiner(10, 20) = 30`, matching `accumulator(10, "20") = 30`. Thus the result does not depend on how the stream is split.

A **wrong example** is an accumulator that adds elements paired with a combiner that subtracts two sums. Although a sequential run might happen to look right because no branch merging occurs, parallel merging alters the meaning; do not use it:

```java
// Wrong: accumulator adds while combiner subtracts, violating compatibility.
long incorrect = java.util.stream.Stream.of("10", "20", "30")
        .parallel()
        .reduce(0L,
                (sum, text) -> sum + Long.parseLong(text),
                (left, right) -> left - right);
```

There is no need to run it to "try your luck" on an output: this is a design bug that must be fixed with `Long::sum`.

### Accumulator Must Be Stateless and Non-Interfering

Lambdas in `reduce` must not depend on mutable external state or modify the Stream source while the pipeline runs. In particular, never write into an external accumulator variable via `forEach`:

```java
int[] total = {0};
java.util.stream.IntStream.rangeClosed(1, 1000)
        .parallel()
        .forEach(n -> total[0] += n); // Wrong: data race.
```

Updates can be lost as multiple threads read/write the same array element concurrently. The right way to sum:

```java
int total = java.util.stream.IntStream.rangeClosed(1, 1000)
        .parallel()
        .sum();
System.out.println(total); // 500500
```

An `AtomicInteger` can prevent the data race for simple addition, yet mutating external state still obscures aggregation intent and can cause contention; `reduce` or `sum()` is the proper approach.

## 6. Why Is Double Addition Not Truly Associative?

IEEE 754 `double` represents a finite number of binary digits. Many additions require rounding as soon as an intermediate result is produced. Consider:

```java
double a = 1e16;
double b = -1e16;
double c = 1.0;

double left = (a + b) + c;
double right = a + (b + c);

System.out.println(left);  // 1.0
System.out.println(right); // 0.0
```

Explanation:

- `a + b = 0`, so `(a + b) + c = 1`.
- `b + c` rounds back to `-1e16` because `1.0` is too small relative to `-1e16` at `double` precision; adding `a` afterward yields `0`.

Therefore, when running `DoubleStream.parallel().sum()` or `reduce(0.0, Double::sum)`, **do not expect every bit of the result to match a sequential left-to-right loop**. Both grouping order and summation algorithm can affect accuracy. Notably, `DoubleStream.sum()` may use compensated summation to improve accuracy, yet the result still must not be treated as exact real-number arithmetic.

Special cases of `NaN`, positive/negative infinity, and `-0.0` must also be tested if datasets can contain them. For example, `Double.sum()`/`DoubleStream.sum()` have specific rules for `NaN` and infinities; do not compare floating-point results as if they were exact decimals.

Practical strategies:

- If you need an **exact decimal sum** per business requirements, consider `BigDecimal` with proper construction and scale.
- If `double` suffices for simulation/statistics, accept differences within a defined tolerance and test inputs with large magnitude disparities.
- If you need bit-exact reproducibility across different execution schedules, control the algorithm, grouping order, and environment; calling `parallel()` alone does not guarantee that.
- Do not use `==` as a general check between sums computed along two different paths when rounding error is permissible; instead compare against a meaningful tolerance and handle `NaN`/infinities explicitly.

## 7. BigDecimal: Exact Addition vs. Intermediate-Rounded Addition

`BigDecimal.add(other)` **without a `MathContext`** performs exact decimal addition, with a result scale reflecting the operands' scales. By numeric value, exact addition is associative, making it a sound choice when summing decimal amounts before business-level rounding:

```java
import java.math.BigDecimal;
import java.util.stream.Stream;

BigDecimal total = Stream.of("0.10", "0.20", "0.30")
        .map(BigDecimal::new)
        .parallel()
        .reduce(BigDecimal.ZERO, BigDecimal::add);

System.out.println(total.toPlainString()); // 0.60
```

Each input value has scale 2. When added exactly, the result has an appropriate scale; using `BigDecimal.ZERO` as the identity is valid by numeric value. If inputs have varying scales, distinguish **numeric equality** (via `compareTo()`) from **`equals()`** (which checks scale too). When the output contract requires a fixed scale, normalize at the defined boundary via `setScale(requiredScale, roundingMode)`.

### Rounding at Every Addition Breaks Associativity

If a lambda rounds after **every addition**, changing grouping can produce different answers. For example, with `HALF_UP` to scale 2:

```text
(a + b) + c, rounding each step:
a = 1.24, b = 0.005, c = 0.005
round2(1.24 + 0.005) = 1.25
round2(1.25 + 0.005) = 1.26

a + (b + c), rounding each step:
round2(0.005 + 0.005) = 0.01
round2(1.24 + 0.01) = 1.25
```

Verification in Java:

```java
BigDecimal a = new BigDecimal("1.24");
BigDecimal b = new BigDecimal("0.005");
BigDecimal c = new BigDecimal("0.005");
java.util.function.BinaryOperator<BigDecimal> roundedAdd =
        (x, y) -> x.add(y).setScale(2, java.math.RoundingMode.HALF_UP);

System.out.println(roundedAdd.apply(roundedAdd.apply(a, b), c)); // 1.26
System.out.println(roundedAdd.apply(a, roundedAdd.apply(b, c))); // 1.25
```

**Do not pass this `roundedAdd` into `parallel().reduce(...)` if you expect a result independent of partitioning.** Likewise, `a.add(b, mathContext)` can round at every step and does not guarantee associativity in machine results. When business rules allow, sum at full/appropriate precision and round **once at the final boundary**:

```java
BigDecimal result = Stream.of(a, b, c)
        .parallel()
        .reduce(BigDecimal.ZERO, BigDecimal::add)
        .setScale(2, java.math.RoundingMode.HALF_UP);

System.out.println(result); // 1.25
```

If business rules mandate rounding each invoice or line item before adding, that is a **different calculation** and must be modeled explicitly; never silently alter the policy just to optimize for parallelism.

## 8. Integer Overflow and the Meaning of Sum

In Java, `int`/`long` addition can overflow the numeric type limits without throwing an error. Wraparound addition on integer types is deterministic, and modular addition for a fixed bit width is in fact still associative, yet **the result no longer equals the mathematical integer sum you may be expecting**.

Example:

```java
int result = java.util.stream.IntStream.of(
        Integer.MAX_VALUE, 1)
        .parallel()
        .reduce(0, Integer::sum);

System.out.println(result); // -2147483648
```

This is `int` overflow behavior, not a bug caused by parallel reduction. If the sum can exceed the `int` range, consider `long` or `BigInteger`:

```java
long exactWithinLong = java.util.stream.IntStream.of(
        Integer.MAX_VALUE, 1)
        .asLongStream()
        .parallel()
        .sum();

System.out.println(exactWithinLong); // 2147483648
```

`long` also has limits. `Math.addExact` helps **detect** overflow via `ArithmeticException`, but it is not universally deterministic across all `long` triples: for sequences with cancelling values, one grouping may overflow mid-way while another does not. If exactness is required for unboundedly large sums, `BigInteger::add` is safer across the value domain.

## 9. Designing Multi-Quantity Numeric Aggregations

To compute both sum and count for an average, **pairwise averaging is not associative**:

```text
avg2(avg2(2, 4), 6) = 4.5
avg2(2, avg2(4, 6)) = 3.5
```

Whereas the arithmetic mean of the three numbers is `(2 + 4 + 6) / 3 = 4.0`. Instead of reducing with a two-number average formula, combine a state holding **sum + count** and divide once at the end:

```java
record SumCount(long sum, long count) {}

SumCount left = new SumCount(10, 1);
SumCount right = new SumCount(20, 1);
SumCount joined = new SumCount(
        left.sum() + right.sum(),
        left.count() + right.count());

System.out.println(joined); // SumCount[sum=30, count=2]
```

This example assumes **placing the record inside a valid class or Java source file** (not directly inside a method body if code depends on outer scope ambiguously). The complete program in Section 11 demonstrates creating an immutable record and reducing in parallel.

Mathematically, merging two `SumCount` values:

```text
combine((s1, n1), (s2, n2)) = (s1 + s2, n1 + n2)
identity = (0, 0)
mean = sum / count   (only after reduce finishes)
```

is associative for exact additions. When using `long`, sum and count must still stay within valid bounds or switch to a wider representation.

For basic cases, you can use the standard library API:

```java
java.util.IntSummaryStatistics stats =
        java.util.stream.IntStream.of(10, 20, 30, 40)
                .parallel()
                .summaryStatistics();

System.out.println(stats.getSum());   // 100
System.out.println(stats.getCount()); // 4
System.out.println(stats.getAverage()); // 25.0
```

`summaryStatistics()` clearly expresses statistical intent (count, sum, min, max, average) without writing a custom combiner. However, it still uses primitive numeric types and carries the overflow/precision limits of those types.

## 10. Choosing Between reduce, collect, sum, and summaryStatistics

| Goal | Suitable API | Reason |
| --- | --- | --- |
| Sum of `int`/`long`/`double` | `IntStream.sum()`, `LongStream.sum()`, `DoubleStream.sum()` | Readable, avoids unnecessary boxing; still subject to numeric bounds. |
| Exact `BigDecimal` sum | `stream.reduce(BigDecimal.ZERO, BigDecimal::add)` | Reduction creates immutable `BigDecimal` values. |
| Max/min of possibly empty stream | `max()`/`min()` or `reduce(BinaryOperator)` | `Optional*` result reflects absence of elements. |
| Primitive sum + count + min + max | `summaryStatistics()` | Specialized API without manually combining multiple reductions. |
| Combining multiple metrics into an immutable result | `reduce` with a record and associative combiner | Clear control over state model and identity. |
| Collecting elements into list/map/set or mutable accumulator | `collect()` / `Collectors` | Mutable reduction has supplier, accumulator, and combiner designed for merging containers. |

**Do not mutate a shared identity inside `reduce`.** For example:

```java
// Wrong for reduce: mutable List is used as identity and mutated inside.
java.util.List<Integer> numbers = java.util.stream.Stream.of(1, 2, 3)
        .parallel()
        .reduce(
                new java.util.ArrayList<>(),
                (list, x) -> { list.add(x); return list; },
                (left, right) -> { left.addAll(right); return left; });
```

This pattern violates the reduction contract and can cause indeterminate behavior from shared data across branches. Use `collect(java.util.stream.Collectors.toList())` to build a collection, or a collector suited to ordering/concurrency needs. `reduce` fits **immutable** accumulator types or side-effect-free combining best.

## 11. Complete Java 17+ Program: Testing Associativity and Parallelism

Save as **`ParallelNumberReductionDemo.java`**:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class ParallelNumberReductionDemo {
    record SumCount(long sum, long count) {}

    public static void main(String[] args) {
        int parallelSum = IntStream.rangeClosed(1, 1000)
                .parallel()
                .reduce(0, Integer::sum);
        int sequentialSum = IntStream.rangeClosed(1, 1000)
                .reduce(0, Integer::sum);
        System.out.println("parallel integer sum = " + parallelSum);
        System.out.println("same as sequential = "
                + (parallelSum == sequentialSum));

        BigDecimal decimalSum = Stream.of("0.10", "0.20", "0.30")
                .map(BigDecimal::new)
                .parallel()
                .reduce(BigDecimal.ZERO, BigDecimal::add);
        System.out.println("exact decimal sum = "
                + decimalSum.toPlainString());

        double a = 1e16;
        double b = -1e16;
        double c = 1.0;
        System.out.println("floating left = " + ((a + b) + c));
        System.out.println("floating right = " + (a + (b + c)));

        BigDecimal x = new BigDecimal("1.24");
        BigDecimal y = new BigDecimal("0.005");
        BigDecimal z = new BigDecimal("0.005");
        java.util.function.BinaryOperator<BigDecimal> roundedAdd =
                (left, right) -> left.add(right)
                        .setScale(2, RoundingMode.HALF_UP);
        System.out.println("rounded left = "
                + roundedAdd.apply(roundedAdd.apply(x, y), z));
        System.out.println("rounded right = "
                + roundedAdd.apply(x, roundedAdd.apply(y, z)));

        SumCount summary = List.of(10L, 20L, 30L, 40L)
                .parallelStream()
                .map(n -> new SumCount(n, 1))
                .reduce(new SumCount(0, 0),
                        (left, right) -> new SumCount(
                                left.sum() + right.sum(),
                                left.count() + right.count()));
        System.out.println("sum = " + summary.sum());
        System.out.println("count = " + summary.count());
        System.out.println("average = "
                + ((double) summary.sum() / summary.count()));

        long parsedTotal = Stream.of("10", "20", "30")
                .parallel()
                .reduce(0L,
                        (sum, text) -> sum + Long.parseLong(text),
                        Long::sum);
        System.out.println("parsed total = " + parsedTotal);
    }
}
```

Compile and run in the file's directory using JDK 17 or newer:

```bash
javac ParallelNumberReductionDemo.java
java ParallelNumberReductionDemo
```

Expected output:

```text
parallel integer sum = 500500
same as sequential = true
exact decimal sum = 0.60
floating left = 1.0
floating right = 0.0
rounded left = 1.26
rounded right = 1.25
sum = 100
count = 4
average = 25.0
parsed total = 60
```

Values in the output are **verifiable results**: non-overflowing `int` addition, exact `BigDecimal.add`, and associative sum/count record reduction; meanwhile the two "left/right" pairs are explicitly parenthesized to demonstrate rounding discrepancies. The program does not depend on any specific thread-splitting schedule to produce its stdout.

Note: **do not prove an operator is broken by running `parallel().reduce` once and looking for a strange answer**. Some runs happen to group sequentially and still look "clean". Proving via mathematical conditions and explicit parenthesized counterexamples as shown above is far more reliable.

## 12. Performance, Side Effects, and Source Characteristics

`parallel()` does not automatically boost performance. Splitting tasks, moving data across threads, and merging results all carry overhead. For small sets or very cheap operations like summing a few dozen numbers, parallel execution can be **slower** than sequential execution. Benchmarks must use identical data, account for JIT warmup, sufficient measurement iterations, and controlled environments; avoid drawing conclusions from a single run.

The source `Spliterator`'s splitting behavior, dataset size, CPU core count, per-element work complexity, and combiner cost all affect results. Parallel streams typically use the fork/join pool, yet **do not guarantee a fixed worker set** or predictable execution order across all pipelines.

Ask these questions before choosing parallel execution:

1. Is the combining operation **associative** over the data domain and rounding policy in use?
2. Is `identity` a true identity element for all merged partitions?
3. For the three-argument form, is `combiner` compatible with `accumulator`?
4. Are all lambdas stateless, non-interfering, and free of shared mutable state?
5. If the stream lacks a fixed encounter order, could the result depend on element order?
6. Can the numeric type overflow or lose significant precision?
7. Is there enough work to outweigh parallelization overhead?

One small note on data flow: `forEach` on a parallel stream can invoke its action on arbitrary threads and in arbitrary order. `forEachOrdered` preserves encounter order for ordered sources, though it can add overhead. This is **different** from how `reduce` groups operations: even when encounter order is preserved, a non-associative operation can still yield different answers due to changed parenthesization.

## 13. Typical Mistakes and How to Fix Them

**Mistake 1 — Using subtraction or division as a reducer.** These operations are not associative; rewrite the goal using state with a proper associative combiner, or run sequentially if semantics truly depend on order.

**Mistake 2 — Using an `identity` that is not the identity element.** For sums, choose `0` instead of a pre-added offset; add any offset once outside `reduce`.

**Mistake 3 — Accumulator adds while combiner subtracts or multiplies.** Check the compatibility equation; naming a combiner "merge" is not enough—it must combine according to the accumulator's semantics.

**Mistake 4 — Mutating the identity object or an external variable.** Use immutable values in `reduce`; use `collect` for mutable containers; avoid data races in `forEach`.

**Mistake 5 — Assuming `double` sums are always bit-identical between sequential and parallel runs.** False for floating point; check within tolerance or use an algorithm with a fixed merge order.

**Mistake 6 — Rounding per step with `BigDecimal` and expecting associativity.** `add(..., MathContext)` or `setScale` after each addition can make results depend on grouping; when business logic allows, add exactly first and round once.

**Mistake 7 — Computing averages via repeated `(a+b)/2`.** Grouping alters weights. Aggregate `sum/count` and divide at the end.

**Mistake 8 — Ignoring overflow.** `int`/`long` can wrap around; use a wider type or `BigInteger` when the mathematical sum must be exact.

**Mistake 9 — Assuming `parallel()` automatically makes things faster.** Measure to decide; many simple pipelines are better off sequential.

**Mistake 10 — Confusing levels of equality.** For decimals with different scales, `BigDecimal.equals()` checks scale whereas `compareTo()` checks numeric value; for `double`, use numeric checks aware of rounding, `NaN`, and infinity.

## 14. Self-Check

**Question 1.** When reducing `Stream.of(10, 3, 2)` by subtraction, why does `parallel()` lack a mathematically stable result independent of grouping?

**Answer:** `(10 - 3) - 2 = 5` whereas `10 - (3 - 2) = 9`; subtraction is not associative.

**Question 2.** What are the proper identities for addition and multiplication?

**Answer:** `0` and `1`. An identity must leave any element unchanged when placed on either side of the operation.

**Question 3.** What compatibility equation does `reduce(0L, accumulator, combiner)` require?

**Answer:** `combiner(u, accumulator(identity, t)) == accumulator(u, t)`, in addition to combiner associativity and identity neutrality.

**Question 4.** Why can `(1e16 + -1e16) + 1.0` differ from `1e16 + (-1e16 + 1.0)` with `double`?

**Answer:** Each addition is limited by floating-point precision. Adding `-1e16 + 1.0` loses `1.0` due to rounding, resulting in `0.0` for the right-hand grouping.

**Question 5.** Should you parallel-reduce using `(x,y) -> x.add(y).setScale(2, HALF_UP)`?

**Answer:** No, if you need a result independent of partitioning. Addition that rounds after each step is not associative; e.g., `1.24, 0.005, 0.005` yields `1.26` or `1.25` depending on grouping.

**Question 6.** When averaging millions of elements, why not use a `(a+b)/2` reducer?

**Answer:** It does not preserve equal weight for every observation across repeated merges. Combine a state with sum and count, or use `summaryStatistics()` per precision requirements.

**Question 7.** Is `Integer.MAX_VALUE + 1` returning `-2147483648` a bug caused by parallel reduce?

**Answer:** No. That is `int` overflow. Choose `long`/`BigInteger` when the mathematical sum exceeds `int` bounds.

**Question 8.** On an empty stream, how do `reduce(0, Integer::sum)` and `reduce(Integer::sum)` differ?

**Answer:** The form with an identity returns `0`; the form without an identity returns `Optional.empty()` or `OptionalInt.empty()` for primitive streams.

**Question 9.** Can you use `Collectors.toList()` instead of mutating an `ArrayList` inside `reduce`?

**Answer:** Yes, that is the purpose of `collect` for mutable reduction. A `reduce` accumulator should honor the contract and avoid shared mutation.

**Question 10.** What mathematical conditions suffice for an aggregation to be semantically valid as a parallel reduction?

**Answer:** The combining operation is associative on the valid domain, the identity is neutral, and in the three-argument form the combiner is compatible with the accumulator; additionally, lambdas must be stateless and non-interfering. For machine floating-point numbers and rounding, you must also define what "correct" means under your precision contract.

## 15. Official Documentation

- [Java SE 17 — Stream.reduce](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html): overloads, identity, associativity requirements, stateless/non-interfering rules, and compatibility equation.
- [Java SE 17 — IntStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/IntStream.html): reduce, sum, summaryStatistics, and primitive streams.
- [Java SE 17 — DoubleStream.sum](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/DoubleStream.html#sum()): floating-point sum behavior and precision notes.
- [Java SE 17 — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): exact addition, MathContext, scale, and rounding.

**Remember:** Parallel reduce is permitted to change how elements are **grouped**. A valid reduction requires **associativity**, a proper **identity**, a compatible **combiner**, and non-interfering stateless lambdas. `double` addition or `BigDecimal` addition with intermediate rounding can change results by grouping; establish clear precision policies and rounding boundaries before choosing parallel reduction.