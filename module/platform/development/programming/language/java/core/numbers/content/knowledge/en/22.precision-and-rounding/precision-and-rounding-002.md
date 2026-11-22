# UNLIMITED, DECIMAL32, DECIMAL64, and DECIMAL128 in Java

## 1. The Problem to Solve

When computing with `BigDecimal`, results can require very many digits. The division `1 / 3` has infinitely many decimal digits; even multiplying two finite decimal numbers can produce a result longer than the needed precision level. `MathContext` in the `java.math` package lets you specify **result precision (precision)** and **rounding rule (rounding mode)** per operation.

Java provides four commonly used `MathContext` constants:

- `MathContext.UNLIMITED`: exact calculation, does not actively round due to a digit limit.
- `MathContext.DECIMAL32`: at most 7 significant digits, `HALF_EVEN` rounding.
- `MathContext.DECIMAL64`: at most 16 significant digits, `HALF_EVEN` rounding.
- `MathContext.DECIMAL128`: at most 34 significant digits, `HALF_EVEN` rounding.

The names `DECIMAL32`/`DECIMAL64`/`DECIMAL128` allude to the precision of the IEEE 754 decimal number formats. In Java, they are **calculation configurations for `BigDecimal`**, not 32/64/128-bit data types, and they do not enforce all exponent limits, representations, or storage constraints of the corresponding IEEE 754 formats.

## 2. Distinguishing precision, scale, and MathContext

A `BigDecimal` consists of an unscaled integer value (`unscaledValue`) and a `scale`; the mathematical value is `unscaledValue × 10^(-scale)`.

- **Precision**: the number of significant digits in the decimal representation of a `BigDecimal`. For example, `123.4500` has precision 7 because both trailing `0` digits are retained in the representation.
- **Scale**: the number of digits to the right of the decimal point under conventional storage; `123.4500` has scale 4. Scale can be negative; for example, `1.23E+4` has scale -2.
- **MathContext precision**: the limit on significant digits of **the result when an operation is invoked with that context**. Not synonymous with the number of digits after the decimal point.
- **Rounding mode**: determines what to do with discarded digits when a result exceeds precision.

For example: `12345.6789` has 9 significant digits. Rounding with `DECIMAL32` (7 digits) produces `12345.68`: keeping a total of 7 significant digits, not keeping 7 digits after the decimal point. For `0.000123456789`, the leading `0` digits do not increase the number of significant digits.

`MathContext` is an immutable object. Simply declaring a context **does not automatically alter** existing `BigDecimal` instances, and Java has no global default MathContext applied to all operations. You must pass the context to an operation, call `round(context)`, or use a constructor that accepts a context.

## 3. Comparison Table of the Four Built-in Constants

| MathContext | `getPrecision()` | `getRoundingMode()` | Meaning |
| --- | ---: | --- | --- |
| `UNLIMITED` | 0 | `HALF_UP` | Precision 0 means **unlimited number of digits**, not keeping only 0 digits. The `HALF_UP` mode is stored in the object but is not used for precision rounding when the limit is 0. |
| `DECIMAL32` | 7 | `HALF_EVEN` | Keeps at most 7 significant digits of the result. |
| `DECIMAL64` | 16 | `HALF_EVEN` | Keeps at most 16 significant digits of the result. |
| `DECIMAL128` | 34 | `HALF_EVEN` | Keeps at most 34 significant digits of the result. |

In terms of configuration, the four constants correspond to:

~~~java
MathContext.UNLIMITED;  // new MathContext(0, RoundingMode.HALF_UP)
MathContext.DECIMAL32;  // new MathContext(7, RoundingMode.HALF_EVEN)
MathContext.DECIMAL64;  // new MathContext(16, RoundingMode.HALF_EVEN)
MathContext.DECIMAL128; // new MathContext(34, RoundingMode.HALF_EVEN)
~~~

These are prebuilt values for reuse; the comments explain the equivalent configurations, not constant reassignments. `new MathContext(7)` defaults to `HALF_UP`, **differing** from `DECIMAL32` in its rounding rule. Similarly, `new MathContext(16)` and `new MathContext(34)` do not default to `HALF_EVEN`.

## 4. Exactness and Controlled Rounding

### 4.1. UNLIMITED Does Not Mean Every Division Returns a Value

For addition, subtraction, and multiplication of finite `BigDecimal` numbers, Java can return an exact decimal result. Division only has a finite decimal result when the reduced fraction has a denominator whose prime factors **consist only of 2 and/or 5**. For example:

- `1 / 8 = 0.125`: finite decimal representation, `divide(8, UNLIMITED)` succeeds.
- `1 / 40 = 0.025`: also finite.
- `1 / 3 = 0.3333…`: infinite repeating decimal, cannot be represented exactly by a finite `BigDecimal`. Calling `divide(3, UNLIMITED)` throws `ArithmeticException`.
- `1 / 7` also has no finite decimal representation.

`UNLIMITED` does not automatically pick a digit count or rounding when encountering a non-terminating division. To get a bounded approximate value, pass a context with positive precision such as `DECIMAL64` or choose `scale` and `RoundingMode` using the appropriate overload of `divide`. Operations like `sqrt` with an unlimited context also require an exact representable result; an inexact root like `sqrt(2)` cannot be returned in exact finite form.

### 4.2. The Three DECIMAL Contexts Round to Significant Digits

For `1 / 3`:

| Context | Result of `BigDecimal.ONE.divide(new BigDecimal("3"), context)` |
| --- | --- |
| `UNLIMITED` | Throws `ArithmeticException` |
| `DECIMAL32` | `0.3333333` (7 digits of 3) |
| `DECIMAL64` | `0.3333333333333333` (16 digits of 3) |
| `DECIMAL128` | `0.3333333333333333333333333333333333` (34 digits of 3) |

When rounding `123456789.987654321`, `DECIMAL32` gives `1.234568E+8`, `DECIMAL64` gives `123456789.9876543`, and `DECIMAL128` keeps `123456789.987654321` unchanged. The `E+8` notation is the scientific display form of `BigDecimal.toString()`; the corresponding value is `123456800`.

### 4.3. What Is HALF_EVEN?

`RoundingMode.HALF_EVEN` is commonly called *banker's rounding*: if the discarded fraction is **exactly half a unit at the rounding position**, choose the last retained digit that is **even**. If it is greater than half, round away from 0; if smaller, keep closer to 0 (explained for positive numbers; the rounding mode is defined for negative numbers as well).

Examples when keeping only **1 significant digit**:

- `2.5 → 2`, because the retained digit is 2 (even).
- `3.5 → 4`, because 3 must be increased to 4 (even).
- `2.51 → 3`: the discarded fraction is strictly greater than half, so the tie-to-even rule does not apply.

`HALF_EVEN` is useful when many values are frequently rounded because it avoids one-sided bias in exact-half cases. However, business rules may mandate `HALF_UP`, `DOWN`, or `UNNECESSARY`; do not change the rule on your own just because a preset name sounds fitting.

## 5. Complete Java Example (Java 17+)

Create the file `MathContextPresetsDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class MathContextPresetsDemo {
    public static void main(String[] args) {
        BigDecimal one = new BigDecimal("1");
        BigDecimal three = new BigDecimal("3");

        System.out.println("UNLIMITED 1/8: " +
                one.divide(new BigDecimal("8"), MathContext.UNLIMITED));
        try {
            System.out.println("UNLIMITED 1/3: " +
                    one.divide(three, MathContext.UNLIMITED));
        } catch (ArithmeticException e) {
            System.out.println("UNLIMITED 1/3: ArithmeticException");
        }

        System.out.println("DECIMAL32 1/3: " +
                one.divide(three, MathContext.DECIMAL32));
        System.out.println("DECIMAL64 1/3: " +
                one.divide(three, MathContext.DECIMAL64));
        System.out.println("DECIMAL128 1/3: " +
                one.divide(three, MathContext.DECIMAL128));

        BigDecimal value = new BigDecimal("123456789.987654321");
        System.out.println("DECIMAL32 round: " + value.round(MathContext.DECIMAL32));
        System.out.println("DECIMAL64 round: " + value.round(MathContext.DECIMAL64));
        System.out.println("DECIMAL128 round: " + value.round(MathContext.DECIMAL128));

        BigDecimal a = new BigDecimal("1.234567");
        BigDecimal b = new BigDecimal("0.0000009");
        System.out.println("sum exact: " + a.add(b));
        System.out.println("sum DECIMAL32: " + a.add(b, MathContext.DECIMAL32));

        MathContext oneDigit = new MathContext(1, RoundingMode.HALF_EVEN);
        System.out.println("HALF_EVEN 2.5: " +
                new BigDecimal("2.5").round(oneDigit));
        System.out.println("HALF_EVEN 3.5: " +
                new BigDecimal("3.5").round(oneDigit));
        System.out.println("setScale(2): " +
                new BigDecimal("1.234567").setScale(2, RoundingMode.HALF_EVEN));
    }
}
~~~

Compile and run:

~~~bash
javac MathContextPresetsDemo.java
java MathContextPresetsDemo
~~~

Standard output:

~~~text
UNLIMITED 1/8: 0.125
UNLIMITED 1/3: ArithmeticException
DECIMAL32 1/3: 0.3333333
DECIMAL64 1/3: 0.3333333333333333
DECIMAL128 1/3: 0.3333333333333333333333333333333333
DECIMAL32 round: 1.234568E+8
DECIMAL64 round: 123456789.9876543
DECIMAL128 round: 123456789.987654321
sum exact: 1.2345679
sum DECIMAL32: 1.234568
HALF_EVEN 2.5: 2
HALF_EVEN 3.5: 4
setScale(2): 1.23
~~~

The `try/catch` block only catches the division that cannot be represented exactly with `UNLIMITED`. The `round` calls affect the **returned result**; the original `value` object still keeps all its digits because `BigDecimal` is immutable. The sum example shows that `add(b)` returns the exact value while `add(b, DECIMAL32)` returns the sum limited to 7 significant digits.

## 6. Using Context Properly in Real Programs

### 6.1. How to Pass MathContext

Common APIs accepting a `MathContext` parameter include `add`, `subtract`, `multiply`, `divide`, `pow`, and `sqrt` (if supported by the Java version), as well as `round` and certain constructors of `BigDecimal`:

~~~java
MathContext mc = MathContext.DECIMAL64;
BigDecimal x = new BigDecimal("19.876543210987654321");
BigDecimal y = new BigDecimal("3");

BigDecimal sum = x.add(y, mc);       // round sum according to mc
BigDecimal product = x.multiply(y, mc); // round product according to mc
BigDecimal quotient = x.divide(y, mc); // round quotient according to mc
BigDecimal rounded = x.round(mc);    // round x itself, without modifying x
BigDecimal roundedOnInput = new BigDecimal("19.876543210987654321", mc);
~~~

This is an **illustrative code snippet** inside a method/block that has `java.math.*` imported, not a standalone `main` program.

Be careful with when rounding happens. `x.multiply(y, mc).add(z, mc)` can differ from `x.multiply(y).add(z).round(mc)` because the first expression rounds at each step. Intermediate rounding error can accumulate; you need to decide based on the algorithm's requirements, even with precision 34.

### 6.2. When to Choose Which Constant?

| Scenario | Choice | Reason/Warning |
| --- | --- | --- |
| Addition, subtraction, multiplication needing exact decimal results | Do not pass context or use `UNLIMITED` | Does not actively round; still need to consider performance/memory if numbers grow too large. |
| Division potentially infinite repeating | `DECIMAL32`/`64`/`128` or custom context | Positive precision allows division to return a rounded result. |
| Problem requires about 7 significant digits | `DECIMAL32` | Fewer digits, but unsuitable when more detail is needed. |
| Need about 16 significant digits | `DECIMAL64` | Suitable if both the significant digit count and `HALF_EVEN` are acceptable. |
| Need about 34 significant digits | `DECIMAL128` | Provides higher precision; does not mean every calculation is strictly exact. |
| Finance requiring 2 decimal places | `setScale(2, roundingMode)` per business rule | Two digits **after the decimal point** is not 2 **significant** digits; `DECIMAL32` does not substitute for scale. |
| Need a different rule or fixed precision | `new MathContext(n, mode)` | For example `new MathContext(20, RoundingMode.HALF_UP)`. |
| Cannot tolerate losing any digit | Context with `RoundingMode.UNNECESSARY` | Throws `ArithmeticException` if operation requires rounding; does not round silently. |

For example, wanting a quotient with **exactly two digits after the decimal point**:

~~~java
BigDecimal price = new BigDecimal("10");
BigDecimal count = new BigDecimal("3");
BigDecimal amount = price.divide(count, 2, RoundingMode.HALF_UP);
// amount.toPlainString() is "3.33"
~~~

Conversely, `price.divide(count, MathContext.DECIMAL32)` gives `3.333333` (7 significant digits), failing the two-decimal-place requirement.

### 6.3. Coordinating Precision and Scale

A calculation may limit significant digits in intermediate steps using `MathContext`, then normalize the number of decimal places using `setScale` at the output boundary. When doing so, **rounding twice can cause double rounding bias** compared to computing exact values and rounding once at the end. If business logic requires exactness up to the settlement point, keep operations exact where possible, round according to the designed rule at the appropriate boundary, and add tests for exact-half cases.

`setScale(2, mode)` enforces scale 2, **not** a cap on total significant digits: `123456.78` still has 8 significant digits. Meanwhile, `round(DECIMAL32)` may produce a negative scale or scientific notation if the integer part is large.

## 7. Common Mistakes

1. **Understanding `UNLIMITED` as "can divide any numbers".** It requires an exact result and throws an exception for repeating quotients like `1/3`. You must supply a precision or scale limit when approximations are acceptable.
2. **Confusing precision with scale.** `DECIMAL64` limits **16 significant digits**, not 16 digits after the decimal point.
3. **Assuming presets always use `HALF_UP`.** The three DECIMAL presets use `HALF_EVEN`; only `UNLIMITED` holds the `HALF_UP` setting and does not use it for precision-based rounding.
4. **Using `new MathContext(7)` instead of `DECIMAL32` without considering the mode.** The single-argument constructor uses `HALF_UP`, so at exact-half ties the results can differ.
5. **Assuming DECIMAL128 equals a full IEEE decimal128 type.** Java's `BigDecimal` does not automatically enforce the exponent limits or encoding format of decimal128 just because this context is passed.
6. **Using `new BigDecimal(0.1)` and trusting a context to fix input error.** The `double` literal `0.1` already lacks an exact decimal representation; the `double` constructor preserves the converted binary value. Use `new BigDecimal("0.1")` or consider `BigDecimal.valueOf(0.1)` for the expected decimal representation.
7. **Rounding too early across multiple steps.** Intermediate results losing digits can affect the final result; the context does not guarantee that digits after rounding steps still reflect the original exact operation.
8. **Comparing results by string or `equals` arbitrarily.** `new BigDecimal("1.0").equals(new BigDecimal("1.00"))` is `false` due to differing scales, whereas `compareTo(...) == 0` when numeric values are equal. A context can change scale and `toString()` format; evaluating by value or representation must match the intent.
9. **Using high precision instead of error checking.** A result with 34 digits is still approximate if a division or intermediate step had to round; appropriate error tolerances/tests must be designed.

## 8. Self-Check Questions

**1. Why is `MathContext.UNLIMITED.getPrecision() == 0`, yet `1/3` causes an exception?** Because precision 0 indicates unlimited, forcing the division to have an exact result representable as a finite decimal. `1/3` does not satisfy that.

**2. To round the monetary amount `123.456` to two digits after the decimal point, should `DECIMAL32` be used?** No. `DECIMAL32` keeps at most 7 significant digits, so in this case it may not round at all; `setScale(2, mode)` should be used according to currency rules.

**3. Does `DECIMAL64` always give a more accurate result than `DECIMAL32`?** It retains more significant digits in the same kind of operation, but that does not automatically guarantee exact inputs, correct intermediate rounding, or a numerically stable algorithm.

**4. When should a custom context be chosen?** When a precision or rounding mode different from the presets is required; for example `new MathContext(12, RoundingMode.HALF_UP)` or using `UNNECESSARY` to detect situations where rounding is needed.

**Takeaway:** Choose `MathContext` based on the **number of significant digits** and **rounding rule** of the operation; choose `setScale` based on the **number of decimal places** needed for presentation/storage. `UNLIMITED` means computing exact results when representable, whereas the three `DECIMALxx` presets accept rounding with `HALF_EVEN`.
