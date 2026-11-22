# Reference Table of Division, Remainder, and Rounding for Negative Numbers in Java

## 1. Reference Goal: Same Negative Number, Different Rules

For positive numbers, many division and rounding operations look the same. However, when negative numbers appear, the following three concepts can lead to very different results:

1. **Integer division truncating toward zero** — Java's `/` operator on two integer types.
2. **Integer division rounding toward negative infinity (floor)** — `Math.floorDiv`.
3. **Rounding a floating-point/decimal number** — `Math.floor`, `Math.ceil`, `Math.round`, `Math.rint`, or `BigDecimal.setScale(..., RoundingMode)`.

Example:

~~~java
System.out.println(-7 / 3);                 // -2
System.out.println(-7 % 3);                 // -1
System.out.println(Math.floorDiv(-7, 3));   // -3
System.out.println(Math.floorMod(-7, 3));   // 2
~~~

If you need to partition time into buckets, compute page indices, wrap indices around, reconcile debt balances, or build financial rounding formulas, confusing these rules can cause serious boundary bugs. This reference focuses on **negative numbers**, while placing positive results alongside them to avoid drawing incorrect rules.

**Quick Map:**

| Desired Operation | API / Operator | Division or Rounding Direction |
| --- | --- | --- |
| Divide `int` / `long`, drop fraction | `a / b` | Integer quotient toward **0** |
| Remainder corresponding to truncation toward 0 | `a % b` | Remainder has sign of **dividend** if nonzero |
| Floor integer division | `Math.floorDiv(a, b)` | Quotient toward **−∞** |
| Floor remainder | `Math.floorMod(a, b)` | Remainder has sign of **divisor** if nonzero |
| Round down along the number line | `Math.floor(x)` | Toward **−∞**, returns `double` |
| Round up along the number line | `Math.ceil(x)` | Toward **+∞**, returns `double` |
| Round to nearest, ties toward +∞ | `Math.round(x)` | Returns `int` for `float`, `long` for `double` |
| Round to nearest, ties to even | `Math.rint(x)` | Returns `double` |
| Decimal rounding with explicit policy | `BigDecimal.setScale(scale, mode)` | Determined by `RoundingMode` |

No generic phrase like "round down" is precise enough when values can be negative. Always ask: "**down along the number line**, or **reduce magnitude toward 0**?"

## 2. Integer Division: `/` Always Truncates Toward 0

When both operands are integer types (`int`, `long`; `byte`/`short`/`char` after numeric promotion), `/` produces an **integer** quotient. Java truncates the fractional part toward **0**, rather than using floor.

| Dividend `a` | Divisor `b` | Exact Quotient | `a / b` (Java) |
| ---: | ---: | ---: | ---: |
| `7` | `3` | `2.333…` | `2` |
| `-7` | `3` | `-2.333…` | `-2` |
| `7` | `-3` | `-2.333…` | `-2` |
| `-7` | `-3` | `2.333…` | `2` |
| `-1` | `3` | `-0.333…` | `0` |
| `-8` | `3` | `-2.666…` | `-2` |

Here `-7 / 3 == -2`, **not −3**. The fractional part is dropped, even though doing so makes the result greater than the exact quotient on the number line.

Operand order matters: `-7 / 3` and `7 / -3` both yield `-2`, but their accompanying remainders differ because the dividends have opposite signs.

### `/` on Floating Point Is Not Integer Division

~~~java
System.out.println(-7 / 3);     // -2, int
System.out.println(-7.0 / 3);   // -2.3333333333333335, double
System.out.println(-7 / 3.0);   // -2.3333333333333335, double
~~~

`-7.0 / 3` is not truncated toward 0: the `double` operand makes the division use floating point. The displayed decimal result is a binary64 approximation, not an exact infinite decimal.

If you want to round a quotient to an integer using another rule, **do not** perform integer division first and then cast to `double` or call `Math.floor`. The fractional part is already lost and cannot be recovered:

~~~java
double tooLate = Math.floor(-7 / 3);    // -2.0, because -7 / 3 already produced -2
double floorReal = Math.floor(-7.0 / 3); // -3.0
~~~

## 3. The `%` Operator: Remainder Keeps the Dividend's Sign

For **integer** division, Java uses a quotient truncated toward 0; the remainder from `a % b` satisfies:

\[
a = (a / b) \times b + (a \% b)
\]

Assume `b != 0` and we are not in the `MIN_VALUE / -1` overflow corner case. When the remainder is nonzero, its sign matches the sign of `a` (the dividend).

| `a` | `b` | `a / b` | `a % b` | Check |
| ---: | ---: | ---: | ---: | --- |
| `7` | `3` | `2` | `1` | `2 × 3 + 1 = 7` |
| `-7` | `3` | `-2` | `-1` | `-2 × 3 − 1 = −7` |
| `7` | `-3` | `-2` | `1` | `-2 × -3 + 1 = 7` |
| `-7` | `-3` | `2` | `-1` | `2 × -3 − 1 = −7` |
| `-8` | `3` | `-2` | `-2` | `-2 × 3 − 2 = −8` |
| `-1` | `3` | `0` | `-1` | `0 × 3 − 1 = −1` |

**Warning:** `%` in Java is often called "modulo", but in terms of sign it is **remainder for division truncated toward 0**. For `-7 % 3`, you get `-1`, not `2` as in positive Euclidean modulo.

Do not directly use `negativeIndex % listSize` to index a list if `negativeIndex` can be negative: a negative result causes `IndexOutOfBoundsException` when accessing the element.

## 4. `Math.floorDiv` and `Math.floorMod`: Division Toward Negative Infinity

`Math.floorDiv(a,b)` chooses the **largest integer quotient not greater than the exact quotient** (floor). `Math.floorMod(a,b)` returns the corresponding remainder such that:

\[
a = \operatorname{floorDiv}(a,b) \times b
    + \operatorname{floorMod}(a,b)
\]

For `b > 0`, `floorMod(a,b)` lies in `[0,b)`. For `b < 0`, a nonzero remainder has a **negative** sign, matching the divisor's sign. Therefore, do not claim `floorMod` is "always non-negative": this is only true when **the divisor is positive**.

| `a` | `b` | `a / b` | `a % b` | `floorDiv(a,b)` | `floorMod(a,b)` |
| ---: | ---: | ---: | ---: | ---: | ---: |
| `7` | `3` | `2` | `1` | `2` | `1` |
| `-7` | `3` | `-2` | `-1` | `-3` | `2` |
| `7` | `-3` | `-2` | `1` | `-3` | `-2` |
| `-7` | `-3` | `2` | `-1` | `2` | `-1` |
| `8` | `3` | `2` | `2` | `2` | `2` |
| `-8` | `3` | `-2` | `-2` | `-3` | `1` |
| `1` | `3` | `0` | `1` | `0` | `1` |
| `-1` | `3` | `0` | `-1` | `-1` | `2` |

Application example: computing a circular index of length 5 from a position that may be negative:

~~~java
int size = 5;
int negativeOffset = -1;

System.out.println(negativeOffset % size);             // -1 (do not use as an index)
System.out.println(Math.floorMod(negativeOffset, size)); // 4 (valid index)
~~~

If `size <= 0`, you must validate input first: `size = 0` causes division by zero; negative `size` is not a valid list size and does not produce the desired index range.

### Do Not Equate `floorDiv` with Casting Real Division

For example, `(int) Math.floor((double) a / b)` can lose precision when a `long` is large due to converting to `double`. `Math.floorDiv(long,long)` operates directly on integers without an intermediate binary64 step and is generally the right choice for floor integer division.

## 5. Edge Cases: Zero, MIN_VALUE, and Division by Zero

- Integer division or integer remainder with a divisor of 0 throws `ArithmeticException`.
- `Math.floorDiv` and `Math.floorMod` with a divisor of 0 also throw `ArithmeticException`.
- `0 / -3 == 0` and `0 % -3 == 0`, because the dividend is 0.
- `Integer.MIN_VALUE / -1` is not within the `int` range because the mathematical quotient is 2147483648; Java wraps the result back to `Integer.MIN_VALUE`. `Math.floorDiv(Integer.MIN_VALUE, -1)` also returns `Integer.MIN_VALUE` in this special case.
- For `Long.MIN_VALUE / -1L`, the same issue occurs in the `long` range.

~~~java
System.out.println(Integer.MIN_VALUE / -1);              // -2147483648
System.out.println(Math.floorDiv(Integer.MIN_VALUE, -1)); // -2147483648
System.out.println(Integer.MIN_VALUE % -1);              // 0
~~~

If a program must detect exact overflow when dividing by -1, check `MIN_VALUE` and divisor `-1` explicitly (or choose a wider numeric range); do not expect `/` or `Math.floorDiv` to throw an overflow error on their own.

**Note on the formula:** the identity expression `(a / b) * b + (a % b)` can also suffer wrap-around due to `int` multiplication/addition in edge cases. When reasoning mathematically about division and remainder, account for the representation limits of actual arithmetic.

## 6. Floating Point: `%` Is Not the Same as `Math.IEEEremainder`

The `%` operator supports both `float` and `double`. Fundamentally, it returns the remainder from a quotient truncated toward 0; the remainder can be negative and differs from the IEEE 754 "nearest integral quotient" remainder.

Example:

~~~java
System.out.println(-7.0 % 4.0);                  // -3.0
System.out.println(Math.IEEEremainder(-7.0, 4.0)); // 1.0
~~~

`Math.IEEEremainder(x,y)` uses the integer quotient **nearest** to `x/y`; when the quotient lies halfway between two integers, it chooses the **even quotient**. It is **not** a positive modulo operation, nor is it a drop-in replacement for `%`.

| Expression | Result | Why |
| --- | ---: | --- |
| `-7.0 % 4.0` | `-3.0` | Quotient -1 when truncated toward 0; remainder -3 |
| `Math.IEEEremainder(-7.0,4.0)` | `1.0` | Nearest quotient -2; remainder +1 |
| `Math.IEEEremainder(6.0,4.0)` | `-2.0` | Quotient 1.5, tie selects even quotient 2 |
| `Math.IEEEremainder(-6.0,4.0)` | `2.0` | Quotient -1.5, tie selects even quotient -2 |

Floating-point division by 0, expressions involving `NaN`, `±Infinity`, and **negative 0.0** have special IEEE semantics. For example, `-7.0 / 0.0` yields negative infinity and `-7.0 % 0.0` is `NaN`; conversely, integer division by 0 throws an exception. Do not write shared logic for both numeric categories while ignoring this difference.

## 7. `Math.floor`, `Math.ceil`, `Math.round`, `Math.rint` with Negative Numbers

You must separate **direction along the number line** from "increasing/decreasing absolute magnitude":

- `Math.floor(x)`: returns the nearest integer **not greater than x**, as a `double`.
- `Math.ceil(x)`: returns the nearest integer **not less than x**, as a `double`.
- `Math.round(float)`: rounds to the nearest `int`, ties toward **+∞**.
- `Math.round(double)`: rounds to the nearest `long`, ties toward **+∞**.
- `Math.rint(double)`: returns a `double` holding the nearest integer value; ties select the **even** value.

Table with key negative numbers:

| `x` | `Math.floor(x)` | `Math.ceil(x)` | `Math.round(x)` when `x` is `double` | `Math.rint(x)` |
| ---: | ---: | ---: | ---: | ---: |
| `-2.1` | `-3.0` | `-2.0` | `-2` | `-2.0` |
| `-2.4` | `-3.0` | `-2.0` | `-2` | `-2.0` |
| `-2.5` | `-3.0` | `-2.0` | `-2` | `-2.0` |
| `-2.6` | `-3.0` | `-2.0` | `-3` | `-3.0` |
| `-3.5` | `-4.0` | `-3.0` | `-3` | `-4.0` |
| `2.5` | `2.0` | `3.0` | `3` | `2.0` |

Specifically:

~~~java
System.out.println(Math.round(-2.5)); // -2
System.out.println(Math.round(-3.5)); // -3
System.out.println(Math.rint(-2.5));  // -2.0
System.out.println(Math.rint(-3.5));  // -4.0
~~~

`Math.round(-2.5)` does **not** round away from 0. If you want "ties away from 0", look at `BigDecimal` with `RoundingMode.HALF_UP` or define an explicit rule for the needed numeric range.

`Math.round` also has specific rules for `NaN`, infinity, and values outside the `int`/`long` range (which can saturate at the bounds). It is not a general overflow-checking operation; avoid treating `Math.round` results as proof that every number can be represented accurately in the target integer type.

## 8. `BigDecimal`: Exact Decimal Rounding with `RoundingMode`

For decimal values that must be rounded according to business policy, `BigDecimal` is useful because it represents decimal strings **exactly**, without forcing a conversion through `double`.

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal negative = new BigDecimal("-2.5");

System.out.println(negative.setScale(0, RoundingMode.HALF_UP));   // -3
System.out.println(negative.setScale(0, RoundingMode.HALF_DOWN)); // -2
System.out.println(negative.setScale(0, RoundingMode.HALF_EVEN)); // -2
~~~

### Complete Table of Eight Modes with Negative Numbers

The examples use `new BigDecimal(value).setScale(0, mode)`, i.e., rounding to the **units place**. `-2.4` is not halfway between two integers; `-2.5` and `-3.5` lie exactly halfway.

| `RoundingMode` | `-2.4` | `-2.5` | `-3.5` | `+2.5` | Rule |
| --- | ---: | ---: | ---: | ---: | --- |
| `UP` | `-3` | `-3` | `-4` | `3` | Away from 0 if any digits must be discarded |
| `DOWN` | `-2` | `-2` | `-3` | `2` | Toward 0 |
| `CEILING` | `-2` | `-2` | `-3` | `3` | Toward positive infinity |
| `FLOOR` | `-3` | `-3` | `-4` | `2` | Toward negative infinity |
| `HALF_UP` | `-2` | `-3` | `-4` | `3` | Nearest; ties away from 0 |
| `HALF_DOWN` | `-2` | `-2` | `-3` | `2` | Nearest; ties toward 0 |
| `HALF_EVEN` | `-2` | `-2` | `-4` | `2` | Nearest; ties choose the kept digit to be even |
| `UNNECESSARY` | error | error | error | error | Forbids rounding that loses value |

"error" in `UNNECESSARY` means `ArithmeticException` because all four inputs require dropping a nonzero fractional part. `UNNECESSARY` still succeeds if changing the scale loses no value:

~~~java
System.out.println(new BigDecimal("-2.00")
        .setScale(0, RoundingMode.UNNECESSARY)); // -2
~~~

**Distinguish the four directions:** for `-2.4`, `UP=-3` and `FLOOR=-3`; `DOWN=-2` and `CEILING=-2`. However, this coincidence no longer holds when switching to positive numbers: `UP(2.4)=3`, `FLOOR(2.4)=2`.

### Half-Even Does Not Mean "All Negative Numbers Go Toward 0"

`HALF_EVEN(-2.5)=-2` whereas `HALF_EVEN(-3.5)=-4`. Only when **two candidates are equidistant** do we inspect which candidate's last kept digit is even. At `-2.6`, every `HALF_*` mode selects `-3` because it is the closer candidate.

## 9. `BigDecimal`: Integral Quotient and Remainder of Negative Numbers

`BigDecimal` **does not support** the `/` or `%` operators directly between two objects. Instead:

- `a.divideToIntegralValue(b)`: the **integral** part of the quotient, truncated toward 0.
- `a.remainder(b)`: the remainder after division using the integral quotient truncated toward 0.
- `a.divideAndRemainder(b)`: returns both the integral quotient and remainder together.
- `a.divide(b, scale, mode)`: decimal quotient with specified scale and rounding mode.

Example:

~~~java
BigDecimal a = new BigDecimal("-7");
BigDecimal b = new BigDecimal("3");

System.out.println(a.divideToIntegralValue(b).toPlainString()); // -2
System.out.println(a.remainder(b).toPlainString());              // -1
System.out.println(a.divide(b, 2, RoundingMode.HALF_UP));        // -2.33
~~~

Notably, `BigDecimal.remainder` does not automatically provide a positive modulo. With `-7` and `3`, the remainder is `-1`, matching the dividend's sign. If you want a modulo in the non-negative range for a positive modulus `m`, you must specify it clearly and write a dedicated helper, for example using `BigInteger.mod` for arbitrary integers.

`BigInteger` has both `remainder` and `mod`, but the two methods have different meanings:

~~~java
import java.math.BigInteger;

BigInteger x = BigInteger.valueOf(-7);
BigInteger m = BigInteger.valueOf(3);

System.out.println(x.remainder(m)); // -1
System.out.println(x.mod(m));       // 2
~~~

`BigInteger.mod` requires a **positive** modulus and throws `ArithmeticException` if the modulus is non-positive. When a system defines a positive time/index wrap-around, `Math.floorMod` (for primitive integers) or `BigInteger.mod` is usually more suitable than a signed remainder.

## 10. Java 17+ Program for Lookup and Verification

Create the file `NegativeDivisionRoundingTable.java`. The program prints the integer division/remainder table, decimal rounding modes, and compares key Math operations.

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class NegativeDivisionRoundingTable {

    static String rounded(String raw, RoundingMode mode) {
        try {
            return new BigDecimal(raw).setScale(0, mode).toPlainString();
        } catch (ArithmeticException ex) {
            return "ERR";
        }
    }

    public static void main(String[] args) {
        System.out.println("a b / % floorDiv floorMod");
        int[][] values = {
                { 7, 3 }, { -7, 3 }, { 7, -3 }, { -7, -3 },
                { 8, 3 }, { -8, 3 }, { 1, 3 }, { -1, 3 }
        };
        for (int[] pair : values) {
            int a = pair[0];
            int b = pair[1];
            System.out.printf("%d %d %d %d %d %d%n",
                    a, b, a / b, a % b,
                    Math.floorDiv(a, b), Math.floorMod(a, b));
        }

        System.out.println("mode -2.4 -2.5 -3.5");
        for (RoundingMode mode : RoundingMode.values()) {
            System.out.printf("%s %s %s %s%n",
                    mode,
                    rounded("-2.4", mode),
                    rounded("-2.5", mode),
                    rounded("-3.5", mode));
        }

        System.out.println("round(-2.5)=" + Math.round(-2.5));
        System.out.println("round(-3.5)=" + Math.round(-3.5));
        System.out.println("rint(-3.5)=" + Math.rint(-3.5));
        System.out.println("floor(-2.4)=" + Math.floor(-2.4));
        System.out.println("ceil(-2.4)=" + Math.ceil(-2.4));

        BigDecimal a = new BigDecimal("-7");
        BigDecimal b = new BigDecimal("3");
        System.out.println("BigDecimal quotient="
                + a.divideToIntegralValue(b).toPlainString());
        System.out.println("BigDecimal remainder="
                + a.remainder(b).toPlainString());
        System.out.println("BigDecimal rounded quotient="
                + a.divide(b, 2, RoundingMode.HALF_UP).toPlainString());
    }
}
~~~

Compile and run:

~~~bash
javac NegativeDivisionRoundingTable.java
java NegativeDivisionRoundingTable
~~~

Stdout:

~~~text
a b / % floorDiv floorMod
7 3 2 1 2 1
-7 3 -2 -1 -3 2
7 -3 -2 1 -3 -2
-7 -3 2 -1 2 -1
8 3 2 2 2 2
-8 3 -2 -2 -3 1
1 3 0 1 0 1
-1 3 0 -1 -1 2
mode -2.4 -2.5 -3.5
UP -3 -3 -4
DOWN -2 -2 -3
CEILING -2 -2 -3
FLOOR -3 -3 -4
HALF_UP -2 -3 -4
HALF_DOWN -2 -2 -3
HALF_EVEN -2 -2 -4
UNNECESSARY ERR ERR ERR
round(-2.5)=-2
round(-3.5)=-3
rint(-3.5)=-4.0
floor(-2.4)=-3.0
ceil(-2.4)=-2.0
BigDecimal quotient=-2
BigDecimal remainder=-1
BigDecimal rounded quotient=-2.33
~~~

The line `UNNECESSARY ERR ERR ERR` represents **cases where rounding is rejected**. In production programs, do not silently ignore the exception: return a validation error according to the contract, or let the exception propagate to where it should be handled. `rounded` catches the exception only so that the lesson has a uniform output table.

## 11. Guide to Choosing Operations by Scenario

| Problem | Choose | Why |
| --- | --- | --- |
| Truncate fraction of integer quotient | `/` | Toward 0 |
| Remainder paired with standard integer division | `%` | `a = (a/b)*b + a%b` |
| Partition integers into buckets that may be negative | `Math.floorDiv` | Floor-based buckets, consistent with the number line |
| Wrap index with positive size | `Math.floorMod` | Non-negative remainder when modulus is positive |
| Round down to integer along the number line | `Math.floor` | For negative numbers, moves away from 0 if fractional |
| Round up to integer along the number line | `Math.ceil` | For negative numbers, moves toward 0 if fractional |
| Nearest, ties biased toward +∞ per `Math.round` | `Math.round` | Differs from HALF_UP on negative ties |
| Nearest, ties to even in floating point | `Math.rint` | Result type `double` |
| Round money/decimals to fixed digits | `BigDecimal.setScale` | Choose an explicit `RoundingMode` policy |
| BigDecimal integral quotient and remainder | `divideToIntegralValue`, `remainder` | Truncation-toward-0 semantics |
| Positive modulo with very large integers | `BigInteger.mod` | Requires positive modulus |

**Time bucketing example:** if each bucket spans 10 seconds relative to 0 and an event has an offset of -1 second, `-1 / 10 == 0` places the event in bucket 0 due to truncation, whereas `Math.floorDiv(-1,10) == -1` places it in the negative bucket matching the interval `[-10,0)`. When defining contiguous floor-based intervals, `floorDiv` avoids bugs around 0.

**Accounting balance example:** `-7 % 3 == -1` is a remainder carrying the dividend's sign; if business rules need "the shortfall remaining to reach a multiple", you must define another quantity explicitly, rather than arbitrarily flipping the sign or taking `Math.abs(remainder)`.

## 12. Common Mistakes

1. **Calling `/` floor division.** For `-7/3`, Java produces `-2`, not `-3`.
2. **Assuming `%` is always non-negative.** `-7%3` produces `-1`.
3. **Assuming `floorMod` is always non-negative.** This is only guaranteed with a **positive modulus**; `floorMod(7,-3)=-2`.
4. **Using a cast to `int` to perform floor.** `(int)-2.7 == -2` because casting truncates toward 0; `Math.floor(-2.7)=-3.0`.
5. **Using `Math.round` as `RoundingMode.HALF_UP`.** `Math.round(-2.5)=-2` whereas `BigDecimal("-2.5").setScale(0, HALF_UP)=-3`.
6. **Equating `BigDecimal.remainder` with non-negative modulo.** `BigDecimal(-7).remainder(3)` is still `-1`.
7. **Forgetting the return types.** `Math.floor` and `Math.ceil` return `double`, `Math.round(float)` returns `int`, `Math.round(double)` returns `long`, and `BigDecimal.setScale` returns `BigDecimal`.
8. **Dividing integers and trying to recover the fraction with a cast.** `(double)(-7/3)` is still `-2.0`.
9. **Ignoring division by 0 and MIN_VALUE/-1.** These cases require dedicated tests; in particular, `MIN_VALUE/-1` can wrap instead of throwing an exception.
10. **Using `double` to round exact monetary amounts.** Some decimals such as 0.1 are not represented exactly in binary64; use `new BigDecimal("...")` and a `RoundingMode` policy matching business requirements.

## 13. Reference Exercises

Do not run the code first; fill in the types and results from the principles, then use a small program to verify:

| # | Expression | Predicted Result |
| ---: | --- | --- |
| 1 | `-11 / 4` | ? |
| 2 | `-11 % 4` | ? |
| 3 | `Math.floorDiv(-11, 4)` | ? |
| 4 | `Math.floorMod(-11, 4)` | ? |
| 5 | `11 % -4` | ? |
| 6 | `Math.floorMod(11, -4)` | ? |
| 7 | `(int) -2.9` | ? |
| 8 | `Math.floor(-2.9)` | ? |
| 9 | `Math.ceil(-2.9)` | ? |
| 10 | `Math.round(-2.5)` | ? |
| 11 | `Math.rint(-2.5)` | ? |
| 12 | `new BigDecimal("-2.5").setScale(0, HALF_UP)` | ? |
| 13 | `new BigDecimal("-2.5").setScale(0, HALF_EVEN)` | ? |
| 14 | `new BigInteger("-11").mod(new BigInteger("4"))` | ? |

Answers (for the BigDecimal/BigInteger items, the corresponding classes and enum must be imported):

| # | Result | Explanation |
| ---: | --- | --- |
| 1 | `-2` (`int`) | Integer quotient truncated toward 0 |
| 2 | `-3` (`int`) | `-11 = (-2)×4 - 3` |
| 3 | `-3` (`int`) | Floor of -2.75 |
| 4 | `1` (`int`) | `-11 = (-3)×4 + 1` |
| 5 | `3` (`int`) | `%` remainder matches sign of dividend 11 |
| 6 | `-1` (`int`) | With negative modulus, `floorMod` returns negative remainder |
| 7 | `-2` (`int`) | Casting floating point to int truncates toward 0 |
| 8 | `-3.0` (`double`) | Floor toward negative infinity |
| 9 | `-2.0` (`double`) | Ceiling toward positive infinity |
| 10 | `-2` (`long`) | `Math.round(double)` ties toward +∞ |
| 11 | `-2.0` (`double`) | Tie chooses even number |
| 12 | `-3` (`BigDecimal`) | HALF_UP ties away from 0 |
| 13 | `-2` (`BigDecimal`) | HALF_EVEN chooses even 2 |
| 14 | `1` (`BigInteger`) | Positive modulo in `[0,4)` |

**Easy-to-remember summary:** `/` and `%` on integers use **truncation toward zero**; `floorDiv`/`floorMod` use **floor-based division**; `Math.floor`, `Math.ceil`, `Math.round`, and `Math.rint` have different policies for negative numbers; `BigDecimal` lets you explicitly specify both mode and scale. When writing code that handles negative numbers, choose the policy according to the mathematical/business definition, not simply because a method name sounds right.
