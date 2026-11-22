# `sum` Can Overflow for Integers in Java

When summing a sequence of integers, every element being valid does not guarantee the sum fits within the data type's range. Java uses fixed-width integer types. If an `int` or `long` addition exceeds its limit, the result **wraps around**; Java does not automatically promote to a wider type, and ordinary addition throws no error. This applies to loops, `IntStream.sum()`, `LongStream.sum()`, `reduce`, and many collectors.

This lesson helps you recognize where overflow occurs, choose the right aggregation strategy, and define a clear API contract: allowing a wider sum, checking each addition, or returning an arbitrary-precision integer beyond 64 bits.

## 1. The Nature of Integer Overflow

| Type | Bits | Minimum | Maximum |
| --- | ---: | ---: | ---: |
| `byte` | 8 | -128 | 127 |
| `short` | 16 | -32.768 | 32.767 |
| `int` | 32 | -2.147.483.648 | 2.147.483.647 |
| `long` | 64 | -9.223.372.036.854.775.808 | 9.223.372.036.854.775.807 |

`int` represents signed integers in 32 bits; `long` uses 64 bits. When addition exceeds the range, the resulting bits are kept modulo \(2^{32}\) or \(2^{64}\). Therefore:

```java
int a = Integer.MAX_VALUE;
int b = 1;
int wrapped = a + b; // -2147483648
```

Here the mathematical sum is `2147483648`, larger than `Integer.MAX_VALUE`, and `wrapped` becomes `Integer.MIN_VALUE`. Similarly, `Long.MAX_VALUE + 1L` produces `Long.MIN_VALUE`.

Distinguish four quantities: **the bound of a single element**, **the mathematical sum**, **the type used for intermediate addition**, and **the return type**. A list with valid `int` values can have a sum exceeding `int` if there are enough elements. Conversely, in some cases the final sum fits in `int`, yet an intermediate sum in a given addition order exceeds `int`.

An especially common mistake:

```java
int x = Integer.MAX_VALUE;
int y = 1;

long wrong = x + y;          // -2147483648: added as int before assignment
long correct = (long) x + y; //  2147483648: added as long
```

The destination variable's type **does not** determine the type of the addition already performed. You must widen **before** adding, or use a wider-type accumulator from the beginning.

## 2. `IntStream.sum()` and `LongStream.sum()` Can Overflow

`IntStream.sum()` returns `int`. `LongStream.sum()` returns `long`. These APIs do not widen automatically or check for overflow:

```java
import java.util.Arrays;

int[] values = {Integer.MAX_VALUE, 1};

int wrong = Arrays.stream(values).sum();                // -2147483648
long right = Arrays.stream(values).asLongStream().sum(); // 2147483648
```

`asLongStream()` converts each `int` to `long` before adding. Thus the running addition happens in the `long` range, wide enough to represent the example's sum.

With a `long[]` source, even `LongStream` still has a limit:

```java
long[] values = {Long.MAX_VALUE, 1L};
long wrong = Arrays.stream(values).sum(); // Long.MIN_VALUE
```

The two snippets above reuse variable names because they are **two separate examples**; place them in separate scopes if trying them in the same program.

Aggregation APIs with notable behavior and return types:

| API/expression | Result type | Potential overflow point |
| --- | --- | --- |
| `int + int` | `int` | At the `+` operation itself |
| `long target = intA + intB` | `int` addition, then `long` assignment | Before assignment |
| `(long) intA + intB` | `long` | If exceeding `long` range |
| `IntStream.sum()` | `int` | 32-bit accumulator |
| `IntStream.asLongStream().sum()` | `long` | 64-bit accumulator |
| `LongStream.sum()` | `long` | 64-bit accumulator |
| `Collectors.summingInt(...)` | `Integer` | 32-bit sum |
| `Collectors.summingLong(...)` | `Long` | 64-bit sum |
| `IntSummaryStatistics.getSum()` | `long` | 64-bit sum |
| `LongSummaryStatistics.getSum()` | `long` | 64-bit sum |

`IntSummaryStatistics` is an easy point of confusion: although it consumes `int` elements, its sum field uses `long`. Still, APIs with a `long` sum are not unbounded exact sums either.

## 3. `reduce`, `Integer::sum`, and Loops Do Not Guard Against Overflow

Streams are a data-processing model, not an arithmetic safeguard. All of the following can produce the wrong sum when using `int`:

```java
int[] data = {Integer.MAX_VALUE, 1};

int loopSum = 0;
for (int value : data) {
    loopSum += value;
}

int reduced = Arrays.stream(data).reduce(0, Integer::sum);
int streamSum = Arrays.stream(data).sum();
```

`Integer.sum(int, int)` performs `int` addition; it **does not** behave like `Math.addExact`. `Collectors.summingInt` also accumulates in `int`:

```java
int result = Stream.of(Integer.MAX_VALUE, 1)
        .collect(Collectors.summingInt(Integer::intValue));
// result = -2147483648
```

The collector example requires `import java.util.stream.Stream;` and `import java.util.stream.Collectors;`.

If the source is a `List<Integer>`, widen each element before aggregating:

```java
List<Integer> numbers = List.of(Integer.MAX_VALUE, 1);
long result = numbers.stream().mapToLong(Integer::longValue).sum();
```

Remember that the snippet below **already overflows before assignment**:

```java
long wrong = numbers.stream().mapToInt(Integer::intValue).sum();
```

An `int[]` array has a maximum length representable by `int`, and each element lies in the `int` range. Therefore, the mathematical sum of all elements in **a single `int[]` array** always fits in `long`: the product of the maximum element count and an element's magnitude is still less than `Long.MAX_VALUE`. This is why `long` is the appropriate type for summing an entire `int[]`.

That **does not apply unconditionally to every `IntStream`**, because a stream can generate more elements than a single array's length limit. A system aggregating across many batches can also exceed `long` over time.

## 4. Solution A: Widen Before Adding and Return `long`

If you know ahead of time that the sum will fit within `long`, use a `long` accumulator:

```java
long total = 0L;
for (int value : values) {
    total += value;
}
```

In `total += value`, `value` is widened to `long` before the addition. For `int[]`, the equivalent is:

```java
long total = Arrays.stream(values).asLongStream().sum();
```

If an API **must return `int`** and only cares whether the final sum fits in `int`, sum safely in `long` and then use `Math.toIntExact`:

```java
long total = Arrays.stream(values).asLongStream().sum();
int result = Math.toIntExact(total);
```

`Math.toIntExact(long)` throws `ArithmeticException` when the value is outside the `int` range, instead of truncating bits like an `(int) total` cast.

However, if the `long` sum itself already overflowed in the preceding step, `Math.toIntExact` cannot recover the original mathematical result. You must ensure the accumulator is wide enough or use `BigInteger`.

### Note on Multiplication Before Addition

Many real-world sums are sums of `quantity * unitPrice`. If both operands are `int`, the multiplication can overflow before reaching `long`:

```java
int quantity = 100_000;
int unitPrice = 50_000;

long wrong = quantity * unitPrice;           // int already overflowed
long correct = (long) quantity * unitPrice;  // 5_000_000_000
```

In a collector or `mapToLong`, place the cast on the operand **before multiplication**. For multiplications that must fail immediately on primitive overflow, Java also provides `Math.multiplyExact`.

## 5. Solution B: Detect Overflow at Every Step with `Math.addExact`

`Math.addExact(int, int)` and `Math.addExact(long, long)` throw `ArithmeticException` if the sum exceeds the respective range.

```java
int checked = Math.addExact(Integer.MAX_VALUE, 1);
// ArithmeticException: integer overflow
```

It can be used in a loop:

```java
int sum = 0;
for (int value : values) {
    sum = Math.addExact(sum, value);
}
```

Or in `IntStream.reduce`:

```java
int sum = Arrays.stream(values).reduce(0, Math::addExact);
```

This is a contract of **checking every intermediate addition**, distinct from checking **only the final sum**. For example:

```text
[2147483647, 1, -1]
```

The final mathematical sum is `2147483647`, which is valid for `int`. Yet when adding left to right, the first two elements sum to `2147483648` and `Math.addExact` throws immediately, even though adding `-1` would bring the sum back within `int`.

Compare:

```java
int[] values = {Integer.MAX_VALUE, 1, -1};

int finalChecked = Math.toIntExact(
        Arrays.stream(values).asLongStream().sum());
// finalChecked = Integer.MAX_VALUE, succeeds.

int everyStepChecked = Arrays.stream(values).reduce(0, Math::addExact);
// ArithmeticException because intermediate sum exceeds int.
```

In a **parallel stream**, reduction can group elements in different intermediate orders. With `Math::addExact`, one grouping may encounter overflow while another does not, even though the final mathematical sum is the same. Therefore, if business logic only wants to check the final sum's range, use a sufficiently wide accumulator or `BigInteger` to compute the exact sum **before** checking the return type. If business logic must reject out-of-range intermediate additions in a deterministic order, specify that order clearly and use a sequential loop.

**Design rule:** Choose and clearly name the two modes `sumCheckingEveryAddition` (fail at any step) and `sumExactlyThenNarrow` (check the final sum). They do not share the same contract.

## 6. Solution C: Use `BigInteger` When `long` Is Still Not Enough

If the sum can exceed 64 bits, use `java.math.BigInteger` to add integers exactly:

```java
import java.math.BigInteger;
import java.util.Arrays;

long[] data = {Long.MAX_VALUE, 1L};

BigInteger total = Arrays.stream(data)
        .mapToObj(BigInteger::valueOf)
        .reduce(BigInteger.ZERO, BigInteger::add);

// total = 9223372036854775808
```

`BigInteger` stores integers with variable bit length; `BigInteger.add` does not wrap around at 32/64-bit limits. `BigInteger.valueOf(long)` preserves the input `long` value. With an `int[]` source, you can use the same approach on `IntStream.mapToObj(BigInteger::valueOf)`; Java widens `int` to `long` to match the `valueOf` signature.

When narrowing the result back to a primitive type, distinguish:

```java
long unsafe = total.longValue();       // May truncate bits.
long checked = total.longValueExact(); // Throws ArithmeticException if outside long range.
```

Similarly, there is `intValueExact()`. `BigInteger` allocates objects and processes more bits than primitive types; use it only when the data range demands it. It does not guarantee unbounded-cost computation: the program still has resource limits.

### Why Not Substitute `double`?

`double` has a wide magnitude range but preserves only 53 significand bits accurately for integers. Beyond that threshold, not every integer is represented exactly; the sum can be rounded. Hence, `double` is not an option for keeping an exact integer sum when the total can exceed `long`.

If the data consists of decimal numbers with fractional parts requiring decimal precision, consider `BigDecimal`; that is a different problem from integer summation and also needs an appropriate scale/rounding policy.

## 7. Scenarios with `summaryStatistics` and Collectors

Sometimes you need not only the sum, but also the element count, min, and max:

```java
import java.util.IntSummaryStatistics;

IntSummaryStatistics stats = Arrays.stream(values).summaryStatistics();
long count = stats.getCount();
long sum = stats.getSum();
int min = stats.getMin();
int max = stats.getMax();
```

`getSum()` returns `long`, which is usually convenient and sufficient for an `int[]`. For an empty stream, `count` is 0 and `sum` is 0; `min` is `Integer.MAX_VALUE`, `max` is `Integer.MIN_VALUE`. Check `count > 0` before interpreting min/max as actual observations.

For a `Stream<Order>` where `Order::quantity` returns `int`, there are two options:

```java
int risky = orders.stream()
        .collect(Collectors.summingInt(Order::quantity));

long wider = orders.stream()
        .collect(Collectors.summingLong(Order::quantity));
```

This example uses a hypothetical `Order` class; it is an **illustrative snippet**, not a standalone program. `summingLong` widens quantities to `long` before adding, though it can still overflow if the sum exceeds `long`.

If you need the total value `quantity * unitPrice`, remember to widen **before multiplying**:

```java
long total = orders.stream()
        .mapToLong(order -> (long) order.quantity() * order.unitPrice())
        .sum();
```

If you do not widen inside the mapper, `int * int` can overflow before becoming `long`. If the sum of multiple products can still exceed `long`, switch to `BigInteger` and compute each product with `BigInteger.multiply`.

## 8. Complete Java 17+ Program

Save the following in **`IntegerSumOverflowDemo.java`**:

```java
import java.math.BigInteger;
import java.util.Arrays;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class IntegerSumOverflowDemo {
    public static void main(String[] args) {
        int[] values = {Integer.MAX_VALUE, 1};

        System.out.println("int sum = " + Arrays.stream(values).sum());
        System.out.println("long sum = "
                + Arrays.stream(values).asLongStream().sum());
        System.out.println("summary sum = "
                + Arrays.stream(values).summaryStatistics().getSum());
        System.out.println("collector sum = "
                + Stream.of(Integer.MAX_VALUE, 1)
                        .collect(Collectors.summingInt(Integer::intValue)));

        try {
            int checked = Arrays.stream(values).reduce(0, Math::addExact);
            System.out.println("checked sum = " + checked);
        } catch (ArithmeticException ex) {
            System.out.println("checked sum = overflow");
        }

        long widened = Arrays.stream(values).asLongStream().sum();
        try {
            System.out.println("toIntExact = " + Math.toIntExact(widened));
        } catch (ArithmeticException ex) {
            System.out.println("toIntExact = overflow");
        }

        int[] mixed = {Integer.MAX_VALUE, 1, -1};
        System.out.println("mixed long final = "
                + Math.toIntExact(Arrays.stream(mixed).asLongStream().sum()));
        try {
            Arrays.stream(mixed).reduce(0, Math::addExact);
            System.out.println("mixed checked = valid");
        } catch (ArithmeticException ex) {
            System.out.println("mixed checked = prefix overflow");
        }

        long[] large = {Long.MAX_VALUE, 1L};
        System.out.println("long overflow = " + Arrays.stream(large).sum());
        BigInteger exact = Arrays.stream(large)
                .mapToObj(BigInteger::valueOf)
                .reduce(BigInteger.ZERO, BigInteger::add);
        System.out.println("big sum = " + exact);
    }
}
```

Compile and run in the directory containing the file:

```bash
javac -encoding UTF-8 IntegerSumOverflowDemo.java
java IntegerSumOverflowDemo
```

Exact stdout (verified expressions on Java 21; the code uses APIs available since Java 17):

```text
int sum = -2147483648
long sum = 2147483648
summary sum = 2147483648
collector sum = -2147483648
checked sum = overflow
toIntExact = overflow
mixed long final = 2147483647
mixed checked = prefix overflow
long overflow = -9223372036854775808
big sum = 9223372036854775808
```

Notice what happens: `IntStream.sum()` and `summingInt` both wrap around; `asLongStream().sum()` and `IntSummaryStatistics.getSum()` preserve the first sum accurately; `Math.addExact` and `Math.toIntExact` check **different conditions**; `LongStream.sum()` can overflow while `BigInteger` preserves the exact sum.

## 9. Defining the Contract of an Aggregation API

A function named `sum()` easily leads callers to assume the result always equals the mathematical sum. If there is any risk of exceeding bounds, the API must state its return type and overflow policy clearly.

| Need | Implementation | Overflow behavior |
| --- | --- | --- |
| Full sum of an `int[]` | `Arrays.stream(values).asLongStream().sum()` | Returns `long`, safe for `int[]` |
| API must return `int`, only final result matters | Sum in `long`, then `Math.toIntExact` | Throws when final sum exceeds `int` |
| Immediately reject any overflowing `int` addition | Loop with `Math.addExact` | Throws at the intermediate addition |
| Sum of `long` values that may exceed 64 bits | `BigInteger` | Returns exact integer sum |
| Need count/min/max/sum on `int[]` | `IntSummaryStatistics` | Sum uses `long`; check source conditions |
| Sum of quantities from objects | `mapToLong` or `Collectors.summingLong` | Computes in `long` |
| `BigInteger` needs conversion to `long` | `longValueExact()` | Throws when sum exceeds `long` |

Method names and signatures should reflect the policy, for example:

```java
long sumIntsAsLong(int[] values);
int sumIntsAndCheckFinalRange(int[] values);
int sumIntsAndCheckEachAddition(int[] values);
BigInteger sumLongsExactly(long[] values);
```

The lines above are **illustrative signatures**; they need method bodies and an enclosing class to compile. API documentation should also specify whether `null` input is valid, whether an empty array returns 0, whether processing order matters, and whether returning a sum wider than the source element type is allowed.

In financial logic storing cents as `long`, do not assume `long` is always enough: consider transaction count limits, per-transaction quantities, and accumulation time horizon. When the upper bound is hard to prove, consider `BigInteger`.

## 10. Common Mistakes and How to Test

### Mistakes to Avoid

1. Believing `IntStream.sum()` automatically widens to `long` or throws an exception on overflow.
2. Assigning an `int + int` expression to `long` and assuming the addition used `long`.
3. Using `Integer::sum` instead of `Math.addExact`, thinking both APIs behave the same way.
4. Using `Collectors.summingInt` when the sum can exceed `int` limits.
5. Thinking checking every addition with `Math.addExact` is always equivalent to checking the final sum.
6. Calling `Math.toIntExact` after a `long` addition that already overflowed; the mathematical result is already lost.
7. Using `BigInteger.longValue()` when value preservation is required instead of `longValueExact()`.
8. Using `double` to "avoid integer overflow" when exact integer precision is needed.
9. Forgetting that `int * int` multiplication can overflow before aggregation.
10. Assuming parallel reduction has no effect on when per-addition overflow is detected.

### Minimum Test Cases

| Input | Mathematical sum | What to verify |
| --- | --- | --- |
| `[]` | 0 | Empty-array contract |
| `[1, 2, 3]` | 6 | Normal case |
| `[Integer.MAX_VALUE, 1]` | 2.147.483.648 | Positive `int` overflow |
| `[Integer.MIN_VALUE, -1]` | -2.147.483.649 | Negative `int` overflow |
| `[Integer.MAX_VALUE, 1, -1]` | 2.147.483.647 | Intermediate overflow despite valid final sum |
| `[Long.MAX_VALUE, 1L]` | 9.223.372.036.854.775.808 | `long` overflow, requires `BigInteger` |
| `[100_000 * 50_000]` with `int` operands | 5.000.000.000 | Requires widening before multiplication |

For code with `parallel()` and per-addition checking, test inputs containing large positive and negative numbers to understand how results depend on grouping order. For APIs checking only the final sum, use a sufficiently wide accumulator and check once.

**Principle:** Determine the maximum element magnitude, maximum element count, and sum bounds. Widen **before computing**; use `long` if provably wide enough, `BigInteger` if a range beyond 64 bits is needed. If an error must be thrown on return-type overflow, specify clearly whether it applies to **each addition step** or the **final sum**.

### Official Java Documentation

- [`IntStream.sum()` and `IntStream.summaryStatistics()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/IntStream.html)
- [`LongStream.sum()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/LongStream.html)
- [`Math.addExact()` and `Math.toIntExact()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html)
- [`Collectors.summingInt()` and `Collectors.summingLong()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Collectors.html)
- [`BigInteger`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigInteger.html)