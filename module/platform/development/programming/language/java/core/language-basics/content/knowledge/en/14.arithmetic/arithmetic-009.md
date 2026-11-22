# Introduction to Math: Absolute Value, Powers, and Rounding in Java

> **Java core — language-basics / Arithmetic**  
> **Environment:** Java 17+, standard library only.  
> **Objectives:** Correctly use `Math.abs`, `Math.pow`, `Math.round`, `Math.floor`, and `Math.ceil`; understand return types, negative number handling, integer type limits, and floating-point precision error.

## 1. How Is the `Math` Class Used?

`java.lang.Math` provides `static` methods for arithmetic computations; you do not need to instantiate a `Math` object or write an `import` statement:

~~~java
int distance = Math.abs(-12);         // 12
double area = Math.pow(3, 2);        // 9.0
long rounded = Math.round(2.7);      // 3L
double below = Math.floor(2.7);      // 2.0
double above = Math.ceil(2.7);       // 3.0
~~~

**Important:** `Math.pow`, `Math.floor`, and `Math.ceil` return `double`. `Math.round(float)` returns `int`, while `Math.round(double)` returns `long`. The `Math.abs` method has overloads for `int`, `long`, `float`, and `double`, returning the corresponding type.

## 2. Absolute Value with `Math.abs`

Absolute value expresses magnitude without sign:

~~~java
Math.abs(-8);     // int 8
Math.abs(-3.25);  // double 3.25
Math.abs(0);      // int 0
~~~

Used when computing distances or differences, but note the **exception regarding integer value ranges**. `int` ranges from `-2147483648` to `2147483647`, so the mathematical absolute value of `Integer.MIN_VALUE` cannot fit in `int`:

~~~java
Math.abs(Integer.MIN_VALUE); // Still -2147483648, throws no error!
~~~

Similarly, `Math.abs(Long.MIN_VALUE)` stays negative. If you want to **detect the unrepresentable case**, Java 17 supports `Math.absExact(int)` and `Math.absExact(long)`, throwing `ArithmeticException` on the minimum value. If you need the absolute value of an `int` as a `long`, **cast beforehand**:

~~~java
long safe = Math.abs((long) Integer.MIN_VALUE); // 2147483648.
~~~

Do not cast after `Math.abs(Integer.MIN_VALUE)` because the calculation in `int` has already produced the unexpected result.

## 3. Exponentiation with `Math.pow`

`Math.pow(base, exponent)` returns `double`, even when two integers are passed:

~~~java
Math.pow(2, 3);    // 8.0
Math.pow(10, 2);   // 100.0
Math.pow(4, -1);   // 0.25
Math.pow(9, 0.5);  // 3.0: equivalent to the square root of 9.
~~~

| Case | Result and Notes |
| --- | --- |
| `Math.pow(2, 10)` | `1024.0`, type `double` |
| `Math.pow(4, -1)` | `0.25`, negative exponent |
| `Math.pow(-2, 0.5)` | `NaN`: no real result |
| `Math.pow(2, 0)` | `1.0` |
| `Math.sqrt(81)` | `9.0`, dedicated API for square roots |

`Math.pow` computes in floating-point and **does not guarantee absolute exactness** for large integers. Avoid directly casting a `double` result to `int`/`long` for computing large integer powers. If exact integer exponentiation is needed, use `BigInteger.pow(int)` when the range may exceed primitive integer types; if overflow detection in integer multiplication is needed, see `Math.multiplyExact`.

## 4. Rounding: `round`, `floor`, `ceil`, and `rint`

| Input | `Math.round(double)` | `Math.floor(double)` | `Math.ceil(double)` |
| --- | ---: | ---: | ---: |
| `2.2` | `2` | `2.0` | `3.0` |
| `2.5` | `3` | `2.0` | `3.0` |
| `-2.2` | `-2` | `-3.0` | `-2.0` |
| `-2.5` | `-2` | `-3.0` | `-2.0` |
| `-2.7` | `-3` | `-3.0` | `-2.0` |

- **`Math.floor(x)`:** the largest integer not exceeding `x`, yet **the return type is `double`**. For negative numbers, `floor(-2.7) == -3.0`.
- **`Math.ceil(x)`:** the smallest integer not less than `x`, return type `double`. For negative numbers, `ceil(-2.7) == -2.0`.
- **`Math.round(x)`:** rounds to the nearest integer; when halfway between two integers, picks the number **toward positive infinity**. Hence `round(2.5) == 3` whereas `round(-2.5) == -2`, not -3.
- **`Math.rint(x)`:** returns `double`; at exact halves, picks the **nearest even integer** (*ties to even*): `rint(2.5) == 2.0` and `rint(3.5) == 4.0`.

Do not confuse `Math.round` with rounding always away from 0. `Double.NaN` and infinity have special handling in `round`; if business logic requires finite numbers, check `Double.isFinite` first.

## 5. Runnable Java 17+ Program

Create the file **MathBasicsDemo.java**:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public final class MathBasicsDemo {
    public static void main(String[] args) {
        System.out.println("absInt=" + Math.abs(-17));
        System.out.println("absDouble=" + Math.abs(-4.25));
        System.out.println("absMinInt=" + Math.abs(Integer.MIN_VALUE));
        System.out.println("absMinAsLong="
                + Math.abs((long) Integer.MIN_VALUE));

        try {
            System.out.println("absExact="
                    + Math.absExact(Integer.MIN_VALUE));
        } catch (ArithmeticException ex) {
            System.out.println("absExact=ArithmeticException");
        }

        System.out.println("power=" + Math.pow(2, 10));
        System.out.println("negativePower=" + Math.pow(4, -1));
        System.out.println("rootViaPow=" + Math.pow(9, 0.5));
        System.out.println("negativeRootNaN="
                + Double.isNaN(Math.pow(-2, 0.5)));

        int roundedFloat = Math.round(2.5f);
        long roundedDouble = Math.round(2.5);
        System.out.println("roundFloat=" + roundedFloat);
        System.out.println("roundDouble=" + roundedDouble);
        System.out.println("roundNegative=" + Math.round(-2.5));
        System.out.println("roundBelowHalf=" + Math.round(2.49));

        System.out.println("floorPositive=" + Math.floor(2.7));
        System.out.println("ceilPositive=" + Math.ceil(2.7));
        System.out.println("floorNegative=" + Math.floor(-2.7));
        System.out.println("ceilNegative=" + Math.ceil(-2.7));
        System.out.println("rintEven2=" + Math.rint(2.5));
        System.out.println("rintEven4=" + Math.rint(3.5));

        BigDecimal value = new BigDecimal("2.345");
        System.out.println("moneyHalfUp="
                + value.setScale(2, RoundingMode.HALF_UP));
        System.out.println("moneyHalfEven="
                + value.setScale(2, RoundingMode.HALF_EVEN));
    }
}
~~~

Open a terminal in the directory containing the file and run (Bash, PowerShell, or Command Prompt):

~~~bash
javac -encoding UTF-8 MathBasicsDemo.java
java MathBasicsDemo
~~~

**Exact expected output:**

~~~text
absInt=17
absDouble=4.25
absMinInt=-2147483648
absMinAsLong=2147483648
absExact=ArithmeticException
power=1024.0
negativePower=0.25
rootViaPow=3.0
negativeRootNaN=true
roundFloat=3
roundDouble=3
roundNegative=-2
roundBelowHalf=2
floorPositive=2.0
ceilPositive=3.0
floorNegative=-3.0
ceilNegative=-2.0
rintEven2=2.0
rintEven4=4.0
moneyHalfUp=2.35
moneyHalfEven=2.34
~~~

Explaining easily confused lines: `absMinInt` stays negative because there is no corresponding positive `int`; `absExact` proactively detects overflow; `negativeRootNaN` is true because a negative base with a fractional exponent yields no real value; `roundNegative=-2` comes from the rule choosing the positive direction at exact halves. The two `BigDecimal` rounding modes show different policies for the digit 5.

## 6. Which API Should You Use When?

| Problem | Suggested API | Additional Checks Needed |
| --- | --- | --- |
| Magnitude of difference, drop sign | `Math.abs` | `MIN_VALUE` of `int`/`long` |
| Integer absolute value, overflow unacceptable | `Math.absExact` | Catch/propagate `ArithmeticException` |
| Floating-point power | `Math.pow` | `NaN`, infinity, `double` precision error |
| Square root of non-negative number | `Math.sqrt` | Negative input gives `NaN` |
| Round to nearest per `Math` | `Math.round` | Half-toward-positive rule, return type |
| Always round down / up | `Math.floor` / `Math.ceil` | Negative numbers and `double` type |
| Half-to-even rounding | `Math.rint` | Return type `double` |
| Currency requiring fixed decimal places | `BigDecimal.setScale` | Choose `RoundingMode` per business logic |

**Do not cast `double` to `int` to "round"**: casting a floating-point number to an integer truncates the fractional part toward 0, which is not equivalent to `Math.round` or `Math.floor`. Monetary or exact-decimal calculations must explicitly specify precision, rather than merely calling `Math.round(x * 100) / 100.0` and assuming binary error is avoided.

## 7. Practice Exercises

**Exercise 1.** Compute `Math.abs(-25)` and `Math.abs(-3.75)`. What types do they return?

**Exercise 2.** Why does `Math.abs(Integer.MIN_VALUE)` stay negative? Write two ways to handle it: converting to `long` beforehand, or detecting the error with `Math.absExact`.

**Exercise 3.** Predict `Math.pow(2, 5)`, `Math.pow(4, -1)`, and `Math.pow(-2, 0.5)`. What type are the results?

**Exercise 4.** Compare `Math.round(-2.5)`, `Math.floor(-2.5)`, `Math.ceil(-2.5)`, and `Math.rint(2.5)`. Pay attention to the rule at exact half values.

**Exercise 5.** Choose an appropriate `RoundingMode` for decimal price quotes with two decimal places; explain why the rounding policy must be documented before implementation.

### Key Takeaways

`Math.abs` computes absolute value but has an exception for the minimum value of `int`/`long`; `Math.pow` returns `double` and can carry error/`NaN`. `Math.round` rounds to nearest (exact halves toward positive infinity), while `Math.floor` and `Math.ceil` always go toward negative/positive infinity; `Math.rint` picks the even integer at exact halves. Choose the method according to the **data type and rounding policy** you actually need.