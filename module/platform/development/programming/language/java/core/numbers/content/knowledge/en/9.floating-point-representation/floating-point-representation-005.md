# Range of Consecutive Integers Represented Exactly by `float` and `double` in Java

## 1. What Does “Consecutively Represented Exactly” Mean?

A floating-point type **represents an integer `n` exactly** when a value of that type equals `n` without rounding to another number. However, the fact that an individual integer is representable does not mean **every adjacent integer** is representable too.

We call `[-M, M]` a **range of consecutive integers represented exactly** when every integer `n` satisfying `-M <= n <= M` has a `float` or `double` value equal to `n`. For Java's two types:

| Type | Significand Precision Bits | Exact Consecutive Integer Range (Inclusive) | Positive Threshold in Decimal |
| --- | ---: | --- | ---: |
| `float` | 24 bits | `[-2^24, 2^24]` | `16_777_216` |
| `double` | 53 bits | `[-2^53, 2^53]` | `9_007_199_254_740_992` |

**Immediately past** the positive threshold, `2^24 + 1` is not represented exactly by `float`, and `2^53 + 1` is not represented exactly by `double`. However, larger integers **can still** be represented exactly, such as `2^24 + 2` as `float` and `2^53 + 2` as `double`.

The word “consecutive” is crucial: you should not write “`float` can only represent integers up to `2^24`” or “`double` can only represent integers up to `2^53`.” Those statements are false: floating-point types can represent many integers of much larger magnitude, but they **skip some integers in between**.

An example right at the boundary:

```java
int a = 16_777_216;       // 2^24
int b = 16_777_217;       // 2^24 + 1
int c = 16_777_218;       // 2^24 + 2

float fa = a;             // exact
float fb = b;             // rounded to 16_777_216f
float fc = c;             // exact
```

Consequently, `fa == fb` is `true` even though `a != b`. This is a latent bug when using `float` for identifier keys, counting large integers, or comparing two results that originally differed by one unit.

## 2. Why Are the Thresholds `2^24` and `2^53`?

Java's `float` and `double` follow the IEEE 754 binary32/binary64 formats. A normal finite number can be interpreted mathematically as:

\[
(-1)^{sign} \times (1.fraction)_2 \times 2^{exponent}
\]

In this form, the effective significand includes the implicit leading `1` bit (*implicit leading bit*) of normal numbers:

| Property | `float` (binary32) | `double` (binary64) |
| --- | ---: | ---: |
| Total bits | 32 | 64 |
| Sign bit | 1 | 1 |
| Exponent field | 8 | 11 |
| Actual stored fraction field | 23 | 52 |
| **Effective significand precision `p`** | **24** | **53** |

In the interval of positive numbers from `2^e` (inclusive) to `2^(e+1)` (exclusive), the spacing between two adjacent normal floating-point numbers is:

\[
ULP = 2^{e-(p-1)}
\]

`ULP` (*unit in the last place*) indicates the spacing at that precision level. For integers:

- When `ULP <= 1`, the representation grid is fine enough to hold **every integer**.
- At `2^p`, the spacing to the next value in the positive direction increases to `2`: the number `2^p + 1` lies halfway between two representable values.
- Beyond higher thresholds, the spacing can become `4`, `8`, `16`, ...; numbers whose low-order bits do not align with the step size can no longer be represented exactly.

For `float`, `p=24`: in `[2^23, 2^24)` the step is `1`, while at and immediately above `2^24` the step is `2`. For `double`, `p=53`: in `[2^52, 2^53)` the step is `1`, while at and above `2^53` the step is `2`.

**Note right at the boundary:** `2^p` itself is still represented exactly, and the integer right before it (`2^p - 1`) is still exact. The step sizes to the left and right of a power of two can differ. Thus, the consecutive exact range has **inclusive** endpoints `±2^p`; however, `2^p` no longer has a floating-point neighbor larger by `1` in the same type.

## 3. Directly Observing Gaps Past the Threshold

### 3.1. `float`: the `2^24` Boundary

| Original Integer | Represented `float` Value (as Integer) | Exact? |
| --- | ---: | --- |
| `16_777_215 = 2^24 - 1` | `16_777_215` | Yes |
| `16_777_216 = 2^24` | `16_777_216` | Yes |
| `16_777_217 = 2^24 + 1` | `16_777_216` | No |
| `16_777_218 = 2^24 + 2` | `16_777_218` | Yes |
| `16_777_219 = 2^24 + 3` | `16_777_220` | No |
| `16_777_220 = 2^24 + 4` | `16_777_220` | Yes |

In the region immediately above `2^24`, only **even** integers are represented exactly. Odd values lying between two representable even integers are rounded when converted to `float`.

Java's default rule for integer-to-floating-point conversion rounds to the nearest value; when exactly halfway between two values, it chooses the result whose least-significant significand bit is **even** (*round to nearest, ties to even*). Therefore:

- `16_777_217` lies halfway between `16_777_216` and `16_777_218`, so it rounds to `16_777_216`.
- `16_777_219` lies halfway between `16_777_218` and `16_777_220`, so it rounds to `16_777_220`.

On the negative side, the behavior is symmetric: `-16_777_217` rounds to `-16_777_216` as a `float`. Do not assume “negative numbers always round down”; rounding here is based on the nearest binary representable number.

### 3.2. `double`: the `2^53` Boundary

| Original Integer | Represented `double` Value (as Integer) | Exact? |
| --- | ---: | --- |
| `9_007_199_254_740_991 = 2^53 - 1` | `9_007_199_254_740_991` | Yes |
| `9_007_199_254_740_992 = 2^53` | `9_007_199_254_740_992` | Yes |
| `9_007_199_254_740_993 = 2^53 + 1` | `9_007_199_254_740_992` | No |
| `9_007_199_254_740_994 = 2^53 + 2` | `9_007_199_254_740_994` | Yes |
| `9_007_199_254_740_995 = 2^53 + 3` | `9_007_199_254_740_996` | No |

Example:

```java
long a = 9_007_199_254_740_992L;
long b = 9_007_199_254_740_993L;

double da = a; // 9_007_199_254_740_992
double db = b; // also 9_007_199_254_740_992
```

Here **two distinct `long` values can become the exact same `double`**. The Java conversion is still valid and throws no error, because it is a language-permitted integer → floating-point conversion.

Some libraries or protocols call `2^53 - 1` the *largest safe integer* because they require adding/subtracting `1` and adjacent numbers to remain distinguishable. In this lesson, we examine the **set of integers represented exactly**, so `2^53` itself is still exact and is the endpoint of the consecutive range; the term “safe” may impose stricter conditions for arithmetic operations.

## 4. Consecutive Range Differs from the Maximum Value of the Type

Do not confuse the `2^24`/`2^53` thresholds with `Float.MAX_VALUE`/`Double.MAX_VALUE`:

- `Float.MAX_VALUE` is approximately `3.4028235 × 10^38`, huge compared to `16_777_216`.
- `Double.MAX_VALUE` is approximately `1.7976931348623157 × 10^308`, huge compared to `9_007_199_254_740_992`.

These `MAX_VALUE` constants describe the **finite upper bound**, not the integer domain where every consecutive value is representable. Farther from 0, the spacing between floating-point values generally increases.

For example, `Long.MIN_VALUE = -2^63` **is represented exactly** by `double` because it is a power of 2, even though its magnitude exceeds `2^53`. In contrast, `Long.MAX_VALUE = 2^63 - 1` **is not exact** when converted to `double` and rounds to `2^63`, a value outside the `long` range.

Similarly, `Integer.MAX_VALUE = 2^31 - 1` when converted to `float` rounds to `2^31`. Notably, the resulting `float` is completely finite; being finite does not prove that the original integer value was preserved.

## 5. Relationship to Java Integer Types

| Conversion | Guaranteed Exact for **Every** Source Value? | Reason |
| --- | --- | --- |
| `byte` → `float` | Yes | The entire 8-bit range lies within `±2^24` |
| `short` → `float` | Yes | The entire 16-bit range lies within `±2^24` |
| `char` → `float` | Yes | `char` values from 0 to 65535 lie within the exact range |
| `int` → `float` | **No** | Many `int` values have magnitudes greater than `2^24` |
| `int` → `double` | **Yes** | The entire `int` range lies within `±2^53` |
| `long` → `float` | **No** | `float` significand has only 24 bits of precision |
| `long` → `double` | **No** | Many `long` values have magnitudes greater than `2^53` |

Even a **widening primitive conversion** like `int` → `float` or `long` → `double` can lose low-order bit information. “Widening” describes Java's conversion classification rule, not a guarantee to preserve every digit accurately.

`float` → `double` preserves the **already-existing `float` value**, but cannot recover the original integer if it was rounded earlier:

```java
int original = 16_777_217;
float rounded = original;       // 16_777_216
double widened = rounded;       // still exact 16_777_216, does not recover 16_777_217
```

A `double` represents every `int` exactly, yet this does not mean *every operation* on `int` values converted to `double` produces results matching exact mathematical integer arithmetic. Operation results can exceed `2^53` or produce unrepresentable fractional parts.

## 6. Using `Math.ulp`, `Math.nextUp`, and `Math.nextDown` to Inspect Spacing

Java provides helpful methods in `Math` to inspect the value “grid”:

- `Math.ulp(x)` returns the size of one ULP at `x` (overloaded for `float` and `double`).
- `Math.nextUp(x)` returns the adjacent representable floating-point value in the positive direction.
- `Math.nextDown(x)` returns the adjacent representable value in the negative direction.

At the `float` threshold:

```java
float edge = 16_777_216f;
float up = Math.nextUp(edge);     // 16_777_218f
float down = Math.nextDown(edge); // 16_777_215f
float step = Math.ulp(edge);      // 2.0f
```

At the `double` threshold:

```java
double edge = 9_007_199_254_740_992d;
double up = Math.nextUp(edge);     // 9_007_199_254_740_994d
double down = Math.nextDown(edge); // 9_007_199_254_740_991d
double step = Math.ulp(edge);      // 2.0d
```

An important detail: **`Math.ulp(edge)` equaling 2 does not mean the value below `edge` is two units away**. The boundary is where the step size increases: `nextDown(edge)` is `1` away, whereas `nextUp(edge)` is `2` away.

`Math.ulp` only measures local spacing, not whether a source conversion preserved full value. To evaluate precision for a specific source value, you must also compare against the source in a way that does not round the source during the check.

## 7. Complete, Directly Runnable Java 17 Example

Create the file `ExactIntegerRangeDemo.java`:

```java
public class ExactIntegerRangeDemo {
    // Use intermediate long to check float -> int without saturating at Integer.MAX_VALUE.
    private static boolean exactAsFloat(int original) {
        float encoded = original;
        return (long) encoded == (long) original;
    }

    // Long.MAX_VALUE in double rounds to 2^63: must guard this boundary.
    private static boolean exactAsDouble(long original) {
        double encoded = original;
        return encoded < 0x1.0p63 && (long) encoded == original;
    }

    public static void main(String[] args) {
        int floatEdge = 1 << 24;
        long doubleEdge = 1L << 53;

        System.out.println("float edge = " + floatEdge);
        System.out.println("float edge+1 stored = "
                + (long) (float) (floatEdge + 1));
        System.out.println("float edge+2 stored = "
                + (long) (float) (floatEdge + 2));
        System.out.println("float edge+1 exact = "
                + exactAsFloat(floatEdge + 1));
        System.out.println("float edge+2 exact = "
                + exactAsFloat(floatEdge + 2));
        System.out.println("float ulp at edge = " + Math.ulp((float) floatEdge));

        System.out.println("double edge = " + doubleEdge);
        System.out.println("double edge+1 stored = "
                + (long) (double) (doubleEdge + 1));
        System.out.println("double edge+2 stored = "
                + (long) (double) (doubleEdge + 2));
        System.out.println("double edge+1 exact = "
                + exactAsDouble(doubleEdge + 1));
        System.out.println("double edge+2 exact = "
                + exactAsDouble(doubleEdge + 2));
        System.out.println("double ulp at edge = "
                + Math.ulp((double) doubleEdge));

        System.out.println("Integer.MAX_VALUE exact as float = "
                + exactAsFloat(Integer.MAX_VALUE));
        System.out.println("Long.MAX_VALUE exact as double = "
                + exactAsDouble(Long.MAX_VALUE));
        System.out.println("Long.MIN_VALUE exact as double = "
                + exactAsDouble(Long.MIN_VALUE));
    }
}
```

Run with JDK 17 or later:

```bash
javac ExactIntegerRangeDemo.java
java ExactIntegerRangeDemo
```

Expected output:

```text
float edge = 16777216
float edge+1 stored = 16777216
float edge+2 stored = 16777218
float edge+1 exact = false
float edge+2 exact = true
float ulp at edge = 2.0
double edge = 9007199254740992
double edge+1 stored = 9007199254740992
double edge+2 stored = 9007199254740994
double edge+1 exact = false
double edge+2 exact = true
double ulp at edge = 2.0
Integer.MAX_VALUE exact as float = false
Long.MAX_VALUE exact as double = false
Long.MIN_VALUE exact as double = true
```

The two check methods above serve **the exact source types declared in their signatures**: one `int` to `float`, and one `long` to `double`. They are not general-purpose checkers for arbitrary real numbers or unbounded integers. `0x1.0p63` is a `double` literal representing exact `2^63`; `Long.MAX_VALUE`, once converted to `double`, becomes that exact value, so an upper-bound check is required before casting back to `long`.

In the `int` → `float` case, casting back to `long` lets the check avoid saturation bugs from `float` → `int` conversion at `Integer.MAX_VALUE`. A `float` converted from an `int` is always finite with magnitude within the `long` range, so casting to `long` has ample range to compare against the original `int`.

## 8. Pitfalls When Checking Whether Data Lost Precision

### 8.1. Mixed Comparisons Can Implicitly Convert the Source to `float`/`double`

```java
int n = 16_777_217;
float f = n;

System.out.println(n == f); // true, even though f holds 16_777_216
```

Java applies *binary numeric promotion*: when comparing `int` with `float`, `n` is also converted to `float`, so **both sides have been rounded** and the comparison reports equality.

Similarly:

```java
long n = 9_007_199_254_740_993L;
double d = n;

System.out.println(n == d); // true, even though d holds 9_007_199_254_740_992
```

Therefore, `original == (float) original` or `original == (double) original` is **not** a test guaranteeing lossless conversion. Keep and compare the source in an appropriate integer type while avoiding saturation traps when casting back.

### 8.2. Casting Back Can Saturate and Cause “False Positives”

A seemingly reasonable check is `(int) (float) n == n`. However, for `n = Integer.MAX_VALUE`, the `float` value rounds to `2^31` (outside the `int` range), and casting back to `int` saturates at `Integer.MAX_VALUE`; the comparison can return `true` even though the intermediate value is wrong.

Similarly, `Long.MAX_VALUE` converted to `double` becomes `2^63`, and casting back to `long` saturates at `Long.MAX_VALUE`. To check accurately, exclude intermediate values at or beyond the target type's bounds before casting, or use a wider intermediate integer type when the source range is known to be small enough, as in section 7.

### 8.3. Exact Decimal Numbers Are a Separate Issue

`0.1` is a real number with a finite decimal representation but no finite binary representation; hence `0.1d` is not mathematically exact. The `2^53` threshold **speaks only of consecutive integers**, not that every real number in `[-2^53, 2^53]` is represented exactly.

For monetary amounts or decimal inputs requiring digit preservation, consider `BigDecimal` created from a string:

```java
java.math.BigDecimal price = new java.math.BigDecimal("0.1");
```

If you need a large integer exceeding the `long` range, use `BigInteger`. It is impossible to recover the rounded-off portion if only `float`/`double` data remains.

### 8.4. Operations Near the Threshold Can Stop Incrementing by One

Example:

```java
float count = 16_777_216f;
count = count + 1f; // still 16_777_216f
```

Because `16_777_217` lies exactly halfway between two representable `float` values, the result rounds to `16_777_216f` (*ties to even*). The operation throws no exception. Likewise, adding `1d` to `9_007_199_254_740_992d` returns the initial value.

Do not use `float` or `double` as counters for operations requiring exact unit-by-unit integer increments over a large range; choose `int`, `long`, or `BigInteger` according to the required range and check for integer overflow where appropriate.

## 9. Rules for Choosing Types by Problem Domain

| Scenario | Approach |
| --- | --- |
| Storing any `int` value for floating-point processing | `double` preserves the integer value of every `int` |
| Storing counts guaranteed within `[-16_777_216, 16_777_216]` in `float` | Every integer in the range is exact, though subsequent operation precision must be checked |
| Converting an `int` outside that range to `float` | Not exact by default; check specific values or keep an integer type |
| Converting `long` to `double` | Every value in `[-2^53, 2^53]` is exact; outside that range only a subset is exact |
| Storing IDs, transaction codes, keys, or large counts | Use integer types (`long`, `BigInteger`) instead of `float`/`double` if every value must remain distinct |
| Working with money / decimals requiring exact decimal digits | Use `BigDecimal` from decimal string sources and explicit rounding rules |
| Inspecting the representation grid around a value | Use `Math.ulp`, `Math.nextUp`, `Math.nextDown`; they do not by themselves verify whether a source lost information |

Values beyond the threshold are not all wrong: for example, `2^60` is represented exactly by `double` because it is a power of 2. The key question is: **“Does this type represent every integer in the range I need accurately, or only discrete values?”**

## 10. Self-Check Questions

1. Does `float` represent `16_777_216` exactly? What about `16_777_217`?
2. Why is `16_777_218` still exact in `float` even though it lies outside the consecutive range?
3. Does a `double` represent every `int` value exactly? Does it represent every `long` value exactly?
4. `Long.MIN_VALUE` is an integer of very large magnitude. Why is it still exact in `double`?
5. Why can `long n = 9_007_199_254_740_993L; double d = n; n == d` be `true`?
6. Can `(int)(float)n == n` be used to guarantee an `int` → `float` conversion is exact?
7. At `2^24f`, how far away are `Math.nextDown` and `Math.nextUp` from that value?

**Answers:**

1. `16_777_216` yes; `16_777_217` no (rounds to `16_777_216`).
2. The step size above the threshold is `2`, so even numbers near the threshold still lie on the representation grid.
3. Yes for every `int`; no for every `long`, because `double` has only 53 bits of exact significand precision.
4. `-2^63` is a power of 2 and is represented exactly despite lying outside the consecutive range.
5. When comparing `long` with `double`, the `long` operand is also converted to `double`, making both sides match after losing information.
6. No; casting a rounded `float` back to `int` can saturate at `Integer.MAX_VALUE`, producing a false positive.
7. `nextDown(2^24f) = 2^24 - 1`, distance `1`; `nextUp(2^24f) = 2^24 + 2`, distance `2`.

**Remember:** `float` preserves *every* consecutive integer up to `±2^24`, and `double` up to `±2^53` (both inclusive). Beyond these ranges, many exact integers still exist, yet no longer **every** adjacent integer. Representable magnitude, significand precision, and calculation accuracy are three distinct properties.