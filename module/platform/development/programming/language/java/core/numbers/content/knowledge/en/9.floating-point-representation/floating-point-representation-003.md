# Binary Precision and Reliable Decimal Digits in Java

When writing `double x = 0.1;`, many people assume the computer has stored an exact **one-tenth**. In reality, Java's `float` and `double` use **binary** floating-point representation, so most decimal fractions like 0.1 cannot be stored exactly. The value is rounded to the nearest representable binary number.

A more important question than “How many digits does `double` have?” is: **how many digits can be relied upon in calculations, and how many decimal digits are needed to write a value out and read back the exact same bit value?** Those two numbers are different.

This lesson clarifies *precision* (significand accuracy), rounding error, spacing between representable numbers (*ULP*), the meaning of “6–9 digits” for `float` and “15–17 digits” for `double`, and how to apply those numbers when programming in Java 17+.

## 1. How Do `float` and `double` Store Numbers in Bits?

Java uses IEEE 754 binary floating-point representation for both types:

| Characteristic | `float` | `double` |
| --- | ---: | ---: |
| Total bits | 32 | 64 |
| Sign bit | 1 | 1 |
| Stored exponent bits (*exponent field*) | 8 | 11 |
| Stored fraction bits (*fraction field*) | 23 | 52 |
| Significand precision (*significand precision*) for normal numbers | **24 bits** | **53 bits** |
| Significant decimal digits typically reliable | **about 6–7** | **about 15–16** |
| Maximum significant decimal digits sufficient to write any value and read back exact bits | **9** | **17** |

Why are there 24 bits when only 23 fraction bits are stored? For **normal numbers**, IEEE 754 has an **implicit** leading 1 bit in the binary significand. Thus, `float` has 24-bit precision and `double` has 53-bit precision. For **subnormal** numbers very close to 0, the implicit 1 bit is no longer present; the effective number of significant bits can be smaller.

Conceptually, a normal number has the form:

```text
(-1)^sign × (1.fractionBits)_2 × 2^exponent
```

The exponent allows representing very large or very small numbers; it is the **number of significand bits** that determines the spacing between adjacent values and the detail that can be retained. Do not confuse **range** (magnitude span) with **precision** (numeric resolution).

For example, `double` can reach magnitudes up to roughly `1.8 × 10^308`, yet cannot distinguish every pair of consecutive integers around `10^16`.

## 2. Why Is Decimal 0.1 Not Stored Exactly?

Binary exactly represents fractions whose reduced denominators are powers of 2:

- `0.5 = 1/2 = 0.1₂` is stored exactly.
- `0.25 = 1/4 = 0.01₂` is stored exactly.
- `0.125 = 1/8 = 0.001₂` is stored exactly.
- `0.1 = 1/10` has a factor of 5 in its denominator, so its binary expansion continues infinitely and cannot be stored exactly in finite bits.

The actual `double` value nearest to `0.1` is:

```text
0.1000000000000000055511151231257827021181583404541015625
```

This is the **exact decimal value of the stored binary number**, not what Java prints by default for the literal. For `System.out.println(0.1)`, Java prints `0.1` because that short string is sufficient to parse back to the exact same `double` value.

```java
System.out.println(0.1);       // 0.1 (short format capable of round-trip)
System.out.println(0.1 + 0.2); // 0.30000000000000004
System.out.println(0.1 + 0.2 == 0.3); // false
```

`0.1`, `0.2`, and `0.3` have all been rounded to binary, and the addition rounds further. Consequently, the result of adding the stored values near `0.1` and `0.2` does not necessarily match the bits of the stored value near `0.3`.

Important: **this discrepancy does not mean the JVM is computing “against the Java standard.”** The `double` operations strictly follow the specified representation and rounding rules; the discrepancy arises when comparing against the exact decimal arithmetic humans expect.

## 3. Binary Precision: 24 Bits and 53 Bits of Significand

`p`-bit significand precision means that around a normal number, the significand carries roughly `p` bits of binary information. Converting to significant decimal digits by approximation:

```text
float:  24 × log10(2) ≈ 7.2247 digits
double: 53 × log10(2) ≈ 15.9546 digits
```

This is why we commonly say **`float` has about 7 significant digits** and **`double` has about 15–16 significant digits**. This is a practical guideline for the relative accuracy of normal numbers, **not a guarantee that every printed value has exactly 7 or 16 trustworthy digits**.

Example:

```java
float f = 16_777_216f;
float changed = f + 1f;
// f and changed are equal: at 2^24, the ULP above is 2 so +1 rounds back
```

At larger magnitudes, smaller units can no longer be distinguished. Always consider **the magnitude of the numbers**, **the differences you need to measure**, and **the operations performed**, rather than merely counting digits after the decimal point.

## 4. Difference Between Trustworthy Digits and Round-Trip Digits

The two data conversion directions are:

1. **Decimal → Binary → Decimal:** we enter a decimal number with a certain number of significant digits, store it in `float`/`double`, and want to express the original number back to the chosen accuracy.
2. **Binary → Decimal → Binary:** we already have an arbitrary `float`/`double` bit value, write it out as a decimal string, and want to parse the string back to the **exact original bit value**.

The two goals require different numbers of digits.

| Question | `float` | `double` |
| --- | ---: | ---: |
| Conservative significant decimal digits commonly used when preserving accuracy | **6** | **15** |
| Digit limit used to **guarantee every finite value** can round-trip binary → sufficiently accurate string → binary | **9** | **17** |
| Approximate guideline for significant precision in calculations | **6–7** | **15–16** |

**9 or 17 are not digits that are “all accurate relative to the original mathematical value.”** They are the number of significant decimal digits sufficient to **distinguish binary values** during text conversion with proper rounding.

Conversely, **6 and 15** are conservative thresholds for discussing the preservation of significant decimal digits across conversions; they do not claim that the 7th or 16th digit is always wrong. Specific values like `0.5` can be represented exactly, whereas numbers like `0.1` cannot.

In Java, `Float.toString` and `Double.toString` choose the short decimal representation needed under Java's conversion rules; when you need to save and restore values, use those APIs and `parseFloat`/`parseDouble` instead of truncating to a fixed 6 or 15 digits yourself.

```java
double original = Math.PI;
String saved = Double.toString(original);
double restored = Double.parseDouble(saved);

boolean sameBits =
        Double.doubleToRawLongBits(original)
        == Double.doubleToRawLongBits(restored);
// true
```

In real programs, if a `NaN` carries a special payload, many bit details are not preserved through text; the example above uses a normal finite value. `Double.toString` outputs `-0.0` distinctly, but do not extend this simple round-trip observation into a guarantee that all `NaN` payloads are preserved.

## 5. ULP: Spacing Between Representable Values

**ULP** (*unit in the last place*) can be understood practically as the size of one numeric grid step at the magnitude under consideration. For a normal number in the interval `[2^e, 2^(e+1))`, the spacing between numbers in that interval is approximately:

```text
ULP ≈ 2^(e - (p - 1))
p = 24 for float; p = 53 for double
```

As numbers grow larger, **the spacing between representable numbers also grows**. Therefore, we cannot say `double` is always accurate to “15 decimal places”: what matters is **significant digits**, and absolute resolution depends on the magnitude of the value.

Java provides `Math.ulp` and `Math.nextUp` for inspection:

```java
System.out.println(Math.ulp(1.0f)); // 1.1920929E-7
System.out.println(Math.ulp(1.0));  // 2.220446049250313E-16
System.out.println(Math.nextUp(1.0)); // 1.0000000000000002
```

At `1.0` itself, `Math.ulp(1.0)` is the gap from 1.0 to the closest larger `double`. Below 1.0, the step can be smaller due to the boundary between two exponent intervals.

### Where Do Consecutive Integers Start “Sticking Together”?

`float` has 24 significand bits, so every integer from `-2^24` to `2^24` is represented exactly; however, `2^24 + 1` cannot be represented as a `float`.

```java
int originalInt = 16_777_217; // 2^24 + 1
float roundedFloat = originalInt; // 16777216.0f
```

`double` has 53 significand bits, so every integer from `-2^53` to `2^53` is represented exactly; `2^53 + 1` cannot be represented as a `double`:

```java
long originalLong = 9_007_199_254_740_993L; // 2^53 + 1
double roundedDouble = originalLong; // 9.007199254740992E15
```

**Both are valid Java widening conversions**, requiring no cast and throwing no exception, yet they lose one unit of value. If your data represents IDs, large integer counts, counters, or values requiring exact comparison, do not convert `long` to `double` casually.

## 6. Having Many Decimal Digits Does Not Mean All of Them Are Trustworthy

Using a very long print format, or converting a `double` into the exact decimal representation of its stored bits, can produce dozens of digits after the decimal point. That **does not turn those digits into new accuracy** relative to the number the user intended to input.

```java
double x = 0.1;
System.out.println(Double.toString(x)); // 0.1
System.out.println(new java.math.BigDecimal(x));
// 0.1000000000000000055511151231257827021181583404541015625
```

`Double.toString(x)` displays a decimal representation suitable for parsing back to the same binary value; `new BigDecimal(x)` takes **the exact binary value currently held** and expresses it in decimal, exposing the discrepancy.

Conversely:

```java
java.math.BigDecimal decimal =
        new java.math.BigDecimal("0.1");
java.math.BigDecimal fromValueOf =
        java.math.BigDecimal.valueOf(0.1);
```

Both in the example above represent the decimal value `0.1` in decimal form; `BigDecimal.valueOf(double)` relies on the string produced by `Double.toString`, **not** exposing the full binary fraction like the `new BigDecimal(double)` constructor.

If data is entered as decimal and must retain that exact decimal value, constructing `BigDecimal` from a **string** or from an integer with a *scale* is clearer than detouring through `double`.

## 7. Accumulated Error and Loss of Significance (Cancellation)

Error does not occur only when creating literals: every floating-point addition, subtraction, multiplication, or division can round. Many consecutive operations can accumulate drift:

```java
double sum = 0.0;
for (int i = 0; i < 10; i++) {
    sum += 0.1;
}
System.out.println(sum); // 0.9999999999999999
```

The mathematical sum is 1, but each addition and assignment can round. **10 operations do not guarantee an error of exactly 10 times**: errors can cancel out or grow depending on the data and order of evaluation.

A notable phenomenon is **cancellation** (loss of significant digits when subtracting two nearly equal numbers):

```java
double large = 1e16;
double tinyAddition = (large + 1.0) - large;
System.out.println(tinyAddition); // 0.0, not 1.0
```

Around `1e16`, the grid spacing of `double` is larger than 1, so `large + 1.0` rounds to `large`. The subsequent subtraction cannot recover the lost part.

Furthermore, when subtracting two large, nearly equal numbers, existing errors in each operand can dominate the small result. This is why numerical problems require evaluating **numerical stability** in addition to choosing between `float` and `double`.

## 8. Comparing Two `double` Values: When to Use `==`?

`==` is an exact comparison under floating-point semantics and does not apply an automatic “approximately equal threshold”:

```java
System.out.println(0.1 + 0.2 == 0.3); // false
```

If two independent calculations must yield **the exact same bit value**, `==` can be appropriate. However, if the goal is “two numeric results are close enough,” you can use an error tolerance designed for the data domain.

A comparison helper for **two finite values**:

```java
static boolean approximatelyEqual(double a, double b,
                                  double absTol, double relTol) {
    double diff = Math.abs(a - b);
    double scale = Math.max(Math.abs(a), Math.abs(b));
    return diff <= Math.max(absTol, relTol * scale);
}
```

This method is an **illustrative snippet inside a class**, assuming `a`, `b` are finite and `absTol`/`relTol` are non-negative; real applications also need to handle `NaN`, infinity, and intermediate overflow during subtraction or threshold calculation. No single fixed tolerance works well for all applications.

For example, a relative tolerance is usually sensible for large numbers, while an absolute tolerance can be useful near 0. For monetary calculations, the right choice is usually not “`double` + epsilon,” but **`BigDecimal`** or integer smallest units with overflow checks.

### Special Values

- `Double.NaN == Double.NaN` evaluates to `false`; use `Double.isNaN` to check for NaN.
- `Double.POSITIVE_INFINITY`/`NEGATIVE_INFINITY` must be handled according to the data domain; calculations involving infinity do not carry the same meaning as finite measurements.
- `0.0 == -0.0` evaluates to `true`, though bit representations and some operations can distinguish the sign of zero.
- `Double.compare` provides ordering under Java's rules, differing from ordinary arithmetic comparison semantics on NaN and signed zero.

For map keys, sorting, serialization, or exact bit checks, choose the appropriate comparison rule rather than blindly replacing every `==` with an epsilon formula.

## 9. `float` vs. `double`: Choosing a Type Based on Real Precision Needs

`double` is usually the default choice for real-number computation in Java. The literal `0.1` has type `double`, and the literal `0.1f` has type `float`:

```java
double d = 0.1;
float f = 0.1f;
// float invalid = 0.1; // error: a double literal does not automatically narrow to float
```

`double` has higher significand precision, yet still **does not represent exact decimal arithmetic**.

For graphics, sensor data, machine learning, or large collections where precision requirements allow, `float` can be sensible for memory and bandwidth. For simulations/computations needing higher relative accuracy, `double` is typically suitable. For prices, interest, taxes, or financial calculations that must follow decimal rules exactly, use `BigDecimal` with an appropriate `RoundingMode` instead of relying on `double` precision.

**Do not use “number of printed digits” as the sole metric.** You need to determine absolute error, relative error, min/max values, computation conditions, and how consumers will use the result.

## 10. Complete Java 17+ Program and Verifiable Output

Save the following as **`BinaryPrecisionDemo.java`**:

```java
import java.math.BigDecimal;

public class BinaryPrecisionDemo {
    public static void main(String[] args) {
        System.out.println("floatBits=" + Float.SIZE);
        System.out.println("doubleBits=" + Double.SIZE);

        System.out.println("exactHalf=" + (0.5 + 0.25));
        System.out.println("decimalSum=" + (0.1 + 0.2));
        System.out.println("decimalEqual=" + (0.1 + 0.2 == 0.3));

        System.out.println("floatUlpOne=" + Math.ulp(1.0f));
        System.out.println("doubleUlpOne=" + Math.ulp(1.0));
        System.out.println("nextDouble=" + Math.nextUp(1.0));

        int bigInt = 16_777_217;
        float roundedFloat = bigInt;
        System.out.println("intViaFloat=" + (int) roundedFloat);

        long bigLong = 9_007_199_254_740_993L;
        double roundedDouble = bigLong;
        System.out.println("longViaDouble=" + (long) roundedDouble);
        System.out.println("longEqualsDouble=" + (bigLong == roundedDouble));

        double d = 0.1;
        System.out.println("shortDecimal=" + Double.toString(d));
        System.out.println("binaryAsDecimal=" + new BigDecimal(d));
        System.out.println("decimalFromString=" + new BigDecimal("0.1"));
        System.out.println("decimalValueOf=" + BigDecimal.valueOf(d));

        String encoded = Double.toString(Math.PI);
        double recovered = Double.parseDouble(encoded);
        System.out.println("roundTrip=" +
                (Double.doubleToRawLongBits(recovered) ==
                 Double.doubleToRawLongBits(Math.PI)));

        double tenTimes = 0.0;
        for (int i = 0; i < 10; i++) {
            tenTimes += 0.1;
        }
        System.out.println("tenTimes=" + tenTimes);
        System.out.println("lostUnit=" + ((1e16 + 1.0) - 1e16));

        System.out.println("nanSelfEqual=" + (Double.NaN == Double.NaN));
        System.out.println("signedZeroEqual=" + (0.0 == -0.0));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac BinaryPrecisionDemo.java
java BinaryPrecisionDemo
```

Output:

```text
floatBits=32
doubleBits=64
exactHalf=0.75
decimalSum=0.30000000000000004
decimalEqual=false
floatUlpOne=1.1920929E-7
doubleUlpOne=2.220446049250313E-16
nextDouble=1.0000000000000002
intViaFloat=16777216
longViaDouble=9007199254740992
longEqualsDouble=true
shortDecimal=0.1
binaryAsDecimal=0.1000000000000000055511151231257827021181583404541015625
decimalFromString=0.1
decimalValueOf=0.1
roundTrip=true
tenTimes=0.9999999999999999
lostUnit=0.0
nanSelfEqual=false
signedZeroEqual=true
```

A surprising detail is `longEqualsDouble=true`: in the comparison `long == double`, `long` is widened to `double` and rounded, so the comparison can return `true` even though the original `long` was not preserved during conversion. You should not compare large `long` values against `double` to verify ID equality.

## 11. Common Mistakes

| Misconception | Correct Understanding |
| --- | --- |
| “`double` has 15 digits after the decimal point.” | It has **53 significand bits**, equivalent to roughly 15–16 **significant decimal digits** for normal numbers; it is not fixed by digits after the decimal point. |
| “9 digits for `float` and 17 digits for `double` are all mathematically exact digits.” | 9/17 are bounds for **binary → sufficiently accurate string → binary round-trips**, not the accuracy of the original measurement. |
| “If Java prints `0.1`, it stored 0.1 exactly.” | `Double.toString` prints a short representation sufficient to recover the same binary value, rather than printing the full exact decimal value of the stored bits. |
| “`float` cannot hold large integers only because its max is ~3.4 × 10^38.” | `float` has a wide **magnitude** range, but 24-bit precision means many consecutive integers near 2^24 cannot be distinguished. |
| “Promoting `long` to `double` is always exact because both are 64 bits.” | `double` uses 53-bit precision, so large `long` values can be rounded. |
| “`==` always works well after floating-point additions.” | Values can differ due to rounding; choose the comparison method based on the problem's requirements. |
| “Adding 0.1 ten times definitely yields 1.0.” | Each addition can round, and evaluation order affects the error. |
| “Printing more digits increases storage accuracy.” | Formatting only changes the display string; it does not add back lost information bits. |
| “`BigDecimal.valueOf(0.1)` is identical to `new BigDecimal(0.1)`.” | `valueOf` uses the canonical string representation of `double`; the `double` constructor expresses the exact binary value stored. |
| “An epsilon of 1e-9 can be chosen for every comparison.” | Reasonable tolerance depends on scale, data domain, measurement error, and algorithm; a specific policy is required. |

### Practice Checklist

1. **Choose the type by precision, not just magnitude.** `float` has 24-bit and `double` has 53-bit significand; if exact decimal is required, consider `BigDecimal`.
2. **Distinguish precision from round-trip:** about 6–7/15–16 significant digits is an accuracy guideline; 9/17 digits suffice to store round-trip strings for all finite values of the respective types.
3. **Do not count digits after the decimal point:** absolute error and ULP spacing vary with magnitude.
4. **Check multi-step addition/subtraction/multiplication:** errors can accumulate or amplify due to loss of significance; evaluate algorithm stability.
5. **Do not default to `==` for approximate arithmetic results:** define the data domain, tolerances, and handling for NaN/infinity appropriately.
6. **When saving and restoring floating-point bits:** use `Float.toString`/`Double.toString` and the corresponding parsers; when exact mathematical decimal values are needed, do not detour through `double`.

**Remember:** `float` and `double` store a **finite binary** grid of values. The 6–9 or 15–17 digit rules only make sense when specifying the goal: **calculation accuracy** or **the string length needed to round-trip the stored value**. Understanding this distinction prevents confusing displayed digits with actual data reliability.