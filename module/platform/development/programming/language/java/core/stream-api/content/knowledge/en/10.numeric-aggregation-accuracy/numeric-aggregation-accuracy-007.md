# Verifying Numeric Result Correctness When Switching to Parallel

> **Chapter:** Numeric Aggregation Accuracy  
> **Module:** JAVA_STREAM_API  
> **Focus:** Verify that a numeric aggregation pipeline using the Java Stream API still meets business requirements when switching from `stream()` to `parallelStream()` or calling `parallel()`. Key factors include combiner associativity, identity values, integer overflow, floating-point rounding error, rounding boundaries, shared state, and `Collector` contracts.

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish **mathematically/business-correct**, **Java-type-valid**, and **stable across runs**.
2. Verify the three key conditions of a parallelizable aggregation: *identity*, *associativity*, and (when using three-argument `reduce`) *compatibility*.
3. Explain why `int`/`long` can overflow and why `double`/`float` addition can change results when combination order changes.
4. Choose `mapToLong`, `BigInteger`, `BigDecimal`, primitive aggregations, or collectors appropriate to precision requirements.
5. Write verification checks using an **independent oracle**, *invariants*, edge cases, and partitioned/reordered inputs.
6. Detect side effects and data races when converting a sequential loop or pipeline into a parallel Stream.
7. Decide whether to enable parallel execution or stay sequential based on **correctness** before benchmarking performance.

The examples use Java 17+ (consistent with `record` and `List.of`). The principles for `reduce`, `collect`, primitive types, and `parallelStream` have applied since Java 8. When using Stream Gatherers or custom collectors in advanced parts of the module, the correctness rule remains verifying state splitting/merging and final results.

## 1. Why Can Switching to Parallel Change Results?

In a sequential pipeline, elements are typically fed into the accumulator in source traversal order. With a parallel stream, work can be split into multiple chunks, each aggregated independently, and intermediate results **combined**. The merge tree can differ from sequential left-to-right evaluation.

~~~text
Ordered source: [a, b, c, d]

Sequential (typical evaluation):
    (((identity ⊕ a) ⊕ b) ⊕ c) ⊕ d

Parallel (one possible grouping):
    (a ⊕ b)       (c ⊕ d)
         \         /
          \       /
       (a ⊕ b) ⊕ (c ⊕ d)

⊕ = accumulation/combining operation provided by the program
~~~

If `⊕` is **associative** and has the right identity element, parenthesization does not change the result under the corresponding algebra. Otherwise, the same dataset can return different values.

Note: **Having an encounter order on a Stream does not mean addition will always be grouped in one fixed order when running in parallel.** Even when `toList()` preserves output element order (for an ordered source), that does not guarantee a floating-point `reduce` combines in the same order as a sequential pipeline.

Common causes of errors:

| Cause | Symptom | Risk severity |
|---|---|---|
| Non-associative accumulator | Subtraction, division, or mid-stream rounding yields different results when regrouped | Logic error |
| `float`/`double` binary rounding | Sum/average can drift in trailing digits, or diverge widely under cancellation | Numerical error |
| `int`/`long` overflow | Negative values, unexpectedly small values, or modulo wraparound | Domain violation |
| Mutating a container outside a lambda | Lost additions, overwritten data, concurrency bugs | Data race |
| Collector with a broken combiner | Missing, duplicated, or partition-dependent results | Contract violation |
| Treating sequential output as the sole oracle | Both modes can suffer the exact same bug | Insufficient testing |
| Comparing `double` with `==` | False failures within tolerance, or masking exactness requirements | Wrong test criterion |

A simple starting example:

~~~java
import java.util.List;

List<Integer> numbers = List.of(1, 2, 3, 4);

int sequential = numbers.stream()
        .mapToInt(Integer::intValue)
        .sum();

int parallel = numbers.parallelStream()
        .mapToInt(Integer::intValue)
        .sum();

System.out.println(sequential); // 10
System.out.println(parallel);   // 10
~~~

This case reveals no bug because the input is small and does not overflow. Correctness must be verified against the **real data domain**, real operations, and edge cases.

## 2. Three Layers of “Correct Result”

Before writing assertions, clarify what must hold:

1. **Business-correct:** monetary totals must be accurate to the dong/cent, averages must round by the agreed rule, and counts must never drop records.
2. **Operation- and type-correct:** `int`, `long`, `double`, and `BigDecimal` have different arithmetic contracts. Addition may be valid Java yet fail to represent the intended mathematical integer when it overflows.
3. **Execution-correct:** the pipeline must not read mutating state, suffer race conditions, or depend on lambda execution order.

Two computations can be **bit-for-bit identical yet business-wrong**. For example, both sequential and parallel runs can compute the same overflowed `int` sum. Conversely, two `double` computations can differ by a few bits yet both fall within the error bound of a statistical problem.

Verification design table:

| Result type | Standard comparison |
|---|---|
| Record counts, integer sums within safe range | **Exact** equality against an oracle |
| Integer sums risking `long` overflow | `BigInteger` oracle or suitably wide arithmetic |
| Currency, decimals requiring exactness | `BigDecimal` oracle built from clean decimal data; round per business rules |
| `double` sums/averages allowing tolerance | Absolute/relative error within defined threshold; check NaN/infinity separately |
| Grouped results | Compare key sets and per-key values; do not rely on `Map` iteration order |
| List outputs | Decide upfront whether order is required or only matching elements/multiset |

For financially sensitive problems, never “widen epsilon” to legitimize a flawed summation; choose the right numeric representation and rounding rules instead.

## 3. Reduction Contract: Identity and Associativity

### 3.1. Identity Value

For a combining function `f` and identity element `e`, we require:

~~~text
f(e, x) = x
f(x, e) = x
~~~

Examples:

- Addition: `e = 0`.
- Multiplication: `e = 1`.
- Maximum: choose an identity matching the data domain, or use the `reduce(BinaryOperator)` overload returning `Optional` if no universal valid identity exists.

**A wrong identity** can badly corrupt parallel results because the identity is seeded into independent sub-computations.

~~~java
import java.util.List;

List<Integer> values = List.of(1, 2, 3);

// Wrong: 10 is not the additive identity.
int bad = values.parallelStream()
        .reduce(10, Integer::sum);

// Correct modulo int (when overflow is not a concern):
int good = values.parallelStream()
        .reduce(0, Integer::sum);

System.out.println(good); // 6
~~~

The value `bad` **must never** be used to infer stability: parallel reduction can add 10 multiple times across different partitions. Even if one run happens to yield a desired number, the aggregation still violates its contract.

### 3.2. Associativity

The operation `f` must satisfy:

~~~text
f(f(a, b), c) = f(a, f(b, c))
~~~

In exact arithmetic, integer addition and multiplication are associative; subtraction and division are **not**.

~~~java
int left = (20 - 5) - 3;
int right = 20 - (5 - 3);

System.out.println(left);  // 12
System.out.println(right); // 18
~~~

Do not use subtraction as an accumulator/combiner in a `reduce` expected to be partition-independent:

~~~java
import java.util.List;

List<Integer> numbers = List.of(20, 5, 3);

// Unsuitable for parallel reduction requirements:
int result = numbers.parallelStream()
        .reduce(0, (a, b) -> a - b);
~~~

Even with fixed input data, the result depends on how intermediate chunks are grouped and merged, so business correctness is not guaranteed. If you want `20 - 5 - 3` sequentially in order, express that order dependency using a loop or an appropriate sequential algorithm.

### 3.3. int Addition Is Associative Modulo 2^32, Yet Still Business-Wrong

In Java, `int` addition overflows with 32-bit wraparound arithmetic. This addition is associative **modulo** \(2^{32}\), yet no longer represents mathematical integer addition when the true result exceeds the `int` range.

~~~java
import java.util.stream.IntStream;

int wrapped = IntStream.of(Integer.MAX_VALUE, 1)
        .parallel()
        .sum();

System.out.println(wrapped); // -2147483648
~~~

The bug here is **choosing a numeric range that is too small**, not evidence that `parallel()` caused rounding error. A sequential `int` sum would return the same wrapped value. Switch to `long` or `BigInteger` depending on the value domain.

## 4. Three-Argument reduce Contract and Compatibility

Signature:

~~~java
<U> U reduce(
        U identity,
        BiFunction<U, ? super T, U> accumulator,
        BinaryOperator<U> combiner
);
~~~

`accumulator` turns a state `U` and element `T` into a new state; `combiner` merges two `U` states. In parallel, the library may run the accumulator across multiple chunks and then use the combiner to merge partial results.

Alongside identity and associativity, **compatibility** is required:

~~~text
combiner(u, accumulator(identity, t)) == accumulator(u, t)
~~~

And `combiner(identity, u) == u`. Writing two operations with inconsistent semantics makes the result depend on partitioning.

Correct example when counting total characters:

~~~java
import java.util.List;

List<String> words = List.of("java", "stream", "api");

int sequential = words.stream()
        .reduce(
                0,
                (length, word) -> length + word.length(),
                Integer::sum
        );

int parallel = words.parallelStream()
        .reduce(
                0,
                (length, word) -> length + word.length(),
                Integer::sum
        );

System.out.println(sequential); // 13
System.out.println(parallel);   // 13
~~~

When total character count might exceed `Integer.MAX_VALUE`, use `long` or `BigInteger`.

Contract-violating example:

~~~java
// Wrong: accumulator adds lengths, while combiner subtracts.
// Do not use this result for business decisions.
int invalid = words.parallelStream()
        .reduce(
                0,
                (length, word) -> length + word.length(),
                (left, right) -> left - right
        );
~~~

Three-argument `reduce` also requires that accumulator/combiner **not mutate a shared mutable container directly**. When collecting into a collection or map, prefer `collect` with a contract-compliant collector.

## 5. Floating-Point Error: double Is Not Generally Associative

`double` follows finite binary floating-point arithmetic. Addition rounds at every step. Consequently:

~~~java
double a = 1.0e16;
double b = -1.0e16;
double c = 1.0;

double left = (a + b) + c;
double right = a + (b + c);

System.out.println(left);  // 1.0
System.out.println(right); // 0.0
~~~

When evaluating `b + c`, `1.0` is vastly smaller than the magnitude of `b`, so it can be lost to rounding. Meanwhile `(a + b) + c` cancels the two huge numbers first, preserving `1.0`.

Diagram:

~~~text
Left grouping:
  10^16 + (-10^16) = 0
  0 + 1 = 1

Right grouping:
  -10^16 + 1 ≈ -10^16  (small part lost to rounding)
  10^16 + (-10^16) = 0

Same 3 inputs, different grouping => different result
~~~

`reduce(0.0, Double::sum)` uses `double` addition, which does not satisfy real-number associativity in all cases. Switching to parallel can alter the merge tree and the result.

~~~java
import java.util.List;

List<Double> values = List.of(1.0e16, -1.0e16, 1.0);

double sequential = values.stream()
        .reduce(0.0, Double::sum);

double parallel = values.parallelStream()
        .reduce(0.0, Double::sum);

// Do not assert that parallel always returns one fixed value.
// Compare against error bounds and an appropriate oracle.
System.out.println("Sequential: " + sequential);
System.out.println("Parallel: " + parallel);
~~~

**Important:** `DoubleStream.sum()` may use *compensated summation* or another implementation strategy to improve accuracy. The API does not guarantee one fixed addition order; therefore, do not predict exact bits of `DoubleStream.sum()` from a manual grouping example or treat its output as the sole definition of “correct”.

### 5.1. Accumulation Error and Cancellation Error

Two common issues:

- **Accumulated rounding:** many small additions can build up noticeable relative error.
- **Cancellation (*cancellation*):** summing nearly equal positive and negative numbers strips significant digits when handling vastly different magnitudes.

For example, summing very large and very small numbers in the same sequence can be sensitive to partitioning and addition order. When the true result is near zero, using **relative error alone** is misleading because the reference denominator is near zero; combine it with an absolute tolerance.

### 5.2. Do Not Promise Bit-for-Bit Determinism for Parallel double

Even when one JDK and one dataset size frequently repeat the same output, **the general contract of double reduction does not guarantee one fixed merge tree across every environment**. Changing the source, `Spliterator`, JDK version, or runtime conditions can change grouping.

If the requirement is “every run must produce the exact same decimal string”, specify a concrete algorithm and rounding rule. For decimal data needing exactness, consider `BigDecimal`. For scientific real numbers, pick a numerically stable algorithm and an explicit error comparison standard; you may need to enforce a fixed processing order.

## 6. int/long Overflow During Aggregation: Choose Numeric Domain Before Parallelizing

### 6.1. Widen Types Before Summing

~~~java
import java.util.List;

List<Integer> amounts = List.of(
        1_500_000_000,
        1_500_000_000
);

int overflowed = amounts.stream()
        .mapToInt(Integer::intValue)
        .sum();

long exactInLong = amounts.parallelStream()
        .mapToLong(Integer::longValue)
        .sum();

System.out.println(overflowed);  // -1294967296
System.out.println(exactInLong); // 3000000000
~~~

Convert to `long` **before `int` addition overflows**. Casting an `int` sum after it has overflowed cannot recover the true value:

~~~java
int badIntSum = amounts.stream()
        .mapToInt(Integer::intValue)
        .sum();

long stillWrong = (long) badIntSum; // Too late
~~~

`long` is wider than `int` yet **not infinite**. `LongStream.sum()` can also overflow if the sum exceeds the `long` range.

### 6.2. Use BigInteger When Mathematical Integer Exactness Is Required

~~~java
import java.math.BigInteger;
import java.util.List;

List<Long> hugeValues = List.of(
        Long.MAX_VALUE,
        Long.MAX_VALUE,
        5L
);

BigInteger exact = hugeValues.parallelStream()
        .map(BigInteger::valueOf)
        .reduce(BigInteger.ZERO, BigInteger::add);

System.out.println(exact); // 18446744073709551619
~~~

`BigInteger` addition does not overflow at a fixed value limit like `long`. `BigInteger::add` is exact and associative for integer arithmetic; `BigInteger.ZERO` is a valid identity.

### 6.3. Math.addExact Detects Overflow, With Important Caveats

~~~java
import java.util.List;

List<Long> values = List.of(5L, 10L, 20L);

long sum = values.parallelStream()
        .reduce(0L, Math::addExact);

System.out.println(sum); // 35
~~~

`Math.addExact` throws `ArithmeticException` whenever **an intermediate addition** exceeds the `long` range. This is helpful when the specification is to **reject computations that overflow**.

However, if the data contains both huge positive and negative values, one grouping can produce an overflowing intermediate sum even though the final mathematical sum fits in `long`. Thus `Math.addExact` is not a test that “the final result fits in `long` regardless of grouping” when cancellation can occur. When exact computation is needed across **every grouping**, use `BigInteger` and check bounds at the **end**:

~~~java
import java.math.BigInteger;

BigInteger total = values.parallelStream()
        .map(BigInteger::valueOf)
        .reduce(BigInteger.ZERO, BigInteger::add);

long safeLong = total.longValueExact(); // Throws if the final result is outside long
~~~

For non-negative inputs only, checking overflow with `addExact` can be suitable because intermediate sums never exceed the final sum; with mixed positive and negative data, verify your assumptions before choosing the technique.

## 7. Money and Decimals: BigDecimal, Scale, and Rounding Timing

`double` does not accurately represent many common decimal fractions such as `0.1`. When business rules require exact monetary sums or decimal ratios, use `BigDecimal` (or store the smallest unit as `long` if overflow is guaranteed impossible and the unit is fixed).

### 7.1. Construct BigDecimal From Clean Decimal Data

~~~java
import java.math.BigDecimal;
import java.util.List;

List<BigDecimal> prices = List.of(
        new BigDecimal("0.10"),
        new BigDecimal("0.20"),
        new BigDecimal("0.30")
);

BigDecimal sequential = prices.stream()
        .reduce(BigDecimal.ZERO, BigDecimal::add);

BigDecimal parallel = prices.parallelStream()
        .reduce(BigDecimal.ZERO, BigDecimal::add);

System.out.println(sequential); // 0.60
System.out.println(parallel);   // 0.60
~~~

In this example, `add` without a `MathContext` is **exact** decimal addition, and the identity `BigDecimal.ZERO` is valid.

**Do not** construct money with `new BigDecimal(0.1)` if business rules intend the exact decimal string `"0.1"`. The `double` constructor captures the exact binary value of the `double`, which may differ from the intended decimal. Use `new BigDecimal("0.1")` or `BigDecimal.valueOf(0.1)` once the input source is understood.

### 7.2. Rounding at Every Step Breaks Associativity

~~~java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

MathContext mc = new MathContext(2, RoundingMode.HALF_UP);

BigDecimal a = new BigDecimal("9.9");
BigDecimal b = new BigDecimal("0.2");
BigDecimal c = new BigDecimal("-9.9");

BigDecimal left = a.add(b, mc).add(c, mc);
BigDecimal right = a.add(b.add(c, mc), mc);

System.out.println(left);  // 0.1
System.out.println(right); // 0.2
~~~

When `MathContext` rounds each addition result, combining is no longer associative under exact decimal math. Putting `add(other, mc)` into `parallelStream().reduce(...)` makes the outcome depend on how chunks are split and merged.

When business rules allow, **add exactly first, then round once at the end**:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal total = prices.parallelStream()
        .reduce(BigDecimal.ZERO, BigDecimal::add);

BigDecimal rounded = total.setScale(2, RoundingMode.HALF_UP);
~~~

However, some problems require **each transaction to be rounded before aggregation** (such as per-item tax/fee rules). In those cases, round **each data row per business rules** first, and then combine the rounded values using exact addition. Rounding rules are part of the data model, not an optional “optimization”.

### 7.3. Comparing BigDecimal Properly

~~~java
import java.math.BigDecimal;

BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

System.out.println(a.equals(b));        // false
System.out.println(a.compareTo(b) == 0); // true
~~~

`equals` compares both **value and scale**, whereas `compareTo` compares numeric value. If the goal is checking **the same monetary amount**, `compareTo(...) == 0` is usually appropriate. If a UI or storage format requires a fixed scale (such as always two decimal places), check or normalize scale under a dedicated contract.

## 8. Arithmetic Mean: Combine Sum and Count, Divide Only at the End

A common mistake is “compute the average of each partition and average the averages”. That only works when partitions have equal size (or when combined with proper weights).

Example:

~~~text
Group A: [10, 20]        average = 15
Group B: [100]           average = 100

Wrong: (15 + 100) / 2 = 57.5
Right: (10 + 20 + 100) / 3 = 43.333...
~~~

If you need an arithmetic mean from a parallel Stream with exact decimal precision, retain the **exact sum** and **count**, and divide only after merging:

~~~java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;
import java.util.List;

record SumCount(BigInteger sum, long count) {
    SumCount add(int value) {
        return new SumCount(sum.add(BigInteger.valueOf(value)),
                            Math.addExact(count, 1));
    }

    SumCount merge(SumCount other) {
        return new SumCount(sum.add(other.sum),
                            Math.addExact(count, other.count));
    }
}

List<Integer> samples = List.of(10, 20, 100);

SumCount stats = samples.parallelStream()
        .reduce(
                new SumCount(BigInteger.ZERO, 0L),
                SumCount::add,
                SumCount::merge
        );

if (stats.count() == 0) {
    System.out.println("No data available to compute average");
} else {
    BigDecimal mean = new BigDecimal(stats.sum())
            .divide(BigDecimal.valueOf(stats.count()),
                    4, RoundingMode.HALF_UP);

    System.out.println(mean); // 43.3333
}
~~~

Key properties:

- `SumCount` is an immutable `record`; accumulator and combiner return **new objects** rather than mutating a shared variable.
- `sum` uses `BigInteger`, keeping an exact integer value.
- `count` adds via `Math.addExact` to detect overflow if it ever happens.
- `merge` adds sums and counts, which is valid across any partitioning.
- `divide` and rounding happen **only after** all data has been merged.

If `double` precision is acceptable to the business, `IntStream.average()` or `DoubleStream.average()` is shorter; you still must check the result and handle empty Streams (the API returns `OptionalDouble`).

## 9. Custom Collectors: Verify supplier, accumulator, combiner, finisher

`collect` can also run in parallel by creating accumulation containers and merging them. The aggregation contract applies to the accumulated **state**, not just the final value.

A sound collector for exact integer totals can use a separate container per execution slice and then merge them:

~~~java
import java.math.BigInteger;
import java.util.List;
import java.util.stream.Collector;

record Row(long cents) {}

class Totals {
    static final class Acc {
        BigInteger sum = BigInteger.ZERO;

        void add(Row row) {
            sum = sum.add(BigInteger.valueOf(row.cents()));
        }

        Acc merge(Acc other) {
            sum = sum.add(other.sum);
            return this;
        }
    }

    static BigInteger total(List<Row> rows, boolean parallel) {
        var source = parallel ? rows.parallelStream() : rows.stream();

        return source.collect(Collector.of(
                Acc::new,
                Acc::add,
                Acc::merge,
                acc -> acc.sum
        ));
    }

    public static void main(String[] args) {
        List<Row> rows = List.of(new Row(100), new Row(250), new Row(-50));
        System.out.println(total(rows, false)); // 300
        System.out.println(total(rows, true));  // 300
    }
}
~~~

Here `Acc` has mutable state **inside the collector container**, yet `Collector.of` does not declare `CONCURRENT`, so the framework manages creating and merging containers across worker threads. Never keep one global `Acc` updated unsynchronized by all threads.

When writing a custom collector, verify:

1. **Supplier** creates a fresh, independent container in the proper initial state.
2. **Accumulator** updates one container accurately with an input element.
3. **Combiner** merges two containers so the result equals processing all elements together.
4. **Finisher** returns the result per contract; if rounding, ensure rounding happens **once at the end**.
5. If `CONCURRENT` is declared, the container and accumulator must genuinely satisfy thread-safety under concurrent access. Never attach this characteristic just to “go faster”.
6. If encounter order must be preserved, do not mark `UNORDERED` casually.

These checks also apply to `groupingBy`, custom collectors, and operations built on the Java Stream API's `Spliterator`.

## 10. Grouping and Summing: Per-Key Correctness

Switching to parallel affects not only a single global total; with `groupingBy` or `toMap`, every group must be verified.

~~~java
import java.math.BigInteger;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Entry(String category, long cents) {}

List<Entry> rows = List.of(
        new Entry("BOOK", 100),
        new Entry("PEN",  40),
        new Entry("BOOK", -20),
        new Entry("PEN",  60)
);

Map<String, BigInteger> totals = rows.parallelStream()
        .collect(Collectors.groupingBy(
                Entry::category,
                Collectors.mapping(
                        e -> BigInteger.valueOf(e.cents()),
                        Collectors.reducing(BigInteger.ZERO, BigInteger::add)
                )
        ));

System.out.println(totals.get("BOOK")); // 80
System.out.println(totals.get("PEN"));  // 100
~~~

`groupingBy` can collect and merge intermediate maps; output `Map` iteration order should not be relied upon. Verify the map by checking the **key set** and **each key's sum**, not by comparing `Map.toString()` output.

If switching to `groupingByConcurrent`, understand the collector's contract, ordering, and concurrency semantics. For decimal additions with intermediate rounding, simply changing `groupingBy` to its concurrent variant does not make the result accurate.

### 10.1. Duplicate Keys and Merge Functions

~~~java
import java.math.BigInteger;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, BigInteger> totals = rows.parallelStream()
        .collect(Collectors.toMap(
                Entry::category,
                e -> BigInteger.valueOf(e.cents()),
                BigInteger::add
        ));
~~~

`toMap` requires a merge function because multiple rows share a key. `BigInteger::add` is associative, making it suitable for combining exact monetary amounts. Conversely, a merge function like `(a, b) -> a - b` or per-step rounding can yield grouping-dependent results.

## 11. Never Mutate External Accumulators From a Parallel Pipeline

The following sequential code may happen to produce the expected output:

~~~java
import java.util.List;

List<Integer> values = List.of(1, 2, 3, 4);
int[] shared = {0};

values.stream().forEach(n -> shared[0] += n);

System.out.println(shared[0]); // 10 in this sequential example
~~~

Yet switching it directly to parallel is wrong:

~~~java
// Avoid:
values.parallelStream().forEach(n -> shared[0] += n);
~~~

`shared[0] += n` consists of a read, add, and write; multiple threads can overwrite one another's updates. `shared` being effectively final does **not** make the array's contents immutable or thread-safe.

Replace with:

~~~java
long total = values.parallelStream()
        .mapToLong(Integer::longValue)
        .sum();

System.out.println(total); // 10
~~~

Likewise, do not write into a shared `ArrayList`/`HashMap` from a parallel `forEach` without proper synchronization design.

### 11.1. Is AtomicInteger the Default Answer?

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.IntStream;

AtomicInteger total = new AtomicInteger();

IntStream.rangeClosed(1, 1000)
        .parallel()
        .forEach(total::addAndGet);

System.out.println(total.get()); // 500500
~~~

`AtomicInteger` ensures atomic updates within `int` range, yet every thread contends on one slot and addition can still overflow. It also makes the pipeline depend on side effects and harder to reason about with short-circuiting operations such as `findAny` or `limit`.

For ordinary aggregations, use `sum`, `reduce`, or a contract-compliant standard collector. If a concurrent external counter is genuinely needed (e.g., recording metrics), evaluate that design separately; metrics must not be confused with business numeric results.

## 12. Verifying With an Independent Oracle

**Never compare only `sequential == parallel` and conclude correctness.** Both can share the exact same bug: overflow, wrong filter rules, wrong currency unit, or rounding in the wrong place.

An oracle is a trusted reference computation that uses a **different execution path** from the pipeline under test. For cent-based monetary sums, a straightforward `BigInteger` loop is a solid oracle.

Complete example using `BigInteger` to verify results on orders with quantities and refund rows (negative cents):

~~~java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.util.List;

public class ParallelTotalVerification {
    record Sale(String id, long centsPerUnit, long quantity) {}

    static BigInteger expectedByLoop(List<Sale> sales) {
        BigInteger total = BigInteger.ZERO;
        for (Sale sale : sales) {
            BigInteger lineTotal =
                    BigInteger.valueOf(sale.centsPerUnit())
                            .multiply(BigInteger.valueOf(sale.quantity()));
            total = total.add(lineTotal);
        }
        return total;
    }

    static BigInteger totalByStream(List<Sale> sales, boolean parallel) {
        var source = parallel ? sales.parallelStream() : sales.stream();

        return source
                .map(sale -> BigInteger.valueOf(sale.centsPerUnit())
                        .multiply(BigInteger.valueOf(sale.quantity())))
                .reduce(BigInteger.ZERO, BigInteger::add);
    }

    static void verify(List<Sale> sales) {
        BigInteger oracle = expectedByLoop(sales);
        BigInteger sequential = totalByStream(sales, false);
        BigInteger parallel = totalByStream(sales, true);

        if (!oracle.equals(sequential)) {
            throw new AssertionError(
                    "Sequential != oracle: " + sequential + " / " + oracle);
        }

        if (!oracle.equals(parallel)) {
            throw new AssertionError(
                    "Parallel != oracle: " + parallel + " / " + oracle);
        }

        System.out.println("PASS: " + oracle + " cents");
    }

    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("S-01", 199, 2),  // +398 cents
                new Sale("S-02", 150, 3),  // +450 cents
                new Sale("R-03", -199, 1)  // -199 cents
        );

        verify(sales); // PASS: 649 cents

        BigInteger cents = totalByStream(sales, true);
        BigDecimal display = new BigDecimal(cents, 2);
        System.out.println(display); // 6.49
    }
}
~~~

In this example:

- Each line multiplies price by quantity using `BigInteger`, preventing `long` overflow right at multiplication.
- The oracle uses a **loop** to compute directly; the pipeline under test uses `map` + `reduce`.
- Both Stream modes are checked against the oracle, not merely against each other.
- Converting cents into a two-decimal-place currency amount happens **after** aggregation.
- If a real source has specific discount, tax, refund, and rounding rules, the oracle must model those exact rules.

This code illustrates a verification strategy; in the STEP 4 workflow, this is learning material and not a project test-run result.

## 13. Testing Invariants When Repartitioning Data

A properly associative aggregation should yield the same result when splitting data into parts and merging them, **assuming the same element multiset and business rules**.

With a `BigInteger` sum:

~~~java
import java.math.BigInteger;
import java.util.List;

List<Long> amounts = List.of(7L, -3L, 20L, 5L);

BigInteger allAtOnce = amounts.parallelStream()
        .map(BigInteger::valueOf)
        .reduce(BigInteger.ZERO, BigInteger::add);

BigInteger firstHalf = amounts.subList(0, 2).stream()
        .map(BigInteger::valueOf)
        .reduce(BigInteger.ZERO, BigInteger::add);

BigInteger secondHalf = amounts.subList(2, 4).stream()
        .map(BigInteger::valueOf)
        .reduce(BigInteger.ZERO, BigInteger::add);

BigInteger recombined = firstHalf.add(secondHalf);

System.out.println(allAtOnce); // 29
System.out.println(recombined); // 29
~~~

Other useful invariants:

- **Partitioning:** `aggregate(A ++ B) = combine(aggregate(A), aggregate(B))` if combining obeys the contract.
- **Identity element:** adding an element of value 0 does not change the sum, provided 0 truly is the identity.
- **Permutation:** for exact sums of integers or `BigDecimal` without intermediate rounding, reordering does not alter the mathematical result.
- **Filtering:** sum of kept elements + sum of excluded elements = sum of all elements, when sums are computed exactly and validly addable.
- **Grouping:** the sum across all groups equals the global total, provided every row belongs to one group without loss or duplication.

**Do not mechanically apply a “bit-for-bit permutation equality” invariant to `double`**, because binary floating-point addition is not associative. There, test against a defined tolerance/numerical property.

## 14. Test Case Matrix When Enabling parallel()

A few small cases cannot substitute for testing across realistic data ranges.

| Case | Purpose | What to verify |
|---|---|---|
| Empty Stream | Identity/default value | Sum 0 or empty result per contract |
| Single element | No loss or duplication | Result equals that element |
| All zeros | Neutral state | Result is 0 |
| All negative numbers | Sign correctness | Sum/average accurate |
| Canceling positive and negative | Intermediate arithmetic error | Final sum and overflow behavior correct |
| `Integer.MAX_VALUE` / `Long.MAX_VALUE` | Numeric type bounds check | No silent overflow |
| Huge and tiny values interleaved | Floating-point stability | Tolerance satisfied |
| `NaN`, ±Infinity, -0.0 | Special IEEE 754 values | Clear policy, no meaningless comparisons |
| Duplicate group keys | Collector and combiner | No dropped or duplicated rows |
| Uneven partition sizes | Averages and reductions | Never average averages |
| Large repeated datasets | Race conditions, contention | Invariant results and counts |
| Ordered/unordered sources | Encounter-order dependence | Numeric result meets requirements |
| Repeated values | Side-effect freedom | Sum reflects exact multiplicity |
| Fixed-seed shuffle | Grouping sensitivity | Result exact or within tolerance |

### 14.1. Running Once Is Not Enough

A data race sometimes fails to surface on small inputs or when the machine uses few threads. Parallel tests should be repeated across varied dataset sizes and distributions. **Even consistently repeated results do not prove contract compliance**: you still need an oracle and carefully crafted counterexamples.

### 14.2. Seeded Permutations to Reproduce Failures

~~~java
import java.math.BigInteger;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Random;

List<Long> original = List.of(
        Long.MAX_VALUE, -Long.MAX_VALUE, 5L, 7L, -3L
);

BigInteger expected = original.stream()
        .map(BigInteger::valueOf)
        .reduce(BigInteger.ZERO, BigInteger::add);

for (int trial = 0; trial < 30; trial++) {
    List<Long> shuffled = new ArrayList<>(original);
    Collections.shuffle(shuffled, new Random(20261118L + trial));

    BigInteger actual = shuffled.parallelStream()
            .map(BigInteger::valueOf)
            .reduce(BigInteger.ZERO, BigInteger::add);

    if (!expected.equals(actual)) {
        throw new AssertionError("Mismatch at trial " + trial);
    }
}
~~~

A fixed seed makes test cases reproducible. For floating-point results that may vary slightly with addition order, permutation tests should evaluate error tolerance rather than demanding exact equality unless business rules require it.

## 15. Comparing double Using Controlled Tolerance

For floating-point results, define **business-driven error thresholds**:

- **Absolute tolerance:** suited when true values are near 0 or measurements have a fixed maximum error.
- **Relative tolerance:** suited when magnitudes vary widely and error scales with magnitude.
- **ULP-based:** occasionally useful for checking binary representation differences, yet does not by itself state business-acceptable error.

A general comparison helper for **two finite values**, placed in a utility class:

~~~java
final class NumericComparison {
    static boolean closeEnough(
            double actual, double expected,
            double absoluteTolerance, double relativeTolerance) {

        if (!Double.isFinite(actual) || !Double.isFinite(expected)) {
            return false; // Special values must be checked under a dedicated policy
        }
        if (!Double.isFinite(absoluteTolerance)
                || !Double.isFinite(relativeTolerance)
                || absoluteTolerance < 0.0
                || relativeTolerance < 0.0) {
            throw new IllegalArgumentException("Invalid tolerance");
        }

        double scale = Math.max(Math.abs(actual), Math.abs(expected));
        double allowed = Math.max(
                absoluteTolerance,
                relativeTolerance * scale
        );

        return Math.abs(actual - expected) <= allowed;
    }
}
~~~

The helper uses the formula:

~~~text
|actual - expected| <= max(absTol, relTol * max(|actual|, |expected|))
~~~

Example:

~~~java
double expected = 100.0;
double actual = 100.0000003;

System.out.println(
        NumericComparison.closeEnough(actual, expected, 1e-6, 1e-9)
); // true
~~~

**This is a sample test criterion**, not an error bound guaranteed by Java. Values like `1e-6` or `1e-9` must come from measurement/business requirements. If huge data causes the difference calculation to overflow to infinity, or an algorithm has strict stability demands, design a more appropriate numerical comparison.

### 15.1. NaN, Infinity, and Signed Zero Need Separate Handling

~~~java
System.out.println(Double.NaN == Double.NaN); // false
System.out.println(Double.isNaN(Double.NaN));  // true

System.out.println(Double.POSITIVE_INFINITY == Double.POSITIVE_INFINITY);
// true

System.out.println(0.0 == -0.0); // true
System.out.println(Double.compare(0.0, -0.0) == 0); // false
~~~

Do not hardcode “two NaNs are equal” or “-0.0 and +0.0 are unequal” universally across all problems. Decide:

- Is `NaN` in the data permitted or rejected?
- May ±Infinity appear?
- Does the sign of 0 matter for downstream math or output formatting?

If special values are invalid, reject/block them during input validation and assert no non-finite values appear in the final result:

~~~java
import java.util.stream.DoubleStream;

double total = DoubleStream.of(1.25, 2.75).parallel().sum();

if (!Double.isFinite(total)) {
    throw new ArithmeticException("Non-finite result");
}
~~~

### 15.2. Decimal Oracles vs. Binary Floating-Point Oracles

If the raw inputs are **decimal strings** such as `"0.10"` and `"0.20"`, use `BigDecimal(String)` as the oracle for exact decimal addition. If the inputs are already an array of `double` from physical calculations, converting them to `BigDecimal.valueOf(double)` does not recover precision lost in earlier steps.

State explicitly whether the oracle represents **a real physical quantity, business decimal, or binary value stored in `double`**. No single comparison standard fits every application.

## 16. Controlled Workflow for Switching From Sequential to Parallel

A practical workflow consists of these steps:

1. **Define the arithmetic contract:** units, value range, allowed error, rounding mode, overflow policy, NaN handling, and empty results.
2. **Audit the source:** Is the Stream splittable? Is data mutating concurrently? Is the source tied to I/O or external resources?
3. **Audit the pipeline:** Are lambdas stateless and non-interfering? Do they write to shared variables or containers?
4. **Audit reduce/collect:** identity, associativity, compatibility, supplier/combiner, and correctness under repartitioning.
5. **Build an independent oracle:** use a simple loop with sufficiently wide/exact arithmetic, or a trusted hand-verified dataset.
6. **Cross-check both modes:** both sequential and parallel must pass the oracle or tolerance bounds; never use one mode as the sole oracle for the other.
7. **Test edge cases, shuffles, and varied sizes:** catch overflow, grouping/combiner bugs, floating-point drift, and race conditions.
8. **Benchmark after correctness is proven:** compare latency/throughput and allocation cost, factoring in `Spliterator`, system load, and data scale.

Decision flowchart:

~~~text
Need parallel aggregation?
        |
        v
Does the combiner have valid identity + associativity?
        |-- No --> Change combiner / keep ordered sequential
        |
        v
Does the numeric type have enough range and precision?
        |-- No --> Widen type / BigInteger / BigDecimal /
        |          change algorithm and rounding policy
        |
        v
Are lambdas and collectors partition-safe?
        |-- No --> Remove shared state, fix combiner
        |
        v
Have independent oracle + edge-case suite?
        |-- No --> Add verification checks
        |
        v
Do both sequential and parallel pass criteria?
        |-- No --> Investigate and fix before deployment
        |
        v
Benchmark with real data; keep parallel only if beneficial
~~~

In learning the Java Stream API, this ties together **reduce**, **collect**, grouping, custom collectors, `Spliterator`, and parallel streams: all require understanding **how data is split, transformed, and combined**.

## 17. Diagnosing Discrepancies in Parallel Results

When a discrepancy appears, do not jump to “parallel Streams are unreliable”. Separate possibilities systematically:

| Symptom | Possible cause | How to check |
|---|---|---|
| Large gap between sequential and parallel | Mismatched accumulator/combiner, side effects, race condition | Shrink dataset, inspect identity and every merge step |
| Both match yet sum is unexpectedly negative | `int`/`long` overflow | Compute a `BigInteger` oracle |
| Differ only in trailing `double` digits | Addition order and binary rounding | Compare against oracle and tolerance |
| Money off by a few cents across partitions | Rounding inside each `add`/`reduce` step | Sum exactly first, then round per policy |
| Average wrong when groups have unequal sizes | Unweighted average of averages | Combine `sum` and `count` |
| Missing data in grouped Map | Broken combiner or shared-state collector | Check every key and the global sum |
| Flaky test passing sometimes and failing others | Race condition or mutating state | Use immutable data; repeat across varied seeds/sizes |
| Bug appears only on file sources | Resource lifecycle, concurrent I/O, read exceptions | Check resource management and data path |
| Parallel is slower | Splitting/merging overhead exceeds useful work | Benchmark after correctness; check data size |

If results differ by only a few ULPs, do not dismiss the discrepancy without reading system requirements. For statistical scores, tiny error may be acceptable. For accounting or user entitlements, every currency unit may be mandatory.

## 18. Practice Exercises (With Answers)

### Exercise 1. Identify the Broken Condition

~~~java
import java.util.List;

List<Integer> nums = List.of(2, 3, 5);

int result = nums.parallelStream()
        .reduce(1, Integer::sum);
~~~

**Question:** Why can `1` not be used as the identity for addition?

**Answer:** The additive identity must be `0`. `1` gets added to every partition's partial sum and can make the result wrong depending on partitioning; replace with `reduce(0, Integer::sum)`.

### Exercise 2. Why Can Two double Calculations Differ?

~~~java
double a = 1.0e16;
double b = -1.0e16;
double c = 1.0;

System.out.println((a + b) + c);
System.out.println(a + (b + c));
~~~

**Answer:** Prints `1.0` and `0.0`. `double` addition rounds at every step, so associativity is not guaranteed. In `parallel().reduce`, element grouping can vary, and error must be checked against business goals.

### Exercise 3. Avoid Overflow Before Summing

**Prompt:** Sum `List.of(1_500_000_000, 1_500_000_000)` without `int` overflow.

**Reference answer:**

~~~java
import java.util.List;

List<Integer> values = List.of(1_500_000_000, 1_500_000_000);

long result = values.parallelStream()
        .mapToLong(Integer::longValue)
        .sum();

System.out.println(result); // 3000000000
~~~

If the sum can exceed `long`, `BigInteger` is required.

### Exercise 4. Analyze MathContext

**Prompt:** Why can `reduce(BigDecimal.ZERO, (a,b) -> a.add(b, mc))` produce different results across groupings?

**Answer:** `add(b, mc)` rounds at each step, so combining loses associativity. If business rules permit, aggregate with exact `BigDecimal::add` first and round once at the end. If each transaction must be rounded, convert input values into rounded transaction amounts first, then sum exactly.

### Exercise 5. Choose a Comparison Criterion

**Prompt:** A floating-point pipeline has oracle `0.0`, parallel result `2e-10`, and a defined absolute tolerance of `1e-9`. Does it pass?

**Answer:** It passes under the absolute tolerance because `2e-10 <= 1e-9`, assuming both values are finite and that threshold is business-approved. You could not conclude that if the problem requires **exact precision**.

### Exercise 6. Spot the Data Race

~~~java
import java.util.stream.IntStream;

int[] sum = {0};

IntStream.rangeClosed(1, 100_000)
        .parallel()
        .forEach(n -> sum[0] += n);
~~~

**Answer:** `sum[0] += n` is non-atomic and multiple threads write to a shared array. Additionally, the true sum is `5_000_050_000`, which overflows `int`. Fix with:

~~~java
long result = IntStream.rangeClosed(1, 100_000)
        .parallel()
        .asLongStream()
        .sum();

System.out.println(result); // 5000050000
~~~

### Exercise 7. Never Average Averages

**Prompt:** Two partitions contain `[10, 20]` and `[100]`. Compute the overall average.

**Answer:** Total is `130`, count is `3`, exact average is `130 / 3`. Do not compute `(15 + 100) / 2` because each average represents a different number of elements. In a parallel pipeline, combine sum and count first and divide at the end.

### Exercise 8. Which Oracle Suits Currency?

**Prompt:** Input values are strings `"0.10"`, `"0.20"`, `"0.30"` and an exact sum to two decimal places is required. Should `double` be used as the oracle?

**Answer:** No, if exact decimal addition is required. Use `BigDecimal(String)` for clean values and `BigDecimal::add` without intermediate rounding, then check the value with `compareTo` or normalize scale per contract.

### Exercise 9. Are Equal Results Enough?

**Prompt:** Sequential and parallel pipelines both return `-1294967296` for two `1_500_000_000` values. Can an equality test mark this as PASS?

**Answer:** No. Both suffered `int` overflow. A mathematical integer oracle shows the sum must be `3_000_000_000`. Widen types before summing or use `BigInteger`.

### Exercise 10. Choose Verification Checks for groupingBy

**Prompt:** Categorized data `BOOK: +100`, `PEN: +40`, `BOOK: -20`, `PEN: +60` is aggregated in parallel. What must be verified?

**Answer:** The resulting Map must have exactly two keys, `BOOK = 80` and `PEN = 100`; the sum across all groups must be `180`. Never compare printed key order when Map ordering is not guaranteed.

---

**Key takeaway:** Before moving a numeric aggregation to a parallel Stream, verify **identity, associativity, compatibility, numeric range, rounding rules, and shared state**. Sequential output equaling parallel output is **not enough** to prove correctness: validate both against an independent oracle, test overflow/cancellation/partitioning cases, and use justified tolerances for floating-point values. Evaluate speedups only after confirming the arithmetic contract and business requirements hold.

