# Exact `BigDecimal.divide` and Non-Terminating Repeating Decimals in Java

## 1. Goals and Key Phenomenon

**java.math.BigDecimal** stores a decimal value using an integer **unscaled value** and a **scale**. With addition, subtraction, and multiplication without a MathContext, we can obtain an **exact** decimal result within resource limits. However, **division** has a mathematical obstacle: the quotient of two terminating decimals can have **infinitely many repeating decimal digits**.

Examples:

- **1/8 = 0.125**: finite representation; BigDecimal can return it exactly.
- **1/3 = 0.333333…**: non-terminating repeating decimal; cannot be stored as a finite BigDecimal while keeping the exact value 1/3.
- **1/6 = 0.166666…**: non-terminating repeating decimal, even though 6 contains a factor of 2.
- **3/6 = 1/2 = 0.5**: the fraction must be **reduced** before concluding whether it has a non-terminating decimal.

In Java:

~~~java
import java.math.BigDecimal;

BigDecimal exact = BigDecimal.ONE.divide(new BigDecimal("8"));
// exact = 0.125

// The statement below throws ArithmeticException at runtime:
// BigDecimal recurring = BigDecimal.ONE.divide(new BigDecimal("3"));
~~~

This behavior is **according to the API contract**. BigDecimal does not try to guess how many digits the user wants to keep, nor does it silently convert a non-terminating result into an approximation when calling the exact division overload.

This lesson explains **when exact division succeeds**, the mechanism behind infinite repetition, how to choose among **divide** overloads, the meaning of **scale**, **precision**, **MathContext**, **RoundingMode**, exceptions, and how to verify them with Java 17+.

## 2. Reviewing the BigDecimal Model

The value of a BigDecimal can be written as:

\[
x = u \times 10^{-s}
\]

Where **u** is the unscaled integer (BigInteger) and **s** is the scale (int). For example:

~~~java
BigDecimal n = new BigDecimal("10.00");

System.out.println(n.unscaledValue()); // 1000
System.out.println(n.scale());         // 2
~~~

We have **1000 × 10^−2 = 10.00**.

BigDecimal is **immutable**: the divide method returns a new BigDecimal without modifying the original operands. A result may have a **different scale** compared to the result of another overload even with the same numeric value.

~~~java
BigDecimal a = new BigDecimal("10.00");
BigDecimal b = new BigDecimal("4");
BigDecimal q = a.divide(b);

System.out.println(q); // 2.50
System.out.println(a); // 10.00
~~~

Do not confuse **numeric value**, **scale**, and **precision**:

- **Numeric value**: 2.5.
- **Scale** in the example: 2, so the string representation is 2.50.
- **Precision** of 2.50: 3 significant digits.

A BigDecimal value with a negative scale is still valid; it may be displayed in scientific notation such as **1E+3**. This also affects how the scale of a division result is determined.

## 3. What Is Exact Division?

**Exact division** means the returned value must equal the **exact mathematical quotient** of the two inputs, **without discarding significant digits** through rounding.

~~~java
BigDecimal one = BigDecimal.ONE;
BigDecimal eight = new BigDecimal("8");

BigDecimal quotient = one.divide(eight); // 0.125
~~~

Because 0.125 terminates after three decimal digits, a finite BigDecimal can represent it exactly.

For a number like **1/3**, there is no finite number of decimal digits that represents the quotient exactly. Even if 10, 100, or a million digits are allowed, every finite representation of the form 0.333… differs from 1/3 by a small amount.

Therefore:

~~~java
BigDecimal one = BigDecimal.ONE;
BigDecimal three = new BigDecimal("3");

// one.divide(three) -> ArithmeticException
~~~

Do not interpret the exception as **64-bit numeric type overflow** or a default precision that is too low. It is a request for an **exact result that does not exist as a terminating decimal**.

### Two Types of ArithmeticException to Distinguish

BigDecimal division can throw ArithmeticException when:

1. **Divisor is 0**: e.g., 1/0; the operation is undefined and BigDecimal does not return infinity/NaN.
2. **Non-terminating decimal quotient when exact is required**: e.g., 1/3 with divide(divisor) or precision=0.

Some overloads also throw an exception when **RoundingMode.UNNECESSARY** requires that the result not be rounded, yet the specified scale/precision is insufficient.

Therefore, catching ArithmeticException and always printing “repeating infinite decimal” is wrong: the cause could be division by zero or prohibited rounding.

## 4. Mathematical Condition: Reduced Denominator Has Only Factors 2 and 5

Consider a rational fraction **a/b**, with b ≠ 0. Reduce it to **p/q**, such that q > 0 and gcd(|p|, q) = 1.

The fraction has a **terminating** decimal representation if and only if q has the form:

\[
q = 2^m5^n,\qquad m,n \ge 0
\]

That is, **the reduced denominator has no prime factors other than 2 and 5**.

Reason: a terminating decimal with d digits after the decimal point has denominator **10^d = 2^d × 5^d**. After reduction, every prime factor of the denominator must come from 2 and 5. Conversely, if q consists only of 2 and 5, you can multiply numerator and denominator to turn the denominator into a power of 10.

| Fraction | Reduced form | Denominator factorization | Decimal form |
| --- | --- | --- | --- |
| 1/2 | 1/2 | 2 | 0.5 — terminating |
| 1/8 | 1/8 | 2³ | 0.125 — terminating |
| 1/40 | 1/40 | 2³ × 5 | 0.025 — terminating |
| 3/6 | 1/2 | 2 | 0.5 — terminating |
| 1/3 | 1/3 | 3 | 0.(3) — repeating |
| 1/6 | 1/6 | 2 × 3 | 0.1(6) — repeating |
| 1/7 | 1/7 | 7 | 0.(142857) — repeating |
| 22/7 | 22/7 | 7 | 3.(142857) — repeating |

The notation **0.(3)** means the digit 3 repeats forever; **0.1(6)** is 0.16666… and **0.(142857)** has a six-digit repeating cycle.

**Important:** examine the **reduced denominator**, not the initial denominator. The case **3/6** has an initial denominator containing factor 3, but after reduction the denominator is 2, so exact division succeeds completely.

### Extending to Any Two BigDecimals with Arbitrary Scales

Given:

\[
x=u_x \times 10^{-s_x}, \qquad y=u_y \times 10^{-s_y}
\]

then:

\[
\frac{x}{y} = \frac{u_x}{u_y} \times 10^{s_y-s_x}
\]

Multiplying by a power of 10 (which only carries factors of 2 and 5) **cannot eliminate prime factors other than 2/5 in the reduced denominator**. Thus checking the denominator of the ratio of the two **unscaled integers** also tells whether the quotient has a terminating decimal expansion, provided the divisor is nonzero.

This is a useful mathematical property for explanation, though you do not always need to implement the check manually: if you only want the exact quotient, just call **divide(divisor)** and handle error conditions per contract.

## 5. divide Signatures and How to Choose an Overload

Common BigDecimal overloads in Java 17:

| Call form | Desired result | Notes |
| --- | --- | --- |
| **a.divide(b)** | Exact quotient, if finitely representable | Throws ArithmeticException on non-terminating decimal quotients |
| **a.divide(b, scale, mode)** | Quotient with **specified scale** | Rounds according to mode if needed |
| **a.divide(b, mode)** | Quotient with **scale equal to a.scale()** | Easy to round unintentionally if a.scale() is small |
| **a.divide(b, mc)** | Quotient rounded by **precision and mode** in MathContext | precision=0 requires exact |
| **a.divide(b, scale, intMode)** | Overload using legacy integer rounding constant | Deprecated; use enum RoundingMode |

No single overload is best for every problem. Choose according to the **result requirement**:

- If **exact** is required and only terminating decimals are accepted: **divide(b)**.
- If **exactly N digits after the decimal point** are needed: **divide(b, scale, roundingMode)**.
- If **N significant digits** across orders of magnitude are needed: **divide(b, MathContext)**.
- If the application wants the result's scale to match the dividend itself: **divide(b, roundingMode)**, though you must understand this is a very specific policy.

**RoundingMode** is an enum in **java.math**; use **RoundingMode.HALF_UP**, **HALF_EVEN**, **DOWN**, **UNNECESSARY**, etc. instead of the deprecated BigDecimal.ROUND_* constants.

## 6. divide(BigDecimal) — Choose When Exactness Is Required

Finite division example:

~~~java
BigDecimal one = BigDecimal.ONE;
BigDecimal eight = new BigDecimal("8");
BigDecimal forty = new BigDecimal("40");

System.out.println(one.divide(eight)); // 0.125
System.out.println(one.divide(forty)); // 0.025
~~~

Non-terminating repeating division example:

~~~java
BigDecimal one = BigDecimal.ONE;
BigDecimal three = new BigDecimal("3");

try {
    System.out.println(one.divide(three));
} catch (ArithmeticException e) {
    System.out.println("Exact decimal quotient is unavailable");
}
~~~

**Do not write exception-handling code like the above to silently continue with an approximate number** when the system truly requires an exact fraction. When a problem must store the quotient 1/3 without rounding, a **fraction representation** (reduced BigInteger numerator and denominator) is needed, since BigDecimal cannot store an entire infinite expansion.

### Preferred Scale of Exact Division

In the BigDecimal specification, the **preferred scale of division** is:

\[
s_{\text{preferred}} = s_{\text{dividend}} - s_{\text{divisor}}
\]

However, the **actual scale may be larger** if additional digits are needed to represent the exact quotient.

For example:

~~~java
BigDecimal q = new BigDecimal("10.00")
        .divide(new BigDecimal("4"));

System.out.println(q);         // 2.50
System.out.println(q.scale()); // 2
~~~

The dividend 10.00 has scale 2; the divisor 4 has scale 0; preferred scale=2 and quotient 2.50 fits nicely. For **1/8**, preferred scale is 0, but representing 0.125 exactly requires increasing to scale 3.

Do not infer that **exact divide always strips all trailing zeros** or always returns the exact scale of the dividend: the preferred scale and exact representation rules govern this.

## 7. divide(divisor, scale, RoundingMode) — Digits After the Decimal Point

Example of rounding a non-terminating quotient:

~~~java
import java.math.RoundingMode;

BigDecimal one = BigDecimal.ONE;
BigDecimal three = new BigDecimal("3");

BigDecimal rounded = one.divide(three, 4, RoundingMode.HALF_UP);
// 0.3333
~~~

This overload produces a result with **scale=4**, meaning 4 positions after the decimal point under the usual interpretation of positive scale. With two digits:

~~~java
BigDecimal two = new BigDecimal("2");
BigDecimal result = two.divide(three, 2, RoundingMode.HALF_UP);
// 0.67
~~~

**Scale is not precision.** Dividing 12345/3 at scale=2 produces a number with two fractional digits (e.g., 4115.00), whereas dividing with MathContext precision=3 yields three significant digits near 4.12E+3.

### Do Not Pick Digit Counts by Habit

If the output is currency and needs 2 digits after the decimal point, scale=2 may be appropriate, **after** defining billing rules and rounding timing. However, if the output is a scientific measurement ratio varying from 10^−12 to 10^12, scale=2 is usually unsuitable. Policy must be chosen before calling the API.

## 8. divide(divisor, RoundingMode) — The Hidden Scale Trap

There is an overload without a scale parameter:

~~~java
BigDecimal result = BigDecimal.ONE.divide(
        new BigDecimal("8"), RoundingMode.HALF_UP);
~~~

**The result is 0**, not 0.13. Because **BigDecimal.ONE.scale() = 0**, this overload produces a quotient with **scale=0**, then rounds 0.125 to the nearest integer using HALF_UP (which is 0).

Compare:

~~~java
BigDecimal a = BigDecimal.ONE;           // scale 0
BigDecimal b = new BigDecimal("1.00");   // scale 2
BigDecimal eight = new BigDecimal("8");

System.out.println(a.divide(eight, RoundingMode.HALF_UP)); // 0
System.out.println(b.divide(eight, RoundingMode.HALF_UP)); // 0.13
~~~

The two dividends **1** and **1.00** have the same numeric value; **only their scales differ**, yet this overload gives different rounded results.

That is why when you need an explicit number of fractional digits, you should use **divide(divisor, scale, roundingMode)** instead of relying on the input's scale.

## 9. divide(divisor, MathContext) — Significant Digits

**MathContext** carries two settings:

- **precision**: number of significant digits for the result.
- **roundingMode**: rounding rule if digits must be discarded.

~~~java
import java.math.MathContext;
import java.math.RoundingMode;

MathContext mc = new MathContext(5, RoundingMode.HALF_UP);
BigDecimal q = BigDecimal.ONE.divide(new BigDecimal("3"), mc);
// 0.33333
~~~

Here **MathContext(5)** keeps 5 significant digits, not 5 digits after the decimal point for every quotient.

Another example:

~~~java
BigDecimal q = new BigDecimal("12345")
        .divide(new BigDecimal("3"),
                new MathContext(3, RoundingMode.HALF_UP));
// 4.12E+3 (value 4120)
~~~

The exact result of 12345/3 is 4115; keeping only three significant digits with HALF_UP rounds it to 4120, displayed scientifically as **4.12E+3**.

### MathContext.UNLIMITED Does Not Solve Infinite Expansions

~~~java
// Still throws ArithmeticException:
BigDecimal.ONE.divide(
        new BigDecimal("3"), MathContext.UNLIMITED);
~~~

**MathContext.UNLIMITED** has **precision=0**, meaning it requests exact computation for the corresponding methods. It does **not** mean BigDecimal is allowed to generate infinitely many digits and run forever. For non-terminating 1/3, Java throws ArithmeticException.

By contrast, **MathContext.DECIMAL32**, **DECIMAL64**, and **DECIMAL128** set finite precision using built-in configurations; they are decimal arithmetic rules and do not turn BigDecimal into a fixed primitive type.

## 10. RoundingMode: Choosing the Rule When Rounding Is Required

Key options:

| RoundingMode | Short meaning |
| --- | --- |
| **HALF_UP** | Midpoint rounds away from 0 |
| **HALF_EVEN** | Midpoint chooses an even last retained digit |
| **HALF_DOWN** | Midpoint rounds toward 0 |
| **DOWN** | When discarding a remainder, rounds toward 0 |
| **UP** | If there is any remainder, rounds away from 0 |
| **FLOOR** | Toward negative infinity |
| **CEILING** | Toward positive infinity |
| **UNNECESSARY** | No rounding allowed; throws ArithmeticException if needed |

The difference between HALF_UP and HALF_EVEN at the **exact midpoint**:

~~~java
BigDecimal one = BigDecimal.ONE;
BigDecimal eight = new BigDecimal("8");

BigDecimal halfEven = one.divide(
        eight, 2, RoundingMode.HALF_EVEN); // 0.12
BigDecimal halfUp = one.divide(
        eight, 2, RoundingMode.HALF_UP);   // 0.13
~~~

The exact quotient 0.125 lies directly halfway between 0.12 and 0.13. HALF_EVEN picks the result ending in **2 (even)**; HALF_UP picks the result **away from 0**, which is 0.13. For negative values, rules toward/away from zero must be understood according to sign, not by string truncation.

### UNNECESSARY Is a Data Quality Constraint

~~~java
BigDecimal exactAtScale = BigDecimal.ONE.divide(
        new BigDecimal("8"), 3, RoundingMode.UNNECESSARY);
// 0.125, no rounding needed

// Throws ArithmeticException because rounding is needed:
BigDecimal.ONE.divide(
        new BigDecimal("3"), 2, RoundingMode.UNNECESSARY);
~~~

Use UNNECESSARY when the business domain **cannot accept losing digits** and wants to detect cases that do not fit the specified scale/precision rather than accidentally rounding.

## 11. Dividing by Zero, Dividing Zero, and Exceptions

| Operation | Behavior |
| --- | --- |
| **0 / 3** | Exact result equal to 0 |
| **1 / 0** | ArithmeticException (division by zero) |
| **0 / 0** | ArithmeticException (undefined division) |
| **1 / 3** via exact divide | ArithmeticException because expansion does not terminate |
| **1 / 3** via MathContext.UNLIMITED | ArithmeticException because exact is still required |
| **1 / 3** via divide(scale=2, UNNECESSARY) | ArithmeticException because rounding is required |
| **1 / 3** via divide(scale=2, HALF_UP) | 0.33 |

BigDecimal **does not have NaN and Infinity** like double. Dividing by zero does not return Double.POSITIVE_INFINITY or NaN; instead it **throws an exception**.

For production code, do not lump every ArithmeticException from divide into the same message. It is usually good practice to check **divisor.signum() == 0** first to distinguish invalid input. Error and rounding policies should be clear to callers.

## 12. Example of Pre-Checking Decimal Termination

When you do not want to attempt division and catch an exception, you can rely on the criterion that the reduced denominator contains only 2 and 5.

Given two finite BigDecimals:

1. Obtain **unscaledValue()** of dividend and divisor.
2. For a divisor equal to 0, reject it.
3. For a numerator equal to 0 and nonzero denominator, the quotient is 0 and terminating.
4. Reduce the ratio of the two unscaled integers using gcd.
5. From the reduced denominator, strip all factors of 2 and 5; if 1 remains, the quotient has a terminating decimal form.

Scale differences between two BigDecimals only correspond to multiplying by a power of 10, so they introduce no prime factors other than 2 and 5.

The following method only illustrates **decimal termination**, without computing the quotient:

~~~java
import java.math.BigDecimal;
import java.math.BigInteger;

static boolean hasTerminatingDecimal(BigDecimal a, BigDecimal b) {
    if (b.signum() == 0) {
        throw new ArithmeticException("Division by zero");
    }
    if (a.signum() == 0) {
        return true;
    }

    BigInteger numerator = a.unscaledValue().abs();
    BigInteger denominator = b.unscaledValue().abs();

    denominator = denominator.divide(denominator.gcd(numerator));

    BigInteger two = BigInteger.valueOf(2);
    BigInteger five = BigInteger.valueOf(5);

    while (denominator.mod(two).signum() == 0) {
        denominator = denominator.divide(two);
    }
    while (denominator.mod(five).signum() == 0) {
        denominator = denominator.divide(five);
    }
    return denominator.equals(BigInteger.ONE);
}
~~~

This is a **method that must be placed inside a class** and requires importing java.math.BigDecimal/BigInteger. It returns:

- **true** for 1/40, 3/6, 0/3.
- **false** for 1/6 or 1/3.
- **ArithmeticException** for divisor 0.

**Practical limitation:** the mathematical conclusion about finite expansion **does not guarantee** that an actual division will always complete within Java's finite memory and scale limits if inputs are huge, scales are extreme, or implementation limits are exceeded. For typical applications, calling **divide** directly is simpler; implementing a custom denominator analyzer is only needed when the criterion itself is part of business logic or you want to explain why rounding occurs.

## 13. Distinguishing Rounding for Calculation vs. Rounding for Display

A data flow can have multiple different values that need to be maintained:

- **Source numbers**: rates, prices, measurements, or unrounded monetary amounts.
- **Computed results**: values after division according to a scale/precision policy.
- **Display strings**: via Locale-aware NumberFormat, which may add grouping separators and round for user readability.

Example of a fee calculation requiring business-defined division and rounding policies:

~~~java
BigDecimal total = new BigDecimal("10.00");
BigDecimal people = new BigDecimal("3");

BigDecimal perPerson = total.divide(
        people, 2, RoundingMode.HALF_UP);
// 3.33
~~~

**3.33 × 3 = 9.99**, not equal to 10.00; 0.01 remains. That is a consequence of non-terminating division and rounding to the smallest unit, not a BigDecimal bug. If **exact allocation of 10.00** is required, there must be a remainder distribution rule (for example, one person receives an extra 0.01) and a final sum check.

Do not automatically convert to double to avoid exceptions or make display easier. Double can introduce binary rounding errors and does not solve allocation/rounding rules on its own.

## 14. Exact Fractions When Rounding Is Not Allowed

If the mathematical requirement is to **keep 1/3 exact**, a finite BigDecimal is insufficient. You can store numerator and denominator as BigInteger and reduce by gcd:

~~~java
import java.math.BigInteger;

BigInteger numerator = BigInteger.ONE;
BigInteger denominator = BigInteger.valueOf(3);

BigInteger gcd = numerator.gcd(denominator);
numerator = numerator.divide(gcd);
denominator = denominator.divide(gcd);
// Rational value preserved as 1/3
~~~

This snippet illustrates a two-component representation, **not a complete fraction class**. In a real system, you must normalize the denominator sign (usually positive), reject zero denominators, handle fraction arithmetic, and enforce resource limits.

Only when outputting decimals for a viewer or sending to an API requiring a finite decimal should an explicit rounding policy be applied. In this way, **model accuracy** is not lost prematurely.

## 15. Overload Selection Checklist

Answer these questions in order:

1. **Is exactness mandatory?** If yes, divide(divisor); if the quotient is non-terminating, reject it or choose a fraction representation.
2. **Does the result have a fixed width in the fractional part?** If yes, divide(divisor, scale, mode).
3. **Does the result only require N significant digits?** If yes, divide(divisor, MathContext).
4. **Do you intentionally want to keep the dividend's scale?** Only if so, choose divide(divisor, mode).
5. **What rounding policy is acceptable?** Determine HALF_EVEN, HALF_UP, or another mode from the contract.
6. **What about division by zero or very large numbers?** Check data domain, scale, precision, resource limits, and error reporting.
7. **Do exact fractions need to be preserved across multiple operations?** If yes, use a numerator/denominator model and avoid intermediate rounding.

The best choice is the one that **matches the data contract**, not the API with the shortest signature.

## 16. Common Pitfalls

| Mistake | Consequence | Right approach |
| --- | --- | --- |
| Calling BigDecimal.ONE.divide(3) expecting Java to give 0.333... | ArithmeticException | Choose rounding or fraction representation |
| Treating every ArithmeticException as division by zero | Misses non-terminating expansion / rounding-forbidden errors | Classify error conditions |
| Thinking BigDecimal can store infinitely many digits | BigDecimal itself is a finite representation | Choose rational representation when exact 1/3 is needed |
| Checking denominator 6 to conclude 3/6 is repeating | Not reduced yet | Reduce with gcd first |
| Assuming a denominator with both 2 and 5 always terminates | Denominator may still have 3 or 7 | Reduced denominator may only contain factors 2 and 5 |
| Using divide(divisor, HALF_UP) thinking it keeps 2 digits | Overload keeps dividend's scale | Use divide(divisor,2,HALF_UP) |
| Confusing MathContext(5) with 5 decimal places | Precision is 5 significant digits | Use scale for fractional places |
| Choosing MathContext.UNLIMITED to avoid 1/3 error | Still demands exactness and throws exception | Finite precision + rounding |
| Using RoundingMode.UNNECESSARY when quotient does not fit scale | ArithmeticException | Increase scale or allow rounding if contract permits |
| Using double as an intermediate before BigDecimal division | Can lose input decimal accuracy | Initialize from String or integer values |
| Rounding at every step assuming the total equals the original | Can drift due to remainders | Design a remainder allocation rule |
| Using NumberFormat as a division calculation step | UI string is not a source number | Compute with BigDecimal, format separately |
| Ignoring input magnitude or precision | Wastes CPU/heap, can exceed implementation limits | Constrain inputs and resources |


## 17. Standalone Runnable Java 17+ Program

Create file **DecimalDivideDemo.java**:

~~~java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.MathContext;
import java.math.RoundingMode;

public class DecimalDivideDemo {
    static boolean hasTerminatingDecimal(BigDecimal a, BigDecimal b) {
        if (b.signum() == 0) {
            throw new ArithmeticException("Division by zero");
        }
        if (a.signum() == 0) {
            return true;
        }

        BigInteger numerator = a.unscaledValue().abs();
        BigInteger denominator = b.unscaledValue().abs();
        denominator = denominator.divide(denominator.gcd(numerator));

        BigInteger two = BigInteger.valueOf(2);
        BigInteger five = BigInteger.valueOf(5);

        while (denominator.mod(two).signum() == 0) {
            denominator = denominator.divide(two);
        }
        while (denominator.mod(five).signum() == 0) {
            denominator = denominator.divide(five);
        }
        return denominator.equals(BigInteger.ONE);
    }

    public static void main(String[] args) {
        BigDecimal one = BigDecimal.ONE;
        BigDecimal three = new BigDecimal("3");
        BigDecimal eight = new BigDecimal("8");

        System.out.println("1 / 8 exact: " + one.divide(eight));
        System.out.println("1 / 40 exact: "
                + one.divide(new BigDecimal("40")));
        System.out.println("10.00 / 4 exact: "
                + new BigDecimal("10.00")
                        .divide(new BigDecimal("4")));

        try {
            one.divide(three);
        } catch (ArithmeticException ex) {
            System.out.println("1 / 3 exact: ArithmeticException");
        }

        try {
            one.divide(three, MathContext.UNLIMITED);
        } catch (ArithmeticException ex) {
            System.out.println("1 / 3 UNLIMITED: ArithmeticException");
        }

        System.out.println("1 / 3 4dp HALF_UP: "
                + one.divide(three, 4, RoundingMode.HALF_UP));
        System.out.println("2 / 3 2dp HALF_UP: "
                + new BigDecimal("2").divide(
                        three, 2, RoundingMode.HALF_UP));
        System.out.println("1 / 3 5sig HALF_UP: "
                + one.divide(three,
                        new MathContext(5, RoundingMode.HALF_UP)));
        System.out.println("12345 / 3 3sig HALF_UP: "
                + new BigDecimal("12345").divide(
                        three, new MathContext(3, RoundingMode.HALF_UP)));

        System.out.println("1 / 8 2dp HALF_EVEN: "
                + one.divide(eight, 2, RoundingMode.HALF_EVEN));
        System.out.println("1 / 8 2dp HALF_UP: "
                + one.divide(eight, 2, RoundingMode.HALF_UP));

        System.out.println("1 / 8 HALF_UP no scale: "
                + one.divide(eight, RoundingMode.HALF_UP));
        System.out.println("1.00 / 8 HALF_UP no scale: "
                + new BigDecimal("1.00")
                        .divide(eight, RoundingMode.HALF_UP));

        try {
            one.divide(three, 2, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException ex) {
            System.out.println("1 / 3 UNNECESSARY: ArithmeticException");
        }

        try {
            one.divide(BigDecimal.ZERO);
        } catch (ArithmeticException ex) {
            System.out.println("1 / 0: ArithmeticException");
        }

        System.out.println("0 / 3 exact: "
                + BigDecimal.ZERO.divide(three));

        System.out.println("1/40 terminates: "
                + hasTerminatingDecimal(one, new BigDecimal("40")));
        System.out.println("1/6 terminates: "
                + hasTerminatingDecimal(one, new BigDecimal("6")));
        System.out.println("3/6 terminates: "
                + hasTerminatingDecimal(three, new BigDecimal("6")));

        System.out.println("1/3 rounded input unchanged: " + one);
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac --release 17 DecimalDivideDemo.java
java DecimalDivideDemo
~~~

Stdout verified with Java:

~~~text
1 / 8 exact: 0.125
1 / 40 exact: 0.025
10.00 / 4 exact: 2.50
1 / 3 exact: ArithmeticException
1 / 3 UNLIMITED: ArithmeticException
1 / 3 4dp HALF_UP: 0.3333
2 / 3 2dp HALF_UP: 0.67
1 / 3 5sig HALF_UP: 0.33333
12345 / 3 3sig HALF_UP: 4.12E+3
1 / 8 2dp HALF_EVEN: 0.12
1 / 8 2dp HALF_UP: 0.13
1 / 8 HALF_UP no scale: 0
1.00 / 8 HALF_UP no scale: 0.13
1 / 3 UNNECESSARY: ArithmeticException
1 / 0: ArithmeticException
0 / 3 exact: 0
1/40 terminates: true
1/6 terminates: false
3/6 terminates: true
1/3 rounded input unchanged: 1
~~~

### Interpreting the Results

1. **1/8 and 1/40** have terminating decimal quotients, so exact divide returns 0.125 and 0.025 properly.
2. **10.00/4 = 2.50** shows that BigDecimal keeps scale according to the preferred scale rule instead of automatically stripping trailing zeros.
3. **1/3** has no terminating decimal, so both exact divide and MathContext.UNLIMITED throw ArithmeticException.
4. **4dp** specifies 4 fractional digits: 0.3333. **5sig** specifies 5 significant digits: 0.33333.
5. **12345/3** is 4115 exactly, while MathContext(3, HALF_UP) rounds to 4120 and displays 4.12E+3.
6. **HALF_EVEN and HALF_UP** on 0.125 at scale=2 yield 0.12 and 0.13, even with identical inputs.
7. **divide(divisor, RoundingMode)** without passing scale uses the **dividend's scale**: from 1 (scale 0) it gives 0, whereas 1.00 (scale 2) gives 0.13.
8. **UNNECESSARY** rejects cases needing digit truncation; division by zero is reported separately.
9. The decimal-termination check returns true for 1/40, false for 1/6, and true for **3/6 after reduction**.
10. The operand BigDecimal.ONE is not modified by division and rounding operations; this is immutability.

## 18. Questions and Exercises

**Exercise 1.** When calling BigDecimal.ONE.divide(new BigDecimal("3")), why do we get ArithmeticException?

*Answer:* The quotient 1/3 is a non-terminating repeating decimal, which cannot be represented exactly by a finite BigDecimal, and this overload has no rounding policy.

**Exercise 2.** Why can 3/6 be divided exactly whereas 1/6 cannot?

*Answer:* Reducing 3/6 gives 1/2, whose denominator has only factor 2. The denominator 6 of 1/6 contains 3, so its decimal expansion does not terminate.

**Exercise 3.** Can a reduced denominator of 2³ × 5² produce a terminating decimal?

*Answer:* Yes. The denominator contains only 2 and 5, so it can be multiplied to become a power of 10.

**Exercise 4.** Why does MathContext.UNLIMITED still throw an exception when dividing 1/3?

*Answer:* Precision=0 means exact calculation is required, not generating an infinite string of digits.

**Exercise 5.** To turn 2/3 into 0.67 with two digits after the decimal point, which method should you call?

*Answer:* **new BigDecimal("2").divide(new BigDecimal("3"), 2, RoundingMode.HALF_UP)**.

**Exercise 6.** To divide a large number keeping only 4 significant digits, should you use scale or MathContext?

*Answer:* **MathContext(4, mode)**. Scale is the number of fractional positions, not total significant digits.

**Exercise 7.** Why does BigDecimal.ONE.divide(new BigDecimal("8"), RoundingMode.HALF_UP) give 0?

*Answer:* This overload keeps the dividend's scale of 0, so 0.125 is rounded to the integer 0.

**Exercise 8.** For 1/8, how does rounding to two digits after the decimal point differ between HALF_EVEN and HALF_UP?

*Answer:* 0.125 lies halfway between 0.12 and 0.13; HALF_EVEN chooses 0.12, while HALF_UP chooses 0.13.

**Exercise 9.** You need to preserve the fraction 1/3 exactly across many operations before outputting a result. What should you do?

*Answer:* Represent it as a normalized integer numerator/denominator (e.g., BigInteger) rather than rounding to BigDecimal early.

**Exercise 10.** Dividing a total of 10.00 equally among three people, each keeping 2 decimal digits of money, why does 3.33×3 not equal 10.00?

*Answer:* Due to rounding a non-terminating quotient. If preserving the total is required, you must define a policy for allocating the 0.01 remainder.

**Exercise 11.** Can BigDecimal.divide be used with a divisor of 0 while expecting Infinity?

*Answer:* No. BigDecimal has no Infinity/NaN; division by zero throws ArithmeticException.

## 19. Official References

- [BigDecimal Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): divide overloads, preferred scale, exact arithmetic, ArithmeticException, and decimal representation.
- [MathContext Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/MathContext.html): precision, roundingMode, and UNLIMITED.
- [RoundingMode Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html): rounding rules for positive and negative numbers.
- [BigInteger Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html): gcd and numerator/denominator representation of exact fractions.