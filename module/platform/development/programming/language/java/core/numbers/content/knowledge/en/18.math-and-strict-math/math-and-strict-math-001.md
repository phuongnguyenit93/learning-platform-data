# abs, min, max, signum, and clamp by JDK Version

> **Java core – numbers · Math and StrictMath**  
> **Goal:** Properly use absolute value, minimum/maximum selection, sign determination, and value clamping functions; handle integer overflow, NaN, infinity, and signed zero; distinguish APIs that run on Java 17 from `Math.clamp`/`StrictMath.clamp` added in JDK 21.

## 1. Overview: 5 Operations That Look Simple but Have Many Traps

When working with numbers, common questions are:

- **`abs(x)`:** what is the non-negative magnitude of x?
- **`min(a,b)`:** which value is smaller?
- **`max(a,b)`:** which value is larger?
- **`signum(x)`:** is x negative, zero, or positive?
- **`clamp(x,low,high)`:** bring x into the **closed interval** from low to high; if x is lower than low take low, if higher than high take high, if within the interval keep x.

Visual example on integers:

```text
             -∞               0         10              +∞
--------------|---------------|----------|----------------|----
                              [0--------10]
clamp(-5,0,10) -> 0
clamp( 7,0,10) -> 7
clamp(20,0,10) -> 10
```

However, Java does not have only one number system: integer types have a finite range; IEEE 754 floating-point types have NaN, ±Infinity, and both +0.0/-0.0. Some APIs are also **not available on older JDKs**. Therefore, you must pay attention to both **parameter types** and **JDK version**.

### API Reference Table

| Operation | Java 17 | JDK 21+ | Notes |
| --- | --- | --- | --- |
| `Math.abs` / `StrictMath.abs` | Yes | Yes | `int/long MIN_VALUE` remains negative when taking regular abs |
| `Math.absExact` / `StrictMath.absExact` | Yes (since 15) | Yes | Throws `ArithmeticException` if integer absolute value overflows |
| `Math.min` / `StrictMath.min` | Yes | Yes | Has int, long, float, double overloads |
| `Math.max` / `StrictMath.max` | Yes | Yes | Passing NaN to float/double overloads returns NaN |
| `Math.signum` / `StrictMath.signum` | Yes | Yes | Only has float/double overloads |
| `Integer.signum` / `Long.signum` | Yes | Yes | Returns int −1, 0, or 1 |
| `Math.clamp` / `StrictMath.clamp` | **No** | **Yes, since 21** | Validates min/max, multiple overloads |

**Special note:** on JDK 21, the `clamp` method for integers takes `(long value,long min,long max)` or `(long value,int min,int max)`; **there is no separate `clamp(int,int,int)` overload in the API table**. A call with three `int` expressions can still use the `long,int,int` overload by widening the first argument to `long`, and the return type in that case is `int`.

## 2. Math vs. StrictMath: Which Should You Choose?

Both `java.lang.Math` and `java.lang.StrictMath` provide basic arithmetic operations. Both classes have **static** methods, so call them directly:

```java
int magnitude = Math.abs(-12);
double minimum = StrictMath.min(3.0, 5.0);
```

Do not instantiate `new Math()` or `new StrictMath()`. These two classes are not designed to be instantiated.

For simple operations in this lesson like `abs`, `min`, `max`, and `signum`, special result rules are clearly documented in the Javadoc and both classes have corresponding semantics. `StrictMath` stands out in advanced mathematical operations with special requirements for algorithmic reproducibility; **you do not need to convert every `Math.abs` into `StrictMath.abs` to fix integer overflow or NaN bugs**.

Since Java 17, Java's floating-point expression semantics have been unified under the *always-strict* mode; this **does not eliminate** NaN, signed zero, or representation limits. `Math` and `StrictMath` remain two separately documented APIs, but in this topic you must focus on **each method's contract** rather than treating the name `StrictMath` as a guarantee that integer operations automatically check for overflow.

## 3. Math.abs and StrictMath.abs: Absolute Value

`abs` returns the magnitude of a number according to the rules of the input type:

```java
System.out.println(Math.abs(-7));        // 7
System.out.println(Math.abs(-7L));       // 7
System.out.println(Math.abs(-3.25));     // 3.25
System.out.println(Math.abs(-3.25f));    // 3.25
```

Standard overloads:

| Function | Parameter | Return Type |
| --- | --- | --- |
| `Math.abs(int)` | int | int |
| `Math.abs(long)` | long | long |
| `Math.abs(float)` | float | float |
| `Math.abs(double)` | double | double |

`StrictMath.abs` also has four corresponding overloads.

With `float`/`double`, remember three cases:

```java
System.out.println(Math.abs(-0.0));                    // 0.0
System.out.println(Math.abs(Double.NEGATIVE_INFINITY)); // Infinity
System.out.println(Double.isNaN(Math.abs(Double.NaN)));  // true
```

`Math.abs(-0.0)` returns **+0.0**, without preserving the negative sign of zero. If you must preserve the sign bit separately (for example, special binary logic), `abs` is not the appropriate operation to keep the sign.

## 4. Important Trap: abs of MIN_VALUE Can Still Be Negative

With signed two's complement integers, the negative range has **one** extra value with no positive counterpart of the same magnitude:

```text
int:
MIN_VALUE = -2147483648
MAX_VALUE =  2147483647

long:
MIN_VALUE = -9223372036854775808
MAX_VALUE =  9223372036854775807
```

Therefore, the mathematical absolute value of `Integer.MIN_VALUE` is 2,147,483,648, **exceeding the `int` range**.

```java
int minimum = Integer.MIN_VALUE;
System.out.println(Math.abs(minimum)); // -2147483648
```

This is the result of **overflow according to Java's integer rules**: `Math.abs(int)` does not throw an exception by itself. Similarly:

```java
System.out.println(Math.abs(Long.MIN_VALUE));
// -9223372036854775808
```

The consequence is very practical:

```java
int hash = Integer.MIN_VALUE;
int bucket = Math.abs(hash) % 10;
System.out.println(bucket); // -8
```

If you subsequently use `bucket` as an array index, you may encounter an error. Do not use the formula `Math.abs(x) % size` as a way that **always guarantees a non-negative index**.

### How to Handle Depending on the Goal

**Need to detect overflow and report an error:** since Java 15 there are `Math.absExact(int)`/`Math.absExact(long)` and the corresponding methods in `StrictMath`:

```java
try {
    Math.absExact(Integer.MIN_VALUE);
} catch (ArithmeticException ex) {
    System.out.println("abs overflow");
}
```

**Need the absolute value of every int value in a sufficiently wide type:**

```java
long exactMagnitude = Math.abs((long) Integer.MIN_VALUE);
System.out.println(exactMagnitude); // 2147483648
```

The cast to `long` must occur **before** calling `abs`. Writing `(long) Math.abs(Integer.MIN_VALUE)` is too late: the `abs(int)` call has already overflowed.

**With `Long.MIN_VALUE`**, even `long` is not enough to hold the positive magnitude. When you need an exact mathematical integer, use `BigInteger`:

```java
import java.math.BigInteger;

BigInteger magnitude =
        BigInteger.valueOf(Long.MIN_VALUE).abs();
System.out.println(magnitude); // 9223372036854775808
```

**If the goal is an index 0..size−1**, consider `Math.floorMod(hash,size)` when `size > 0`, instead of forcing absolute value:

```java
System.out.println(Math.floorMod(Integer.MIN_VALUE, 10)); // 2
```

The chosen formula depends on business requirements: `floorMod` means non-negative modulo with a positive modulus, which is **different** from taking the absolute value and then taking the remainder.

## 5. min and max for Integers

The `Math.min(a,b)` and `Math.max(a,b)` methods select the smaller/larger element in numerical order.

```java
System.out.println(Math.min(7, 12));   // 7
System.out.println(Math.max(7, 12));   // 12
System.out.println(Math.min(-5L, 3L)); // -5
```

There are int, long, float, and double overloads. When mixing types, **numeric promotion** and overload resolution are things to watch out for:

```java
int small = 5;
long large = 9L;
long result = Math.max(small, large); // selects long overload
```

If the result is required to remain type `int`, ensure that the operands and value range are appropriate. Do not narrowing-cast a `long` value to `int` before choosing min/max if bits could be lost.

### min/max Do Not Automatically Check Input Expression Overflow

```java
int a = Integer.MAX_VALUE;
int b = 2;
int chosen = Math.max(a + b, 0); // a+b overflows to negative
System.out.println(chosen);      // 0
```

`Math.max` cannot know that the expression `a+b` was intended to represent a number larger than `Integer.MAX_VALUE`. You must check the addition beforehand, such as with `Math.addExact(a,b)` or converting to `long` before the addition if the range is wide enough.

## 6. min/max with float/double: NaN and Signed Zero

Unlike integers, IEEE 754 types have `NaN` and two ways to encode zero.

### 6.1. When One Argument Is NaN

For `float`/`double` overloads:

```java
double result = Math.min(Double.NaN, 42.0);
System.out.println(Double.isNaN(result)); // true
```

Similarly:

```java
System.out.println(Double.isNaN(
        Math.max(42.0, Double.NaN))); // true
```

**Traditional Math.min/max here are NaN-propagating.** Do not assume that `Math.max(x,0.0)` "filters out NaN" or returns 0 when `x` is NaN.

If business logic dictates ignoring NaN measurement samples, define missing/invalid data handling logic beforehand, rather than expecting `min/max` to automatically discard NaN values. NaN-skipping rules differ from standard algebraic operation rules.

### 6.2. When One Argument Is +0.0 and the Other Is -0.0

The two zeros compare equal under `==`:

```java
System.out.println(+0.0 == -0.0); // true
```

However, `Math.min` and `Math.max` distinguish the sign of zero:

```java
System.out.println(Math.min(+0.0, -0.0)); // -0.0
System.out.println(Math.max(+0.0, -0.0)); // 0.0
```

In the ordering of these methods, **−0.0 is considered smaller than +0.0**. This differs from using `<`/`>` operators on zero because `-0.0 < +0.0` is false.

The same cases apply to the `float` overload:

```java
float small = Math.min(+0.0f, -0.0f); // -0.0f
float big = Math.max(+0.0f, -0.0f);   // +0.0f
```

When debugging bit patterns, check:

```java
long bits = Double.doubleToRawLongBits(
        Math.min(+0.0, -0.0));
System.out.printf("%016x%n", bits);
// 8000000000000000
```

The number `0x8000000000000000` is the IEEE 754 pattern for `-0.0`. Use raw bits when you need to verify the exact sign of zero or binary encoding.

## 7. signum Is the Sign of a Number, Not Its Absolute Value

`Math.signum(float)` and `Math.signum(double)` return:

- `-1.0` or `-1.0f` if the argument is a **non-zero** negative number;
- `+1.0` or `+1.0f` if the argument is a **non-zero** positive number;
- preserves `+0.0` or `-0.0` if the input is signed zero;
- returns `NaN` if the argument is NaN.

```java
System.out.println(Math.signum(-12.5)); // -1.0
System.out.println(Math.signum( 12.5)); // 1.0
System.out.println(Math.signum(  0.0)); // 0.0
System.out.println(Math.signum( -0.0)); // -0.0
System.out.println(Double.isNaN(
        Math.signum(Double.NaN)));      // true
```

With `±Infinity`, the sign is still defined: `signum(+Infinity)=+1.0`, `signum(-Infinity)=-1.0`.

**There is no `Math.signum(int)` or `Math.signum(long)` overload.** For integers, use:

```java
System.out.println(Integer.signum(-12)); // -1
System.out.println(Integer.signum(0));   // 0
System.out.println(Long.signum(100L));   // 1
```

Do not assume the return type of `Math.signum(-12)` is `int`: the `int` argument can be converted to `float` and select the `float` overload (according to Java's overload rules); the result is **not** type `int`. When you need explicit, properly typed integer handling, choose `Integer.signum`/`Long.signum`.

### Why Is signum(-0.0) Not Positive 0.0?

According to IEEE 754, `-0.0` and `+0.0` have different signs even though `==` returns true. `Math.signum` returns **the exact input zero** when the argument equals zero, so:

```java
double negativeZero = -0.0;
double result = Math.signum(negativeZero);
System.out.println(result); // -0.0
```

If you only need a 3-state classification `-1,0,+1` in your application and **do not want to distinguish zero signs**, you can check `x == 0.0` first to return the integer 0 according to business meaning. However, you must handle NaN separately because both comparisons `NaN == 0.0` and `NaN < 0.0` are false.

## 8. What Does Clamp Mean?

*Clamp* (bounding/saturation) brings a value into the closed interval `[min,max]`:

\[
\operatorname{clamp}(x,\ell,h)=
\begin{cases}
\ell,&x<\ell\\
h,&x>h\\
x,&\ell\le x\le h.
\end{cases}
\]

Application examples:

- Capping volume level from 0 to 100.
- Bounding progress indicator from 0.0 to 1.0.
- Bringing out-of-range scores to valid boundaries **when business rules accept saturation**.
- Converting a `long` to an `int` by **saturating** to `int` bounds, instead of truncating bits.

**Clamp is not the same** as modulo division, bit narrowing, or normalization. `clamp(150,0,100)` is 100; `150 % 101` is 49, while casting to `byte` can yield yet another number.

In particular, clamp is also **not validation** in the sense of rejecting any out-of-range value; it **actively replaces** the value with the bound. If out-of-range data must cause an error, check the bounds and throw an exception instead of silently clamping.

## 9. JDK Versions: Math.clamp/StrictMath.clamp Added in 21

A very common compatibility trap:

```java
// Available only since JDK 21:
// int volume = Math.clamp(150L, 0, 100);
```

This code **does not compile when using `javac --release 17`** or compiling on JDK 17 because the `clamp` method does not exist on `Math` there.

JDK 21 added four overloads in both `Math` and `StrictMath`:

| Overload Signature | Result Type | Meaning |
| --- | --- | --- |
| `clamp(long value, int min, int max)` | `int` | Clamps a `long` into the specified `int` range |
| `clamp(long value, long min, long max)` | `long` | Clamps a 64-bit integer |
| `clamp(float value, float min, float max)` | `float` | Clamps a 32-bit floating-point number |
| `clamp(double value, double min, double max)` | `double` | Clamps a 64-bit floating-point number |

These overloads have the same basic semantics in `Math` and `StrictMath`. Java 21 documentation explicitly notes `Since: 21` for them.

A call with three `int`s is resolved via the overload taking `long,int,int`:

```java
// Java 21+:
int level = Math.clamp(150, 0, 100);
System.out.println(level); // 100
```

However, you should write `150L` if illustrating the **saturating narrowing of long to int** feature, so the overload intent is clear.

### Usage When Code Runs Across Multiple JDK Versions

If a project targets Java 17 or still ships applications for Java 17:

- **Do not call** `Math.clamp` directly in shared code compiled with `--release 17`.
- Write a clamp helper for the required type, with a `min <= max` check.
- When upgrading the minimum version to JDK 21+, consider migrating the helper to `Math.clamp` and re-testing NaN/±0.0 cases.

Do not evaluate API availability solely by the JDK running on the developer's machine: a project may use a newer JDK to build while passing `--release 17` for compatibility targets.

## 10. Integer Clamp: From long to int via Saturation

The overload:

```java
// Java 21+:
int result = Math.clamp(hugeLong, lowInt, highInt);
```

takes a `long` input value and two `int` bounds; the result always lies within the interval defined by the two bounds, so it can return type `int` without **dropping high bits like a narrowing cast**.

Example:

```java
// Java 21+:
long count = 5_000_000_000L;
int limited = Math.clamp(count, 0, 100);

System.out.println(limited); // 100
```

Compare with a cast:

```java
long count = 5_000_000_000L;
int truncated = (int) count; // bitwise narrowing, not clamping
```

The two operations represent **two completely different contracts**:

- `(int) longValue`: keeps the low 32 bits and may change the sign/value.
- `Math.clamp(longValue, min, max)`: returns the nearest bound if exceeded, keeps the value when within the interval.
- `Math.toIntExact(longValue)`: requires the value to be within `int` range, otherwise **throws `ArithmeticException`**.

If the requirement is "keep exact or fail", `Math.toIntExact` is more suitable than clamp. If the requirement is "always produce an index or level within bounds", clamp is right.

### Invalid Bounds Must Be Rejected

```java
// Java 21+:
// Math.clamp(5L, 10, 0); // IllegalArgumentException because 10 > 0
```

Standard clamp **does not swap min and max automatically**. If the application allows reversed bounds and wants to swap them, that is a separate **business data normalization** step; it must be explicitly defined before calling the API.

## 11. Float/Double Clamp: NaN and Signed Zero Are Not Ignored

With JDK 21+:

```java
double result = Math.clamp(1.4, 0.0, 1.0);
System.out.println(result); // 1.0
```

However, floating-point requires checking special constraints:

**1. If `value` itself is NaN**, the result remains NaN:

```java
// Java 21+:
double result = Math.clamp(Double.NaN, 0.0, 1.0);
System.out.println(Double.isNaN(result)); // true
```

**2. If either bound is NaN**, the method throws `IllegalArgumentException`:

```java
// Java 21+:
// Math.clamp(0.5, Double.NaN, 1.0); // IllegalArgumentException
```

**3. If `min > max`**, the method throws `IllegalArgumentException`. This is a contract check that should not be omitted when writing your own helper for Java 17.

**4. Signed zero is distinguished according to clamp's ordering.**

```java
// Java 21+:
double z = Math.clamp(-0.0, +0.0, 1.0);
System.out.println(z); // 0.0 (positive zero)
```

When the lower bound is `+0.0` and the value is `-0.0`, clamping raises it to `+0.0`. This differs from writing it manually:

```java
double naive = -0.0;
if (naive < +0.0) naive = +0.0; // condition is false!
```

Because `-0.0 < +0.0` returns false, pure `<`/`>` comparisons may **fail to reproduce** `Math.clamp` results accurately.

**5. An interval with `min=+0.0` and `max=-0.0` is considered invalid**, even though `+0.0 == -0.0` is true under arithmetic comparison:

```java
// Java 21+:
// Math.clamp(0.0, +0.0, -0.0); // IllegalArgumentException
```

With valid bounds `min=-0.0`, `max=+0.0`, this interval allows both forms of zero according to the signed-zero rules of the floating-point API.

### Infinity Is Also an Argument with Clear Rules

Bounds can be ±Infinity if the order is valid; for example `[-Infinity,+Infinity]` is the full interval according to the ordering of non-NaN floating-point numbers.

If the input is `+Infinity` and the upper bound is finite, clamp returns the upper bound. However, if the application requires the input to **be finite**, clamp does not replace checking `Double.isFinite(x)` beforehand (especially if the bounds allow Infinity).

## 12. Java 17: Writing a Clamp Helper When the API Does Not Exist Yet

An integer helper on Java 17:

```java
static int clampInt17(int value, int min, int max) {
    if (min > max) {
        throw new IllegalArgumentException("min > max");
    }
    return Math.max(min, Math.min(value, max));
}
```

This is an **illustrative method** and must be placed inside a class. It performs saturation as defined by clamp for type `int`, with valid-bounds checking.

If you need saturating narrowing from `long` to `int` on Java 17, use an appropriate helper:

```java
static int clampLongToInt17(long value, int min, int max) {
    if (min > max) {
        throw new IllegalArgumentException("min > max");
    }
    if (value < min) return min;
    if (value > max) return max;
    return (int) value; // safe: proven to lie between int bounds
}
```

This is a readable version of the idea behind the `Math.clamp(long,int,int)` overload in Java 21+. The comparisons widen the `int` bounds to `long`; the final cast **only occurs once the value is within the int bounds range**.

### Should You Write float/double Clamp Yourself Using Math.min/max?

You can write:

```java
double candidate = Math.max(min, Math.min(value, max));
```

in contexts where bounds are already guaranteed valid, but **do not treat this as a complete drop-in replacement for Math.clamp in all cases** without adding checks for NaN bounds, reversed bounds, and signed zero. On JDK 21+, prefer the standard API when semantic accuracy is needed; on Java 17, explicitly define the policy for handling special floating-point values and test it.

### Avoid the Clamp-Then-Cast Trap

```java
// Need safe long narrowing on Java 17:
long total = 5_000_000_000L;
int limited = clampLongToInt17(total, 0, 100);
// limited == 100
```

Do not do this:

```java
// Wrong order:
// int limited = clampInt17((int) total, 0, 100);
```

Because the `long → int` cast can lose bits **before** clamping, causing the value to take the wrong branch.

## 13. Reading Overloads Correctly: Literals, Promotion, and Return Types

Java selects an overload based on the **compile-time types of the arguments**, not just their runtime values.

```java
int i = 5;
long l = 5L;

int small = Math.abs(i);  // overload int -> int
long big = Math.abs(l);   // overload long -> long
```

In `min/max`, when mixing `int` and `long`, the `long` overload can be selected:

```java
int a = 100;
long b = 200L;
long larger = Math.max(a, b); // 200L
```

With `signum`, only `float` and `double` overloads exist in `Math`/`StrictMath`. To get back an integer −1/0/1, use `Integer.signum` or `Long.signum`.

With `clamp` on JDK 21+:

```java
// long, int, int => int result:
int first = Math.clamp(15L, 0, 10);  // 10

// long, long, long => long result:
long second = Math.clamp(15L, 0L, 10L); // 10

// double, double, double => double result:
double third = Math.clamp(1.5, 0.0, 1.0); // 1.0
```

To emphasize: **literal types** `0`, `0L`, and `0.0` can affect which method gets called and the type of the resulting expression.

Avoid writing "flexible" code with arbitrary casts like `Math.clamp((int) someLong,... )`: that cast may have already lost data before the call even starts.

## 14. Choosing the Right Function for the Business Goal

| Goal | Option |
| --- | --- |
| Absolute value of float/double, accepting +0.0 and NaN | `Math.abs(x)` |
| Absolute value of int/long without allowing overflow | `Math.absExact(x)` (Java 15+) |
| Absolute value of any int within long range | `Math.abs((long) x)` |
| Absolute value of any long including MIN_VALUE as mathematical value | `BigInteger.valueOf(x).abs()` |
| Choose smallest/largest between two integers | `Math.min/max` |
| Choose min/max floating-point per Java rules, NaN propagates | `Math.min/max` |
| Classify sign of float/double, preserving ±0.0 | `Math.signum` |
| Classify sign of int/long into −1/0/1 | `Integer.signum`/`Long.signum` |
| Saturate within interval on JDK 21+ | `Math.clamp`/`StrictMath.clamp` |
| Saturate on Java 17 | Helper with bounds check |
| Reject out-of-range numbers instead of modifying value | Compare bounds and throw error; use `Math.toIntExact` when converting long → int |
| Get non-negative modulo index | `Math.floorMod(x,size)` with positive size |

Three **non-equivalent** strategies to distinguish:

1. **Clamp/saturation**: pull back to the bound if exceeded.
2. **Checked conversion**: reject out-of-range data.
3. **Modulo/wraparound**: take remainder or keep low bits.

An out-of-range value can have different valid treatments depending on requirements. Document the data contract clearly instead of choosing by an API name that "sounds safe".

## 15. Standalone Java 17+ Program

Create file **`MathBoundsJava17Demo.java`**:

```java
public class MathBoundsJava17Demo {
    private static int clampInt17(int value, int min, int max) {
        if (min > max) {
            throw new IllegalArgumentException("min > max");
        }
        return Math.max(min, Math.min(value, max));
    }

    private static int clampLongToInt17(long value, int min, int max) {
        if (min > max) {
            throw new IllegalArgumentException("min > max");
        }
        if (value < min) return min;
        if (value > max) return max;
        return (int) value;
    }

    public static void main(String[] args) {
        System.out.println("abs(-7) = " + Math.abs(-7));
        System.out.println("abs(INT_MIN) = "
                + Math.abs(Integer.MIN_VALUE));

        try {
            Math.absExact(Integer.MIN_VALUE);
        } catch (ArithmeticException ex) {
            System.out.println("absExact(INT_MIN) = rejected");
        }

        System.out.println("wide abs(INT_MIN) = "
                + Math.abs((long) Integer.MIN_VALUE));
        System.out.println("min(7,12) = " + Math.min(7, 12));
        System.out.println("max(7,12) = " + Math.max(7, 12));

        System.out.println("min(+0,-0) = "
                + Math.min(+0.0, -0.0));
        System.out.println("max(+0,-0) = "
                + Math.max(+0.0, -0.0));
        System.out.println("min(NaN,1) is NaN = "
                + Double.isNaN(Math.min(Double.NaN, 1.0)));

        System.out.println("signum(-3.5) = "
                + Math.signum(-3.5));
        System.out.println("signum(-0.0) = "
                + Math.signum(-0.0));
        System.out.println("int signum(-42) = "
                + Integer.signum(-42));
        System.out.println("strict abs(-7) = "
                + StrictMath.abs(-7));

        System.out.println("clamp17(-5) = "
                + clampInt17(-5, 0, 10));
        System.out.println("clamp17(7) = "
                + clampInt17(7, 0, 10));
        System.out.println("clamp17(20) = "
                + clampInt17(20, 0, 10));
        System.out.println("long-to-int clamp17 = "
                + clampLongToInt17(5_000_000_000L, 0, 100));

        try {
            clampInt17(5, 10, 0);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid bounds = rejected");
        }

        System.out.println("floorMod(INT_MIN,10) = "
                + Math.floorMod(Integer.MIN_VALUE, 10));
    }
}
```

Compile against Java 17 APIs even when a newer JDK is installed on the machine:

```bash
javac --release 17 MathBoundsJava17Demo.java
java MathBoundsJava17Demo
```

**Expected stdout:**

```text
abs(-7) = 7
abs(INT_MIN) = -2147483648
absExact(INT_MIN) = rejected
wide abs(INT_MIN) = 2147483648
min(7,12) = 7
max(7,12) = 12
min(+0,-0) = -0.0
max(+0,-0) = 0.0
min(NaN,1) is NaN = true
signum(-3.5) = -1.0
signum(-0.0) = -0.0
int signum(-42) = -1
strict abs(-7) = 7
clamp17(-5) = 0
clamp17(7) = 7
clamp17(20) = 10
long-to-int clamp17 = 100
invalid bounds = rejected
floorMod(INT_MIN,10) = 2
```

Explanation:

- `Math.abs(Integer.MIN_VALUE)` lacks positive range and returns the same negative number; `absExact` detects that case.
- Casting `int → long` before `abs` preserves enough range to obtain `2147483648`.
- Floating-point `min/max` handles signed zero and NaN differently from regular arithmetic comparisons.
- `signum(-0.0)` preserves the zero sign; `Integer.signum` returns primitive int.
- Both Java 17 helpers perform integer clamping with bounds checking; the `long→int` helper avoids premature narrowing cast.
- `floorMod` yields a non-negative remainder when the modulus is positive.

## 16. Separate Example for JDK 21+ with Math.clamp

This program is **not compatible with Java 17**. Create file **`MathClampJava21Demo.java`** and compile with `--release 21` or use JDK 21+:

```java
public class MathClampJava21Demo {
    public static void main(String[] args) {
        System.out.println("int from long = "
                + Math.clamp(5_000_000_000L, 0, 100));
        System.out.println("long = "
                + Math.clamp(15L, 0L, 10L));
        System.out.println("double = "
                + Math.clamp(1.5, 0.0, 1.0));
        System.out.println("strict = "
                + StrictMath.clamp(-3L, 0L, 10L));

        double zero = Math.clamp(-0.0, +0.0, 1.0);
        System.out.println("negative zero clamped = " + zero);

        double nan = Math.clamp(Double.NaN, 0.0, 1.0);
        System.out.println("NaN value = "
                + Double.isNaN(nan));

        try {
            Math.clamp(5L, 10, 0);
        } catch (IllegalArgumentException ex) {
            System.out.println("reversed bounds = rejected");
        }

        try {
            Math.clamp(0.5, Double.NaN, 1.0);
        } catch (IllegalArgumentException ex) {
            System.out.println("NaN bound = rejected");
        }

        try {
            Math.clamp(0.0, +0.0, -0.0);
        } catch (IllegalArgumentException ex) {
            System.out.println("signed zero bounds = rejected");
        }
    }
}
```

Commands:

```bash
javac --release 21 MathClampJava21Demo.java
java MathClampJava21Demo
```

**Expected stdout (JDK 21+):**

```text
int from long = 100
long = 10
double = 1.0
strict = 0
negative zero clamped = 0.0
NaN value = true
reversed bounds = rejected
NaN bound = rejected
signed zero bounds = rejected
```

These are two **separate demo files by JDK baseline**, not mixed together. When a project still requires Java 17, use the first program or custom helpers; do not call Java 21's clamp API expecting a Java 17 runtime to understand it.

## 17. Common Mistakes and How to Fix Them

| Misconception | What Is True |
| --- | --- |
| "`Math.abs` is always non-negative" | `abs(Integer.MIN_VALUE)` or `abs(Long.MIN_VALUE)` remains negative due to overflow |
| "Casting the result of abs int to long fixes the bug" | You must cast the **input** to long before calling `abs` |
| "absExact exists on all older JDKs" | Available since Java 15; if targeting lower, you must check manually |
| "`Math.signum(int)` is a standard method" | Use `Integer.signum(int)`; Math.signum only has float/double |
| "`Math.min` with NaN returns the other number" | `Math.min/max` for float/double returns NaN if given NaN |
| "+0.0 and -0.0 cannot be distinguished by min/max" | `min(+0,-0)=-0.0`, `max(+0,-0)=+0.0` |
| "`Math.clamp` exists in Java 17" | The API was added in Java 21 |
| "`Math.clamp` is just shorthand for a cast" | Clamp saturates to bounds; narrowing cast truncates bits |
| "JDK 21 has a separate clamp(int,int,int) overload" | Integer overloads are `(long,int,int)` and `(long,long,long)`; int can widen |
| "Floating-point clamp can use < > comparators without checking zero" | `<` `>` comparisons do not distinguish -0.0 and +0.0 |
| "Clamp automatically filters out NaN" | NaN in **value** is preserved; NaN in **bound** causes `IllegalArgumentException` |
| "If min is greater than max, Java swaps them automatically" | `Math.clamp` throws `IllegalArgumentException` |
| "Math.max(x,0) prevents x from being NaN" | No; NaN propagates when using float/double overloads |
| "StrictMath will fix overflow or invalid types" | StrictMath also follows the contract of the called operation |
| "Clamp is always data validation" | It replaces out-of-range values with bounds; to reject, validate separately |

## 18. Exercises with Answers

**Exercise 1.** What does `Math.abs(Integer.MIN_VALUE)` return? Why?  
**Solution:** `-2147483648` because `+2147483648` exceeds the `int` range. Use `Math.absExact` to detect it or `Math.abs((long) x)` to get the true magnitude of any int.

**Exercise 2.** Do `Math.min(+0.0,-0.0)` and `Math.max(+0.0,-0.0)` produce the same result?  
**Solution:** No. They are `-0.0` and `+0.0` respectively, even though `+0.0 == -0.0` is true.

**Exercise 3.** What do `Math.signum(-0.0)` and `Integer.signum(0)` return?  
**Solution:** `-0.0` of type double and `0` of type int. The two methods do not have completely identical types or signed-zero contracts.

**Exercise 4.** Does `Math.min(Double.NaN,5.0)` return 5 or NaN?  
**Solution:** NaN. Use `Double.isNaN` to check; do not assume NaN is ignored.

**Exercise 5.** Will a Java 17 program containing `Math.clamp(150L,0,100)` compile with `--release 17`?  
**Solution:** No. `Math.clamp` was introduced in JDK 21. On Java 17, use a clamp helper with bounds checking.

**Exercise 6.** On JDK 21+, what type and value does `Math.clamp(5_000_000_000L,0,100)` return?  
**Solution:** Type `int`, value **100** via the `(long,int,int)` overload.

**Exercise 7.** Which zero does `Math.clamp(-0.0,+0.0,1.0)` return on JDK 21+?  
**Solution:** `+0.0` because clamp considers signed-zero ordering and does not allow −0.0 to be below the lower bound +0.0.

**Exercise 8.** On JDK 21+, is `Math.clamp(0.0,+0.0,-0.0)` valid?  
**Solution:** No. The bound pair +0.0 and −0.0 in this order is considered reversed; throws `IllegalArgumentException`.

**Exercise 9.** Given `long x = Long.MIN_VALUE` and needing the exact positive magnitude, is `Math.abs(x)` sufficient?  
**Solution:** No. You need `BigInteger.valueOf(x).abs()` or a representation not limited to the `long` range.

**Exercise 10.** A method must **reject** quantities outside 0..100. Is using clamp appropriate?  
**Solution:** No if the contract requires rejection. Clamp will replace any out-of-range value with 0 or 100; you must validate input and report an error.

**Exercise 11.** When `Integer.MIN_VALUE` is passed into the index formula `Math.abs(hash)%10`, what happens?  
**Solution:** `Math.abs(hash)` remains `Integer.MIN_VALUE`; the `%` operator can produce a negative result `-8`. Use `Math.floorMod(hash,10)` if the goal is a non-negative modulo.

**Exercise 12.** Why does a helper `Math.max(min,Math.min(value,max))` not completely replace `Math.clamp` if bounds checking is missing?  
**Solution:** That helper does not automatically throw errors when min>max or when a bound is NaN as required by `Math.clamp`'s contract. For floating-point, you must also watch out for ±0.0 and special values.

## 19. Checklist When Reading Math/StrictMath Code

1. Identify the **minimum JDK** the code must run on: Java 17 lacks `clamp`, Java 21+ has it.
2. Identify the **overload types**: int, long, float, double; especially integer clamp has the `long,int,int` overload.
3. With `abs(int/long)`, check for `MIN_VALUE` and decide **whether to allow overflow, throw an error, or widen types**.
4. With `min/max(float/double)`, check **NaN** and **signed zero** behavior if they can appear.
5. With `signum`, distinguish `Math.signum(float/double)` from `Integer/Long.signum`.
6. With `clamp`, check the **min <= max** constraint, plus NaN/signed-zero rules for floating-point.
7. Do not clamp after a **lossy narrowing cast** or after an overflowing calculation.
8. Distinguish **saturation, exact conversion, and modulo**; choose according to the business contract.
9. If using a Java 17 helper, test boundary values, NaN variants, and clearly document invalid-bounds handling.
10. Test examples on the **exact target Java version** with `javac --release N` when feasible.
11. For APIs that need to preserve integer values exceeding long, consider `BigInteger` instead of forcing into range.
12. In code reviews, prefer **clear intent** over hard-to-read nested min/max expressions.

### Reference Documentation by Version

- [Math – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html)
- [StrictMath – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StrictMath.html)
- [Math – Java SE 21 (including clamp)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html)
- [StrictMath – Java SE 21 (including clamp)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/StrictMath.html)

**Key takeaway:** `abs`, `min`, `max`, and `signum` are present in Java 17, but you must respect integer boundaries and IEEE 754 rules. `Math.clamp`/`StrictMath.clamp` only appeared in **JDK 21**, with bounds validation and clear specifications for NaN/±0.0. When choosing an API, check the **data types**, **out-of-range handling goal**, and **JDK version** instead of guessing from function names.
