# Integer Overflow When Summing and How to Choose Types

When using the Java Stream API to sum quantities, revenue, or scores, the `sum()` syntax is concise but **does not automatically guarantee an exact sum**. Addition on `int` and `long` has a finite value range. If a sum exceeds the allowed range, Java can produce a negative number or an incorrect positive number without throwing an exception.

This lesson belongs to the **Numeric Aggregation Accuracy** chapter of the **JAVA_STREAM_API** module. The goal is to understand when `IntStream.sum()`, `LongStream.sum()`, `reduce()`, and collectors can overflow; learn to **widen types before computing**, use `Math.addExact` when you want overflow detection, choose `BigInteger` when an integer sum must not be bounded by `long`, and evaluate these choices against real data. These principles also apply to `filter`, `map`, `groupingBy`, custom collectors, and parallel pipelines.

## 1. What Is Integer Overflow?

Java uses fixed-width primitive integers:

| Type | Bits | Minimum value | Maximum value |
| --- | ---: | ---: | ---: |
| `byte` | 8 | -128 | 127 |
| `short` | 16 | -32,768 | 32,767 |
| `int` | 32 | -2,147,483,648 | 2,147,483,647 |
| `long` | 64 | -9,223,372,036,854,775,808 | 9,223,372,036,854,775,807 |

`IntStream` computes its sum as `int`, while `LongStream` computes its sum as `long`. If addition exceeds the limit, Java keeps the low bits under two's-complement integer semantics; the result wraps around (*wraparound*). Ordinary primitive addition **does not automatically throw `ArithmeticException` on overflow**.

Example:

```java
int intMax = Integer.MAX_VALUE;
long longMax = Long.MAX_VALUE;

System.out.println(intMax + 1);  // -2147483648
System.out.println(longMax + 1); // -9223372036854775808
```

Mathematically, both sums must be greater than the maximum value. The Java results differ because the storage type cannot hold the value to be represented.

### 1.1. Overflow Occurs Even When the Pipeline Looks Valid

```java
import java.util.stream.IntStream;
import java.util.stream.LongStream;

public class OverflowBasics {
    public static void main(String[] args) {
        int wrong = IntStream.of(Integer.MAX_VALUE, 1)
            .sum();

        long correctWithinLong = IntStream.of(Integer.MAX_VALUE, 1)
            .asLongStream()
            .sum();

        long wrongAgain = LongStream.of(Long.MAX_VALUE, 1L)
            .sum();

        System.out.println(wrong);             // -2147483648
        System.out.println(correctWithinLong); // 2147483648
        System.out.println(wrongAgain);        // -9223372036854775808
    }
}
```

`asLongStream()` widens each `int` to `long` **before adding**, so the sum `2,147,483,648` is preserved accurately. Even so, `long` also has a limit and does not solve every case.

## 2. Distinguish the Input Data Type from the Sum Operation Type

A common mistake is looking only at **the type of the variable receiving the result**:

```java
import java.util.stream.IntStream;

long total = IntStream.of(1_500_000_000, 1_500_000_000)
    .sum();

System.out.println(total); // -1294967296 (wrong compared to the mathematical sum)
```

`IntStream.sum()` returns `int`. The `int` addition has already overflowed **before** the result is assigned to the `long` variable. Declaring `long total` only widens the **already-wrong value** after overflow; it does not fix the earlier calculation.

To get the correct sum, you must convert the type **before summing**:

```java
long total = IntStream.of(1_500_000_000, 1_500_000_000)
    .asLongStream()
    .sum();

System.out.println(total); // 3000000000
```

An equivalent approach is mapping to `long`:

```java
long total = IntStream.of(1_500_000_000, 1_500_000_000)
    .mapToLong(value -> value)
    .sum();
```

### 2.1. `Stream<Integer>` Also Needs the Right Addition Operation

A `List<Integer>` produces a `Stream<Integer>`. If you use `reduce` with an `Integer` target type, the sum still runs in `int`:

```java
import java.util.List;

List<Integer> values = List.of(1_500_000_000, 1_500_000_000);

int wrong = values.stream()
    .reduce(0, Integer::sum);

long correct = values.stream()
    .mapToLong(Integer::longValue)
    .sum();

System.out.println(wrong);   // -1294967296
System.out.println(correct); // 3000000000
```

`mapToLong(Integer::longValue)` converts each `Integer` to `long` and then performs the sum on a `LongStream`. This is convenient when the source data uses wrapper types while the sum requires a larger range.

If `List<Integer>` can contain `null`, `Integer::longValue` will throw `NullPointerException`. Define a policy for missing values before unboxing, such as `filter(Objects::nonNull)` if the business logic allows skipping missing elements.

### 2.2. Type Widening Must Happen Before Multiplication Too

Suppose each invoice line has `int quantity` and `int unitPrice`. Writing `mapToLong(x -> x.quantity() * x.unitPrice())` **can still be wrong**, because both operands are `int`, so the multiplication executes in `int`, and only afterward is the result converted to `long`.

```java
record Item(int quantity, int unitPriceVnd) {}

Item item = new Item(50_000, 50_000);

long wrong = item.quantity() * item.unitPriceVnd();

long correct = (long) item.quantity() * item.unitPriceVnd();

System.out.println(wrong);   // -1794967296
System.out.println(correct); // 2500000000
```

Correct in a pipeline:

```java
import java.util.List;

List<Item> items = List.of(new Item(50_000, 50_000));

long revenue = items.stream()
    .mapToLong(item -> (long) item.quantity() * item.unitPriceVnd())
    .sum();

System.out.println(revenue); // 2500000000
```

**Rule:** Check the type at **every intermediate operation**, not just at `sum()` or the receiving variable.

## 3. Choose Types According to the Problem's Value Domain

Type selection should start from the maximum number of elements, the range of each value, and the intermediate calculations.

Suppose there are at most `N` integer values, each with absolute magnitude at most `M`. Then the magnitude of the sum does not exceed `N × M`. You can use this bound to evaluate numeric types, provided **computing the bound itself** does not overflow.

For example: a system has at most one million records, and each record has a product quantity of at most one million. The largest sum is `10^12`; that exceeds the `int` limit but fits within `long`. Therefore `mapToLong` or `LongStream` is more appropriate than `IntStream.sum()`.

For sums containing both negative and positive values, pay attention to both the lower and upper bounds of the type. Even when the **final sum** fits within the range, intermediate sums can still exceed the bounds if data is added in an unfavorable order.

| Need | Suitable type/strategy | Key point to remember |
| --- | --- | --- |
| Values and all intermediate sums are guaranteed to fit in 32 bits | `int` / `IntStream.sum()` | Readable and concise, but has no default overflow check. |
| Values are `int`, sum needs 64-bit range | `IntStream.asLongStream().sum()` or `Stream<T>.mapToLong(...).sum()` | Widen **before adding**. |
| Data is already `long` and guaranteed not to exceed 64 bits | `LongStream.sum()` | `long` addition can still overflow if assumptions fail. |
| Must fail if addition exceeds the chosen type | `Math.addExact` with `reduce` or a loop | Exception occurs at the intermediate addition that overflows. |
| Sum may exceed `Long.MAX_VALUE` or needs an unbounded exact integer result | `BigInteger` | Exact integer arithmetic, at the cost of object/memory overhead. |
| Money with fractional parts or calculations requiring decimal rounding rules | `BigDecimal` | Choose `scale` and rounding mode according to business rules. |

Do not use `double` just to avoid the limits of `long`: `double` does not guarantee exact representation of every large integer. Consecutive integers are only guaranteed to be exact up to `2^53`; beyond that level, distinct values share the same `double` representation.

## 4. Detecting Overflow With `Math.addExact`

`Math.addExact(int, int)` and `Math.addExact(long, long)` perform addition and **throw `ArithmeticException` if the result exceeds the range of the corresponding type**.

```java
int safe = Math.addExact(1_000_000, 2_000_000);
System.out.println(safe); // 3000000

try {
    int overflow = Math.addExact(Integer.MAX_VALUE, 1);
    System.out.println(overflow);
} catch (ArithmeticException exception) {
    System.out.println("Sum exceeds int range");
}
```

In a Stream, you can pass `Math::addExact` to `reduce`:

```java
import java.util.stream.IntStream;

int exactSum = IntStream.of(100, 200, 300)
    .reduce(0, Math::addExact);

System.out.println(exactSum); // 600
```

If an intermediate sum overflows, `reduce` will throw the exception:

```java
try {
    int total = IntStream.of(Integer.MAX_VALUE, 1)
        .reduce(0, Math::addExact);

    System.out.println(total);
} catch (ArithmeticException exception) {
    System.out.println("Overflow detected during reduce");
}
```

Similarly with `LongStream`:

```java
import java.util.stream.LongStream;

long total = LongStream.of(1_000_000_000L, 2_000_000_000L)
    .reduce(0L, Math::addExact);

System.out.println(total); // 3000000000
```

### 4.1. `Math.addExact` Does Not “Widen” the Range

`Math.addExact` **detects errors**; it does not automatically promote the sum to a larger type. If a sum is mathematically valid yet exceeds `int`, you must choose `long` or `BigInteger` depending on requirements.

For instance, `Integer.MAX_VALUE + 1` is exact in `long`, so if business rules allow that sum, `asLongStream().sum()` makes more sense than attempting `int` addition and catching an exception.

### 4.2. A Final Sum That Fits Can Still Overflow Intermediately

Consider the sequence:

```text
[2_147_483_647, 1, -1]
Final mathematical sum = 2_147_483_647
```

When adding left to right with `Math.addExact`, the step `2_147_483_647 + 1` throws an exception **before** `-1` is added, even though the final sum is representable as an `int`.

```java
import java.util.stream.IntStream;

try {
    int total = IntStream.of(Integer.MAX_VALUE, 1, -1)
        .reduce(0, Math::addExact);
    System.out.println(total);
} catch (ArithmeticException exception) {
    System.out.println("An intermediate sum exceeded the int range");
}
```

When using `parallel()`, chunks of elements may be summed and combined in different orders; with `Math.addExact`, whether an intermediate overflow is triggered can depend on the grouping. Therefore, if the requirement is **an exact mathematical integer final result checked afterward to see if it fits in `int`**, accumulate with a sufficiently wide type or `BigInteger`, then convert back to the target type using a checked conversion.

## 5. Summing Beyond 64 Bits With `BigInteger`

`BigInteger` in `java.math` represents arbitrary-precision integers, bounded mainly by memory and execution resources. It is not a primitive type, and **there is no built-in `BigIntegerStream`** in the Java Stream API.

You can start from a `LongStream`, convert each `long` into a `BigInteger`, and reduce by addition:

```java
import java.math.BigInteger;
import java.util.stream.LongStream;

public class BigIntegerSumDemo {
    public static void main(String[] args) {
        BigInteger total = LongStream.of(Long.MAX_VALUE, 1L)
            .mapToObj(BigInteger::valueOf)
            .reduce(BigInteger.ZERO, BigInteger::add);

        System.out.println(total); // 9223372036854775808
    }
}
```

`mapToObj(BigInteger::valueOf)` creates a `Stream<BigInteger>` from `long` values. `reduce(BigInteger.ZERO, BigInteger::add)` uses `ZERO` as the identity element and `add` for aggregation. Addition on `BigInteger` does not overflow like `long`; larger datasets increase computation and memory cost.

A similar example with a domain object:

```java
record Entry(long amountVnd) {}

BigInteger total = java.util.List.of(
        new Entry(Long.MAX_VALUE),
        new Entry(1L)
    ).stream()
    .map(entry -> BigInteger.valueOf(entry.amountVnd()))
    .reduce(BigInteger.ZERO, BigInteger::add);

System.out.println(total); // 9223372036854775808
```

If input values **already exceed `long`**, you cannot store them in a `long` first and convert to `BigInteger` afterward. You must read and store them properly from the start, for example:

```java
BigInteger huge = new BigInteger("123456789012345678901234567890");
BigInteger answer = huge.add(BigInteger.ONE);

System.out.println(answer);
// 123456789012345678901234567891
```

### 5.1. Converting the Result Back to a Smaller Type After Checking

`BigInteger` provides `intValueExact()` and `longValueExact()`. They throw `ArithmeticException` if the value cannot be represented exactly in the target type.

```java
BigInteger sum = BigInteger.valueOf(Integer.MAX_VALUE)
    .add(BigInteger.ONE);

long asLong = sum.longValueExact();
System.out.println(asLong); // 2147483648

try {
    int asInt = sum.intValueExact();
    System.out.println(asInt);
} catch (ArithmeticException exception) {
    System.out.println("Exact sum exceeds int range");
}
```

This approach is useful when inputs have offsetting positive and negative signs so the final sum stays within bounds, while ensuring no information is lost from intermediate overflow.

## 6. Overflow in `reduce`, `collect`, and Statistics

The method name `sum` is not the only sign of risk. Any aggregation that adds using a finite type needs to be examined.

### 6.1. `reduce` Does Not Automatically Check Overflow

```java
import java.util.List;

List<Integer> values = List.of(Integer.MAX_VALUE, 1);

int totalWithReduce = values.stream()
    .reduce(0, Integer::sum);

System.out.println(totalWithReduce); // -2147483648
```

`Integer::sum` adds as `int` and has the same limit as the `+` operator. The identity `0` does not make addition any more accurate.

### 6.2. `Collectors.summingInt` and `summingLong`

`Collectors.summingInt` returns `Integer`; `Collectors.summingLong` returns `Long`. They can also overflow if the sum exceeds their respective ranges.

```java
import java.util.List;
import java.util.stream.Collectors;

record Expense(String category, int amountVnd) {}

List<Expense> expenses = List.of(
    new Expense("Equipment", 1_500_000_000),
    new Expense("Equipment", 1_500_000_000)
);

int wrong = expenses.stream()
    .collect(Collectors.summingInt(Expense::amountVnd));

long correctWithinLong = expenses.stream()
    .collect(Collectors.summingLong(expense -> (long) expense.amountVnd()));

System.out.println(wrong);             // -1294967296
System.out.println(correctWithinLong); // 3000000000
```

In the `summingLong` expression, the mapper returns `long`, so values are widened before aggregation.

### 6.3. Distinguishing `IntStream.sum()` from `IntSummaryStatistics.getSum()`

An easily overlooked detail: `IntStream.sum()` returns `int`, whereas `IntSummaryStatistics.getSum()` returns `long`.

```java
import java.util.IntSummaryStatistics;
import java.util.stream.IntStream;

int overflowed = IntStream.of(1_500_000_000, 1_500_000_000)
    .sum();

IntSummaryStatistics statistics =
    IntStream.of(1_500_000_000, 1_500_000_000)
        .summaryStatistics();

long widened = statistics.getSum();

System.out.println(overflowed); // -1294967296
System.out.println(widened);     // 3000000000
```

`IntSummaryStatistics` adds `int` values into a `long` accumulator; this solves the example above, but **does not mean a `long` sum is always safe**. `LongSummaryStatistics.getSum()` also returns `long` and can overflow beyond 64 bits.

Similarly, `Collectors.summarizingInt(...)` returns `IntSummaryStatistics`, so `getSum()` is `long`; do not confuse it with `Collectors.summingInt(...)` which returns `Integer`.

### 6.4. Grouping With `groupingBy` Still Requires Choosing the Sum Type

Suppose you want to report totals by region. If a group total may exceed `int` while fitting within `long`, use:

```java
import java.util.Map;
import java.util.stream.Collectors;

record Sale(String region, int amountVnd) {}

List<Sale> sales = List.of(
    new Sale("North", 1_500_000_000),
    new Sale("North", 1_500_000_000),
    new Sale("South", 100_000_000)
);

Map<String, Long> totals = sales.stream()
    .collect(Collectors.groupingBy(
        Sale::region,
        Collectors.summingLong(sale -> (long) sale.amountVnd())
    ));

System.out.println(totals.get("North")); // 3000000000
System.out.println(totals.get("South")); // 100000000
```

If a group total may exceed `long`, use `BigInteger` inside an appropriate collector:

```java
import java.math.BigInteger;
import java.util.Map;
import java.util.stream.Collectors;

record LargeSale(String region, long amountVnd) {}

List<LargeSale> largeSales = List.of(
    new LargeSale("North", Long.MAX_VALUE),
    new LargeSale("North", 1L)
);

Map<String, BigInteger> exactTotals = largeSales.stream()
    .collect(Collectors.groupingBy(
        LargeSale::region,
        Collectors.reducing(
            BigInteger.ZERO,
            sale -> BigInteger.valueOf(sale.amountVnd()),
            BigInteger::add
        )
    ));

System.out.println(exactTotals.get("North"));
// 9223372036854775808
```

`Collectors.reducing` lets you explicitly choose **both the accumulator type and the combining function**. A custom collector may fit more complex aggregations, but is unnecessary when `reducing` satisfies the requirement.

## 7. Overflow in Multiplication Before Aggregation

Real-world problems often compute `unit price × quantity` before summing lines. Every multiplication must be protected just like addition.

Buggy example:

```java
record Purchase(int quantity, int unitPriceVnd) {}

Purchase purchase = new Purchase(50_000, 50_000);

long wrong = purchase.quantity() * purchase.unitPriceVnd();

System.out.println(wrong); // -1794967296
```

To use `long` from the start:

```java
long lineTotal = (long) purchase.quantity()
    * purchase.unitPriceVnd();

System.out.println(lineTotal); // 2500000000
```

If the product still risks exceeding `long`, use `Math.multiplyExact(long, long)` to detect it or `BigInteger.multiply` to compute it exactly.

```java
long price = 4_000_000_000L;
long quantity = 3L;

long safeProduct = Math.multiplyExact(price, quantity);
System.out.println(safeProduct); // 12000000000
```

When unit price and quantity are much larger, an expression such as `Math.multiplyExact(Long.MAX_VALUE, 2L)` will throw an exception. `BigInteger` supports large multiplication:

```java
BigInteger exactProduct = BigInteger.valueOf(Long.MAX_VALUE)
    .multiply(BigInteger.valueOf(2L));

System.out.println(exactProduct); // 18446744073709551614
```

Therefore, in a `filter → mapToLong → sum` pipeline, you must check **both the mapping expression that produces numeric values** and the final sum.

## 8. Money With Fractional Parts: Do Not Substitute `double`

If the data represents money with fractional parts, using `double` to avoid integer overflow can introduce binary representation errors.

```java
double result = 0.1 + 0.2;
System.out.println(result); // 0.30000000000000004
```

For currency, the usual choices are:

- Use `long` to store the **smallest unit** such as dong, xu, or cents, if bounds and rounding rules are well defined.
- Use `BigDecimal` when fractional decimals exist and decimal arithmetic with explicit rounding rules is required.

`BigDecimal` example:

```java
import java.math.BigDecimal;
import java.util.List;

List<BigDecimal> amounts = List.of(
    new BigDecimal("0.10"),
    new BigDecimal("0.20")
);

BigDecimal total = amounts.stream()
    .reduce(BigDecimal.ZERO, BigDecimal::add);

System.out.println(total); // 0.30
```

This example uses decimal strings to construct `BigDecimal` values matching the exact input data. Avoid `new BigDecimal(0.1)` if you intend the exact decimal `0.1`, because the `double` argument already carries an approximate binary representation. Specify rules for `scale` and `RoundingMode` when calculating percentages, taxes, or division.

`BigDecimal` solves decimal arithmetic; `BigInteger` solves arbitrarily large integer arithmetic. Choose based on **business semantics**, not just because you want a “bigger” type.

## 9. Complete Example: Safe Revenue Aggregation

The Java 17+ snippet below shows three clear strategies:

1. `long` for common sums whose range is controlled.
2. `Math.multiplyExact` and `Math.addExact` to detect overflow in `long`.
3. `BigInteger` when you want exact addition even if the sum can exceed `long`.

```java
import java.math.BigInteger;
import java.util.List;

public class SafeRevenueAggregation {
    record Order(String id, long unitPriceVnd, long quantity) {}

    static long totalWithLong(List<Order> orders) {
        return orders.stream()
            .mapToLong(order ->
                order.unitPriceVnd() * order.quantity()
            )
            .sum();
    }

    static long totalWithExactChecks(List<Order> orders) {
        return orders.stream()
            .mapToLong(order -> Math.multiplyExact(
                order.unitPriceVnd(), order.quantity()
            ))
            .reduce(0L, Math::addExact);
    }

    static BigInteger totalWithBigInteger(List<Order> orders) {
        return orders.stream()
            .map(order -> BigInteger.valueOf(order.unitPriceVnd())
                .multiply(BigInteger.valueOf(order.quantity())))
            .reduce(BigInteger.ZERO, BigInteger::add);
    }

    public static void main(String[] args) {
        List<Order> regularOrders = List.of(
            new Order("O-01", 1_500_000_000L, 2L),
            new Order("O-02", 2_000_000_000L, 3L)
        );

        System.out.println(totalWithLong(regularOrders));
        System.out.println(totalWithExactChecks(regularOrders));
        System.out.println(totalWithBigInteger(regularOrders));
        // All three print: 9000000000

        List<Order> hugeOrders = List.of(
            new Order("O-03", Long.MAX_VALUE, 1L),
            new Order("O-04", 1L, 1L)
        );

        System.out.println(totalWithLong(hugeOrders));
        // -9223372036854775808: overflowed value, unusable for business logic.

        try {
            System.out.println(totalWithExactChecks(hugeOrders));
        } catch (ArithmeticException exception) {
            System.out.println("Sum exceeds long range");
        }

        System.out.println(totalWithBigInteger(hugeOrders));
        // 9223372036854775808: exact sum.
    }
}
```

**Analysis:** `totalWithLong` is suitable only when there is evidence that **both every multiplication and the addition** fit within `long`. `totalWithExactChecks` guards multiplication and addition with exceptions; if the policy is to reject out-of-range data, that is straightforward to follow. `totalWithBigInteger` accepts object and arbitrary-precision arithmetic overhead to keep an exact integer result.

Never use an overflowed result to store invoices, settlements, or credit limits. Select the right strategy at the data boundary and validate bounds across intermediate steps.

## 10. Laziness, Parallelism, and Correctness of Addition

`filter`, `map`, `mapToLong`, and `mapToObj` are intermediate operations, typically executed when a terminal operation such as `sum()` or `reduce()` consumes the pipeline. A Stream can only be consumed once.

```java
import java.util.stream.LongStream;

var amounts = LongStream.of(100L, 200L)
    .filter(value -> value > 0L); // Sum not computed yet.

long total = amounts.sum(); // 300

// amounts.count(); // Cannot reuse an already-consumed Stream.
```

### 10.1. Parallelism Does Not Fix Overflow

`parallel()` splits processing into chunks and combines the results. It **does not widen numeric types**:

```java
int wrong = java.util.stream.IntStream
    .of(Integer.MAX_VALUE, 1)
    .parallel()
    .sum();

System.out.println(wrong); // -2147483648
```

`int` addition is still `int` addition. With two's-complement integers, overflow wraps modulo the bit width; whether the pipeline runs sequentially or in parallel, that result is still **not the exact mathematical sum**.

`BigInteger::add` is associative, making it semantically suitable for parallel `reduce` when there are no side effects and `BigInteger.ZERO` is used as the identity element. However, parallel processing carries splitting/combining and allocation overhead; it is not automatically faster on small datasets.

### 10.2. `Math.addExact` and Grouping Order

As in section 4.2, `Math.addExact` throws an exception on an overflowing intermediate addition. Under parallel execution, how chunks are grouped affects which intermediate sums are formed; therefore, this strategy should not be used as an order-independent proof that “the final mathematical sum fits in bounds”.

When you need to check **only the final sum** (allowing intermediate values to exceed bounds), use `BigInteger` and call `intValueExact()` or `longValueExact()` at the end. When the goal is **never performing an operation that exceeds the `long` range**, checking with `Math.addExact`/`Math.multiplyExact` is appropriate.

### 10.3. Shared State in Pipelines

Do not accumulate money manually into a variable outside a lambda:

```java
long[] total = {0L};

orders.parallelStream().forEach(order ->
    total[0] += order.unitPriceVnd() * order.quantity()
); // Unsafe: potential race condition.
```

Use `mapToLong(...).sum()` when the `long` range suffices, `reduce(0L, Math::addExact)` to detect overflow, or `reduce(BigInteger.ZERO, BigInteger::add)` for an exact integer sum. Grouping/collector methods must also follow parallel-safe accumulator rules.

If performance influences design decisions, benchmark with representative data using an appropriate tool such as JMH. `BigInteger` may consume more memory, whereas `long` can be faster once correctness is guaranteed. Performance only matters when **both options return the correct result required**.

## 11. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Assigning `IntStream.sum()` to a `long` variable and assuming it is safe | `int` already overflowed before assignment | Use `asLongStream()` or `mapToLong` before `sum()`. |
| Writing `mapToLong(x -> x.intA() * x.intB())` | Multiplies in `int` before widening | Cast one operand to `long` before multiplication. |
| Using `Integer::sum` in `reduce` for large sums | Silent `int` overflow | Use `mapToLong`, `Math.addExact`, or `BigInteger` depending on the goal. |
| Assuming `Collectors.summingLong` never overflows | Still bounded by `long` | Check bounds or aggregate with `BigInteger`. |
| Using `Math.addExact` expecting a sum larger than the type | Throws an exception instead of producing a larger number | Choose `long` or `BigInteger`. |
| Using `long` to multiply numbers already computed in `int` | Information loss happened before assignment | Convert types before the operation. |
| Using `double` to store very large integer sums | May lose exact integer precision | Keep `long` if sufficient, or use `BigInteger`. |
| Using `new BigDecimal(0.1)` to represent exact 0.1 | Carries binary approximation from `double` | Use a decimal string or normalized value. |
| Inspecting only the final sum while ignoring intermediate multiplications/additions | Intermediates already overflowed; result is unreliable | Audit the entire pipeline and mapping expressions. |
| Thinking `parallel()` makes summing more accurate | Does not change value ranges | Choose exact numeric types and operations first. |

## 12. Practice Exercises

### Exercise 1: `IntStream.sum()` Overflow

Given `IntStream.of(1_200_000_000, 1_200_000_000)`, predict the result of `sum()`. Rewrite it using `asLongStream().sum()` and explain why assigning the original `sum()` result to `long` cannot fix the bug.

### Exercise 2: Computing Invoice Line Totals

Each line has `quantity` and `unitPriceVnd` of type `int`, each set to `60_000`. Write `Stream<Item>.mapToLong(...).sum()` to aggregate 100 lines correctly. Try writing `item.quantity() * item.unitPriceVnd()` before casting and observe the difference.

### Exercise 3: Detecting Rather Than Accepting Overflow

Create `IntStream.of(Integer.MAX_VALUE, 1)`. Compare `sum()` with `reduce(0, Math::addExact)`. When should you throw an exception, and when should you widen to `long`?

### Exercise 4: Final Sum Within Range While Intermediates Exceed Range

Test the sequence `[Integer.MAX_VALUE, 1, -1]` with `reduce(0, Math::addExact)`. Then change the pipeline to `mapToObj(BigInteger::valueOf)` (from `IntStream`), `reduce(BigInteger.ZERO, BigInteger::add)`, and `intValueExact()`. Explain the semantic difference between the two strategies.

### Exercise 5: Grouped Sums With `BigInteger`

Given multiple orders with `region` and `amountVnd` of type `long`, use `Collectors.groupingBy` combined with `Collectors.reducing` to build a `Map<String, BigInteger>`. Test a group containing two elements `Long.MAX_VALUE` and `1L`.

### Exercise 6: Bounds and Performance Planning

Suppose a day can have two million transactions, each valued between -2 million and +2 million units. Compute the mathematical bounds of the sum, pick a suitable type for `sum()`, and state the required assumptions. If volume grows to several billion transactions, re-evaluate the bounds and describe the checks needed.

### Exercise 7: Money With Fractional Parts

Aggregate `0.10` and `0.20` using `double` and `BigDecimal`. Compare the results, then explain when a system should store money in the smallest unit using `long` and when it needs `BigDecimal`.

## 13. Self-Check Questions

- What type does `IntStream.sum()` return, and what is the range of that type?
- Why does `long total = intStream.sum()` fail to prevent `int` overflow?
- At what point must casting happen if multiplying two `int` values can exceed the range?
- Does `Math.addExact` detect overflow or widen numbers? When does it throw an exception?
- Why can a sequence whose final sum fits in `int` still throw an error when summed with `Math.addExact`?
- How does `IntSummaryStatistics.getSum()` differ from `IntStream.sum()` in return type?
- When is `BigInteger` better suited than `long`, and how do you check when converting back?
- Why does `parallelStream()` not cure overflow or shared side effects?
- For decimal money, what problem does `BigDecimal` solve that `BigInteger` does not directly model?

**Key takeaway:** The accuracy of a sum depends on **the type of each operation**, not on the type of the variable receiving the final result. Widen to `long` **before adding or multiplying** if 64 bits suffice; use `Math.addExact`/`Math.multiplyExact` to fail on overflow; choose `BigInteger` when integer sums may exceed `long`. With the Java Stream API, carefully inspect `map`, `reduce`, `sum`, collectors, and the impact of parallel processing to keep business results accurate.
