# Casting `float` or `double` to Integer: Truncation Toward Zero in Java

## 1. Nature of the cast

In Java, a `float` or `double` value can contain a fractional part, whereas the integer types `byte`, `short`, `int`, `long`, and `char` represent whole values within finite ranges. When casting a floating-point number to an integer using `(T) expression`, Java performs a **narrowing primitive conversion**.

For a **finite floating-point number whose integer part is representable**, the conversion discards the fractional part using the **round toward zero** (*truncation*) rule:

- `(int) 7.9` equals **7**.
- `(int) 7.1` equals **7**.
- `(int) -7.9` equals **-7**.
- `(int) -7.1` equals **-7**.

This is **not rounding to the nearest integer**. Nor is it always "rounding down": for negative numbers, `-7.9` converts to `-7`, whereas `Math.floor(-7.9)` is `-8.0`.

Another key point: when the floating-point value is **NaN**, **infinity**, or has a magnitude exceeding the target integer range, Java has dedicated rules. Simply saying "drop the decimal point" or "remove the fractional part" cannot explain all cases.

## 2. Syntax and result type

Syntax:

```java
int n = (int) 12.75;      // 12
long m = (long) -12.75;   // -12
float f = 3.99f;
int fromFloat = (int) f;  // 3
double d = -3.99;
long fromDouble = (long) d; // -3
```

`(int)` and `(long)` are **explicit cast operators**. The resulting expression has the type corresponding to the type name written inside the parentheses. Java does not automatically allow assigning an arbitrary `double` to an `int` without a cast:

```java
double value = 12.75;
// int invalid = value; // COMPILE ERROR: risk of losing the fractional part
int valid = (int) value;
```

Syntactically, the parentheses in `(int) value` are part of the cast, not a method call. Put outer parentheses around an expression when you need to cast the entire expression's result:

```java
double a = 1.9;
double b = 2.9;

int castEach = (int) a + (int) b; // 1 + 2 = 3
int castSum = (int) (a + b);      // (int) 4.8 = 4
```

**Casting each operand and then adding** differs from **adding the floating-point numbers first and then casting the result**. Which one is right depends on the business requirement; you cannot move the cast's position arbitrarily.

## 3. Truncating toward zero differs from `floor`, `ceil`, and nearest rounding

See the comparison table with `double` inputs:

| Input value | `(int) x` | `Math.floor(x)` | `Math.ceil(x)` | `Math.round(x)` |
|---:|---:|---:|---:|---:|
| 3.8 | 3 | 3.0 | 4.0 | 4 |
| 3.2 | 3 | 3.0 | 4.0 | 3 |
| -3.8 | -3 | -4.0 | -3.0 | -4 |
| -3.2 | -3 | -4.0 | -3.0 | -3 |
| 2.5 | 2 | 2.0 | 3.0 | 3 |
| -2.5 | -2 | -3.0 | -2.0 | -2 |

Meaning:

- **Cast `(int) x`**: truncates toward 0; result has type `int`.
- **`Math.floor(x)`**: takes the integer toward **negative infinity**; with a `double` argument, the result still has type `double`.
- **`Math.ceil(x)`**: takes the integer toward **positive infinity**; with a `double` argument, the result still has type `double`.
- **`Math.round(double)`**: picks the nearest integer, resolving exact halves toward positive infinity; returns `long`. For `float`, the `Math.round(float)` overload returns `int`.

For instance, `Math.round(-2.5)` equals -2, while `Math.round(2.5)` equals 3. Casting both produces -2 and 2 because it only strips the fractional part.

**Do not use `Math.floor` to emulate casting on negative numbers.** If you want cast behavior, write the cast and apply NaN/range checks as needed. If you want rounding rules for finance, exact precision, or half-up/half-even rounding, specify the requirement clearly and pick the appropriate API; casting does not satisfy those rounding requirements.

## 4. Complete example: truncating the fractional part toward zero

Create the file `TruncationDemo.java`:

```java
public class TruncationDemo {
    public static void main(String[] args) {
        double positive = 7.9;
        double negative = -7.9;

        System.out.println("(int) 7.9 = " + (int) positive);
        System.out.println("(int) -7.9 = " + (int) negative);
        System.out.println("(long) -7.9 = " + (long) negative);
        System.out.println("(int) -0.9 = " + (int) -0.9);
        System.out.println("(int) 0.9 = " + (int) 0.9);

        System.out.println("floor(-7.9) = " + Math.floor(negative));
        System.out.println("ceil(-7.9) = " + Math.ceil(negative));
        System.out.println("round(7.9) = " + Math.round(positive));
        System.out.println("round(-7.9) = " + Math.round(negative));

        double a = 1.9;
        double b = 2.9;
        System.out.println("cast each = " + ((int) a + (int) b));
        System.out.println("cast sum = " + (int) (a + b));
    }
}
```

Compile and run with Java 17+:

```bash
javac TruncationDemo.java
java TruncationDemo
```

Output:

```text
(int) 7.9 = 7
(int) -7.9 = -7
(long) -7.9 = -7
(int) -0.9 = 0
(int) 0.9 = 0
floor(-7.9) = -8.0
ceil(-7.9) = -7.0
round(7.9) = 8
round(-7.9) = -8
cast each = 3
cast sum = 4
```

A note on **-0.0**: `double` and `float` have both +0.0 and -0.0, whereas Java integer types do not have two kinds of zero. Casting `-0.0` to `int` or `long` yields **0**.

## 5. The rules Java actually uses when converting to integer

The Java Language Specification (JLS, section *Narrowing Primitive Conversion*) defines converting from `float`/`double` to an integral type in **two steps**.

### Step 1: convert to `int` or `long`

- If the final target type is `long`, the first step converts to `long`.
- If the final target type is `byte`, `short`, `char`, or `int`, the first step converts to `int`.

Rules of this step:

1. **NaN** → integer result **0**.
2. **Finite number** → round toward 0; if the integer part is representable in the intermediate type, take that integer part.
3. **Too large or +Infinity** → use the **maximum** value of `int` or `long`, respectively.
4. **Too small or -Infinity** → use the **minimum** value of `int` or `long`, respectively.

Bringing an out-of-range result to the boundary value is commonly called **saturation/clamping**. It differs from the bit-discarding rule used when converting from a larger integer type to a smaller integer type.

### Step 2: if the target is `byte`, `short`, or `char`

The `int` result of the first step is further **narrowed according to integer conversion rules**: keep the low 8 or 16 bits, then interpret according to the target type. Therefore, the result **can wrap around or change sign**, rather than clamping directly to the `byte`/`short` range.

For example:

```java
byte b = (byte) 130.9; // step 1: int 130; step 2: byte -126
short s = (short) 32768.7; // step 1: int 32768; step 2: short -32768
char c = (char) -1.9; // step 1: int -1; step 2: char code unit 65535
```

**Do not confuse the two kinds of narrowing:** casting floating-point to `int`/`long` has rounding and boundary-clamping rules; casting an `int` to `byte`/`short`/`char` proceeds by keeping the low bits.

## 6. Special values that must be validated before casting

The truncate-toward-zero rule only describes finite numbers within range. For `NaN`, casting to `int` or `long` yields `0`; for `+Infinity`, `-Infinity`, or out-of-range values, the result is clamped at the corresponding bound. If the target is `byte`, `short`, or `char`, Java converts through `int` first and then keeps the low bits of the target type; hence there is no direct clamping rule at `byte` or `short` limits.

For example, `(int) Double.NaN == 0` and `(byte) Double.POSITIVE_INFINITY == -1`. These results are merely cast rules; they do not prove the input data is valid. When an API requires an integer from a measurement, use `Double.isFinite` and check the range before casting. The next lesson examines `NaN`, infinity, and floating-point boundary cases in detail with full traces and examples.

## 7. Precision loss can happen **even before the cast**

`float` (32 bits) has about 24 binary significand bits; `double` (64 bits) has about 53 significand bits. Not every decimal or large integer is represented accurately.

For example:

```java
float f = 16_777_217f;  // does not store this exact number
int value = (int) f;     // 16777216
```

The mathematical integer **16_777_217** cannot be represented exactly in `float`; the value in the variable was already rounded to 16_777_216 **before** casting. The `(int) f` cast merely converts **the value actually stored**, without recovering lost digits.

Similarly, many decimal fractions like `0.1` are not represented exactly in binary floating-point. With integer casts, this is especially important when a computed result lands near an integer boundary.

```java
double value = 0.1 + 0.2;
System.out.println(value); // 0.30000000000000004
System.out.println((int) value); // 0
```

Do not treat casting as a way to fix floating-point inaccuracies. When you need to preserve decimal digits and controlled rounding rules (such as currency), consider `BigDecimal` with an appropriate data source and `RoundingMode`.

## 8. Why is `Math.round` not the same as casting?

A program may need "the integer part" in several senses:

- **Drop the fractional part toward 0**: `(int) x` or `(long) x`.
- **Get the greatest integer not greater than x**: `Math.floor(x)`.
- **Get the smallest integer not less than x**: `Math.ceil(x)`.
- **Pick the nearest integer**: `Math.round(x)` according to the method's rules.

These methods do not differ only on negative numbers; they also have different **return types** and special rules.

For example:

```java
System.out.println((int) 2.9);       // 2
System.out.println(Math.round(2.9));  // 3
System.out.println((int) -2.9);      // -2
System.out.println(Math.round(-2.9)); // -3
System.out.println(Math.floor(-2.9)); // -3.0
System.out.println(Math.ceil(-2.9));  // -2.0
```

`Math.round(double)` returns `long`, whereas `Math.round(float)` returns `int`; that method also defines behavior for NaN and out-of-range values, so **do not replace validity checks with `round`**. Furthermore, `Math.floor`/`ceil` results remain floating-point types, not `int` or `long`.

If the requirement is to **reject any value with a fractional part**, a plain cast is insufficient because it intentionally drops the fraction. Use an appropriate check before converting.

## 9. Validating data before converting to `int`

Suppose an application receives a `double` externally and requires:

1. The value must be **finite** (not NaN, not infinity).
2. The input value must **fall within the `int` integer range**.
3. **Truncation toward 0** according to this lesson's rules is acceptable.

An explicit validation method:

```java
static int truncateFiniteInt(double value) {
    if (!Double.isFinite(value)
            || value < Integer.MIN_VALUE
            || value >= 2_147_483_648.0) {
        throw new IllegalArgumentException("outside int input range");
    }
    return (int) value;
}
```

This is an **illustrative method snippet** that needs to be placed inside a Java class. The upper bound uses `2_147_483_648.0` because it is the **first number greater than `Integer.MAX_VALUE`** in the integer range; `(double) Integer.MAX_VALUE` is represented as 2_147_483_647.0 exactly.

This method applies a **policy requiring the original floating-point input to lie within the `int` range**, rather than merely checking "after truncation, is the integer representable?" For example, `-2_147_483_648.5` if cast directly would yield `Integer.MIN_VALUE`, yet the policy above rejects it because the **input value** is below the lower bound. This is a clear, strict validation choice for an API.

If the application also requires **no fractional part**, add:

```java
if (value != Math.rint(value)) {
    throw new IllegalArgumentException("fractional input");
}
```

This condition should only be used **after checking `Double.isFinite`**; `Math.rint` returns the nearest integral `double` using round-half-to-even, and comparing for equality only checks whether the stored value is already an integer. It **does not prove** the original input text had no decimal fraction, because the `double` data may have lost precision earlier.

### Runnable version with validation

Create the file `ValidatedTruncation.java`:

```java
public class ValidatedTruncation {
    static int truncateFiniteInt(double value) {
        if (!Double.isFinite(value)
                || value < Integer.MIN_VALUE
                || value >= 2_147_483_648.0) {
            throw new IllegalArgumentException("outside int input range");
        }
        return (int) value;
    }

    public static void main(String[] args) {
        System.out.println(truncateFiniteInt(15.9));
        System.out.println(truncateFiniteInt(-15.9));

        for (double value : new double[] {
                Double.NaN, Double.POSITIVE_INFINITY, 1.0e20
        }) {
            try {
                System.out.println(truncateFiniteInt(value));
            } catch (IllegalArgumentException e) {
                System.out.println("rejected");
            }
        }
    }
}
```

Run:

```bash
javac ValidatedTruncation.java
java ValidatedTruncation
```

Output:

```text
15
-15
rejected
rejected
rejected
```

For `long`, special care is needed: **`(double) Long.MAX_VALUE` rounds to \(2^{63}\)**, which is **outside the `long` range**. Therefore, checking `value <= Long.MAX_VALUE` in floating-point comparison fails to guard the upper limit. Under a policy requiring the input value to lie within the `long` range, useful bounds are:

```java
static long truncateFiniteLong(double value) {
    if (!Double.isFinite(value)
            || value < -0x1.0p63
            || value >= 0x1.0p63) {
        throw new IllegalArgumentException("outside long input range");
    }
    return (long) value;
}
```

`0x1.0p63` is Java's **hexadecimal floating-point literal**, with exact value \(2^{63}\) as a `double`. It is not an integer literal. The lower bound \(-2^{63}\) is a valid exact `long` value, while the upper bound \(2^{63}\) is the first value excluded from the range.

## 10. When is `BigDecimal` or an exact conversion needed?

If the original data is a **decimal string** or the value must preserve its fractional part accurately (such as money), reading into a `double` first can lose precision. `BigDecimal` represents decimal numbers in base 10 and controls conversion:

```java
import java.math.BigDecimal;

BigDecimal amount = new BigDecimal("123.75");
int truncated = amount.intValue(); // 123, though fractional part can be lost
```

This is an **illustrative code snippet** inside a method, not a standalone runnable file. If you want to **fail when a fractional part exists or the value does not fit the target type**, use:

```java
BigDecimal amount = new BigDecimal("123.75");
// int exact = amount.intValueExact(); // throws ArithmeticException
```

`intValueExact()` succeeds only when the value is an exact integer within the `int` range; `longValueExact()` does the same for `long`. When rounding is required before converting, choose `setScale(0, RoundingMode.XXX)` with an explicit policy and then call the appropriate conversion method.

If integers can exceed the `long` range, `BigInteger` is an option for arbitrary-magnitude integers; `BigDecimal.toBigIntegerExact()` requires the decimal value to be an exact integer. Do not assume casting from `double` to `long` automatically extends storage limits.

## 11. Common errors

| Symptom | Cause | How to handle |
|---|---|---|
| `(int) -3.9` gives -3 rather than -4 | Cast truncates toward 0 | Use `Math.floor` if rounding down is required |
| `(int) 3.9` gives 3 rather than 4 | Cast does not round to nearest | Use `Math.round` per the appropriate rule |
| `(int) Double.NaN` gives 0 | Java's NaN conversion rule | Check `Double.isNaN` or `isFinite` beforehand |
| `(int) Double.POSITIVE_INFINITY` gives MAX | Out-of-range value clamps at bound | Reject non-finite values if invalid |
| `(int) 1e20` still produces an `int` value | Cast saturates, does not throw | Check range before converting |
| `(byte) 130.9` becomes -126 | Converts double → int 130 → keeps 8 bits | Also check `byte` range if exact value is needed |
| `(byte) +Infinity` becomes -1 | +Infinity → `Integer.MAX_VALUE` → low 8 bits | Understand the two-step process and reject infinity |
| `(int) 16_777_217f` gives 16_777_216 | `float` already lost precision earlier | Use a type/format suited to the data source |
| `(int) a + (int) b` differs from `(int)(a+b)` | Truncation happens at different points | Place casts and parentheses per the requirement |
| Checking `doubleValue <= Long.MAX_VALUE` is unreliable | `Long.MAX_VALUE` converts to double as \(2^{63}\) | Use the exact bound `value < 0x1.0p63` |
| Using a cast to verify "input is an integer" | Cast silently drops the fractional part | Check fractional part or use `intValueExact` |

## 12. Self-check exercises

**Question 1.** What do `(int) 8.99` and `(int) -8.99` equal?  
**Answer:** 8 and -8 because both truncate the fractional part toward 0.

**Question 2.** Does `(int) -0.99` equal -1?  
**Answer:** No. The result is 0.

**Question 3.** How does `(int) -2.7` differ from `Math.floor(-2.7)`?  
**Answer:** -2 and -3.0 respectively; `floor` rounds down, while cast truncates toward 0.

**Question 4.** Why does `(int) Double.NaN` produce 0 while `(int) Double.POSITIVE_INFINITY` produces 2_147_483_647?  
**Answer:** The JLS specifies NaN becomes integer 0; positive infinity becomes the maximum value of the intermediate type.

**Question 5.** What result does `(byte) 130.9` give?  
**Answer:** -126. First it truncates toward 0 to `int` 130, then narrows to `byte` by keeping the low 8 bits.

**Question 6.** Given `double a = 1.9, b = 2.9`, what do `(int)a + (int)b` and `(int)(a+b)` produce?  
**Answer:** 3 and 4. The cast occurs at two different points.

**Question 7.** Does casting from `double` to `int` throw an exception when out of range?  
**Answer:** No. It yields the corresponding MIN/MAX bound; if data must be rejected, validate beforehand.

**Question 8.** Is `float f = 16_777_217f; (int) f` guaranteed to equal 16_777_217?  
**Answer:** No. `float` rounds the value to 16_777_216 before the cast.

**Question 9.** Why must checking a `double` against `Long.MAX_VALUE` be done carefully?  
**Answer:** Because `Long.MAX_VALUE` is not represented exactly as a `double` and rounds to \(2^{63}\), outside the `long` range. A safe upper bound under an input-range policy is `value < 0x1.0p63`.

**Question 10.** When decimal data is required to be an exact integer, what should be used?  
**Answer:** For `BigDecimal` data, use `intValueExact()` or `longValueExact()`. For `double`, check finiteness, range, and zero fractional part before converting, while recognizing that the value may already have lost precision at the source.

## 13. Key takeaways and references

- **Within valid range and for finite numbers:** `float/double → int/long` by casting **truncates toward 0**, for both positive and negative numbers.
- **NaN → 0**, **+Infinity/too large → MAX**, **-Infinity/too small → MIN** of the intermediate type; does not throw exceptions automatically.
- **Casting to `byte/short/char` is two steps:** to `int` under floating-point rules, then further integer narrowing by bits.
- **Cast timing matters:** `(int)a + (int)b` can differ from `(int)(a+b)`.
- **Choose conversion policy based on need:** truncation, rounding, rejecting out-of-range data, or requiring exact conversion are four distinct goals.

Language specification source: [Java Language Specification — Chapter 5, Conversions and Contexts, §5.1.3 Narrowing Primitive Conversion](https://docs.oracle.com/javase/specs/jls/se26/html/jls-5.html).
