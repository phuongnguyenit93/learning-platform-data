# `RoundingMode.UNNECESSARY`: Requiring Results That Need No Rounding in Java

## 1. Why Do We Need a "No Rounding Allowed" Mode?

When working with `BigDecimal`, developers often specify **scale** (digits after the decimal point) or **precision** (significant digits). If the exact result has more digits than requested, the calculation must discard or alter digits. In that case, a mode such as `HALF_UP` or `HALF_EVEN` decides how to round.

**`RoundingMode.UNNECESSARY` has a different meaning:** it asserts that the operation **must be achievable without changing the mathematical value**. If the scale/precision constraint cannot be satisfied while keeping the value intact, `BigDecimal` throws `ArithmeticException` instead of silently rounding.

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal exact = new BigDecimal("12.3400");
BigDecimal a = exact.setScale(2, RoundingMode.UNNECESSARY); // 12.34
BigDecimal b = exact.setScale(5, RoundingMode.UNNECESSARY); // 12.34000

// Throws ArithmeticException at runtime because digit 5 must be dropped:
BigDecimal c = new BigDecimal("12.345")
        .setScale(2, RoundingMode.UNNECESSARY);
~~~

The lines above are an **illustrative code snippet**, placed inside an appropriate method or program. A standalone runnable version is in section 6.

Key point: `UNNECESSARY` **does not mean skipping the operation, does not mean preserving the input string verbatim, and does not guarantee by itself that the operation always succeeds**. It is an **exactness assertion** for the operation under the requested constraint. `BigDecimal` may still change its representation, adding or removing trailing zeros, as long as the value does not change.

## 2. Foundation: Value, Scale, and Precision of `BigDecimal`

`BigDecimal` stores an integer **unscaled value**, combined with an integer **scale**:

~~~text
value = unscaledValue × 10^(-scale)
~~~

Examples:

| `BigDecimal` created from string | Unscaled value | Scale | Precision |
| --- | ---: | ---: | ---: |
| `"12.34"` | 1234 | 2 | 4 |
| `"12.3400"` | 123400 | 4 | 6 |
| `"0.00120"` | 120 | 5 | 3 |
| `"1200"` | 1200 | 0 | 4 |

**Scale** is the decimal point position in the current representation; scale can be negative (for example, scale = -2 indicates multiples of 100). **Precision** is the number of decimal digits in the unscaled value ignoring sign; it is not synonymous with digits after the decimal point.

`new BigDecimal("12.3400")` and `new BigDecimal("12.34")` have **equal numerical value**, though their initial scale/precision differ. Therefore:

- `compareTo()` returns 0 when two `BigDecimal` values have the same mathematical value.
- `equals()` also checks scale, so the two objects above are **not equal according to `equals`**.
- `setScale(2, UNNECESSARY)` can turn `12.3400` into `12.34` because only zeros that do not affect the value are removed.

For example, `setScale(5, UNNECESSARY)` instead appends zeros to produce `12.34000`, which is still an **exact** conversion. Thus "no rounding needed" differs from "cannot change display format".

## 3. `setScale(..., RoundingMode.UNNECESSARY)`: Checking Exact Representation at the Desired Scale

The method:

~~~java
BigDecimal result = value.setScale(targetScale, RoundingMode.UNNECESSARY);
~~~

requires representing the value with exact `targetScale`. There are three situations:

1. **Increasing scale:** appends `0` digits in the fractional part to preserve value, so it can be done exactly.
2. **Decreasing scale while only dropping trailing zeros:** still exact, succeeds.
3. **Decreasing scale and having to drop a non-zero digit:** cannot preserve the value; throws `ArithmeticException`.

| Input value | Call | Result |
| --- | --- | --- |
| `12.34` | `setScale(4, UNNECESSARY)` | `12.3400` |
| `12.3400` | `setScale(2, UNNECESSARY)` | `12.34` |
| `12.345` | `setScale(2, UNNECESSARY)` | `ArithmeticException` |
| `1000` | `setScale(-2, UNNECESSARY)` | `1.0E+3` (scale = -2) |
| `1250` | `setScale(-2, UNNECESSARY)` | `ArithmeticException` |

In the last two rows, scale = -2 requires the value to be an exact multiple of **100**: `1000` is divisible by 100, while `1250` is not. The string form `1.0E+3` is simply how `BigDecimal.toString()` displays `1000` with scale -2.

For the same conversion of `12.345` down to 2 digits, other rounding modes could produce `12.35` or `12.34`, depending on the rule; `UNNECESSARY` chooses **to raise an error** so the caller does not mistake a modified result for exact.

### 3.1. Application: Validating Data Has at Most the Allowed Decimal Places

Suppose a system only accepts money with at most two digits after the decimal point, while preserving the exact value entered by the customer:

~~~java
public static BigDecimal requireTwoDecimalPlaces(String input) {
    return new BigDecimal(input)
            .setScale(2, RoundingMode.UNNECESSARY);
}
~~~

This is a method to be placed inside a class that imports `java.math.BigDecimal` and `java.math.RoundingMode`.

- `"19"` → `19.00`.
- `"19.2"` → `19.20`.
- `"19.2000"` → `19.20`: redundant zeros do not change the value.
- `"19.201"` → `ArithmeticException`: cannot be represented exactly at scale 2.

This checks **exact representability at scale 2**, not whether **the original string had exactly two digits**. If the requirement is that exactly two digits were entered, string format must be validated separately. In addition, real-world monetary policies may also need constraints on negative numbers, value ranges, currency, and business rules.

## 4. `MathContext` and Precision: Rounding by Significant Digits

`MathContext` combines precision and rounding mode. Example:

~~~java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

MathContext exactThreeDigits =
        new MathContext(3, RoundingMode.UNNECESSARY);

BigDecimal x = new BigDecimal("123.00").round(exactThreeDigits);
// x = 123: drops 2 trailing zeros without changing value.

// Throws ArithmeticException: cannot represent 123.40 exactly
// using at most 3 significant digits.
BigDecimal y = new BigDecimal("123.40").round(exactThreeDigits);
~~~

`MathContext(3, UNNECESSARY)` requires the result to both have **at most 3 significant digits** and **lose no value**. It does not mean "keep exactly 3 digits after the decimal point". For instance, `123.00` reduces to `123` while remaining exact, whereas `123.40` needs four significant digits to keep the exact value `123.4`.

Some operations such as `add`, `subtract`, `multiply`, and `divide` have overloads accepting `MathContext`. When the result must fit the given precision, they perform the same check. With `UNNECESSARY`, if the exact result needs more significant digits and cannot be reduced by dropping value-neutral zeros, the operation fails.

### 4.1. Precision = 0 Is a Special Case

~~~java
MathContext unlimited =
        new MathContext(0, RoundingMode.UNNECESSARY);
~~~

In `MathContext`, **precision = 0 means unlimited precision**. In that case, the rounding mode does not act to limit significant digits, because no limit is imposed. However, this **does not make divisions with infinite decimal expansions suddenly representable**: `1 / 3` still has no exact `BigDecimal` result with finitely many digits.

`MathContext.UNLIMITED` is a constant with precision 0 and rounding mode `HALF_UP`; in operations without a precision limit, its rounding mode makes no difference. Do not assume `MathContext.UNLIMITED` disables all arithmetic errors (for example, division by 0 and non-terminating division still error).

## 5. Division: Where `UNNECESSARY` Often Creates Confusing Errors

### 5.1. Distinguishing Three Overloads of `divide`

| Call | Result constraint | What happens if exactness is impossible? |
| --- | --- | --- |
| `a.divide(b)` | Exact result with finite decimal representation | `ArithmeticException` when division does not terminate, e.g., `1/3` |
| `a.divide(b, scale, UNNECESSARY)` | Result at exact specified scale, no rounding | `ArithmeticException` if a non-zero digit would be dropped |
| `a.divide(b, mathContextWithUNNECESSARY)` | Result within precision limit, no rounding | `ArithmeticException` if rounding is needed or result cannot be represented exactly at that precision |

Another overload, `a.divide(b, RoundingMode.UNNECESSARY)`, uses **the scale of `a`** as the result scale, which easily surprises developers. For example, `new BigDecimal("10").divide(new BigDecimal("4"), RoundingMode.UNNECESSARY)` fails because the scale of `10` is 0, even though the exact quotient `2.5` can be stored by `BigDecimal`. If a scale-1 result is desired, you must call the overload with an explicit scale parameter.

### 5.2. "Exact Division" Differs from "Exact Division at Requested Scale/Precision"

~~~java
BigDecimal ten = new BigDecimal("10");
BigDecimal four = new BigDecimal("4");

// Exact at scale 1:
BigDecimal ok = ten.divide(four, 1, RoundingMode.UNNECESSARY);
// ok = 2.5

// Cannot be exact at scale 0:
BigDecimal fail = ten.divide(four, 0, RoundingMode.UNNECESSARY);
// ArithmeticException
~~~

`10 ÷ 4 = 2.5` is **completely representable as a finite decimal**, yet not at scale 0. This error comes from **the representation constraint**, not because the division is "inherently inexact".

With precision it is similar:

~~~java
MathContext p3 = new MathContext(3, RoundingMode.UNNECESSARY);

BigDecimal ok = BigDecimal.ONE.divide(new BigDecimal("8"), p3);
// 0.125 has 3 significant digits: succeeds.

BigDecimal fail = BigDecimal.ONE.divide(new BigDecimal("32"), p3);
// 0.03125 has 4 significant digits: ArithmeticException.
~~~

### 5.3. Non-Terminating Decimal Division

`1 / 3 = 0.3333...` cannot be written exactly using a `BigDecimal` with finitely many decimal digits:

~~~java
BigDecimal a = BigDecimal.ONE;
BigDecimal b = new BigDecimal("3");

// Neither can return an exact BigDecimal:
a.divide(b);
a.divide(b, new MathContext(20, RoundingMode.UNNECESSARY));
~~~

In the two lines above, the error occurs on whichever division executes first; to test the second line independently, place them in separate `try/catch` blocks.

A reduced fraction `n/d` has a finite decimal representation when **the denominator d has only prime factors 2 and 5**. For example, `1/8 = 0.125` and `1/20 = 0.05` terminate; `1/3` and `1/6` do not. This criterion applies after reducing the fraction, with a positive integer denominator.

If business requirements **allow rounding**, choose an intentional scale or precision and rounding mode, for example:

~~~java
BigDecimal oneThird = BigDecimal.ONE.divide(
        new BigDecimal("3"), 2, RoundingMode.HALF_UP);
// oneThird = 0.33, an approximate value.
~~~

If business rules **forbid rounding**, keep `UNNECESSARY` and treat the error as a signal that data or operation expectations did not meet the condition, rather than switching to `HALF_UP` on your own.

## 6. Compilable and Runnable Java 17+ Program

Create the file **UnnecessaryDemo.java**:

~~~java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class UnnecessaryDemo {
    private static void attempt(String label, Runnable calculation) {
        try {
            calculation.run();
        } catch (ArithmeticException ex) {
            System.out.println(label + " -> ArithmeticException");
        }
    }

    public static void main(String[] args) {
        BigDecimal amount = new BigDecimal("12.3400");

        System.out.println("scale down exact: "
                + amount.setScale(2, RoundingMode.UNNECESSARY));
        System.out.println("scale up exact: "
                + amount.setScale(5, RoundingMode.UNNECESSARY));

        attempt("scale down inexact", () ->
                System.out.println(new BigDecimal("12.345")
                        .setScale(2, RoundingMode.UNNECESSARY)));

        System.out.println("divide exact scale: "
                + new BigDecimal("10").divide(
                        new BigDecimal("4"), 1, RoundingMode.UNNECESSARY));

        attempt("divide inexact scale", () ->
                System.out.println(new BigDecimal("10").divide(
                        new BigDecimal("4"), 0, RoundingMode.UNNECESSARY)));

        MathContext precision3 =
                new MathContext(3, RoundingMode.UNNECESSARY);
        System.out.println("precision exact: "
                + new BigDecimal("123.00").round(precision3));

        attempt("precision inexact", () ->
                System.out.println(new BigDecimal("123.40")
                        .round(precision3)));

        System.out.println("exact division: "
                + BigDecimal.ONE.divide(new BigDecimal("8")));

        attempt("nonterminating division", () ->
                System.out.println(BigDecimal.ONE.divide(
                        new BigDecimal("3"), precision3)));

        System.out.println("exact precision division: "
                + BigDecimal.ONE.divide(new BigDecimal("8"), precision3));

        attempt("precision division", () ->
                System.out.println(BigDecimal.ONE.divide(
                        new BigDecimal("32"), precision3)));

        MathContext unlimited =
                new MathContext(0, RoundingMode.UNNECESSARY);
        System.out.println("unlimited division: "
                + BigDecimal.ONE.divide(new BigDecimal("32"), unlimited));
    }
}
~~~

Compile and run:

~~~bash
javac UnnecessaryDemo.java
java UnnecessaryDemo
~~~

Output:

~~~text
scale down exact: 12.34
scale up exact: 12.34000
scale down inexact -> ArithmeticException
divide exact scale: 2.5
divide inexact scale -> ArithmeticException
precision exact: 123
precision inexact -> ArithmeticException
exact division: 0.125
nonterminating division -> ArithmeticException
exact precision division: 0.125
precision division -> ArithmeticException
unlimited division: 0.03125
~~~

In the program, `attempt` catches `ArithmeticException` so that subsequent cases can continue running after an intentionally constraint-violating calculation. Real applications should have an appropriate error-handling policy, avoiding swallowing errors or returning an arbitrary fallback value.

## 7. Where to Use `UNNECESSARY`?

### 7.1. Validating Data Before Saving

If the database uses `DECIMAL(12, 2)` and business rules require not losing fractional precision, you can use:

~~~java
BigDecimal normalized =
        input.setScale(2, RoundingMode.UNNECESSARY);
~~~

Afterward you **must still check magnitude/integer-digit limits** to match column precision and other business rules. `setScale(2, UNNECESSARY)` only proves that the value can be represented accurately at scale 2; it does not prove the value fits every column or lies within a valid range.

### 7.2. Distributing Integer Quantities

If dividing an integer total into parts while requiring no remainder, you can use `divide(..., 0, UNNECESSARY)` to require an exact integer quotient. For example, `10 / 2` succeeds at scale 0, whereas `10 / 4` throws an error because the quotient 2.5 is not an integer. If you want to check divisibility of **integers**, `BigInteger.divideAndRemainder` or integer division and remainder may express the intent more clearly.

### 7.3. Checking Invariants in Calculations

In a chain of calculations where business logic confirms **no digits may be lost**, `UNNECESSARY` turns the assumption "this division/normalization is definitely exact" into a runtime-checked condition. This is especially useful at **data boundaries**: before persisting, sending to an API, or converting to a standard scale.

However, `UNNECESSARY` does not eliminate errors that originated from earlier data sources. For example, `new BigDecimal(0.1)` carries the exact binary value of the `double` literal 0.1 after IEEE 754 rounding, not the expected exact decimal 0.1. When exact decimal data matching text is needed, prefer `new BigDecimal("0.1")` or a controlled decimal source. If actually starting with a `double`, `BigDecimal.valueOf(0.1)` uses the canonical decimal representation of the double value and is usually better than the double constructor, though it does not recover an unknown original decimal number.

## 8. Exceptions and Misconceptions to Avoid

| Misconception | Fact |
| --- | --- |
| `UNNECESSARY` means "do nothing" | The API still changes scale/precision when possible without losing value |
| Using `UNNECESSARY` guarantees the result will succeed | It throws `ArithmeticException` if rounding is needed |
| `setScale(2, UNNECESSARY)` forces the input string to have exactly 2 digits after the dot | It checks whether the **value** can be represented exactly at scale 2 |
| Precision = 2 equals scale = 2 | Precision counts significant digits; scale specifies decimal point position |
| Every finite division succeeds at any scale | `10/4` is finite yet cannot be represented exactly at scale 0 |
| `MathContext(0, UNNECESSARY)` makes `1/3` representable exactly | Unlimited precision still cannot produce a finite decimal equal to `1/3` |
| `BigDecimal.divide(BigDecimal, UNNECESSARY)` does not set scale | This overload uses **the dividend's scale** |
| `UNNECESSARY` validates range, format, or business validity | It only checks **whether rounding is required** in the invoked operation |

Additional note: **not every `ArithmeticException` is caused by `UNNECESSARY`**. Division by 0 also throws `ArithmeticException`; therefore, when logging and reporting business errors, distinguish the input data, invoked operation, and desired constraint, rather than assuming every error means "rounding needed".

## 9. Self-Check Knowledge

1. Does `new BigDecimal("5.000").setScale(0, UNNECESSARY)` succeed? **Yes**, yielding `5` because only redundant zeros are dropped.
2. Does `new BigDecimal("5.001").setScale(2, UNNECESSARY)` succeed? **No**, because `5.001` cannot be preserved with only 2 digits after the decimal point.
3. What happens with `new BigDecimal("1").divide(new BigDecimal("8"), 2, UNNECESSARY)`? **Throws `ArithmeticException`**, because `0.125` cannot be exact at scale 2.
4. What about the same division with `scale = 3`? **Succeeds**, yielding `0.125`.
5. What happens with `new BigDecimal("123.00").round(new MathContext(3, UNNECESSARY))`? **Succeeds**, yielding `123` because redundant zeros can be dropped while preserving value.
6. When should `HALF_EVEN` or `HALF_UP` be used? **When business rules intentionally allow rounding** and have specified the rule. When required strictly not to change the value, use `UNNECESSARY` to detect violations.

**Takeaway:** `RoundingMode.UNNECESSARY` is a way to express the requirement **"the result at this scale/precision must be exact, otherwise throw an error"**. To use it properly, first identify whether you are constraining **scale** or **precision**, then anticipate and handle `ArithmeticException` when the constraint cannot be met.