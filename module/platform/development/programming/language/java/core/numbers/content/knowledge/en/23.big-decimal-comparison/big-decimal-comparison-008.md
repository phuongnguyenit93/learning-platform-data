# Checking for zero using signum() or compareTo() in Java BigDecimal

## 1. Goal: check the numeric value, without confusing it with representation

When working with `java.math.BigDecimal`, we often need to determine whether a number equals 0: whether an account balance is exhausted, whether a subtraction result has reached 0, whether a delta is negative/positive/unchanged, or whether division by a denominator should proceed.

Two direct, accurate expressions are:

~~~java
value.signum() == 0
value.compareTo(BigDecimal.ZERO) == 0
~~~

Both check **whether the numeric value is 0**, regardless of what scale the `BigDecimal` object currently has. This differs from `value.equals(BigDecimal.ZERO)`: `equals` also checks **scale**, so it can return `false` even when the numeric value is exactly 0.

This lesson focuses on choosing between `signum()` and `compareTo(BigDecimal.ZERO)`, distinguishing `equals`, handling zero across multiple decimal forms, and real-world cases that can cause bugs.

## 2. Approach 1: BigDecimal.signum()

`public int signum()` returns **the sign of the numeric value**:

| `value.signum()` | Value of `value` | Equal to 0? |
| ---: | --- | --- |
| `-1` | Less than 0 | No |
| `0` | Equal to 0 | **Yes** |
| `1` | Greater than 0 | No |

Therefore:

~~~java
boolean isZero = value.signum() == 0;
boolean isNegative = value.signum() < 0;
boolean isPositive = value.signum() > 0;
~~~

Here, `value` is a declared, non-null `BigDecimal`. There is no rounding, conversion to `double`, or scale change. `signum()` returns exactly `-1`, `0`, or `1`.

Examples:

| Created value | `signum()` | Explanation |
| --- | ---: | --- |
| `new BigDecimal("0")` | `0` | Zero |
| `new BigDecimal("0.000")` | `0` | Multiple zero digits is still 0 |
| `new BigDecimal("-0.00")` | `0` | There is no separate negative zero numeric value in BigDecimal |
| `new BigDecimal("0.0000000001")` | `1` | Very small, yet still greater than 0 |
| `new BigDecimal("-0.0000000001")` | `-1` | Very small, yet still negative |
| `new BigDecimal("100.0")` | `1` | Positive |

Advantage of `signum()`: it concisely expresses the question "is the value negative, positive, or zero?" without needing to reference or pass a comparison baseline object.

## 3. Approach 2: BigDecimal.compareTo(BigDecimal.ZERO)

`compareTo(BigDecimal other)` compares the **numeric values** of two `BigDecimal` objects. When `other` is `BigDecimal.ZERO`, the meaning of the result is:

~~~java
boolean isZero = value.compareTo(BigDecimal.ZERO) == 0;
boolean isNegative = value.compareTo(BigDecimal.ZERO) < 0;
boolean isPositive = value.compareTo(BigDecimal.ZERO) > 0;
~~~

`BigDecimal.ZERO` is a built-in constant for 0 in the standard library, so there is no need to repeatedly write `new BigDecimal("0")` on every check. If `compareTo` returns negative, the left value is less than 0; if 0, the two numbers are numerically equal; if positive, the left value is greater than 0.

For any non-null `BigDecimal value`:

~~~java
(value.signum() == 0)
        == (value.compareTo(BigDecimal.ZERO) == 0)
~~~

Both expressions evaluate to the same boolean result. Likewise, `value.signum() < 0` is equivalent to `value.compareTo(BigDecimal.ZERO) < 0`, and `> 0` is also equivalent.

**Do not compare the `compareTo` result to `1` or `-1` to test greater-than/less-than.** Under the `Comparable` contract, only check whether the result is **positive** or **negative**. `signum()` specifically guarantees returning `-1`, `0`, or `1`, though using `< 0` and `> 0` remains readable and consistent.

## 4. Why can equals(BigDecimal.ZERO) return false?

`BigDecimal` stores a number using an unscaled integer value (`unscaledValue`) and a `scale`. The corresponding mathematical value is `unscaledValue × 10^(-scale)`.

Examples:

| String creating BigDecimal | Numeric value | `scale()` | `signum()` | `compareTo(ZERO) == 0` | `equals(ZERO)` |
| --- | ---: | ---: | ---: | --- | --- |
| `"0"` | 0 | 0 | 0 | `true` | `true` |
| `"0.0"` | 0 | 1 | 0 | `true` | `false` |
| `"0.00"` | 0 | 2 | 0 | `true` | `false` |
| `"-0.00"` | 0 | 2 | 0 | `true` | `false` |
| `"0E+3"` | 0 | -3 | 0 | `true` | `false` |

All of the numbers above **are numerically equal to 0**. However, `BigDecimal.ZERO` has scale 0; for `equals`, a zero with scale 1, 2, or -3 differs from the representation of zero with scale 0.

Consequently, the snippet below easily causes business bugs:

~~~java
BigDecimal amount = new BigDecimal("0.00");

System.out.println(amount.equals(BigDecimal.ZERO));    // false
System.out.println(amount.signum() == 0);               // true
System.out.println(amount.compareTo(BigDecimal.ZERO) == 0); // true
~~~

When the requirement is "**does this amount equal 0?**", use `signum()` or `compareTo`. Only use `equals` if the requirement genuinely includes matching **scale**, such as validating a fixed decimal representation.

Also do not use `value == BigDecimal.ZERO`: the `==` operator between two object references checks **whether they are the same object**, not numeric value.

## 5. Complete, runnable Java 17+ example

Save the following program as `BigDecimalZeroDemo.java`.

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class BigDecimalZeroDemo {
    private static void describe(String input) {
        BigDecimal value = new BigDecimal(input);

        int comparisonSign =
                Integer.signum(value.compareTo(BigDecimal.ZERO));

        System.out.printf(
                "%s: signum=%d, compareToZeroSign=%d, equalsZero=%s%n",
                input,
                value.signum(),
                comparisonSign,
                value.equals(BigDecimal.ZERO));
    }

    public static void main(String[] args) {
        for (String input : new String[]{
                "0", "0.00", "-0.00", "0.0001", "-0.0001"}) {
            describe(input);
        }

        BigDecimal tiny = new BigDecimal("0.004");
        BigDecimal rounded = tiny.setScale(2, RoundingMode.DOWN);

        System.out.println("tiny is zero = " + (tiny.signum() == 0));
        System.out.println("rounded = " + rounded.toPlainString());
        System.out.println("rounded is zero = " + (rounded.signum() == 0));

        BigDecimal sum = new BigDecimal("0.1")
                .add(new BigDecimal("-0.10"));

        System.out.println("sum = " + sum.toPlainString());
        System.out.println("sum compared to zero = "
                + sum.compareTo(BigDecimal.ZERO));
    }
}
~~~

Open a terminal in the folder containing the file, using JDK 17 or later:

~~~bash
javac BigDecimalZeroDemo.java
java BigDecimalZeroDemo
~~~

Expected output:

~~~text
0: signum=0, compareToZeroSign=0, equalsZero=true
0.00: signum=0, compareToZeroSign=0, equalsZero=false
-0.00: signum=0, compareToZeroSign=0, equalsZero=false
0.0001: signum=1, compareToZeroSign=1, equalsZero=false
-0.0001: signum=-1, compareToZeroSign=-1, equalsZero=false
tiny is zero = false
rounded = 0.00
rounded is zero = true
sum = 0.00
sum compared to zero = 0
~~~

Points to note:

1. `Integer.signum(value.compareTo(BigDecimal.ZERO))` normalizes the comparison result to `-1`, `0`, or `1` for clean printing; when you only need to check for zero, write `compareTo(...) == 0` directly.
2. `"0.00"` and `"-0.00"` both have `signum() == 0`, yet `equals(BigDecimal.ZERO)` is `false` because the scale is 2 instead of 0.
3. `0.0001` is not 0 even though it is very close to 0. Exact numeric checks do not apply an implicit tolerance.
4. When rounding `0.004` with `RoundingMode.DOWN` to two decimal places, the result is `0.00`. **The original value is non-zero; the rounded value is zero.**
5. Adding `0.1 + (-0.10)` yields zero with scale 2 (`0.00`). `compareTo(BigDecimal.ZERO)` recognizes the zero value accurately regardless of scale.

## 6. Checking for zero before and after calculations

An easy point to overlook: *when* you check can change the meaning.

### Checking for a non-zero denominator before division

If the denominator is `new BigDecimal("0.000")`, `equals(BigDecimal.ZERO)` is false even though dividing by that denominator is still division by zero. Check by numeric value:

~~~java
static BigDecimal safeDivide(BigDecimal numerator,
                             BigDecimal denominator) {
    if (denominator.signum() == 0) {
        throw new IllegalArgumentException("Denominator must be non-zero");
    }
    return numerator.divide(
            denominator, 6, java.math.RoundingMode.HALF_EVEN);
}
~~~

This is a **method snippet** placed inside a Java class that imports `BigDecimal`; both arguments are assumed non-null. Scale 6 and `HALF_EVEN` merely illustrate a calculation policy and must be adjusted to specific requirements. Using `compareTo(BigDecimal.ZERO) == 0` in the `if` condition yields the exact same behavior.

### Checking subtraction results

~~~java
BigDecimal debit = new BigDecimal("10.00");
BigDecimal credit = new BigDecimal("10.0");
BigDecimal balance = debit.subtract(credit);

boolean fullyOffset = balance.signum() == 0; // true
~~~

The two inputs have different scales, yet the result is numerically 0. There is no need to call `setScale(0)` or `stripTrailingZeros()` to check.

### Checking rounded values

~~~java
BigDecimal original = new BigDecimal("-0.004");
BigDecimal displayed = original.setScale(2, RoundingMode.DOWN);

boolean rawZero = original.signum() == 0;        // false
boolean displayedZero = displayed.signum() == 0; // true
~~~

Distinguish the two questions:

- "**Is the actual data equal to 0?**" → check `original`.
- "**Is the result after rounding equal to 0?**" → check `displayed`.

Do not round arbitrarily to turn small numbers into 0 before checking, as that can erase a distinction required by the business logic.

## 7. Negative zero: BigDecimal does not keep a separate negative sign for zero

Many developers have encountered `-0.0` with `double` and `float` under IEEE 754. A `double` value can carry a negative sign bit while comparing equal to zero numerically. `BigDecimal` works differently: zero has an unscaled integer value of 0, and `signum()` returns **0** for both input strings `"0.00"` and `"-0.00"`.

~~~java
BigDecimal minusZero = new BigDecimal("-0.00");

System.out.println(minusZero.signum());       // 0
System.out.println(minusZero.toPlainString()); // 0.00
~~~

There is no way to determine whether a user **typed a minus sign** solely from the sign of the `BigDecimal` object after parsing. If preserving the minus sign of the raw string is a requirement (for instance a form needing exact input preservation), store the raw string or sign information as a separate field **before conversion**.

`BigDecimal` also has no `NaN` or infinity like `double`. There is no need to add a `NaN` check to `signum() == 0`; if input is not a valid decimal number, constructing from a string throws an error rather than producing `NaN`.

## 8. Tiny values and "near zero" are two different requirements

`BigDecimal` can represent very small decimal numbers with high precision. For example:

~~~java
BigDecimal x = new BigDecimal("0.000000000000000000000000000001");
System.out.println(x.signum() == 0); // false
~~~

This number is non-zero, so both exact checks return false:

~~~java
x.signum() == 0                        // false
x.compareTo(BigDecimal.ZERO) == 0      // false
~~~

If a problem genuinely requires accepting an **allowed tolerance**, explicitly specify a range such as `-0.001 <= x <= 0.001`. Once `tolerance` is verified to be **non-negative**:

~~~java
BigDecimal tolerance = new BigDecimal("0.001");
BigDecimal measurement = new BigDecimal("-0.0005");

boolean nearZero =
        measurement.abs().compareTo(tolerance) <= 0;
// true: absolute value of -0.0005 does not exceed 0.001
~~~

This is a **near-zero** check, not an **exact-zero** check. It depends on measurement units, sensor resolution, statistical rules, or business contracts. Do not apply an arbitrary epsilon by default in `BigDecimal` calculations, especially when handling money or balances.

If `tolerance = 0`, `abs().compareTo(tolerance) <= 0` is equivalent to checking for exact zero. If `tolerance` is negative, the defined interval is invalid and must be rejected or handled according to application rules.

## 9. Choosing signum or compareTo?

Both are correct for checking whether a `BigDecimal` is 0, though their expressiveness differs slightly:

| Goal | Expression | Suggestion |
| --- | --- | --- |
| Only check for zero | `x.signum() == 0` | Concise, directly expresses a sign check |
| Check positive, negative, zero | `x.signum() > 0`, `< 0`, `== 0` | Clean when branching on sign |
| Check zero alongside other comparisons | `x.compareTo(BigDecimal.ZERO) == 0` | Consistent with other `compareTo` threshold checks |
| Compare against a non-zero threshold | `x.compareTo(threshold) >= 0` | This is the general strength of `compareTo` |
| Compare object value and scale | `x.equals(other)` | Use when representation is part of the condition |

A readable branching pattern:

~~~java
int sign = amount.signum();

if (sign < 0) {
    System.out.println("Negative");
} else if (sign == 0) {
    System.out.println("Zero");
} else {
    System.out.println("Positive");
}
~~~

This code snippet assumes `amount` has already been initialized to a non-null `BigDecimal`. It avoids calling `signum()` multiple times when reusing the same sign result.

Regarding performance, do not assume one option is always significantly faster across all JDK versions and number shapes. Choose the expression that clearly reflects your intent, and optimize only based on proper measurements when needed.

## 10. Nulls, immutability, and common mistakes

**1. Null objects.** `null` is not the numeric value 0. If `value == null`, both `value.signum()` and `value.compareTo(BigDecimal.ZERO)` throw `NullPointerException`. Validate inputs or use `Objects.requireNonNull(value)` per your API contract. Do not default a null variable to zero unless specified.

**2. Using equals to check for zero.** `new BigDecimal("0.00").equals(BigDecimal.ZERO)` is false due to differing scales. Switch to `signum() == 0` or `compareTo(ZERO) == 0` when comparing numeric value.

**3. Using the == operator with BigDecimal.** `value == BigDecimal.ZERO` checks object reference identity, not value. A newly constructed `BigDecimal` representing 0 will not be reliably recognized this way.

**4. Truncating to int before checking.** `new BigDecimal("0.5").intValue() == 0` is true even though the original value is not 0. `intValue()` discards the fractional part or loses information; never use it to check for zero.

**5. Converting to double.** Do not use `value.doubleValue() == 0.0`. Extremely small `BigDecimal` values can **underflow to 0.0** when converted to `double`, even though the original value is non-zero. Check directly with `signum`/`compareTo`.

**6. Rounding before checking unintentionally.** `0.004` rounded to scale 2 with `DOWN` becomes `0.00`; clarify whether the requirement refers to the raw number or the rounded number.

**7. Assuming negative zero has `signum() == -1`.** `BigDecimal("-0.00")` has `signum() == 0`. You cannot infer a minus sign from parsed data.

**8. Normalizing just to perform a simple check.** `value.stripTrailingZeros().equals(BigDecimal.ZERO)` can detect zero, but introduces unnecessary representation processing. When simply asking whether the value is zero, use `signum() == 0` for clarity.

**9. Confusing equal-to-zero with "small enough".** `0.0001` is still non-zero. If you need a near-zero threshold, represent the threshold explicitly in domain data and compare `abs()` against it.

## 11. Practice exercises with answers

For each value below, predict `signum()`, `compareTo(BigDecimal.ZERO) == 0`, and `equals(BigDecimal.ZERO)`:

| Value | signum | compareTo zero == 0 | equals ZERO |
| --- | ---: | --- | --- |
| `new BigDecimal("0")` | 0 | true | true |
| `new BigDecimal("0.000")` | 0 | true | false |
| `new BigDecimal("-0.000")` | 0 | true | false |
| `new BigDecimal("0.00000001")` | 1 | false | false |
| `new BigDecimal("-0.00000001")` | -1 | false | false |
| `new BigDecimal("10").subtract(new BigDecimal("10.00"))` | 0 | true | false |

Applied exercises:

1. Write `boolean isZero(BigDecimal amount)` returning true for `0`, `0.000`, `-0.00`, and false for `0.000001`. Specify the behavior when `amount == null`.
2. Write a condition allowing division only when `denominator.signum() != 0`. Test with denominators `"0.000"` and `"-0.00"`.
3. Evaluate `new BigDecimal("0.009").setScale(2, RoundingMode.DOWN)`. Is the initial value equal to 0? Is the resulting value equal to 0?
4. Write a "near zero" check with `tolerance = 0.01`, clearly distinguished from an exact zero check.

One implementation of exercise 1 when null is invalid:

~~~java
static boolean isZero(BigDecimal amount) {
    return java.util.Objects.requireNonNull(amount, "amount").signum() == 0;
}
~~~

This is a **method snippet** that belongs inside a Java class importing `java.math.BigDecimal`. For exercise 3, `0.009` with `DOWN` at scale 2 becomes `0.00`, so the original value is non-zero while the rounded value is zero.

**Key takeaway:** For `BigDecimal`, `value.signum() == 0` and `value.compareTo(BigDecimal.ZERO) == 0` both determine **numeric equality to 0**. `equals(BigDecimal.ZERO)` also checks scale and can be wrong for your intent. Always clarify whether the value being compared is the original number or a transformed/rounded number, and clearly distinguish exact zero from threshold-based near-zero.
