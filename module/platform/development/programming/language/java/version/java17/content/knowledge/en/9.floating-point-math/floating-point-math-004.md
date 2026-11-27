# Floating-Point Numbers in Java 17: `NaN`, Infinity, and Signed Zero

Java has two commonly used primitive floating-point types: **`float`** (single precision, 32-bit) and **`double`** (double precision, 64-bit). They represent numbers according to the IEEE 754 floating-point standard, so their value domain is not limited to finite numbers. A `float` or `double` value can also be **NaN** (Not a Number), **positive infinity**, **negative infinity**, **positive zero** (`+0.0`), or **negative zero** (`-0.0`).

These special values can appear in calculations, division, math functions, values parsed from strings, or intermediate results. If a program only checks `value < 0` or `value == 0`, it may miss `NaN`, infinity, or the sign of zero. This lesson explains how these values behave in Java 17, how to detect them, and how to handle them appropriately in a program.

## 1. Special Values of `float` and `double`

Java provides constants in the two wrapper classes `Float` and `Double`:

| Value | `double` | `float` | Meaning |
| --- | --- | --- | --- |
| NaN | `Double.NaN` | `Float.NaN` | Result is not a meaningful real number under IEEE 754 operations. |
| Positive infinity | `Double.POSITIVE_INFINITY` | `Float.POSITIVE_INFINITY` | Infinity with a positive sign. |
| Negative infinity | `Double.NEGATIVE_INFINITY` | `Float.NEGATIVE_INFINITY` | Infinity with a negative sign. |
| Positive zero | `+0.0` or `0.0` | `+0.0f` or `0.0f` | Zero value with a positive sign bit. |
| Negative zero | `-0.0` | `-0.0f` | Zero value with a negative sign bit. |

The constants `NaN` and infinity are floating-point values, not `null`, not the string `"NaN"`, and not exceptions. Example:

```java
double notANumber = Double.NaN;
double positiveInfinity = Double.POSITIVE_INFINITY;
double negativeInfinity = Double.NEGATIVE_INFINITY;
double positiveZero = 0.0;
double negativeZero = -0.0;
```

`float` has similar special values, though with lower precision and a smaller finite range than `double`. In calculations involving floating-point numbers, Java may perform numeric conversions between `float` and `double`; pay attention to operand types and the result type.

## 2. What Is `NaN`?

`NaN` stands for **Not a Number**. It represents a result that is not a valid real number under floating-point operations, such as:

- `0.0 / 0.0`;
- `Double.POSITIVE_INFINITY - Double.POSITIVE_INFINITY`;
- `Double.POSITIVE_INFINITY / Double.POSITIVE_INFINITY`;
- `0.0 * Double.POSITIVE_INFINITY`;
- `Math.sqrt(-1.0)`.

Example:

```java
public class NaNDemo {
    public static void main(String[] args) {
        double a = 0.0 / 0.0;
        double b = Math.sqrt(-1.0);

        System.out.println(a); // NaN
        System.out.println(b); // NaN
        System.out.println(Double.isNaN(a)); // true
        System.out.println(Double.isNaN(b)); // true
    }
}
```

An operation producing `NaN` **does not necessarily throw an exception**. The program continues running and can carry this value through many subsequent calculations. Therefore, if a `NaN` result is not handled, it can propagate to display, storage, or business decisions.

### 2.1. Comparisons with `NaN`

This is a very important property: **`NaN` is not equal to itself, and all ordering comparisons with `NaN` return `false`**. Specifically, `==`, `<`, `>`, `<=`, and `>=` return `false`; the `!=` operator returns `true`.

```java
double value = Double.NaN;

System.out.println(value == value); // false
System.out.println(value != value); // true
System.out.println(value < 0.0);    // false
System.out.println(value > 0.0);    // false
System.out.println(value <= 0.0);   // false
System.out.println(value >= 0.0);   // false
```

Therefore, you cannot use `value == Double.NaN` to check for NaN:

```java
double result = 0.0 / 0.0;

if (result == Double.NaN) {
    System.out.println("NaN"); // Does not execute
}
```

Use the dedicated method:

```java
if (Double.isNaN(result)) {
    System.out.println("Result is NaN");
}
```

For `float`, use `Float.isNaN(value)`.

### 2.2. `NaN` Can Propagate Through Operations

In most floating-point arithmetic operations, if one operand is `NaN`, the result remains `NaN`:

```java
double invalid = Double.NaN;

System.out.println(invalid + 10);       // NaN
System.out.println(invalid * 2);        // NaN
System.out.println(Math.abs(invalid));  // NaN
System.out.println(Math.max(5.0, invalid)); // NaN
```

Once an invalid value appears, subsequent operations generally cannot recover a finite number on their own. You should identify the point of origin and define a handling policy instead of only checking at the end of the program.

### 2.3. `NaN` Is Not the Only Sign of Invalid Data

A `NaN` value may mean an undefined calculation, missing data represented by convention, or corrupted numeric input. Conversely, a finite value can still be invalid in the business domain, such as a temperature of `-500.0` or a ratio of `1.7` in a domain that only allows 0 to 1.

Therefore, distinguish:

- **Arithmetic validity:** is it NaN/infinity?
- **Business domain validity:** is the value within the range allowed by the application?
- **Data presence:** is data present or missing? Do not automatically use `NaN` as a substitute for every missing-data case.

## 3. Infinity: Positive Infinity and Negative Infinity

Floating-point numbers in Java can take two infinity values:

```java
double positive = Double.POSITIVE_INFINITY;
double negative = Double.NEGATIVE_INFINITY;

System.out.println(positive); // Infinity
System.out.println(negative); // -Infinity
System.out.println(Double.isInfinite(positive)); // true
System.out.println(Double.isInfinite(negative)); // true
```

Infinity can occur when an operation exceeds the finite representable range (overflow), or when dividing a non-zero floating-point number by a signed zero:

```java
double a = 1.0 / 0.0;
double b = -1.0 / 0.0;
double c = 1.0 / -0.0;

System.out.println(a); // Infinity
System.out.println(b); // -Infinity
System.out.println(c); // -Infinity
```

With floating-point operations, division by zero **is not like** integer division by zero. Integer division is explained in Section 5.

### 3.1. Checking for Infinity

Use `Double.isInfinite()` or `Float.isInfinite()`:

```java
double value = 1.0 / 0.0;

if (Double.isInfinite(value)) {
    System.out.println("Infinite value");
}
```

If you only need to know whether a value is finite, you can use `Double.isFinite()` or `Float.isFinite()`:

```java
double[] values = {
        12.5,
        Double.NaN,
        Double.POSITIVE_INFINITY,
        Double.NEGATIVE_INFINITY
};

for (double value : values) {
    System.out.println(value + " -> " + Double.isFinite(value));
}
```

`isFinite` returns `true` for finite numbers, including both `+0.0` and `-0.0`; it returns `false` for NaN and both infinities. This is often a concise input check when an algorithm only accepts finite numbers.

### 3.2. Selected Operations with Infinity

| Expression | Result |
| --- | --- |
| `Double.POSITIVE_INFINITY + 100.0` | `Infinity` |
| `Double.NEGATIVE_INFINITY - 100.0` | `-Infinity` |
| `Double.POSITIVE_INFINITY + Double.NEGATIVE_INFINITY` | `NaN` |
| `Double.POSITIVE_INFINITY - Double.POSITIVE_INFINITY` | `NaN` |
| `Double.POSITIVE_INFINITY * 2.0` | `Infinity` |
| `Double.POSITIVE_INFINITY * -2.0` | `-Infinity` |
| `0.0 * Double.POSITIVE_INFINITY` | `NaN` |
| `Double.POSITIVE_INFINITY / 2.0` | `Infinity` |
| `Double.POSITIVE_INFINITY / Double.POSITIVE_INFINITY` | `NaN` |
| `2.0 / Double.POSITIVE_INFINITY` | `+0.0` |
| `-2.0 / Double.POSITIVE_INFINITY` | `-0.0` |

Do not assume every operation involving infinity produces infinity. Certain combinations are **indeterminate** under floating-point arithmetic and return NaN.

### 3.3. Comparing Infinity with Finite Numbers

Infinity follows intuitive comparison ordering:

```java
double positive = Double.POSITIVE_INFINITY;
double negative = Double.NEGATIVE_INFINITY;

System.out.println(positive > Double.MAX_VALUE); // true
System.out.println(negative < -Double.MAX_VALUE); // true
System.out.println(positive > 1.0e300); // true
```

However, remember that NaN does not participate in this ordering with standard `<`, `>` operators. For example, `Double.NaN < Double.POSITIVE_INFINITY` is still `false`.

## 4. Signed Zero: `+0.0` and `-0.0`

A notable aspect of IEEE 754 is having **two zero representations differing in sign bit**:

```java
double positiveZero = +0.0;
double negativeZero = -0.0;

System.out.println(positiveZero == negativeZero); // true
System.out.println(positiveZero < negativeZero);  // false
System.out.println(positiveZero > negativeZero);  // false
```

Under the `==` operator, these two values are equal. However, they are **not identical in every operation**. The sign of zero can affect the direction of infinity when used as a denominator, and is preserved in certain mathematical operations.

### 4.1. Division Exposes the Sign of Zero

```java
double positiveZero = +0.0;
double negativeZero = -0.0;

System.out.println(1.0 / positiveZero); // Infinity
System.out.println(1.0 / negativeZero); // -Infinity
System.out.println(-1.0 / positiveZero); // -Infinity
System.out.println(-1.0 / negativeZero); // Infinity
```

Therefore, the sign of zero is not merely a display artifact. It can carry information about the **direction of approach toward zero** in numerical computation and numerical algorithms.

### 4.2. How Can Signed Zero Appear?

Besides the literal `-0.0`, negative zero can arise from operation results:

```java
double a = -1.0 / Double.POSITIVE_INFINITY;
double b = -0.0 * 2.0;
double c = -1.0e-300 * 1.0e-300; // Underflows to -0.0

System.out.println(a); // -0.0
System.out.println(b); // -0.0
System.out.println(c); // -0.0
```

When a result has a magnitude too small to be represented as non-zero, it can **underflow** to signed zero. The sign is preserved according to the rules of the operation.

### 4.3. Checking the Sign of Zero

Do not use `value == 0.0` to distinguish the two zeros because both compare equal under this operator. An explicit check is bitwise comparison:

```java
static boolean isNegativeZero(double value) {
    return Double.doubleToRawLongBits(value)
            == Double.doubleToRawLongBits(-0.0d);
}

static boolean isPositiveZero(double value) {
    return Double.doubleToRawLongBits(value)
            == Double.doubleToRawLongBits(+0.0d);
}

public static void main(String[] args) {
    System.out.println(isNegativeZero(-0.0)); // true
    System.out.println(isNegativeZero(+0.0)); // false
    System.out.println(isPositiveZero(+0.0)); // true
}
```

`Double.doubleToRawLongBits()` returns the raw bit pattern, preserving NaN payload information. `Double.doubleToLongBits()` normalizes all NaN values into a canonical NaN representation, while still distinguishing `+0.0` from `-0.0`. For distinguishing the sign of zero, either method works; the `raw` name emphasizes that NaN is not canonicalized.

Another way to observe the sign is:

```java
System.out.println(Math.copySign(1.0, +0.0)); // 1.0
System.out.println(Math.copySign(1.0, -0.0)); // -1.0
```

`Math.copySign(magnitude, sign)` takes the magnitude from the first argument and the sign from the second argument.

## 5. Distinguishing Floating-Point Division and Integer Division

This is a practical difference that frequently causes bugs:

```java
double floatingResult = 10.0 / 0.0;
System.out.println(floatingResult); // Infinity

int integerResult = 10 / 0;
// ArithmeticException: / by zero
```

Division between floating-point operands follows IEEE 754 rules: the result can be infinity or NaN. Integer division in Java has no infinity value; dividing by zero throws `ArithmeticException`.

If both operands are integers, assigning the result to a `double` **does not turn the division into floating-point division**:

```java
double wrong = 1 / 2;   // 0.0: int division executes first
double correct = 1.0 / 2; // 0.5: has double operand

System.out.println(wrong);
System.out.println(correct);
```

Similarly:

```java
double result = (double) 1 / 0; // Infinity
```

Casting one operand to `double` before dividing makes the operation floating-point division. If you write `double result = (double) (1 / 0);`, integer division happens first and still throws an exception.

## 6. Comparing Primitives vs. `equals()` and `compare()`

Another source of confusion is that the `==` operator on `double`/`float` behaves differently from the wrapper class's `equals()` method.

### 6.1. Primitive `==` vs. Wrapper `equals`

```java
double nan1 = Double.NaN;
double nan2 = Double.NaN;

System.out.println(nan1 == nan2); // false
System.out.println(Double.valueOf(nan1).equals(Double.valueOf(nan2))); // true

double plusZero = +0.0;
double minusZero = -0.0;

System.out.println(plusZero == minusZero); // true
System.out.println(Double.valueOf(plusZero).equals(Double.valueOf(minusZero))); // false
```

Differences:

| Case | Primitive `==` | `Double.equals()` |
| --- | --- | --- |
| `NaN` vs. `NaN` | `false` | `true` |
| `+0.0` vs. `-0.0` | `true` | `false` |
| Two finite numbers with the same value | `true` | `true` |

`Float.equals()` has analogous rules. Therefore, when using `Double` as a key in a `HashMap` or an element in a `HashSet`, equality behavior follows the wrapper's contract, not the primitive `==` operator.

### 6.2. `Double.compare()` Establishes Total Ordering

When sorting or comparing with a defined order that includes special values, use `Double.compare(a, b)`:

```java
System.out.println(Double.compare(-0.0, +0.0)); // negative number
System.out.println(Double.compare(+0.0, -0.0)); // positive number
System.out.println(Double.compare(Double.NaN, Double.POSITIVE_INFINITY)); // positive number
System.out.println(Double.compare(Double.NaN, Double.NaN)); // 0
```

Key points to remember:

- `Double.compare()` considers `-0.0` less than `+0.0`.
- NaN is considered equal to NaN in wrapper comparison order.
- NaN is ordered after positive infinity.
- For ordinary finite values, ordering follows arithmetic order.

This is why sorting methods and comparators can handle special values deterministically. If business logic does not allow NaN or infinity, filter or reject them **before sorting**, rather than relying on the default ordering to express business rules.

### 6.3. Implications for `hashCode()`

The contract of `equals()` requires that two equal objects have the same `hashCode()`. `Double` and `Float` are designed to satisfy this:

- NaN values are canonicalized when computing the hash, consistent with wrapper `equals()` treating NaN as equal to NaN.
- `+0.0` and `-0.0` have different hash codes, consistent with wrapper `equals()` treating them as distinct.

Do not use `hashCode()` to check whether two numbers have the same value. Hash collisions can still occur, and a hash code is not a unique identifier.

## 7. Safely Checking and Handling Floating-Point Values

Commonly used methods:

| Method | Purpose |
| --- | --- |
| `Double.isNaN(value)` | Checks for NaN. |
| `Double.isInfinite(value)` | Checks for positive or negative infinity. |
| `Double.isFinite(value)` | Checks for a finite value, including both signed zeros. |
| `Float.isNaN(value)` | Checks for NaN on `float`. |
| `Float.isInfinite(value)` | Checks for infinity on `float`. |
| `Float.isFinite(value)` | Checks for a finite value on `float`. |
| `Math.copySign(magnitude, sign)` | Creates a value with the magnitude of the first argument and the sign of the second. |
| `Math.signum(value)` | Returns the sign according to the function's rules, preserving NaN and the sign of zero. |

### 7.1. Accept Only Finite Numbers

If a calculation method cannot handle NaN or infinity, check upfront:

```java
static double calculateRatio(double numerator, double denominator) {
    if (!Double.isFinite(numerator)
            || !Double.isFinite(denominator)) {
        throw new IllegalArgumentException("Inputs must be finite numbers");
    }

    if (denominator == 0.0) {
        throw new IllegalArgumentException("Denominator must not be zero");
    }

    double result = numerator / denominator;
    if (!Double.isFinite(result)) {
        throw new ArithmeticException("Result is not finite");
    }
    return result;
}
```

Note that `denominator == 0.0` matches **both `+0.0` and `-0.0`**. This is appropriate if neither is acceptable as a denominator under business rules.

Checking the result after division is also important: two finite operands can still produce an infinite result due to overflow, or a very small value can underflow to zero.

### 7.2. Distinguish Missing Data from a `NaN` Result

Do not default to using `Double.NaN` as a placeholder for every missing-data case. Represent it explicitly:

```java
import java.util.OptionalDouble;

static OptionalDouble average(double[] values) {
    if (values.length == 0) {
        return OptionalDouble.empty();
    }

    double total = 0.0;
    for (double value : values) {
        if (!Double.isFinite(value)) {
            throw new IllegalArgumentException("Contains a non-finite element");
        }
        total += value;
    }

    return OptionalDouble.of(total / values.length);
}
```

`OptionalDouble.empty()` expresses **no result**, whereas an `OptionalDouble` containing NaN (if intentionally produced and permitted by an algorithm) expresses a special numeric value. Separating these two meanings makes the API clearer to use.

In some systems, a dedicated result type with statuses like `MISSING`, `INVALID`, `FINITE`, or other domain states can be used instead of a special number as a sentinel.

### 7.3. Do Not Validate Data Only with `<`, `>`, or `==`

Example checking a value within a range:

```java
static boolean isValidPercentage(double value) {
    return Double.isFinite(value)
            && value >= 0.0
            && value <= 100.0;
}
```

Even without `Double.isFinite`, NaN makes both range comparisons return `false`, so this example happens to reject NaN too; however, explicit finiteness checks clarify the contract and prevent accidentally accepting special values in more complex expressions. Infinity also does not fall within 0 to 100.

If you only check `value != 0.0`, NaN returns `true` because NaN is unequal to everything under `==`. That is why you should check finiteness or NaN explicitly rather than inferring from a single comparison.

## 8. Reading and Writing NaN and Infinity from Strings

Java's floating-point parsing methods accept special string representations:

```java
double a = Double.parseDouble("NaN");
double b = Double.parseDouble("Infinity");
double c = Double.parseDouble("-Infinity");

System.out.println(Double.isNaN(a)); // true
System.out.println(Double.isInfinite(b)); // true
System.out.println(c); // -Infinity
```

Corresponding forms exist in `Float.parseFloat()`. Strings that are not accepted numeric representations trigger `NumberFormatException`:

```java
try {
    double value = Double.parseDouble("not-a-number");
} catch (NumberFormatException ex) {
    System.out.println("String is not a valid number");
}
```

Do not confuse two situations:

- `"NaN"` is a string recognized by the parser and converted into `Double.NaN`.
- `"not-a-number"` is an invalid string and the parser throws `NumberFormatException`.

After parsing, if business logic only allows finite numbers, check `Double.isFinite(value)` before using it.

### 8.1. When Exporting Data to JSON or Other Systems

The standard JSON specification **does not define** numeric tokens `NaN`, `Infinity`, or `-Infinity` as valid JSON numbers. Some libraries may reject them, transform them, or allow emitting them via non-standard extensions. Therefore:

- Do not assume all JSON parsers/clients accept `NaN` or infinity.
- Choose an explicit convention such as `null`, the string `"NaN"`, or an object with a status field if the data contract allows it.
- Do not silently convert special values to `null` if doing so loses business information.
- Check serializer configuration and test the actual output format transmitted.

If the data represents measurements, consider transmitting both **measurement status** and **value** to distinguish missing results, faulty sensors, out-of-scale readings, or indeterminate results.

## 9. `double` and Precision: Special Values Do Not Solve Rounding Errors

`NaN`, infinity, and signed zero are valid values of the floating-point system; they are not solutions to all numeric problems. `float` and `double` have finite precision, so many decimal numbers are not represented exactly in binary:

```java
double result = 0.1 + 0.2;
System.out.println(result); // typically displays 0.30000000000000004
```

The result above is a **finite** number, not NaN. When comparing floating-point numbers in problems involving measurement or calculation error, an error threshold may be needed:

```java
static boolean approximatelyEqual(double a, double b, double epsilon) {
    if (!Double.isFinite(a) || !Double.isFinite(b)) {
        return Double.compare(a, b) == 0;
    }
    return Math.abs(a - b) <= epsilon;
}
```

This illustrative function requires choosing `epsilon` according to the problem's units and scale. In financial systems requiring exact decimal numbers under business rules, consider `BigDecimal`; `BigDecimal` does not represent NaN or infinity like `double`.

### 9.1. Overflow and Underflow

An operation on finite values can produce a result outside the representable range:

```java
double overflow = Double.MAX_VALUE * 2.0;
double underflow = -Double.MIN_VALUE / 2.0;

System.out.println(overflow); // Infinity
System.out.println(underflow); // -0.0
```

`Double.MAX_VALUE` is the largest positive finite number. `Double.MIN_VALUE` is the **smallest positive non-zero** representable number, not the smallest negative number. For very small numbers, results can become subnormal before underflowing to zero.

Do not confuse `Double.MIN_VALUE` with `-Double.MAX_VALUE`; the two constants refer to opposite ends of the value range.

## 10. Floating-Point Behavior in Java 17

Starting in Java 17, JEP 306 restores always-strict floating-point semantics. Floating-point expressions are evaluated under consistent IEEE 754 semantics, eliminating historical platform-dependent extended evaluation modes.

Therefore, in new Java 17 code, there is no need to add `strictfp` to request strict floating-point behavior. The keyword still exists for language compatibility, but it no longer changes arithmetic results in Java 17. When reading older documentation or code mentioning `strictfp` for cross-platform consistency, understand that historical context; you do not need to apply it as a new configuration step.

## 11. Comprehensive Demonstration Program

Create the file `SpecialFloatingPointDemo.java`:

```java
public class SpecialFloatingPointDemo {
    public static void main(String[] args) {
        double nan = 0.0 / 0.0;
        double positiveInfinity = 1.0 / 0.0;
        double negativeInfinity = 1.0 / -0.0;
        double positiveZero = +0.0;
        double negativeZero = -0.0;

        System.out.println("NaN: " + nan);
        System.out.println("isNaN: " + Double.isNaN(nan));
        System.out.println("isFinite(NaN): " + Double.isFinite(nan));

        System.out.println("Positive infinity: " + positiveInfinity);
        System.out.println("Negative infinity: " + negativeInfinity);
        System.out.println("isInfinite: "
                + Double.isInfinite(positiveInfinity));

        System.out.println("Positive zero == negative zero: "
                + (positiveZero == negativeZero));
        System.out.println("1 / positive zero: " + (1.0 / positiveZero));
        System.out.println("1 / negative zero: " + (1.0 / negativeZero));

        System.out.println("NaN == NaN: " + (nan == nan));
        System.out.println("Double.equals NaN: "
                + Double.valueOf(nan).equals(Double.valueOf(Double.NaN)));
        System.out.println("Double.compare(+0, -0): "
                + Double.compare(+0.0, -0.0));

        double[] values = {
                12.5,
                nan,
                positiveInfinity,
                negativeInfinity,
                positiveZero,
                negativeZero
        };

        for (double value : values) {
            System.out.println(value + " -> finite: "
                    + Double.isFinite(value));
        }
    }
}
```

Compile and run with JDK 17:

```bash
javac SpecialFloatingPointDemo.java
java SpecialFloatingPointDemo
```

Key output lines:

```text
NaN: NaN
isNaN: true
isFinite(NaN): false
Positive infinity: Infinity
Negative infinity: -Infinity
isInfinite: true
Positive zero == negative zero: true
1 / positive zero: Infinity
1 / negative zero: -Infinity
NaN == NaN: false
Double.equals NaN: true
Double.compare(+0, -0): 1
```

The `true`/`false` values, infinity signs, and `Double.compare` ordering show why you must choose the right check for the goal: mathematical comparison, special-value detection, or wrapper object equality.

## 12. Common Errors and How to Handle Them

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `value == Double.NaN` is always `false` | Under IEEE 754 rules, NaN equals no value, including itself. | Use `Double.isNaN(value)`. |
| Infinity appears without an exception | `float`/`double` operations can return infinity per IEEE 754. | Use `isInfinite` or `isFinite`; check for overflow and input ranges. |
| Dividing floating-point by zero throws no error | Floating-point division returns infinity or NaN depending on numerator and sign of zero. | If business rules forbid a zero denominator, check both `+0.0` and `-0.0` before dividing. |
| Dividing an integer by zero throws `ArithmeticException` | Integer division has no infinity value. | Check the denominator or switch to floating-point division if appropriate. |
| `+0.0 == -0.0` is `true` yet division gives different results | The `==` operator ignores zero's sign; IEEE 754 still retains the sign bit. | Use bitwise checks or `Math.copySign` when the sign of zero matters. |
| `Double.equals` differs from `==` | Wrapper has an equality contract intended for objects and hash collections. | Distinguish primitive comparison from wrapper equality; use `Double.compare` when ordering is needed. |
| Intermediate value becomes NaN and propagates | An indeterminate operation produced NaN. | Validate data and mathematical steps right at the source. |
| Parser accepts `"NaN"` but rejects other strings | `"NaN"` is a valid special floating-point token for the parser; arbitrary strings are not numbers. | Catch `NumberFormatException`, then check `isFinite` per contract. |
| JSON serializer rejects Infinity or NaN | Standard JSON lacks these numeric tokens. | Choose an explicit interchange representation and configure the serializer accordingly. |
| `Double.MIN_VALUE` is not the most negative number | This constant is the smallest positive non-zero number. | Use `-Double.MAX_VALUE` if you need the smallest (most negative) finite number. |

## 13. Practice Exercises

### Exercise 1 — Predict the Output

```java
double a = 0.0 / 0.0;
double b = 5.0 / 0.0;
double c = -5.0 / 0.0;

System.out.println(a == a);
System.out.println(Double.isNaN(a));
System.out.println(Double.isInfinite(b));
System.out.println(b > Double.MAX_VALUE);
System.out.println(c < -Double.MAX_VALUE);
```

Predict the five outputs before running the program.

**Answer:** `false`, `true`, `true`, `true`, `true`.

### Exercise 2 — Distinguishing the Two Zeros

```java
double positiveZero = +0.0;
double negativeZero = -0.0;

System.out.println(positiveZero == negativeZero);
System.out.println(1.0 / positiveZero);
System.out.println(1.0 / negativeZero);
System.out.println(Double.compare(positiveZero, negativeZero));
```

**Answer:** `true`, `Infinity`, `-Infinity`, a positive number. The `==` operator treats both zeros as equal, while division and `Double.compare` distinguish the sign.

### Exercise 3 — Input Validation

Write a method that accepts a `double` and returns `true` only if the value is a finite number in the range from 0 to 1, inclusive of both endpoints. Test with `0.0`, `-0.0`, `0.5`, `1.0`, `Double.NaN`, `Double.POSITIVE_INFINITY`.

Hint:

```java
static boolean validRate(double rate) {
    return Double.isFinite(rate)
            && rate >= 0.0
            && rate <= 1.0;
}
```

Decide whether the business rules accept `-0.0` as zero or must explicitly reject negative signs.

### Exercise 4 — Integer Division or Floating-Point Division?

Explain the results and how to fix:

```java
double ratio1 = 1 / 4;
double ratio2 = 1.0 / 4;
```

**Answer:** `ratio1` is `0.0` because integer division executes before assignment; `ratio2` is `0.25` because there is a `double` operand.

### Exercise 5 — Wrappers and Primitives

Compare:

```java
Double x = Double.NaN;
Double y = Double.NaN;

System.out.println(x == y);
System.out.println(x.equals(y));
System.out.println(Double.compare(x, y));
```

Explain why reference comparison, `equals()`, and `compare()` do not necessarily give the same result. Hint: `x == y` when both are wrappers compares **references** (do not rely on a fixed outcome when two wrappers are created separately); `equals()` compares wrapper values, while `compare()` defines ordering for numeric values. For two NaNs, `equals()` is `true` and `compare()` returns `0`.

## 14. Key Takeaways When Using Floating-Point Numbers

- `NaN` is a special value unequal to itself under `==`; check it with `Double.isNaN()` or `Float.isNaN()`.
- `+Infinity` and `-Infinity` are valid floating-point values; check with `isInfinite()` or reject all non-finite values with `isFinite()`.
- `+0.0` and `-0.0` are equal under primitive `==`, but have different sign bits and can yield different results when dividing.
- Dividing floating-point numbers by zero can return infinity or NaN; dividing integers by zero throws `ArithmeticException`.
- `Double.equals()` and `Double.compare()` have their own rules for NaN and signed zero; do not equate them with primitive `==`.
- Text parsers can read `"NaN"` and `"Infinity"`, but interchange formats like JSON require explicit conventions for these values.
- Special arithmetic checks do not replace business domain validation; a finite number can still be invalid for the application.

### References

- [Java SE 17 API — `Double`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html) — constants, inspection methods, bit conversions, comparisons, and parsing for `double`.
- [Java SE 17 API — `Float`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Float.html) — corresponding constants and methods for `float`.
- [Java SE 17 API — `Math`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html) — operations and mathematical functions.
- [JLS Java SE 17 — §4.2.3 Floating-Point Types, Formats, and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.3) — floating-point value domain and formats.
- [JLS Java SE 17 — §15.17.2 Division Operator](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.17.2) — integer and floating-point division rules.
- [JEP 306: Restore Always-Strict Floating-Point Semantics](https://openjdk.org/jeps/306) — floating-point semantics change effective from Java 17.
