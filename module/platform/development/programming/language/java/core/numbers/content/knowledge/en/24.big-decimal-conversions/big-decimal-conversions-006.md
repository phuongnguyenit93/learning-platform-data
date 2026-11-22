# `toBigInteger()` vs. `toBigIntegerExact()`: Converting `BigDecimal` to Exact Integers

## 1. Lesson Objectives

`BigDecimal` represents decimal values with arbitrary precision; `BigInteger` represents integers of arbitrary magnitude. When converting from `BigDecimal` to `BigInteger`, Java provides two options with **different contracts**:

- `toBigInteger()`: **discards the fractional part** of the decimal value, moving toward **0**, and returns a `BigInteger`. This conversion can lose data without reporting an error.
- `toBigIntegerExact()`: converts only if the value can be represented **exactly as an integer**. If there is a non-zero fractional part, it throws `ArithmeticException`.

This is a difference in **data-handling policy**, not merely a difference in method names. After this lesson, you will be able to predict results for positive/negative numbers, fractional parts, trailing zeros, and scientific notation; write input validation matching business requirements; and avoid confusion with `intValue()`, `intValueExact()`, `RoundingMode`, or `Math.floor`.

## 2. Two Methods Returning the Same Type, Yet Handling Fractional Parts Differently

In `java.math.BigDecimal`, there are the methods:

```java
public BigInteger toBigInteger();
public BigInteger toBigIntegerExact();
```

Both return a `java.math.BigInteger` of **arbitrary integer magnitude**, rather than being capped at 32 bits (`int`) or 64 bits (`long`). But pay attention to the fractional part:

| Input `BigDecimal` | `toBigInteger()` | `toBigIntegerExact()` | Reason |
|---|---:|---:|---|
| `12` | `12` | `12` | Already an integer |
| `12.00` | `12` | `12` | Fractional part consists only of 0s |
| `12.99` | `12` | **Throws `ArithmeticException`** | Has non-zero fractional part |
| `-12.99` | `-12` | **Throws `ArithmeticException`** | Has non-zero fractional part |
| `-0.75` | `0` | **Throws `ArithmeticException`** | Truncates fractional part toward 0 |
| `0.000` | `0` | `0` | Numeric value equals 0 |
| `1E+3` | `1000` | `1000` | Exactly an integer |
| `1E-3` | `0` | **Throws `ArithmeticException`** | Exactly 0.001 |

**Key point:** `Exact` means "without losing a significant fractional part." It **does not require `BigDecimal`'s scale to be 0**: `12.00` has scale 2 yet is still the integer value 12 and converts accurately.

## 3. Mechanism: Truncating Toward 0 vs. Preserving Value

### 3.1. `toBigInteger()` Truncates Toward 0

Consider the expression `new BigDecimal("12.99").toBigInteger()`: the result is `12`. The `.99` part disappears; there is no rounding to the nearest integer.

For negative values, the result is `-12`, **not `-13`**:

```text
-13 ----- -12.99 ----- -12 ----- 0 ----- 12 ----- 12.99 ----- 13
                        ^                         ^
             toBigInteger(-12.99)       toBigInteger(12.99)
```

Moving toward 0 differs from moving toward negative infinity:

- `toBigInteger(-12.99)` = `-12`: discards fractional part, toward 0.
- `Math.floor(-12.99)` = `-13.0`: takes integer toward −∞.
- `Math.ceil(-12.99)` = `-12.0`: takes integer toward +∞.

Although `toBigInteger()` and `Math.ceil()` give the same integer part in this negative-number example, they are **not equivalent operations** across both positive and negative numbers.

Arithmetically, for positive `x`: `toBigInteger(x)` corresponds to `floor(x)`; for negative `x`: it corresponds to `ceil(x)`; for integer `x`: it keeps it unchanged. If you want to express discarding the fractional part directly via a `RoundingMode`, the corresponding name is `RoundingMode.DOWN` (toward 0), not `RoundingMode.FLOOR`.

### 3.2. `toBigIntegerExact()` Rejects Fractional Data Loss

`toBigIntegerExact()` returns only if the conversion preserves the **numeric value**. Examples:

```java
new BigDecimal("42.000").toBigIntegerExact(); // BigInteger 42
new BigDecimal("-42.000").toBigIntegerExact(); // BigInteger -42
new BigDecimal("42.001").toBigIntegerExact(); // ArithmeticException
```

Both `42.000` and `-42.000` have scale 3, yet their fractional parts equal 0. Therefore, **do not check `scale() == 0` as the sole condition** to decide whether an exact conversion is possible.

If there is a non-zero fractional part, Java throws `ArithmeticException` so the programmer has the opportunity to handle input that violates the contract. If the application needs to accept decimals and intentionally round them, you must choose a separate rounding policy; do not use `toBigInteger()` as an implicit rounding step.

## 4. Complete Java Program: Results for Each Case

**File `BigDecimalToBigIntegerDemo.java`** (Java 17+):

```java
import java.math.BigDecimal;
import java.math.BigInteger;

public class BigDecimalToBigIntegerDemo {
    public static void main(String[] args) {
        String[] inputs = {
                "12.99",
                "-12.99",
                "12.000",
                "0.00",
                "1E+3",
                "1E-3"
        };

        for (String input : inputs) {
            BigDecimal amount = new BigDecimal(input);
            BigInteger truncated = amount.toBigInteger();

            System.out.print("input=" + amount.toPlainString()
                    + ", trunc=" + truncated + ", exact=");

            try {
                System.out.println(amount.toBigIntegerExact());
            } catch (ArithmeticException ex) {
                System.out.println("ArithmeticException");
            }
        }
    }
}
```

Compile and run:

```bash
javac BigDecimalToBigIntegerDemo.java
java BigDecimalToBigIntegerDemo
```

Output:

```text
input=12.99, trunc=12, exact=ArithmeticException
input=-12.99, trunc=-12, exact=ArithmeticException
input=12.000, trunc=12, exact=12
input=0.00, trunc=0, exact=0
input=1000, trunc=1000, exact=1000
input=0.001, trunc=0, exact=ArithmeticException
```

These lines show three things:

1. `toBigInteger()` **always supplies an integer part** for the normal values above; it does not warn about losing `.99` or `.001`.
2. `toBigIntegerExact()` fails **only when the value is non-integer** (or cannot be converted accurately due to resource limits in extreme cases), not simply when the string contains a decimal point.
3. `toPlainString()` is used to display `1E+3` as `1000` and `1E-3` as `0.001`. Both `BigInteger` conversion methods always output an integer and do not carry over the input's scale.

## 5. How Do `Scale`, Trailing Zeros, and Scientific Notation Affect This?

A `BigDecimal` is described by an **unscaled value** and a **scale**:

```text
value = unscaledValue × 10^(-scale)

"12.000" => unscaledValue = 12000, scale = 3
"1E+3"  => unscaledValue = 1,     scale = -3
"1E-3"  => unscaledValue = 1,     scale = 3
```

The task of `toBigIntegerExact()` is to determine **whether the final numeric value is an integer**, not to inspect whether `scale` is positive, negative, or zero.

- A positive scale **can still** convert exactly if all digits of the fractional part are 0, e.g. `12.000`.
- A zero scale is an integer already represented directly, e.g. `12`.
- A negative scale makes the value a multiple of a power of 10, e.g. `1E+3 = 1000`; it is still an integer.
- A positive scale with a non-zero fractional part causes `toBigIntegerExact()` to fail, e.g. `1E-3 = 0.001`.

**There is no need to call `stripTrailingZeros()` before `toBigIntegerExact()`.** The exact method evaluates the integrality of the value itself. Calling `stripTrailingZeros()` can change the scale and display string, so use it only if business logic genuinely requires normalizing the representation.

For example, `2.0` and `2.00` from strings have scales 1 and 2 respectively. Both convert to the same integer `2` via `toBigIntegerExact()` without losing **numeric value**. However, the resulting `BigInteger` no longer remembers whether the input had one or two decimal places. "Exact" here means exact in **value**, not "format-preserving."

## 6. How `toBigInteger` Differs from `setScale` Rounding

If you want to round before converting to an integer, write the rule explicitly:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal x = new BigDecimal("-12.99");

System.out.println(x.toBigInteger()); // -12
System.out.println(x.setScale(0, RoundingMode.DOWN));    // -12
System.out.println(x.setScale(0, RoundingMode.FLOOR));   // -13
System.out.println(x.setScale(0, RoundingMode.CEILING)); // -12
System.out.println(x.setScale(0, RoundingMode.HALF_UP)); // -13
```

This snippet is an illustrative example inside a runnable method (imports must be placed at the top of the file). With `x = -12.99`:

| Approach | Result | Rule |
|---|---:|---|
| `x.toBigInteger()` | `-12` | Truncates toward 0, drops fraction |
| `x.setScale(0, DOWN)` | `-12` | Rounds toward 0 |
| `x.setScale(0, FLOOR)` | `-13` | Rounds toward −∞ |
| `x.setScale(0, CEILING)` | `-12` | Rounds toward +∞ |
| `x.setScale(0, HALF_UP)` | `-13` | Rounds to nearest, HALF_UP rule on ties |

Once rounded with `setScale(0, mode)`, you can call `toBigIntegerExact()` at the final step: the value already has scale 0, so the conversion step drops no further fractional digits. Example:

```java
BigInteger rounded = x.setScale(0, RoundingMode.FLOOR)
                      .toBigIntegerExact(); // -13
```

Here, rounding is **intentional** and explicitly stated in the code. Conversely, calling `toBigIntegerExact()` directly on `-12.99` will throw an exception.

**Common mistake:** Because some texts refer to truncating the fractional part as "round down," learners easily equate it with `FLOOR`. In Java's `RoundingMode`, `DOWN` means toward **0**, whereas `FLOOR` means toward **negative infinity**. Testing with negative numbers exposes the difference immediately.

## 7. Distinguishing from `intValue()`, `longValue()`, and `Exact` Variants

After `toBigInteger...`, you receive a `BigInteger` of arbitrary magnitude. If the final target is `int` or `long`, you must check for **two independent risks**:

1. **Is there a fractional part?** If so, converting to an integer can lose the decimal part.
2. **Does it exceed the target type's limits?** If so, converting to `int`/`long` can lose high bits.

That is why the other exact methods also matter:

| Method on `BigDecimal` | Fractional Loss Allowed? | Checks `int`/`long` Range? |
|---|---|---|
| `toBigInteger()` | Yes | Not applicable: target is `BigInteger` |
| `toBigIntegerExact()` | No | Not applicable: target is `BigInteger` |
| `intValue()` / `longValue()` | Yes | No, can lose high bits |
| `intValueExact()` / `longValueExact()` | No | Yes; throws `ArithmeticException` if out of range |

Example when the integer exceeds `int`:

**File `BigIntegerRangeDemo.java`:**

```java
import java.math.BigDecimal;
import java.math.BigInteger;

public class BigIntegerRangeDemo {
    public static void main(String[] args) {
        BigDecimal source = new BigDecimal("2147483648");
        BigInteger big = source.toBigIntegerExact();

        System.out.println("BigInteger=" + big);
        System.out.println("long=" + source.longValueExact());

        try {
            System.out.println("int=" + source.intValueExact());
        } catch (ArithmeticException ex) {
            System.out.println("intValueExact: ArithmeticException");
        }
    }
}
```

```bash
javac BigIntegerRangeDemo.java
java BigIntegerRangeDemo
```

```text
BigInteger=2147483648
long=2147483648
intValueExact: ArithmeticException
```

The value `2_147_483_648` is greater than `Integer.MAX_VALUE` (`2_147_483_647`), yet still fits in `long` and can always be stored in `BigInteger`. Using `toBigIntegerExact()` avoids losing fractional parts, but **does not automatically check** whether the value fits `int` or `long` when converting further; use `big.intValueExact()` or `big.longValueExact()` if needed.

## 8. Practice: Validating That a Quantity Is a Whole Number

Suppose a system reads a `quantity` field from decimal data. Requirement: the quantity must be an integer and non-negative; `2.8` must never be allowed to turn into `2`.

**File `WholeQuantityDemo.java`:**

```java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.util.Objects;

public class WholeQuantityDemo {
    public static BigInteger requireWholeQuantity(BigDecimal quantity) {
        Objects.requireNonNull(quantity, "quantity");

        if (quantity.signum() < 0) {
            throw new IllegalArgumentException("Quantity cannot be negative");
        }

        try {
            return quantity.toBigIntegerExact();
        } catch (ArithmeticException ex) {
            throw new IllegalArgumentException(
                    "Quantity must be a whole number: " + quantity, ex);
        }
    }

    public static void main(String[] args) {
        BigDecimal[] values = {
                new BigDecimal("2.00"),
                new BigDecimal("2.8"),
                new BigDecimal("0"),
                new BigDecimal("-1.0")
        };

        for (BigDecimal value : values) {
            try {
                System.out.println(value + " -> "
                        + requireWholeQuantity(value));
            } catch (IllegalArgumentException ex) {
                System.out.println(value + " -> REJECTED");
            }
        }
    }
}
```

```bash
javac WholeQuantityDemo.java
java WholeQuantityDemo
```

```text
2.00 -> 2
2.8 -> REJECTED
0 -> 0
-1.0 -> REJECTED
```

In this example, catching `ArithmeticException` is meaningful: data with a fractional part violates the business rule and is converted into an appropriate error message. You should not catch it and silently fall back to `toBigInteger()`, because that turns invalid input into "faked valid" input.

If the system only accepts positive quantities, add a `quantity.signum() > 0` check; if a maximum limit is needed, use `BigInteger.compareTo(maximum)` after the exact conversion.

### When Is `toBigInteger()` a Valid Choice?

In some problems, the requirement **deliberately discards the fractional part**. For example, taking the integer part of a measurement with a clearly defined truncate-toward-zero rule. In that case `toBigInteger()` matches the requirement; name the variable/method to clearly reflect the intent, such as `truncatedUnits`.

Whereas for identifiers, item counts, sequence numbers, limit configurations, or data where fractional parts are invalid, `toBigIntegerExact()` is safer because it expresses the contract in code and fails fast.

## 9. Edge Cases and Common Mistakes

### 9.1. Negative Numbers Close to 0

```java
BigDecimal x = new BigDecimal("-0.99");

System.out.println(x.toBigInteger()); // 0
// x.toBigIntegerExact() would throw ArithmeticException.
```

A negative value can be truncated to 0. If the system relies on the sign or group-indexing rules, losing sign information like that can cause logic bugs.

### 9.2. Trailing Zeros and Different Scales

```java
new BigDecimal("2.0").toBigIntegerExact();  // 2
new BigDecimal("2.00").toBigIntegerExact(); // 2
new BigDecimal("2.01").toBigIntegerExact(); // ArithmeticException
```

Exactness is based on whether the fractional part **has a non-zero value**, independent of the number of digits entered. The returned `BigInteger` no longer retains the scale.

### 9.3. Initializing from `double` Can Introduce Binary Error

```java
BigDecimal a = new BigDecimal("0.1");
BigDecimal b = new BigDecimal(0.1);
```

`a` represents decimal `0.1` accurately. `b` represents the exact binary value of the `double` near 0.1, so it has many extra digits. **Do not create `BigDecimal` from `double` if you need to preserve the input's exact decimal digits.** Prefer `BigDecimal(String)` for decimal data or consider `BigDecimal.valueOf(double)` when you already have a `double` and understand its limitations. Once the object is created, conversion methods cannot recover precision already lost beforehand.

### 9.4. Do Not Swallow Exceptions

This example loses an important validation:

```java
// What NOT to do if rules require an exact integer:
try {
    return amount.toBigIntegerExact();
} catch (ArithmeticException ignored) {
    return amount.toBigInteger(); // Silently truncates the fractional part
}
```

This only illustrates the body of a method having a `BigDecimal` variable `amount`. If rounding is needed, specify the rounding mode explicitly and document the decision. If rejection is needed, throw an error with context.

### 9.5. Do Not Confuse Integrality Exceptions with `null` and Unparseable Data

If the `BigDecimal` variable is `null`, calling either of the two methods will throw `NullPointerException`. If the input string is invalid, `new BigDecimal(text)` throws `NumberFormatException` right at parse time, before reaching the `BigInteger` conversion stage. These two error types are distinct from `ArithmeticException` caused by a non-zero fractional part.

### 9.6. Very Large Values

`BigInteger` is not capped at `Integer.MAX_VALUE` or `Long.MAX_VALUE`, but it is still subject to practical memory and representation limits. Do not treat "arbitrary precision" as "never hits resource limits." Also avoid converting onward to a fixed integer type without checking bounds.

## 10. Self-Check Exercises (with Answers)

1. **What does `new BigDecimal("8.999").toBigInteger()` return?**  
   `8`, because it truncates the fractional part toward 0.

2. **What does `new BigDecimal("-8.999").toBigInteger()` return?**  
   `-8`, not `-9`: `toBigInteger()` is not floor.

3. **Does `new BigDecimal("8.000").toBigIntegerExact()` throw an error?**  
   No. The result is a `BigInteger` with value `8`, even though the input scale is greater than 0.

4. **What does `new BigDecimal("8.001").toBigIntegerExact()` do?**  
   Throws `ArithmeticException` because the fractional part is non-zero.

5. **Does `new BigDecimal("1E+5").toBigIntegerExact()` fail because it is written in scientific notation?**  
   No. The result is `100000`, an exact integer.

6. **The value `2.99` must be rounded up to `3` per business rules. Which method should be used?**  
   `new BigDecimal("2.99").setScale(0, RoundingMode.CEILING).toBigIntegerExact()` (for this positive number, gives `3`). Calling `toBigInteger()` directly only gives `2`.

7. **The value `2147483648.00` is an exact integer but exceeds `int`. Does `toBigIntegerExact()` succeed?**  
   Yes. The result is `2147483648` as a `BigInteger`. However, converting onward with `intValueExact()` will throw `ArithmeticException`.

8. **What is the difference between `toBigIntegerExact()` and `intValueExact()`?**  
   Neither permits losing a fractional part; `intValueExact()` must also ensure the result lies within the `int` range, whereas `BigInteger` supports arbitrarily large integers.

## 11. Summary and API Selection

Decide according to your data contract:

| Requirement | Solution |
|---|---|
| Intentionally discard fractional part, toward 0 | `decimal.toBigInteger()` |
| Accept only exact integer values | `decimal.toBigIntegerExact()` |
| Must round per a specific policy | `decimal.setScale(0, mode).toBigIntegerExact()` |
| Must convert to `int` exactly | `decimal.intValueExact()` or `decimal.toBigIntegerExact().intValueExact()` |
| Must convert to `long` exactly | `decimal.longValueExact()` or `decimal.toBigIntegerExact().longValueExact()` |

Quick mnemonic: **Without `Exact`: fractional truncation is accepted. With `Exact`: no fractional part is lost; if the value cannot be preserved, an error is raised.** In all cases, still check target types, nullability, and corresponding resource limits.

Official Javadoc references:

- [Java 21 — `BigDecimal`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html)
- [Java 21 — `BigInteger`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigInteger.html)
- [Java 21 — `RoundingMode`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/RoundingMode.html)
