# Distinguishing Floating-Point Division by Zero from Integer Division by Zero in Java

## 1. Learning Objectives

In Java, even with the same division operator `/` and a visible denominator of `0`, the result can be **completely different depending on the operand types**:

- **Integer division** with a divisor of 0 (such as `int` or `long`) **throws `ArithmeticException` at runtime**.
- **Floating-point division** with `float` or `double` does not automatically throw `ArithmeticException` merely because the divisor is 0. Under the IEEE 754 semantics specified by Java, the result can be **`Infinity`, `-Infinity`, or `NaN`**.
- **`%` (remainder)** also differs: integer remainder with 0 throws `ArithmeticException`; floating-point remainder with 0 produces `NaN`.
- An operation involving both an integer and a floating-point number can undergo **numeric promotion** to `float`/`double`, so you cannot predict the outcome solely from the numerator's type.
- A `BigDecimal` object does not use the division rules of primitive `float`/`double`: dividing by `BigDecimal.ZERO` throws `ArithmeticException`.

This lesson belongs to **Java core — exception / Runtime Exceptions**, so beyond predicting the result, you need to know *when an exception is thrown to be caught*, *when no exception is thrown yet a non-finite result is returned*, and *how to check properly before using the result*.

After this lesson, you will be able to distinguish operand types, the sign of zero, `NaN` propagation rules, remainder operations, checks using `Double.isFinite`/`isNaN`, and common mistakes when writing `try/catch` for division.

Examples use Java 17+; each complete program has a filename, `javac`/`java` commands, and deterministic `stdout`. Snippets intended only for illustration are explicitly noted.

## 2. Core Rules in One Table

| Expression | Operation Type | Runtime Result |
| --- | --- | --- |
| `7 / 0` | `int` integer division | Throws `ArithmeticException` |
| `7L / 0L` | `long` integer division | Throws `ArithmeticException` |
| `7 % 0` | `int` integer remainder | Throws `ArithmeticException` |
| `7.0 / 0.0` | `double` division | `Infinity` |
| `-7.0 / 0.0` | `double` division | `-Infinity` |
| `7.0 / -0.0` | `double` division | `-Infinity` |
| `0.0 / 0.0` | `double` division | `NaN` |
| `0.0f / 0.0f` | `float` division | `NaN` |
| `7.0 % 0.0` | `double` remainder | `NaN` |
| `7 / 0.0` | `double` division after promotion | `Infinity` |
| `7.0 / 0` | `double` division after promotion | `Infinity` |
| `7 / 2` | Integer division | `3`, fractional part is truncated |
| `7 / 2.0` | `double` division | `3.5` |

**Key takeaway:** Java determines division semantics based on the **operand types after binary numeric promotion**. It is not the case that "a denominator of 0 always produces `ArithmeticException`."

The phrase "floating-point division" in this lesson refers to primitive **`float` and `double`** operands, and does not imply that all decimal representation classes such as `BigDecimal` share the same behavior.

## 3. Integer Division by 0: `ArithmeticException`

`int` and `long` perform integer division. According to the JLS, if **the right-hand operand after type conversion has an integer value of 0**, the `/` operator throws `ArithmeticException`. The same rule applies to integer `%`.

Example:

```java
int numerator = 10;
int denominator = 0;
int value = numerator / denominator; // Throws ArithmeticException.
```

This is an illustrative snippet. `value` receives no value because the expression on the right-hand side does not complete normally.

### Runnable Program: Integer Division Cases

Create the file **`IntegerZeroDivisionDemo.java`**:

```java
public class IntegerZeroDivisionDemo {
    static void divideInt(int numerator, int denominator) {
        try {
            System.out.println("int=" + (numerator / denominator));
        } catch (ArithmeticException failure) {
            System.out.println("int error=" + failure.getMessage());
        }
    }

    static void divideLong(long numerator, long denominator) {
        try {
            System.out.println("long=" + (numerator / denominator));
        } catch (ArithmeticException failure) {
            System.out.println("long error=" + failure.getMessage());
        }
    }

    static void remainderInt(int numerator, int denominator) {
        try {
            System.out.println("remainder=" + (numerator % denominator));
        } catch (ArithmeticException failure) {
            System.out.println("remainder error=" + failure.getMessage());
        }
    }

    public static void main(String[] args) {
        divideInt(10, 2);
        divideInt(10, 0);
        divideLong(10L, 0L);
        remainderInt(10, 0);
    }
}
```

Compile and run:

```bash
javac IntegerZeroDivisionDemo.java
java IntegerZeroDivisionDemo
```

`stdout`:

```text
int=5
int error=/ by zero
long error=/ by zero
remainder error=/ by zero
```

**Explanation:**

1. `10 / 2` produces `5`.
2. When calling `divideInt(10, 0)`, integer division has no valid result; `catch (ArithmeticException)` executes.
3. `long` is also subject to the integer division-by-zero rule; there is no "infinity" value for integers.
4. `10 % 0` also throws `ArithmeticException`. It does **not** return `0` or `NaN` like the floating-point `%` operator.
5. `failure.getMessage()` for integer division by zero used by the JDK in this example is `/ by zero`. Do not build business logic around the message string; rely on the exception type and input data instead.

### Is `ArithmeticException` Checked or Unchecked?

`ArithmeticException` extends `RuntimeException`, so it is an **unchecked exception**. You are not required to declare `throws ArithmeticException` in a method performing integer division:

```java
static int divide(int a, int b) {
    return a / b;
}
```

This is a valid Java method. If `b == 0`, it still throws at runtime. "Unchecked" does **not** mean "cannot happen"; it only means the compiler does not require `try/catch` or `throws`.

### Integer Overflow Differs from Division by Zero

A special case:

```java
int value = Integer.MIN_VALUE / -1;
System.out.println(value);
```

This is a valid snippet; the result is `-2147483648` due to the special overflow rule of integer division. It does **not** throw `ArithmeticException` just because the mathematical result exceeds the `int` range. Do not equate integer overflow with division by zero.

## 4. Dividing `float`/`double` by 0: Special Results, No Automatic Throw

Java uses IEEE 754-compatible floating-point semantics for primitive `float`/`double` types. For floating-point division:

- A **non-zero, finite** numerator divided by zero produces infinity with the appropriate sign.
- Zero divided by zero produces `NaN` (*Not a Number*).
- Operations involving `NaN` or infinity follow additional special rules.
- Java **does not throw an exception at the floating-point `/` operation** merely because infinity or `NaN` is produced.

### Runnable Program: Floating-Point Results

Create the file **`FloatingZeroDivisionDemo.java`**:

```java
public class FloatingZeroDivisionDemo {
    public static void main(String[] args) {
        double positive = 7.0 / 0.0;
        double negative = -7.0 / 0.0;
        double negativeZero = 7.0 / -0.0;
        double undefined = 0.0 / 0.0;
        float singlePrecision = 7.0f / 0.0f;

        System.out.println("positive=" + positive);
        System.out.println("negative=" + negative);
        System.out.println("negative zero=" + negativeZero);
        System.out.println("zero over zero=" + undefined);
        System.out.println("float=" + singlePrecision);

        System.out.println("isInfinite="
                + Double.isInfinite(positive));
        System.out.println("isNaN="
                + Double.isNaN(undefined));
    }
}
```

```bash
javac FloatingZeroDivisionDemo.java
java FloatingZeroDivisionDemo
```

`stdout`:

```text
positive=Infinity
negative=-Infinity
negative zero=-Infinity
zero over zero=NaN
float=Infinity
isInfinite=true
isNaN=true
```

All divisions in the program complete **without automatically throwing `ArithmeticException`**. Java produces special values of type `double` or `float`.

### Why Do `Infinity` and `NaN` Exist?

Under floating-point semantics:

- `7.0 / +0.0` → `+Infinity`.
- `-7.0 / +0.0` → `-Infinity`.
- `7.0 / -0.0` → `-Infinity`.
- `0.0 / 0.0` → `NaN`.
- `-0.0 / -0.0` is also `NaN`.

`Infinity` is not a new data type: it is **a special value of `double` or `float`**. Similarly, `NaN` is not an exception, but a special floating-point value.

You can use `Double.POSITIVE_INFINITY`, `Double.NEGATIVE_INFINITY`, `Double.NaN`, and the corresponding `Float` constants to represent these values explicitly.

**Do not rely on checking `result == Double.NaN`** to detect NaN; equality comparisons with NaN always return `false`. Use `Double.isNaN(result)` or `Float.isNaN(result)`.

## 5. Negative Zero (`-0.0`) Flips the Sign of the Result

Java integer types do not have a `-0` value distinct from `0`. For integers:

```java
int zero = -0;
System.out.println(zero == 0);
```

This is a valid snippet and prints `true`.

However, `float` and `double` have distinct **+0.0** and **-0.0** representations. Although `0.0 == -0.0` returns `true` in standard numeric comparison, the sign of zero affects division.

### Runnable Program: Sign of Zero

Create the file **`SignedZeroDemo.java`**:

```java
public class SignedZeroDemo {
    public static void main(String[] args) {
        double plusZero = 0.0;
        double minusZero = -0.0;

        System.out.println("zero equal="
                + (plusZero == minusZero));
        System.out.println("1/+0="
                + (1.0 / plusZero));
        System.out.println("1/-0="
                + (1.0 / minusZero));
        System.out.println("-1/-0="
                + (-1.0 / minusZero));
        System.out.println("Double.compare="
                + Double.compare(minusZero, plusZero));
    }
}
```

```bash
javac SignedZeroDemo.java
java SignedZeroDemo
```

`stdout`:

```text
zero equal=true
1/+0=Infinity
1/-0=-Infinity
-1/-0=Infinity
Double.compare=-1
```

- `==` treats both zeros as equal in floating-point comparison.
- `1.0 / +0.0` and `1.0 / -0.0` have results with opposite signs.
- `Double.compare(-0.0, +0.0)` defines a consistent ordering for special values and returns a negative number (specifically `-1` in this program).
- A signed zero can arise from arithmetic operations, underflow, or a literal. Never assume every expression that compares equal to 0 represents `+0.0`.

If your algorithm does not need to distinguish the sign of zero, you can check the denominator with `denominator == 0.0` to catch both `+0.0` and `-0.0`. If the sign of zero has physical or numerical significance, a different policy must be designed.

## 6. The `/` Operator Is Determined by **Numeric Promotion**, Not Just Literals

A common mistake is seeing an `int` numerator and concluding "this is integer division." Java first performs **binary numeric promotion** on arithmetic operands.

Useful summary:

1. If either operand is of type `double`, both are converted to `double`.
2. Otherwise, if either operand is of type `float`, both are converted to `float`.
3. Otherwise, if either operand is of type `long`, both are converted to `long`.
4. Otherwise (smaller integer types such as `byte`, `short`, `char`), both are converted to `int`.

Therefore:

```java
int a = 7;
int b = 0;

double first = a / b;       // STILL int division -> ArithmeticException.
double second = a / 0.0;   // double division -> Infinity.
double third = (double) a / b; // double division -> Infinity.
```

This is an **illustrative snippet**. Assigning the result to a `double` variable **cannot change how the expression `a / b` was evaluated**. To force floating-point division, at least one operand must be converted to `float`/`double` *before the division*.

### Runnable Program: Verifying Operand Types

Create the file **`NumericPromotionDemo.java`**:

```java
public class NumericPromotionDemo {
    public static void main(String[] args) {
        int seven = 7;
        int two = 2;
        int zero = 0;

        double assignedAfterIntegerDivide = seven / two;
        double floatingDivide = seven / 2.0;
        double castBeforeDivide = (double) seven / two;

        System.out.println("int into double="
                + assignedAfterIntegerDivide);
        System.out.println("with double="
                + floatingDivide);
        System.out.println("cast before="
                + castBeforeDivide);

        try {
            double invalid = seven / zero;
            System.out.println(invalid);
        } catch (ArithmeticException failure) {
            System.out.println("int denominator zero: exception");
        }

        System.out.println("double denominator zero="
                + (seven / 0.0));
        System.out.println("float denominator zero="
                + (seven / 0.0f));
    }
}
```

```bash
javac NumericPromotionDemo.java
java NumericPromotionDemo
```

`stdout`:

```text
int into double=3.0
with double=3.5
cast before=3.5
int denominator zero: exception
double denominator zero=Infinity
float denominator zero=Infinity
```

Analyzing two easily confused lines:

- `double assignedAfterIntegerDivide = seven / two;`: because both operands are `int`, the result is `3` first, and only then is it converted to `3.0` for assignment to `double`.
- `double floatingDivide = seven / 2.0;`: `2.0` is `double`, so `seven` is promoted; the result is `3.5`.

Similarly, `(double) (seven / two)` yields `3.0` because the cast happens **after the integer division**; `((double) seven) / two` performs floating-point division. Cast placement matters.

### `byte`/`short`/`char` and `long`

- `byte`, `short`, and `char` are promoted to `int` when used with `/` or `%` together (unless a wider type is present), so dividing by zero still throws.
- `long` divided by a `long` zero still throws `ArithmeticException`.
- `long` divided by `0.0` becomes `double` division and produces infinity according to the sign.
- Literal types matter: `0` is `int`, `0L` is `long`, `0.0` defaults to `double`, and `0.0f` is `float`.

Do not confuse `0.0f` with `0`: the mathematical value "zero" is the same, but **the operation type and whether an exception is thrown** differ.

## 7. The Remainder Operator `%`: Same Type-Distinction Rules

`%` does not apply only to integers. Java also supports floating-point remainder; however, behavior with a zero divisor still splits into two groups.

- `int % 0`, `long % 0L` → throws `ArithmeticException`.
- `double % 0.0`, `float % 0.0f` → `NaN`.
- For floating-point values, Java's `%` operator uses its own remainder rule; it is **not identical** to `Math.IEEEremainder`.

### Runnable Program: `%` with Zero

Create the file **`RemainderZeroDemo.java`**:

```java
public class RemainderZeroDemo {
    public static void main(String[] args) {
        try {
            int result = 5 % 0;
            System.out.println(result);
        } catch (ArithmeticException failure) {
            System.out.println("integer remainder: exception");
        }

        double floatingRemainder = 5.0 % 0.0;
        float floatRemainder = 5.0f % 0.0f;

        System.out.println("double remainder="
                + floatingRemainder);
        System.out.println("float remainder="
                + floatRemainder);
        System.out.println("isNaN="
                + Double.isNaN(floatingRemainder));

        System.out.println("finite percent infinity="
                + (5.0 % Double.POSITIVE_INFINITY));
    }
}
```

```bash
javac RemainderZeroDemo.java
java RemainderZeroDemo
```

`stdout`:

```text
integer remainder: exception
double remainder=NaN
float remainder=NaN
isNaN=true
finite percent infinity=5.0
```

Another rule: the floating-point `%` operator with an **infinite divisor** and a finite dividend returns the dividend; but when the divisor is **zero**, it returns `NaN`. Do not mechanically carry integer `%` assumptions over to `double`.

### `Math.IEEEremainder` Differs from `%`

Java provides `Math.IEEEremainder(double f1, double f2)`. It uses the IEEE rule of selecting the nearest integer quotient (ties to even), whereas `%` follows the remainder rule tied to division with truncation. They can return different results for the same two ordinary numbers.

For example, `5.0 % 3.0` is `2.0`, whereas `Math.IEEEremainder(5.0, 3.0)` is `-1.0`. Neither makes integer division by zero valid; they are distinct floating-point operations.

## 8. `NaN` Is Not an Exception, and Comparing with `NaN` Is Error-Prone

`NaN` is a special `float`/`double` value used for floating-point calculations that have no ordinary numeric result, such as `0.0 / 0.0`.

Comparisons:

- `Double.NaN == Double.NaN` → `false`.
- `Double.NaN != Double.NaN` → `true`.
- `Double.NaN < 1.0`, `Double.NaN > 1.0`, and `Double.NaN == 1.0` → all `false`.
- `Double.isNaN(value)` is the proper API to detect `NaN`.

### Runnable Program: Comparisons and Check APIs

Create the file **`NaNInfinityChecksDemo.java`**:

```java
public class NaNInfinityChecksDemo {
    public static void main(String[] args) {
        double positiveInfinity = 1.0 / 0.0;
        double undefined = 0.0 / 0.0;
        double ordinary = 5.0 / 2.0;

        System.out.println("NaN == NaN: "
                + (undefined == undefined));
        System.out.println("NaN != NaN: "
                + (undefined != undefined));
        System.out.println("NaN > 1: " + (undefined > 1.0));

        System.out.println("isNaN=" + Double.isNaN(undefined));
        System.out.println("isInfinite="
                + Double.isInfinite(positiveInfinity));

        System.out.println("infinity finite="
                + Double.isFinite(positiveInfinity));
        System.out.println("NaN finite="
                + Double.isFinite(undefined));
        System.out.println("ordinary finite="
                + Double.isFinite(ordinary));
    }
}
```

```bash
javac NaNInfinityChecksDemo.java
java NaNInfinityChecksDemo
```

`stdout`:

```text
NaN == NaN: false
NaN != NaN: true
NaN > 1: false
isNaN=true
isInfinite=true
infinity finite=false
NaN finite=false
ordinary finite=true
```

`Double.isFinite(x)` returns `true` only when `x` is **neither** infinite **nor** `NaN`. It is a clean check when an application only accepts finite floating-point results.

The corresponding `Float.isNaN`, `Float.isInfinite`, and `Float.isFinite` APIs serve the `float` type.

### Why Is `try/catch (ArithmeticException)` Useless for Detecting NaN?

Because **no `ArithmeticException` is thrown by floating-point `/` with zero**, that handler will never execute. Detect abnormal values using the `NaN`/infinity check APIs and **define your application's own policy**, rather than relying on an exception that Java does not throw automatically.

## 9. When Does Infinity Appear Even **Without** Dividing by 0?

Do not conclude that "seeing `Infinity` definitely means the denominator was 0." Floating-point numbers have **representation limits**; calculations can overflow the finite range.

Example:

```java
double overflow = Double.MAX_VALUE * 2.0;
double veryLargeQuotient =
        Double.MAX_VALUE / Double.MIN_VALUE;

System.out.println(overflow);
System.out.println(veryLargeQuotient);
```

This is valid Java and prints:

```text
Infinity
Infinity
```

`Double.MIN_VALUE` is the **smallest positive non-zero `double` value** (subnormal), not the finite negative number with the largest absolute magnitude. Therefore, the denominator in the second division is **not zero**, yet the mathematical result is too large to represent as a finite `double`.

Similarly:

- `Math.sqrt(-1.0)` produces `NaN` without any division by zero.
- Certain operations with infinity can produce `NaN`, such as `Double.POSITIVE_INFINITY - Double.POSITIVE_INFINITY`.
- The product `0.0 * Double.POSITIVE_INFINITY` is `NaN`.

When a floating-point result is business-critical, check **both input validity** and **the final result**. Checking only whether the denominator is 0 is not enough to guarantee a finite result.

## 10. Is Checking the Denominator with `== 0.0` Enough?

If the goal is to **reject `+0.0` and `-0.0` specifically**, check:

```java
if (denominator == 0.0) {
    throw new IllegalArgumentException("denominator must not be zero");
}
```

This is an illustrative snippet with a `double` variable `denominator`. Because `+0.0 == -0.0` is `true`, both signs are rejected.

However, there are limitations:

- `denominator = Double.NaN`: the expression `denominator == 0.0` is `false`, yet division typically produces NaN.
- `denominator = Double.POSITIVE_INFINITY`: not equal to zero; can yield a finite zero result in some divisions.
- `numerator` is already `NaN` or infinity: the result may not be finite.
- `denominator` is extremely small but **non-zero**: division can overflow to infinity.
- Checking `Math.abs(denominator) < epsilon` is **a numerical threshold policy**, not strictly equivalent to "division by zero." The threshold must be based on data scale and application requirements.

Therefore, if the problem requires **never returning NaN or infinity**, check `Double.isFinite(...)` on both inputs and the result.

## 11. Explicitly Throwing Exceptions for Floating-Point Division When Business Logic Requires It

Java does not automatically throw on floating-point division by zero, but **an application can intentionally throw** an exception to enforce its contract.

For example, the following method rejects all non-finite inputs, all zero denominators, and all non-finite results.

Create the file **`FiniteDivisionDemo.java`**:

```java
public class FiniteDivisionDemo {
    static double divideFinite(double numerator, double denominator) {
        if (!Double.isFinite(numerator)
                || !Double.isFinite(denominator)) {
            throw new IllegalArgumentException(
                    "inputs must be finite");
        }
        if (denominator == 0.0) {
            throw new ArithmeticException(
                    "floating denominator is zero");
        }

        double result = numerator / denominator;
        if (!Double.isFinite(result)) {
            throw new ArithmeticException(
                    "floating result is not finite");
        }
        return result;
    }

    public static void main(String[] args) {
        System.out.println("valid="
                + divideFinite(5.0, 2.0));

        try {
            divideFinite(1.0, 0.0);
        } catch (ArithmeticException failure) {
            System.out.println("zero="
                    + failure.getMessage());
        }

        try {
            divideFinite(Double.MAX_VALUE, Double.MIN_VALUE);
        } catch (ArithmeticException failure) {
            System.out.println("overflow="
                    + failure.getMessage());
        }

        try {
            divideFinite(Double.NaN, 2.0);
        } catch (IllegalArgumentException failure) {
            System.out.println("invalid="
                    + failure.getMessage());
        }
    }
}
```

```bash
javac FiniteDivisionDemo.java
java FiniteDivisionDemo
```

`stdout`:

```text
valid=2.5
zero=floating denominator is zero
overflow=floating result is not finite
invalid=inputs must be finite
```

**Essential distinction:** `ArithmeticException` here is thrown **by validation code written by the developer**. It is not an exception automatically generated by the `double / double` operator. Another library might choose `IllegalArgumentException`, a dedicated result object, or returning IEEE values; that is part of the API design contract.

### Which Check Should You Choose?

| Requirement | Appropriate Check |
| --- | --- |
| Disallow zero denominator, accept other IEEE results | `denominator == 0.0` |
| Disallow `NaN` or infinity inputs | `Double.isFinite(numerator)` and `Double.isFinite(denominator)` |
| Require the final result to be finite | `Double.isFinite(result)` |
| Need to distinguish negative/positive zero | Check the sign via `Math.copySign` or raw bits when truly necessary |
| Need to treat values near zero according to business scale | Designed and tested relative/absolute threshold |
| Financial calculations with decimal precision and rounding policy | Consider `BigDecimal` with an appropriate `MathContext`/`RoundingMode` |

Choosing the exception, message, return type, and threshold cannot be based solely on the operator. It is part of the API contract and numerical accuracy requirements.

## 12. `BigDecimal` and `BigInteger`: `double` Infinity Rules Do Not Apply

Beginners often think of "decimal numbers" as a single category. In reality, **`BigDecimal` is an exact scaled decimal arithmetic class**, not a binary floating-point type like `double`.

Example:

```java
java.math.BigDecimal.ONE.divide(java.math.BigDecimal.ZERO);
```

This is a Java snippet; it throws `ArithmeticException`. It does **not** return a `BigDecimal` representing infinity, because the `BigDecimal` API does not have the same set of infinity/NaN values as `double`.

Similarly, `BigInteger.ONE.divide(BigInteger.ZERO)` throws `ArithmeticException`.

### Runnable Program: Comparing with `BigDecimal`

Create the file **`BigDecimalDivisionDemo.java`**:

```java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;

public class BigDecimalDivisionDemo {
    public static void main(String[] args) {
        try {
            System.out.println(
                    BigDecimal.ONE.divide(BigDecimal.ZERO));
        } catch (ArithmeticException failure) {
            System.out.println("BigDecimal divide zero: exception");
        }

        try {
            System.out.println(
                    BigInteger.ONE.divide(BigInteger.ZERO));
        } catch (ArithmeticException failure) {
            System.out.println("BigInteger divide zero: exception");
        }

        BigDecimal one = BigDecimal.ONE;
        BigDecimal three = new BigDecimal("3");

        System.out.println("rounded="
                + one.divide(three, 2, RoundingMode.HALF_UP));
        System.out.println("double="
                + (1.0 / 0.0));
    }
}
```

```bash
javac BigDecimalDivisionDemo.java
java BigDecimalDivisionDemo
```

`stdout`:

```text
BigDecimal divide zero: exception
BigInteger divide zero: exception
rounded=0.33
double=Infinity
```

**Another `BigDecimal` note:** `BigDecimal.ONE.divide(new BigDecimal("3"))` **can also throw `ArithmeticException`** if you use the overload that requires an exact decimal representation without a finite result. When dividing `1/3`, you must choose a rounding policy such as `RoundingMode` or `MathContext`. This case is **non-terminating decimal expansion** (cannot be represented exactly with a finite number of decimal digits), which is completely different from division by 0.

Do not use `BigDecimal` expecting it to "automatically produce NaN" when dividing by 0. Decide on the business policy and catch/check errors using the appropriate API.

## 13. Proper `try/catch` for the Two Division Families

Integer division:

```java
static int integerDivide(int numerator, int denominator) {
    if (denominator == 0) {
        throw new IllegalArgumentException("denominator must not be zero");
    }
    return numerator / denominator;
}
```

This is a valid method. You can reject upfront with a guard or let `ArithmeticException` from the division propagate and handle it at an appropriate boundary. Using a guard allows a domain-specific message; you do not necessarily have to catch every `ArithmeticException`, as it can also arise from other operations.

Floating-point division:

```java
static double floatingDivide(double numerator, double denominator) {
    double result = numerator / denominator;
    if (!Double.isFinite(result)) {
        throw new ArithmeticException("result is not finite");
    }
    return result;
}
```

This is an **application policy** that chooses to throw when the result is non-finite. Unlike `integerDivide`, the expression `numerator / denominator` itself does not throw `ArithmeticException` for a zero denominator.

If you only need IEEE semantics for scientific computing, you can **intentionally allow** infinity/NaN and handle them at the mathematical layer. In billing systems, numerical reporting, or input validation, it is usually necessary to reject non-finite values and have dedicated rounding/precision strategies.

### Why Is Catching `ArithmeticException` Around `1.0 / 0.0` Usually Pointless?

```java
try {
    double result = 1.0 / 0.0;
    System.out.println(result);
} catch (ArithmeticException failure) {
    System.out.println("caught");
}
```

This is a valid snippet. It prints `Infinity` and **does not print `caught`**. The catch block is syntactically allowed because `ArithmeticException` is unchecked, but that does not make floating-point `/` start throwing exceptions.

Conversely, with `int numerator = 1; int denominator = 0;`, the statement `numerator / denominator` will enter the catch branch if one is present.

## 14. `Double.NaN` in Conditions and Loops

An algorithm using a check like:

```java
if (value > threshold) {
    // ...
}
```

may skip a NaN value not because the value is "safe," but because the `>` comparison with NaN returns `false`. Similarly:

```java
if (value <= threshold) {
    // ...
}
```

can also return `false` for NaN. Neither condition covers all floating-point values, even though from ordinary real-number intuition you might expect one of the two to be true.

If inputs come from external data, sensors, or a previous division, **handle NaN explicitly** before applying thresholds if business requirements need every state classified.

Example snippet:

```java
if (Double.isNaN(value)) {
    throw new IllegalArgumentException("measurement is NaN");
}
if (Double.isInfinite(value)) {
    throw new IllegalArgumentException("measurement is infinite");
}
```

This is especially important in validation systems: if you only check `value < min || value > max`, NaN can slip through because both comparisons are false. Using `Double.isFinite(value)` is often an appropriate gate before threshold comparisons.

## 15. Mistakes from Casting and Evaluation Order

Several cases need to be distinguished:

```java
int numerator = 1;
int denominator = 0;

// A: integer division first, then cast -> throws ArithmeticException.
double a = (double) (numerator / denominator);

// B: convert numerator to double before division -> Infinity.
double b = (double) numerator / denominator;

// C: convert denominator to double before division -> Infinity.
double c = numerator / (double) denominator;
```

This is an **illustrative snippet**: statement A throws and prevents subsequent statements from running if there is no handler. Forms B and C only produce Infinity when actually executed.

If you write:

```java
int result = (int) (1.0 / 0.0);
System.out.println(result);
```

This is a valid snippet and prints `2147483647` (`Integer.MAX_VALUE`) according to the **narrowing primitive conversion** rule from `+Infinity` to `int`. It does **not** automatically produce `ArithmeticException`. Converting `NaN` to `int` yields `0` under the conversion rules.

Learning point: *once a division has been performed as `double`, casting the result to `int` afterward does not turn it into integer division*. However, narrowing can lose precision or saturate to the integer bounds, which is dangerous if the application assumes the value is still valid.

### Runnable Program: Casting After Floating-Point Division

Create the file **`FloatingCastDemo.java`**:

```java
public class FloatingCastDemo {
    public static void main(String[] args) {
        double positiveInfinity = 1.0 / 0.0;
        double negativeInfinity = -1.0 / 0.0;
        double notANumber = 0.0 / 0.0;

        System.out.println("double positive=" + positiveInfinity);
        System.out.println("to int positive=" + (int) positiveInfinity);
        System.out.println("to int negative=" + (int) negativeInfinity);
        System.out.println("to int NaN=" + (int) notANumber);
    }
}
```

```bash
javac FloatingCastDemo.java
java FloatingCastDemo
```

`stdout`:

```text
double positive=Infinity
to int positive=2147483647
to int negative=-2147483648
to int NaN=0
```

These cast results **do not prove that the original division was business-valid**. If you need to reject infinity/NaN, check before converting to an integer to avoid masking a non-finite condition.

## 16. Common Mistakes and How to Fix Them

**"Any division by 0 in Java throws `ArithmeticException`."** False. Only **integer** division/remainder and certain specific APIs (e.g., BigDecimal) follow the throwing rule; the floating-point `/` operator uses infinity/NaN.

**"`1.0 / 0.0` always throws because the denominator is 0."** False. It produces `Infinity`.

**"`0.0 / 0.0` is 0."** False. It produces `NaN`.

**"`0 / 0` also returns NaN."** False. Both operands are `int`, so it throws `ArithmeticException`.

**"`1 / 0.0` has an int numerator, so it throws."** False. There is a `double` on the right-hand operand, so promotion to `double` occurs; the result is `Infinity`.

**"Assigning `double x = intA / intB` will automatically perform floating-point division."** False. The `int` division runs **before** the conversion for assignment.

**"Negative zero and positive zero are identical in all double operations."** False. `==` treats them as equal, but `1.0 / -0.0` and `1.0 / +0.0` have opposite signs.

**"`try/catch (ArithmeticException)` will catch a NaN result."** False. NaN is a value, not a throwable.

**"`Double.NaN == Double.NaN` is true because both sides are the same."** False. Equality with NaN in floating-point arithmetic returns false.

**"You can check for NaN using `value == Double.NaN`."** False. Use `Double.isNaN(value)`.

**"`Infinity` only appears when dividing by zero."** False. Floating-point overflow also produces infinity.

**"Checking `denominator != 0.0` is enough to guarantee a finite result."** False. NaN, infinity, and overflow can still occur from other inputs.

**"`BigDecimal` is a floating-point/decimal type, so dividing by `BigDecimal.ZERO` gives Infinity."** False. `BigDecimal.divide` throws `ArithmeticException` when dividing by zero.

**"`BigDecimal.divide` only throws when dividing by zero."** False. A division with a non-terminating decimal expansion without appropriate rounding can also throw.

**"`int` divided by 0 is a checked exception, so you must write `throws ArithmeticException`."** False. `ArithmeticException` is unchecked.

**"`5.0 % 0.0` throws `ArithmeticException` just like `5 % 0`."** False. The floating-point form produces NaN.

**"`(double) (1 / 0)` avoids the integer division error."** False. Integer division is performed before the cast.

**"Casting Infinity to int will throw a division-by-zero exception."** False. Floating-point-to-integer conversion has its own rules, which can yield boundary values or 0.

**"`Double.MIN_VALUE` is the smallest negative number."** False. It is the smallest positive non-zero `double`; distinguish it from `-Double.MAX_VALUE`.

## 17. Self-Check Exercises

### Exercise 1: Identify the Division Type

Predict:

```java
int a = 6;
int b = 0;
double x = a / b;
```

**Answer:** throws `ArithmeticException`, because `a / b` is `int` division. Declaring `x` as `double` does not change the type of division that occurred.

### Exercise 2: Adding a `.0` Literal

```java
int a = 6;
double x = a / 0.0;
```

**Answer:** `Infinity` due to promotion to `double`.

### Exercise 3: Zero Divided by Zero

```java
double x = 0.0 / -0.0;
```

**Answer:** `NaN`, no exception thrown.

### Exercise 4: Sign of Zero

```java
double x = -6.0 / -0.0;
```

**Answer:** `Infinity`.

### Exercise 5: Integer Remainder

```java
int remainder = 6 % 0;
```

**Answer:** `ArithmeticException`.

### Exercise 6: Floating Remainder

```java
double remainder = 6.0 % 0.0;
```

**Answer:** `NaN`.

### Exercise 7: Cast Before or After?

```java
int a = 1;
int b = 2;
System.out.println((double) (a / b));
System.out.println((double) a / b);
```

**Answer:** the first line prints `0.0`, the second prints `0.5`.

### Exercise 8: Checking NaN

```java
double x = 0.0 / 0.0;
System.out.println(x == x);
System.out.println(Double.isNaN(x));
```

**Answer:** `false` then `true`.

### Exercise 9: Infinity Not Caused by Zero

```java
double x = Double.MAX_VALUE * 2.0;
```

**Answer:** `Infinity`, even with no division.

### Exercise 10: BigDecimal

```java
java.math.BigDecimal.ONE.divide(java.math.BigDecimal.ZERO);
```

**Answer:** `ArithmeticException`, not infinity.

### Exercise 11: Converting a Special Result

```java
System.out.println((int) (0.0 / 0.0));
```

**Answer:** `0`. This is the result of narrowing NaN to int, not the result of floating-point division.

### Exercise 12: API Requiring Finite Results

If the requirement is "must never return infinity or NaN," is checking the denominator with `denominator == 0.0` **enough?** **No.** Check the finiteness of both inputs and the result, and choose an appropriate policy for overflow/underflow.

### Exercise 13: Checked or Unchecked?

Is `ArithmeticException` checked or unchecked? **Unchecked**, because it extends `RuntimeException`.

### Exercise 14: Sign of Zero

`0.0 == -0.0` is `true`. So are `1.0 / 0.0` and `1.0 / -0.0` the same? **No**: one results in `Infinity`, the other in `-Infinity`.

### Exercise 15: Blocking NaN from Threshold Checks

With `double value = Double.NaN`, does the expression `value < 0 || value > 100` detect the invalid value? **No**, both comparisons are false. You should also use `Double.isFinite(value)` when only finite numbers are accepted.

## 18. Official Java 17 Documentation

- [Java Language Specification 17 — `15.17.2 Division Operator /](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.17.2): integer division, floating-point division, and zero.
- [Java Language Specification 17 — `15.17.3 Remainder Operator %](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.17.3): integer and floating-point remainder.
- [Java Language Specification 17 — `5.6 Numeric Contexts](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.6): numeric promotion and operand types.
- [Java Language Specification 17 — `4.2.3 Floating-Point Types, Formats, and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.3): infinity, NaN, signed zero, and floating-point values.
- [Java Language Specification 17 — `5.1.3 Narrowing Primitive Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.3): converting NaN/infinity from float/double to integer types.
- [Java SE 17 — ArithmeticException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ArithmeticException.html): unchecked exception for illegal arithmetic conditions.
- [Java SE 17 — Double](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html): `isNaN`, `isInfinite`, `isFinite`, and special constants.
- [Java SE 17 — Float](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Float.html): checking and representing float values.
- [Java SE 17 — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): divide, rounding, and `ArithmeticException` errors.
- [Java SE 17 — Math.IEEEremainder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html#IEEEremainder(double,double)): comparison with the `%` operator.

**Remember:** For the `/` and `%` operators on Java **integer types**, a denominator of 0 causes `ArithmeticException` (unchecked). For `float`/`double`, operations use IEEE 754 semantics and can return `Infinity`, `-Infinity`, or `NaN` **without throwing an exception**. Consider operand types after numeric promotion, not just the literal `0`; use `Double.isNaN`/`Double.isInfinite`/`Double.isFinite` and an explicit validation policy if the application does not accept special values.
