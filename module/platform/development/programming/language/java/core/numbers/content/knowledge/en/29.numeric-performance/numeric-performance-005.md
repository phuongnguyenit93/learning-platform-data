# Avoiding Unnecessary Precision or Scale Growth with BigDecimal

## 1. Problem and Learning Objectives

`BigDecimal` is an important choice when Java must process exact decimal numbers, such as currency, rates, or measurements with explicit rounding requirements. However, "exact" does not mean always keeping **as many digits as possible**. A pipeline that keeps extending the fractional part, multiplies many values with large scales, or converts to overly long decimal strings can increase memory, CPU, storage, and data transfer costs.

You need to distinguish two things:

- **Do not lose required precision:** do not round arbitrarily, do not silently switch to `double`, and do not strip scale if scale carries business meaning.
- **Do not create unnecessary representation size:** do not add thousands of trailing zeros, do not let scale grow unchecked across many multiplications, and do not request excessive precision or display formats.

The objective of this lesson is to understand the relationship between `precision`, `scale`, and representation size; recognize operations that can make them grow; design reasonable bounds at calculation, storage, and display boundaries; and verify correctness before optimizing.

Prerequisite: **performance must never be silently traded for wrong results**. A normalization, rounding, or precision truncation step is only valid when the data contract permits it.

## 2. Precision and Scale Are Not the Same Thing

A `BigDecimal` value is modeled as:

\[
\text{value} = \text{unscaledValue} \times 10^{-\text{scale}}
\]

Where:

- `unscaledValue()` returns an unbounded `BigInteger` representing the digits.
- `scale()` indicates the position of the decimal point in base 10; it can be positive, zero, or negative.
- `precision()` is the number of decimal digits in the unscaled value of the current representation, excluding the sign. Zero has precision 1.

Examples:

| Created value | `unscaledValue` | `precision` | `scale` | Arithmetic value |
| --- | ---: | ---: | ---: | --- |
| `new BigDecimal("1.2300")` | `12300` | `5` | `4` | `1.23` |
| `new BigDecimal("1.23")` | `123` | `3` | `2` | `1.23` |
| `new BigDecimal("1000")` | `1000` | `4` | `0` | `1000` |
| `new BigDecimal("1E+3")` | `1` | `1` | `-3` | `1000` |
| `new BigDecimal("1E-100000")` | `1` | `1` | `100000` | `10^-100000` |

Two numbers that are equal under `compareTo` can still differ under `equals` because `equals` also checks `scale`. For example, `1.2300` and `1.23` have the same value but different scales.

The last example in the table is an important trap: `1E-100000` has **precision 1** yet **scale 100000**. A large scale does not prove that the object holds 100000 digits in its unscaled value; conversely, producing a plain string or forcing another scale can cause memory to spike sharply.

## 3. Why Can Precision or Scale Affect Performance?

`BigDecimal` is an **immutable** type. Each operation produces a new result (though the implementation may occasionally reuse internal objects or cached values). Larger digit counts typically lead to larger integer representations, more arithmetic work, and more data to copy or convert.

Scenarios prone to unnecessary cost:

1. **Scale accumulating in exact multiplication**: the result keeps trailing zeros even when those zeros do not change the mathematical value.
2. **`setScale` to an excessively large value**: increasing scale from 0 to tens of thousands may require creating an unscaled value containing huge numbers of zeros.
3. **Forcing non-exponential strings**: `toPlainString()` can expand a very small or very large number into an enormous string.
4. **Division with overly high precision/scale**: computing and retaining more digits than required can incur substantial cost.
5. **Unbounded chains of operations**: precision, scale, and serialized length can grow across uncontrolled inputs or iterations.

These are **data- and algorithm-dependent risks**, not a claim that increasing precision or scale by one unit degrades performance by a fixed ratio. You must measure with proper benchmarks and monitor real inputs before drawing optimization conclusions.

## 4. Which Operations Naturally Increase Scale?

### Addition and subtraction

In ordinary exact addition/subtraction, the result has a scale equal to **the larger scale of the two operands** (when operations are valid and representable):

~~~java
BigDecimal a = new BigDecimal("1.2");    // scale 1
BigDecimal b = new BigDecimal("3.4500"); // scale 4
BigDecimal sum = a.add(b);

System.out.println(sum.toPlainString()); // 4.6500
System.out.println(sum.scale());         // 4
~~~

Because the fractional parts must align, an operand with a large scale can affect the result's scale. If trailing zeros carry no meaning in the contract, they can become a source of representation growth over many steps.

### Multiplication

With `multiply(BigDecimal)` **without `MathContext`**, the result scale equals the sum of the two operands' scales:

\[
\text{result.scale} = \text{left.scale} + \text{right.scale}
\]

~~~java
BigDecimal x = new BigDecimal("1.2300"); // scale 4
BigDecimal y = new BigDecimal("2.00");   // scale 2
BigDecimal product = x.multiply(y);

System.out.println(product.toPlainString()); // 2.460000
System.out.println(product.scale());         // 6
System.out.println(product.precision());     // 7
~~~

The arithmetic value is only `2.46`, yet the result retains scale 6. This may be **necessary** to preserve a representation policy; if unnecessary, trailing zeros can inflate precision/scale in subsequent steps.

Example of multiplying `1.000000` five times, starting from `BigDecimal.ONE`:

~~~java
BigDecimal value = BigDecimal.ONE;
BigDecimal factor = new BigDecimal("1.000000");

for (int i = 0; i < 5; i++) {
    value = value.multiply(factor);
}

System.out.println(value.toPlainString());
// 1.000000000000000000000000000000
System.out.println(value.precision()); // 31
System.out.println(value.scale());     // 30
~~~

**The value is always 1**, yet the representation's precision grows to 31 and scale to 30. As loop scale grows and inputs have large scales, representation size can become problematic.

### Division

`divide(BigDecimal)` without a rounding mode only returns an **exact** decimal result, or throws `ArithmeticException` if the decimal expansion does not terminate (e.g., `1 / 3`).

~~~java
BigDecimal one = BigDecimal.ONE;
System.out.println(one.divide(new BigDecimal("8"))); // 0.125

// one.divide(new BigDecimal("3"))
// -> ArithmeticException: non-terminating decimal expansion
~~~

When dividing for a controlled approximation, supply a **scale** or **`MathContext`** matching the output requirements. Do not pick an arbitrarily huge precision "just to be safe" if the pipeline has no reason to use those digits.

## 5. `stripTrailingZeros()`: Reducing Redundant Representation, with Conditions

`stripTrailingZeros()` returns an arithmetically equivalent `BigDecimal` by removing trailing factors of 10 from the unscaled value and adjusting the scale. This is not rounding.

~~~java
BigDecimal original = new BigDecimal("1.2300");
BigDecimal compact = original.stripTrailingZeros();

System.out.println(original.precision()); // 5
System.out.println(original.scale());     // 4
System.out.println(compact.precision());  // 3
System.out.println(compact.scale());      // 2
System.out.println(compact);              // 1.23
~~~

After normalization, subsequent operations can keep shorter representations:

~~~java
BigDecimal rawProduct = original.multiply(new BigDecimal("2.00"));
BigDecimal compactProduct = compact.multiply(new BigDecimal("2"));

System.out.println(rawProduct.toPlainString());     // 2.460000
System.out.println(compactProduct.toPlainString()); // 2.46
~~~

**Do not use this method blindly.** The following differences can matter:

- `new BigDecimal("1.2300").equals(new BigDecimal("1.23"))` is `false` because the scales differ.
- `new BigDecimal("1000").stripTrailingZeros()` typically produces `1E+3` with a **negative scale** (`-3`), not `scale = 0`.
- `new BigDecimal("0.000").stripTrailingZeros()` returns zero with `scale = 0`.
- If business units or schemas require "keeping exactly two decimal places", reducing scale from 2 to 0 may be inappropriate.

Normalization should only be applied when **scale differences carry no meaning**. Although `stripTrailingZeros` can shrink representation size, it has processing cost itself, so do not automatically invoke it after **every operation** without reason or measurement evidence.

## 6. `setScale`: Choosing Scale Deliberately, Avoiding Representation Bloat

`setScale(newScale, roundingMode)` creates a representation at the requested scale. Increasing scale usually appends zeros to the unscaled value without changing arithmetic value. Decreasing scale can drop nonzero digits, requiring a `RoundingMode` or `UNNECESSARY` to demand exactness.

~~~java
BigDecimal number = new BigDecimal("123");

System.out.println(number.setScale(6).toPlainString());
// 123.000000

BigDecimal exact = new BigDecimal("123.4500")
        .setScale(2, RoundingMode.UNNECESSARY);

System.out.println(exact.toPlainString()); // 123.45
~~~

In the first example, six zeros are added to represent 123 exactly at scale 6; if the target format only needs an integer, the added representation is unnecessary. In the second example, reducing scale stays exact because the dropped part consists solely of zeros.

When reducing the scale of `123.456` to 2, you must decide whether rounding is allowed:

~~~java
BigDecimal x = new BigDecimal("123.456");

BigDecimal rounded = x.setScale(2, RoundingMode.HALF_EVEN);
System.out.println(rounded.toPlainString()); // 123.46

// x.setScale(2, RoundingMode.UNNECESSARY)
// -> ArithmeticException because nonzero digits must be dropped
~~~

For currency or measurements, never pick `HALF_EVEN`, `HALF_UP`, or another mode merely to reduce size. The rule, place, and timing of rounding must come from business specifications.

A practical design often stores values at an internal precision sufficient for calculations and applies output formatting/scale **at defined boundaries**, such as posting to a ledger or issuing an invoice. However, in some systems, regulations require rounding **each line item** before summing; rounding once at the end yields a different result. You must follow business boundaries instead of treating "round at the end" as a universal rule.

## 7. `MathContext` Limits Precision When the Problem Permits Rounding

`MathContext` holds precision (desired significant digits) and `RoundingMode`. For example:

~~~java
MathContext mc = new MathContext(8, RoundingMode.HALF_EVEN);

BigDecimal third = BigDecimal.ONE.divide(new BigDecimal("3"), mc);
System.out.println(third.toPlainString()); // 0.33333333
System.out.println(third.precision());     // 8
~~~

You can pass `MathContext` to supporting operations such as `add`, `multiply`, `divide`, or `pow` to cap the **precision of that operation's result**.

Do not confuse them:

| API | What does it limit? | Example |
| --- | --- | --- |
| `setScale(2, HALF_EVEN)` | Two digits after the decimal point | `123.456 → 123.46` |
| `round(new MathContext(4, HALF_EVEN))` | Four significant digits | `123.456 → 123.5` |
| `divide(divisor, 2, HALF_EVEN)` | Quotient scale equal to 2 | `1 / 3 → 0.33` |
| `divide(divisor, new MathContext(8, HALF_EVEN))` | Quotient precision at most 8 | `1 / 3 → 0.33333333` |

In particular, **`MathContext` is not synonymous with an absolute scale bound**:

~~~java
BigDecimal tiny = new BigDecimal("1E-100000");
MathContext mc = new MathContext(8, RoundingMode.HALF_EVEN);

System.out.println(tiny.precision()); // 1
System.out.println(tiny.scale());     // 100000
System.out.println(tiny.round(mc).scale()); // 100000
~~~

Precision is already under 8, so no rounding is needed; scale remains huge. An API accepting external data must check **both precision and scale** if extreme exponents can occur.

### Do not "round to optimize" step-by-step without proving correctness

Rounding at intermediate steps can yield a wrong result compared to performing exact operations and rounding at the required boundary.

Example:

~~~java
BigDecimal first = new BigDecimal("0.125")
        .setScale(2, RoundingMode.HALF_UP);
BigDecimal second = new BigDecimal("0.125")
        .setScale(2, RoundingMode.HALF_UP);

System.out.println(first.add(second)); // 0.26

BigDecimal exactSum = new BigDecimal("0.125")
        .add(new BigDecimal("0.125"));
System.out.println(
        exactSum.setScale(2, RoundingMode.HALF_UP)
); // 0.25
~~~

Both calculations round with `HALF_UP`, yet the **rounding timing** differs. An optimization is valid only if it preserves the agreed-upon semantics.

When multi-step computation with finite precision is needed, design internal precision, guard digits (*guard digits*) if necessary, and verify acceptable error bounds. Do not pass an overly small `MathContext` throughout a pipeline merely because it can shrink object size.

## 8. Standalone Runnable Java 17+ Example

Create the file `BigDecimalPrecisionScaleDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class BigDecimalPrecisionScaleDemo {
    public static void main(String[] args) {
        BigDecimal original = new BigDecimal("1.2300");
        BigDecimal compact = original.stripTrailingZeros();

        System.out.printf(
                "original: %s, precision=%d, scale=%d%n",
                original.toPlainString(),
                original.precision(),
                original.scale()
        );
        System.out.printf(
                "compact: %s, precision=%d, scale=%d%n",
                compact.toPlainString(),
                compact.precision(),
                compact.scale()
        );

        BigDecimal rawProduct = original.multiply(new BigDecimal("2.00"));
        BigDecimal compactProduct = compact.multiply(new BigDecimal("2"));
        System.out.printf(
                "raw product: %s, precision=%d, scale=%d%n",
                rawProduct.toPlainString(),
                rawProduct.precision(),
                rawProduct.scale()
        );
        System.out.printf(
                "compact product: %s, precision=%d, scale=%d%n",
                compactProduct.toPlainString(),
                compactProduct.precision(),
                compactProduct.scale()
        );

        BigDecimal grown = BigDecimal.ONE;
        BigDecimal factor = new BigDecimal("1.000000");
        for (int i = 0; i < 5; i++) {
            grown = grown.multiply(factor);
        }
        System.out.printf(
                "repeated multiply: precision=%d, scale=%d%n",
                grown.precision(),
                grown.scale()
        );

        MathContext mc = new MathContext(8, RoundingMode.HALF_EVEN);
        BigDecimal third = BigDecimal.ONE.divide(new BigDecimal("3"), mc);
        System.out.println("third: " + third.toPlainString());

        BigDecimal exactScale = new BigDecimal("123.4500")
                .setScale(2, RoundingMode.UNNECESSARY);
        System.out.println("exact scale reduction: "
                + exactScale.toPlainString());

        BigDecimal exponent = new BigDecimal("1E+3");
        System.out.println("exponent scale: " + exponent.scale());
        System.out.println("exponent plain: " + exponent.toPlainString());
    }
}
~~~

Command to run in the file's directory:

~~~bash
javac BigDecimalPrecisionScaleDemo.java
java BigDecimalPrecisionScaleDemo
~~~

Exact stdout:

~~~text
original: 1.2300, precision=5, scale=4
compact: 1.23, precision=3, scale=2
raw product: 2.460000, precision=7, scale=6
compact product: 2.46, precision=3, scale=2
repeated multiply: precision=31, scale=30
third: 0.33333333
exact scale reduction: 123.45
exponent scale: -3
exponent plain: 1000
~~~

What can be concluded from the program is that **representations genuinely differ** and scale/precision grow according to the demonstrated operations. This program does not measure time, allocation counts, or throughput, so **it is not a performance benchmark** and does not prove any specific speedup from normalization.

Note the negative scale in the last line: `1E+3` has precision 1, scale -3, and `toPlainString()` displays `1000`. If you recreate it from that plain string with `new BigDecimal("1000")`, the new object has scale 0. This matters if you want both optimization and representation round-tripping.

## 9. Resource Bounds When Accepting External Decimals

A service can receive overly long values or extreme exponents. Even though parsing and storing a number like `1E-100000` can be quite compact since its unscaled value is 1, calling `toPlainString()` will have to build a string consisting of vast numbers of `0` characters.

Example **not to run with untrusted exponents**:

~~~java
BigDecimal externallySupplied = new BigDecimal("1E-100000");
// Plain string will be very long even though precision is only 1.
String huge = externallySupplied.toPlainString();
~~~

Boundary design:

1. Limit input string length before parsing, and disallow formats outside the schema.
2. Parse directly from `String` into `BigDecimal`, without going through `double`.
3. Check `precision()`, `scale()`, and value range per the contract; convert to `long` when needed to safely take the absolute scale, avoiding `Math.abs(Integer.MIN_VALUE)` remaining negative.
4. Do not generate plain strings, force huge scales, repeat multiplications excessively, or persist to the database before checking bounds.
5. When outputting JSON, know clearly whether the consumer expects a decimal string or a numeric token, whether exponential notation is accepted, and whether scale must be preserved.

Illustrative validation method example:

~~~java
static BigDecimal parseBounded(String raw) {
    if (raw == null || raw.length() > 128) {
        throw new IllegalArgumentException("Decimal input too long");
    }

    final BigDecimal parsed;
    try {
        parsed = new BigDecimal(raw);
    } catch (NumberFormatException ex) {
        throw new IllegalArgumentException("Invalid decimal", ex);
    }

    if (parsed.precision() > 40
            || Math.abs((long) parsed.scale()) > 12) {
        throw new IllegalArgumentException("Decimal outside limits");
    }
    return parsed;
}
~~~

This is an **illustrative method** to place inside a Java class, not a complete application. The limits 128/40/12 are merely examples; the business schema must decide them. For gigantic exponents, parsing can also throw `NumberFormatException` because scale exceeds the `int` range, so handle errors appropriately.

A `precision <= 40` limit does not replace a scale limit, and a scale limit does not replace an **arithmetic value limit**. The number `999999999999` may exceed the business range even though both precision and scale are within bounds.

## 10. Storing and Transmitting Data at the Right Precision

### Database `DECIMAL(p,s)` or `NUMERIC(p,s)`

Database schemas usually specify significant digit width and scale. If a column requires `DECIMAL(18,2)`, there is no general reason to routinely expand values to 100 decimal places before writing. Nor should you round automatically just to fit the column without a policy.

Example:

~~~java
BigDecimal amount = new BigDecimal("19.9900");
BigDecimal valueForColumn =
        amount.setScale(2, RoundingMode.UNNECESSARY);
System.out.println(valueForColumn.toPlainString()); // 19.99
~~~

`UNNECESSARY` succeeds because only redundant zeros are dropped. For `19.995`, it throws `ArithmeticException`; you must decide whether rounding is permitted and which mode to use. Do not call `setScale(2)` by default when rounding may be needed without specifying the mode explicitly.

When using JDBC, pass via `PreparedStatement.setBigDecimal` and read via `ResultSet.getBigDecimal`; avoid converting through an intermediate `Double`. Drivers/databases may enforce rules on precision/scale, so test round-trips against the real schema.

### JSON and JavaScript clients

An API exchanging large or high-precision decimals with JavaScript can typically choose a **JSON string** representation:

~~~json
{
  "amount": "9007199254740993.01"
}
~~~

If a JSON number is used and a client calls standard `JSON.parse`, the value can be converted to binary64 and lose exactness. Strings preserve the characters and let consumers pick an appropriate decimal library. When preserving **scale**, decide whether to use `BigDecimal.toString()` (which round-trips scale) or a wire format containing `unscaledValue + scale`. `toPlainString()` can lose negative scale upon re-parsing; do not blindly convert every value to a plain string if representation constraints matter.

### Logging and display

There is usually no need to display every digit a `BigDecimal` holds if the UI has its own digit-count contract. Apply formatting at the UI or presenter layer according to policy, without mutating source data just for prettier logs. Avoid logging plain strings for values with huge scales when inputs are unbounded; scientific notation may be more suitable if readers support it.

## 11. Choosing an Optimization Strategy by Problem

| Problem | Approach | Constraints |
| --- | --- | --- |
| Repeated multiplications inflating scale | Consider stripping redundant zeros on inputs or checkpoints with `stripTrailingZeros()` | Only when original scale does not need to be kept |
| Result needs exactly two decimal places | Use `setScale(2, mode)` at business boundaries | Mode and timing must be specified |
| Non-terminating division | Specify sufficient scale or `MathContext` | May alter result due to rounding |
| Payload with untrusted exponent | Bound text length, precision, and scale before memory-heavy conversions | Prevent resource exhaustion |
| Financial data requiring exact decimals | Keep `BigDecimal` and decimal string / standard decimal types | Do not convert through `double` |
| Scientific calculation allowing bounded error | Choose precision per analyzed error budget | Do not truncate precision arbitrarily |
| Results compared by arithmetic value | `compareTo`, optionally normalized if contract allows | `equals` and hash remain scale-sensitive |
| Representation/scale must be preserved over the wire | Use `toString()` or unscaled/scale pair | Do not strip trailing zeros arbitrarily |

There is no single "fastest" `MathContext` configuration or `stripTrailingZeros` call for every application. Decisions require examining **actual magnitudes, operation counts, scale semantics, serialization frequency, storage costs, and permissible error**.

## 12. Measuring Performance Without Drawing False Conclusions

A single test using `System.nanoTime()` is often distorted by JIT compilation, warmup, garbage collection, and JVM optimizations. For a meaningful optimization, use a proper microbenchmark framework such as **JMH**, measure on realistic data, and ensure results are not eliminated by optimizations.

Test groups can be designed around:

- **Low scale vs. high scale**: identical mathematical value but differing trailing-zero counts.
- **Repeated multiplication**: keeping exact scale versus a pipeline permitted to normalize.
- **Serialization**: `toString()` vs. `toPlainString()` across differing exponents.
- **Precision bounds**: exact business precision versus much higher precision.
- **Allocation and GC**: object counts, allocated bytes, and latency, in addition to throughput.

A benchmark must confirm that both sides perform **the same business task**. For example, comparing an exact calculation with a precision-truncated calculation is not a fair comparison if the output requires exactness. Do not treat shrinking digit counts as a win when the result is wrong.

## 13. Common Mistakes

1. **Confusing scale with precision:** `1E-100000` has precision 1, scale 100000; checking only one does not fully protect you.
2. **Increasing `setScale` "to be safe" at every step:** may just pad zeros, growing representation size without adding information.
3. **Relying solely on `MathContext` to guard scale:** a value with small precision can still have a gigantic scale.
4. **Calling `stripTrailingZeros` when scale must be preserved:** the result can differ in `equals` and even have a negative scale.
5. **Rounding intermediates too early:** multiple roundings can change the final total; design clear boundaries.
6. **Converting via `double` to "speed up" money:** can lose exactness, which cannot be recovered when converting back to `BigDecimal`.
7. **Calling `toPlainString` on untrusted huge exponents:** can generate enormous strings and cause memory pressure.
8. **Benchmarking without warmup or result correctness checks:** environmental noise or skipped work can produce false conclusions.

## 14. Self-Check

Consider the code snippet:

~~~java
BigDecimal a = new BigDecimal("2.5000");
BigDecimal b = new BigDecimal("3.00");
BigDecimal c = a.multiply(b);
BigDecimal d = a.stripTrailingZeros()
        .multiply(b.stripTrailingZeros());
~~~

Answer before running:

1. What are `a.precision()` and `a.scale()`?
2. What does `c` print via `toPlainString()`? What are `c`'s precision and scale?
3. What does `d` print via `toPlainString()`? What are `d`'s precision and scale?
4. What do `c.compareTo(d)` and `c.equals(d)` return?
5. Why does using `new MathContext(4, RoundingMode.HALF_EVEN)` **not** replace scale checks on all inputs?
6. If `"2.5000"` must be stored accurately with scale 4, should it be replaced with `stripTrailingZeros()`?

**Answers:**

1. `a` has unscaled value `25000`, precision 5, and scale 4.
2. `c` is `7.500000`, precision 7, scale 6 (4 + 2).
3. `d` is `7.5`, precision 2, scale 1.
4. `compareTo` returns `0` because the arithmetic values are equal; `equals` returns `false` because the scales differ.
5. `MathContext` limits **the number of significant digits** of an operation's result, yet a number like `1E-100000` still has small precision and an enormous scale.
6. No, if the original scale is part of the exchange or storage requirement.

Remember: optimizing decimal numbers requires defining **what precision must be kept, what scale means, and when rounding is allowed**. Reducing redundant representation can help, yet correctness, data contracts, and real measurements always come before every optimization.
