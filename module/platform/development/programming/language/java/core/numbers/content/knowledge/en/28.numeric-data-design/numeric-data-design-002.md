# Choosing Intermediate Calculation Types Separately from Storage Types in Java

## 1. Why Shouldn't One Numeric Type Be Used for Every Stage?

When designing numeric data, you must distinguish **the type of the stored value** from **the type used in intermediate calculations**. A property may comfortably fit in an `int` or `long` in its final state, while the calculation that produces it may require a wider range, different precision, or a different representation.

For example, quantity and unit price are both `int`:

```java
int quantity = 50_000;
int unitPrice = 50_000;
long total = quantity * unitPrice; // Wrong: int multiplication overflows before assignment.
```

The expected mathematical value is `2_500_000_000`, which is greater than `Integer.MAX_VALUE` (`2_147_483_647`). Because both operands are `int`, Java **multiplies using `int` first**, the result overflows to `-1_794_967_296`, and only then is it widened to `long`. Assigning to a `long` variable cannot fix a calculation that has already overflowed.

The correct approach when the total's range fits within `long`:

```java
long total = (long) quantity * unitPrice; // 2_500_000_000
```

**Fundamental rule:** determine the bounds and precision at *each calculation step*, then choose the type that performs the operation; only at the storage or output boundary should you validate and convert to the target type. Never assume the receiving variable's type dictates the calculation's type.

## 2. Two Contracts to Define

### Calculation Contract

You need to answer:

- What are the maximum and minimum ranges of **intermediate results**?
- Are there additions, multiplications, aggregations of millions of records, squaring, ratios, or divisions producing fractional parts?
- Must the operation be strictly exact, or is floating-point error acceptable?
- If the range is exceeded, must the program throw an error, switch to a larger type, or follow a rounding rule?
- Are there units that must be kept consistent, such as **dong** vs. **cents**, **meters** vs. **millimeters**, **seconds** vs. **nanoseconds**?

### Storage Contract

You need to answer:

- Is the field a Java `int`/`long`, a database `INTEGER`/`BIGINT`/`DECIMAL(p,s)`, or a numeric string in a JSON interface?
- How many decimal places must the final value keep, can it be negative, and must scale be preserved?
- Are there requirements for schema compatibility, indexing, querying, data size, or interoperability with other systems?
- May narrowing conversions round? How must out-of-range data be rejected?

Only after defining both contracts can you choose the architecture. You might use `int` to store birth year, `long` to store total view counts; use `long` to store money in minor units while computing tax with `BigDecimal`; or use `BigInteger` to sum massive values before verifying that the final result can be stored in `long`.

## 3. Value Ranges of Common Numeric Types

| Java Type | Range and Characteristics | Common Role |
| --- | --- | --- |
| `byte` | -128 to 127 | Binary or protocol data, rarely an aggregation calculation type |
| `short` | -32,768 to 32,767 | Storing small-range fields; arithmetic operations are normally promoted to `int` |
| `int` | -2³¹ to 2³¹-1 | Counters or small attributes, general-purpose integers |
| `long` | -2⁶³ to 2⁶³-1 | Large counters, sums and products exceeding `int` range |
| `float` | IEEE 754 32-bit; finite precision | Approximate measurements under specific resource constraints |
| `double` | IEEE 754 64-bit; ~15–17 significant decimal digits | Statistics, science, ratios where approximation error is acceptable |
| `BigInteger` | Integers whose magnitude is limited primarily by resources | Integer arithmetic exceeding `long` |
| `BigDecimal` | Decimal with unscaled integer and `scale`; precision per operation/`MathContext` | Finance, exact decimals, and controlled rounding |

`float` and `double` have a very wide magnitude range, yet **do not represent every integer or decimal number exactly** within that range. Choosing `double` merely because it can hold a "very large" number can lose low-order integer digits. Conversely, using `BigDecimal` for a physical measurement that already has input measurement error does not magically create precision that never existed.

Never choose a type based solely on current values. You must account for **intermediate operation bounds**, future data volume, negative signs, multiplier factors, and aggregation limits.

## 4. Type Promotion and Overflow Before Assignment

In Java, the result of addition, subtraction, or multiplication on `byte`, `short`, and `char` is normally promoted to `int`. When both operands are `int`, the operation still has type `int`. Having one `long` operand in an integer operation causes the calculation to execute in `long`, provided no sub-expression overflowed earlier.

```java
int x = 50_000;
int y = 50_000;

long wrong = x * y;          // -1_794_967_296: int overflowed
long right = (long) x * y;   //  2_500_000_000: multiplied as long
long also = 1L * x * y;      //  2_500_000_000: long literal
long stillWrong = (long) (x * y); // overflow occurred inside parentheses
```

Casting **after** the calculation cannot recover lost data.

For sums:

```java
int a = 2_000_000_000;
int b = 1_000_000_000;

long wrongSum = a + b;          // -1_294_967_296
long rightSum = (long) a + b;   //  3_000_000_000
```

Division also depends on operand types:

```java
int sum = 5;
int count = 2;

double wrongAverage = sum / count;         // 2.0: integer division occurred
double rightAverage = (double) sum / count; // 2.5
```

In a complex expression, widen the type at the **exact operation that needs the wider range**. For example, `(long) quantity * unitPrice` widens the multiplication immediately; whereas `(long) (quantity * unitPrice)` widens too late.

### Java Does Not Automatically Throw Errors on All Overflowing Operations

Ordinary `int` and `long` addition, subtraction, and multiplication can overflow and produce results using modular arithmetic (mod 2^32 or 2^64), rather than throwing an exception. To detect overflow when it is an error, use `Math.addExact`, `Math.subtractExact`, `Math.multiplyExact`, `Math.incrementExact`, `Math.negateExact`, or `Math.toIntExact` as appropriate.

```java
long valid = Math.multiplyExact((long) 50_000, 50_000); // 2_500_000_000
int invalid = Math.multiplyExact(50_000, 50_000);       // ArithmeticException
```

The second line intentionally demonstrates the exception; if executed sequentially without `try/catch`, the program stops there. `multiplyExact(int,int)` detects `int` overflow, while `multiplyExact(long,long)` detects `long` overflow. Widening to `long` does not guarantee freedom from overflow in every problem.

## 5. Complete Java 17+ Program Demonstrating the Bug and Fix

Save the file `IntermediateIntegerDemo.java`:

```java
import java.util.stream.IntStream;

public class IntermediateIntegerDemo {
    public static void main(String[] args) {
        int quantity = 50_000;
        int unitPrice = 50_000;

        long overflowed = quantity * unitPrice;
        long widened = (long) quantity * unitPrice;
        long exact = Math.multiplyExact((long) quantity, unitPrice);

        System.out.println("int multiplication: " + overflowed);
        System.out.println("long multiplication: " + widened);
        System.out.println("checked long product: " + exact);

        try {
            Math.multiplyExact(quantity, unitPrice);
        } catch (ArithmeticException e) {
            System.out.println("int overflow detected");
        }

        try {
            Math.toIntExact(exact);
        } catch (ArithmeticException e) {
            System.out.println("cannot store in int");
        }

        int intSum = IntStream.of(2_000_000_000, 1_000_000_000).sum();
        long longSum = IntStream.of(2_000_000_000, 1_000_000_000)
                .asLongStream().sum();

        System.out.println("IntStream sum: " + intSum);
        System.out.println("long stream sum: " + longSum);
    }
}
```

Run:

```bash
javac IntermediateIntegerDemo.java
java IntermediateIntegerDemo
```

Exact stdout:

```text
int multiplication: -1794967296
long multiplication: 2500000000
checked long product: 2500000000
int overflow detected
cannot store in int
IntStream sum: -1294967296
long stream sum: 3000000000
```

This example only illustrates intermediate ranges and overflow; those values must not be interpreted as "Java returning random numbers." The first negative output and the negative `IntStream.sum()` output are deterministic consequences of overflowing 32-bit integer arithmetic.

To aggregate quantities larger than the `long` range, switch entirely to `BigInteger` or calculate within a proven safe range. `LongStream.sum()` uses `long` but does not automatically protect against overflow.

## 6. Small Storage Types Do Not Require Small Intermediate Types

Suppose a system stores scores as `short` because each score is from 0 to 100. An arithmetic average needs a much larger sum when there are millions of records; computing directly in `short` is a design flaw even when **the final average result** still falls within 0..100.

Another example is per-line quantities that fit in `int`, while the order total must be `long`. You can keep storing per-line quantities as `int` and return the total as `long`. There is no need to change every data column to `long` just because an aggregate sum can be large.

On the other hand, if an intermediate calculation uses `long` and the final value must be stored in `int`, you must check **the target range upon conversion**:

```java
long total = 2_500_000_000L;
int unsafe = (int) total; // -1_794_967_296, lossy narrowing

// Throws ArithmeticException instead of silently corrupting:
int checked = Math.toIntExact(total);
```

The `Math.toIntExact` line will throw an exception in this illustrative scenario; these lines are not a full sequentially runnable program.

For `short` and `byte`, there are no standard `Math.toShortExact`/`Math.toByteExact` methods; you can validate the range first:

```java
static short toShortExact(int value) {
    if (value < Short.MIN_VALUE || value > Short.MAX_VALUE) {
        throw new ArithmeticException("Out of short range");
    }
    return (short) value;
}
```

This snippet is a method that can be placed inside a class; it has no standalone `main`. It helps express **narrowing rules** clearly. Never use a direct narrowing cast when data loss is forbidden.

## 7. When BigInteger Is Needed as an Intermediate Calculation Type

`long` has the limit `Long.MAX_VALUE = 9_223_372_036_854_775_807`. If inputs or sums/products can exceed that limit, `BigInteger` enables integer arithmetic without fixed-width overflow:

```java
import java.math.BigInteger;

public class BigIntegerIntermediateDemo {
    public static void main(String[] args) {
        BigInteger total = BigInteger.valueOf(Long.MAX_VALUE)
                .add(BigInteger.ONE);

        System.out.println("Exact total: " + total);
        System.out.println("Beyond long: "
                + (total.compareTo(BigInteger.valueOf(Long.MAX_VALUE)) > 0));

        try {
            total.longValueExact();
        } catch (ArithmeticException e) {
            System.out.println("Cannot fit long");
        }
    }
}
```

Run:

```bash
javac BigIntegerIntermediateDemo.java
java BigIntegerIntermediateDemo
```

Stdout:

```text
Exact total: 9223372036854775808
Beyond long: true
Cannot fit long
```

`longValue()` truncates high bits if the value is outside `long`, yielding a semantically wrong result. `longValueExact()` is the right choice when you want to validate conversion back to the storage type. Similarly, `BigInteger.intValueExact()` verifies that a value fits in `int`.

Do not overuse `BigInteger` for every counter variable: it allocates objects and has higher overhead than primitive arithmetic. Choose `BigInteger` when calculations genuinely have the potential to exceed `long` or when the domain range contract cannot establish a safe bound.

## 8. double Can Be Wider Than int/long, Yet Does Not Preserve Every Digit

`double` is often used as an intermediate type for statistics, ratios, positions, measurements, or approximation algorithms. It has a wide magnitude range but only **53 bits of binary precision** (including the implicit leading bit), so it only represents every integer exactly in a contiguous range up to 2^53. Larger integers may be rounded when converted to `double`.

Example:

```java
long exactCount = 9_007_199_254_740_993L; // 2^53 + 1
double approximate = exactCount;
System.out.println(approximate == 9_007_199_254_740_992.0); // true
```

`approximate` cannot preserve the ones digit of `exactCount`. Therefore, do not convert all large integer totals or IDs to `double` just to "avoid overflow." In particular, IDs, minor currency units, and counts requiring exactness should remain `long`/`BigInteger` as appropriate.

Decimals also have representation issues:

```java
double binary = 0.1 + 0.2;
System.out.println(binary); // 0.30000000000000004
```

This is not a Java calculation bug, but an IEEE 754 property: `0.1` and `0.2` cannot be represented exactly with finitely many binary bits. Use `double` when **approximation error is acceptable and has a testing policy**, and when exact decimals are required, use `BigDecimal` with appropriate inputs.

A few points to remember when converting from `double` to integers:

- `(int) doubleValue` can drop the fractional part, saturate at the target type's bounds when out of range, and convert `NaN` to 0; it is not an exact checked conversion.
- `Math.round` applies its own rounding rule and still requires range considerations; it is not equivalent to an exact conversion.
- When fractional parts or non-finite values are unacceptable, validate inputs and range before narrowing, or use an appropriate `BigDecimal` representation if the domain requires decimal numbers.

## 9. BigDecimal for Decimal Calculations, Storage Type May Differ

A common design pattern in financial systems is storing the **smallest unit** as `long` (e.g., cents) while computing taxes, discounts, interest, rates, and rounding using `BigDecimal`.

Reasons:

1. `long` stores integer minor units accurately and works well for querying/reconciliation when the schema sets valid bounds.
2. Percentage or ratio calculations can produce numbers with many decimal digits, even though the final stored value only has two digits.
3. Round only at a **defined business boundary**, then convert back to the storage unit with exact and range checks.

For instance: pre-tax amount is 37.02, tax rate is 7.5%; the exact tax before rounding is 2.77650, and rounding to two digits with `HALF_UP` yields 2.78. Storing every step directly into `long` cents before applying a rounding policy can lose digits needed for calculation.

### Complete Java 17+ Program

Save the file `MoneyIntermediateDemo.java`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class MoneyIntermediateDemo {
    static BigDecimal fromCents(long cents) {
        return BigDecimal.valueOf(cents, 2);
    }

    static long toCentsExact(BigDecimal amount) {
        return amount.movePointRight(2).longValueExact();
    }

    public static void main(String[] args) {
        long unitPriceCents = 1_234L;
        long quantity = 3L;

        long subtotalCents = Math.multiplyExact(unitPriceCents, quantity);
        BigDecimal subtotal = fromCents(subtotalCents);

        BigDecimal exactTax = subtotal.multiply(new BigDecimal("0.075"));
        BigDecimal bookedTax = exactTax.setScale(2, RoundingMode.HALF_UP);
        BigDecimal total = subtotal.add(bookedTax);
        long storedTotalCents = toCentsExact(total);

        System.out.println("Subtotal: " + subtotal);
        System.out.println("Tax before rounding: " + exactTax);
        System.out.println("Tax booked: " + bookedTax);
        System.out.println("Total: " + total);
        System.out.println("Stored cents: " + storedTotalCents);

        try {
            toCentsExact(new BigDecimal("1.005"));
        } catch (ArithmeticException e) {
            System.out.println("Fractional cent rejected");
        }
    }
}
```

Run:

```bash
javac MoneyIntermediateDemo.java
java MoneyIntermediateDemo
```

Stdout:

```text
Subtotal: 37.02
Tax before rounding: 2.77650
Tax booked: 2.78
Total: 39.80
Stored cents: 3980
Fractional cent rejected
```

Explanation:

- `Math.multiplyExact` detects `long` overflow when multiplying price by quantity.
- `BigDecimal.valueOf(cents, 2)` represents the monetary amount accurately with scale 2.
- Multiplying `BigDecimal` by the string `"0.075"` preserves the exact decimal value of the tax rate.
- `setScale(2, HALF_UP)` is **the example's rounding rule**, not a default rule for every system or currency.
- `movePointRight(2).longValueExact()` converts to cents only if the value is an exact whole number of cents within the `long` range. The value `1.005` becomes `100.5` cents, so it is rejected rather than silently rounded.

This is an example of conversion boundaries, not complete tax software. A real system must specify the currency, rounding timing, tax policy, remainder allocation, and valid storage representation.

## 10. Intermediate Calculations with Precision and Scale Different from Storage

`BigDecimal` has `scale` (number of digits after the decimal point for non-negative scale) and `precision` (number of digits in the unscaled integer). Inputs, intermediate results, and outputs can have different scales while representing the same mathematical value.

Example:

```java
BigDecimal amount = new BigDecimal("12.34");
BigDecimal ratio = new BigDecimal("0.075");
BigDecimal product = amount.multiply(ratio); // 0.92550

BigDecimal finalValue = product.setScale(2, RoundingMode.HALF_EVEN);
// 0.93
```

This is an illustration inside a method with `BigDecimal` and `RoundingMode` imported. Intermediate calculations keep extra digits, then convert to the storage scale at **the proper rounding point**. Calling `setScale(2, ...)` at every step can accumulate error across a chain of operations and make the final result differ from rounding only at the end.

Also keep in mind:

- `new BigDecimal("0.1")` represents exact decimal 0.1; `new BigDecimal(0.1)` receives an approximate binary `double` value.
- `divide(divisor)` requires an exact finite decimal quotient; if a quotient like 1/3 is non-terminating, Java throws `ArithmeticException`. You must define an appropriate `scale`, `MathContext`, or `RoundingMode`.
- `RoundingMode.UNNECESSARY` is useful when the contract forbids any loss of significant digits: if changing scale/precision actually requires rounding, the conversion throws an error.
- Storing `BigDecimal` as `DECIMAL(p,s)` in a database requires checking the column's **precision/scale** limits and validating on the application side. Do not assume the database will always throw an error or round according to Java's policy.
- When receiving and outputting values, align on format, scale, unit, and policy for numbers that are too large or have too many digits.

## 11. Designing Numeric Domains and Conversion Boundaries

Rather than allowing every layer to cast arbitrarily, define clear boundaries:

```text
Stored/input data
    |
    | parse + validate range, unit, scale
    v
Sufficiently wide/exact intermediate calculation type
    |
    | calculations with overflow/rounding checks
    v
Business result
    |
    | validate limits and exact type conversion
    v
Storage type/DTO/output schema
```

Warehouse example:

- `quantityPerLine` can be `int` when each line's limit is small and validated.
- `totalQuantity` can be `long` when summing across many lines.
- `grandTotal` can use `BigDecimal` when applying decimal prices, taxes, and discounts.
- Stored total data can be `long` cents or a `DECIMAL(p,s)` column, depending on the schema/domain.
- Before saving, invoke an exact conversion or validation; if it exceeds storage capacity, return a contextual error rather than casting and corrupting data.

You can place `fromStorage(...)` and `toStorageExact(...)` methods in domain types or adapters. They centralize the conversion policy, freeing the calculation layer from knowing whether the DB uses `BIGINT` or `DECIMAL(18,2)`. If a business-valid result does not fit the storage type, that is a signal to re-evaluate the **schema**, not to drop fractional digits by default to force a fit.

### Units Are Part of the Contract

Two `long` values can still have completely different meanings:

```java
long amountCents = 1_234L;  // 12.34 major currency units
long amountUnits = 1_234L;  // 1234 major currency units
```

They share the same primitive type, yet cannot be added or compared as if they shared the same unit. For complex domains, consider creating named, validated `record`/class types such as `MoneyCents`, `DurationMillis`, `Quantity`, instead of scattering unit conversions around. Unit conversions can multiply and cause overflow, so they must use `Math.multiplyExact` or a wider type first.

## 12. Databases and Data Exchange Interfaces

Choosing a storage type requires considering layers outside Java.

| Need | Suitable Calculation Type | Suitable Storage Type | Risks to Check |
| --- | --- | --- | --- |
| Daily event counts | `long` or checked `BigInteger` if huge | `BIGINT` | Sum exceeding `int` or `long` |
| Summing quantities from many `int` lines | `long` | `INTEGER`/`BIGINT` depending on final total limit | Narrowing cast corrupting value |
| Money in minor units | `long` for checked integer add/multiply; `BigDecimal` for rates | `BIGINT` cents | Unit mismatch, overflow, rounding |
| Decimal tax/interest/fees | `BigDecimal` | `DECIMAL(p,s)` or minor unit after rounding | Scale loss, wrong rounding policy |
| Approximate statistics | `double` and suitable summation algorithm | `DOUBLE PRECISION` or field with precision convention | IEEE 754 error, NaN/Infinity |
| Very large integers | `BigInteger` | Sufficiently large `DECIMAL(p,0)` or string per contract | Exceeding schema precision/limits |

`DECIMAL(12,2)` typically provides 12 digits of precision, 2 of which are decimal digits, leaving at most 10 integer digits; confirm the specific database's limits. Before inserting/updating, check that the storage type has sufficient range, scale, and required rounding rules.

**JSON/JavaScript:** JavaScript `Number` is also binary floating-point (typically IEEE 754 double). It cannot represent every `long` integer accurately. For IDs or integers exceeding `Number.MAX_SAFE_INTEGER`, consider transmitting decimal strings or using an encoding/schema with explicit large-integer types. Do not assume that Java serializing a `long` as a JSON number lets every client preserve all digits.

Similarly, converting from `BigDecimal` to `double` before returning an API response can lose precision even when data in Java and the DB remains accurate. Communication boundaries need their own contracts rather than relying solely on internal types.

## 13. Evidence-Based Space and Performance Optimization

Small storage types can reduce size or match a schema, but you should never introduce overflow risk during processing just to save temporary memory.

Questions worth considering:

1. **Value range:** do `int`, `long`, or `BigInteger` have enough range for the largest calculation?
2. **Precision:** does the calculation need exact decimal or binary approximation?
3. **Number of rounding steps:** can rounding be deferred to a defined boundary to reduce drift?
4. **Immutability/allocation cost:** `BigInteger` and `BigDecimal` are immutable objects; operations allocate new objects and have overhead compared to primitives.
5. **Collection/stream types:** `IntStream.sum()` returns `int`; if `long` is needed, switch using `mapToLong(...)` or an appropriate aggregation algorithm from the start.
6. **Failure observability:** use checked arithmetic and exact conversions to catch out-of-range data instead of failing silently.

Do not prematurely optimize by keeping calculations in `int` if the business cannot guarantee the range. If `BigDecimal` performance is a measured bottleneck, you can use fixed-scale integer units and checked arithmetic in appropriate steps, while ensuring all rate calculations follow domain rounding.

## 14. Common Pitfalls

| Mistake | Consequence | Correct Approach |
| --- | --- | --- |
| `long total = intA * intB` | `int` overflows before assignment | `(long) intA * intB`, or `Math.multiplyExact` with a wider type |
| `(long) (intA * intB)` | Cast happens after data loss | Promote **before** multiplying |
| `double mean = intSum / intCount` | Integer division drops fraction | `(double) intSum / intCount` and check count |
| `int result = (int) longResult` | May turn into an unrelated value | `Math.toIntExact(longResult)` |
| Using `double` for all large integer totals | Loss of integer digits outside exact range | Keep `long`/`BigInteger` |
| Computing money in `double` then storing cents | Binary error and hard-to-control rounding | Use `BigDecimal` or minor-unit integers with clear contracts |
| Rounding money after every intermediate step regardless of domain | Cumulative drift | Round at defined boundaries |
| Using `BigDecimal.longValue()` to store without checking | Can drop fractions/overflow | `longValueExact()` after normalization |
| Assuming `long` cannot overflow | Huge sums/products can overflow | `Math.addExact`/`multiplyExact` or `BigInteger` |
| Storing `BigDecimal` into `DECIMAL(p,s)` without validating | Unintended rounding or rejection | Validate precision/scale against schema |
| Using the same `long` for cents and major units | Off by a factor of 100 | Domain types/field names and explicit conversions |
| Outputting large `long` as JSON number to JavaScript `Number` | Client loses digits | Decimal string contract or suitable large-number type |

## 15. Situation-Based Type Selection Guide

**Aggregating quantities:** if individual values are `int` but the sum can exceed `int`, calculate in `long` from the very first addition; use checked addition if there is a risk of exceeding `long`. Store into `int` only after `Math.toIntExact` succeeds.

**Multiplying quantity by unit price:** determine the maximum range of the product; if both are `int` and the product exceeds `int`, cast one operand to `long` before multiplying. For products exceeding `long`, use `BigInteger`. The unit price storage type can remain as is if its own range still fits.

**Ratios or averages:** if the problem only needs an approximation, `double` with checks for division by zero and NaN/Infinity suffices in many cases. If exact decimal is needed, use `BigDecimal` specifying `scale` and `RoundingMode`, or keep integer numerator/denominator separately until rounding is required.

**Currency:** specify the smallest unit, currency, tax/discount policy, and rounding. You can store cents as `long` and use `BigDecimal` in between. Converting back to cents must be an exact check; do not assume all currencies have two decimal places.

**Interface/API limits:** a Java value stored accurately in `long`/`BigInteger` can exceed the receiving system's numeric type. Check the *entire pipeline*, not only correctness inside Java.

**Values with wildly varying magnitudes:** avoid overflow in intermediate variables when squaring or raising to powers. You may need `BigInteger`/`BigDecimal`, or an alternative algorithm that avoids producing huge intermediate results if the final output is just a comparison.

## 16. Self-Check

1. **Why can `long x = 50_000 * 50_000` be wrong?** Because both literals default to `int`, so multiplication overflows before assignment. Use `50_000L * 50_000`.
2. **Does casting `(long) (a * b)` fix `int` overflow?** No. One operand must be widened before multiplication.
3. **What if you need to store a `long` result into `int` without accepting data loss?** Use `Math.toIntExact` or full range validation.
4. **When should you use `BigInteger`?** When integer calculations must be exact and can exceed `long` limits.
5. **Is it safe to use `double` to hold any large integer?** No; `double` does not represent every integer above 2^53 accurately.
6. **Why might monetary totals be stored as `long` cents while tax is computed with `BigDecimal`?** Because applying rates produces intermediate decimal fractions that need a rounding policy; storing cents is only appropriate after remainders are handled.
7. **What does `BigDecimal.longValueExact()` check?** That the value is an exact integer and within the `long` range; no silent truncation of fractions or overflow.
8. **Does `IntStream.sum()` automatically switch to `long` when the sum is large?** No; it returns `int`. You must choose a `long` aggregation from the start.
9. **Why must types be checked at the JSON boundary?** Because an exact integer in Java may lose exactness when a client uses `Number`.
10. **Must every storage type always match the intermediate calculation type?** No; the intermediate type serves calculation correctness, while the storage type serves the data contract. There must be validated conversions between the two layers.

## 17. Key Takeaways

**Choose intermediate calculation types according to the maximum range and precision of the calculation; choose storage types according to the finalized data's range and representation.** The receiving variable's type does not change the type used to evaluate the expression. To prevent `int` overflow, promote before the operation; to detect overflow, use checked arithmetic; to narrow, perform exact checks.

For large integers, use `long` or `BigInteger` according to range; for exact decimal calculations, use `BigDecimal` with an explicit rounding policy; for approximate measurements, use `double` when approximation error is accepted. Every conversion to storage schemas, minor units, and API formats must be treated as a contract-checking step, avoiding storing data that "fits the type" yet carries the wrong meaning.