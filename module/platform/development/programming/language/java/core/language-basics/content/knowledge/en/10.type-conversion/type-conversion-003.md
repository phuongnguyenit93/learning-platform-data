# Widening Integers to Floating-Point Can Still Lose Precision

> **Java core — language-basics / Type Conversion**  
> **Environment:** JDK 17+; standard library only.  
> **Objective:** Understand why `int → float` and `long → double` are valid widening conversions that can round and lose data. Know the 24/53-bit precision thresholds, the risks of mixed comparisons, and how to handle integer values that must be preserved strictly.

## 1. Type widening does not guarantee preserving the original value

Java allows converting integers to floating-point numbers without a cast:

~~~java
int count = 123;
float f = count;   // Valid.
double d = count;  // Valid.

long id = 9_007_199_254_740_993L;
double approximateId = id; // Valid, but may lose precision.
~~~

`int` and `long` represent every integer accurately within their signed ranges. `float` and `double` represent IEEE 754 binary floating-point numbers. They have a very wide magnitude range, yet the significand only has a finite number of precision bits:

- **`float`:** 24 bits of significand precision, including the leading bit of normalized numbers.
- **`double`:** 53 bits of significand precision.
- **`int`:** 32 signed bits; **`long`:** 64 signed bits.

When an integer cannot be represented accurately by the target floating-point type, Java rounds to a representable floating-point value; in exact tie cases halfway between two values, the conversion chooses the value whose last significand bit is even (*round to nearest, ties to even*).

**Widening conversion** means a conversion permitted by the language without a cast. It does **not** mean all digits of the integer are always preserved.

## 2. Which conversions are always exact?

| Conversion | Automatic widening? | Exact for **every** source value? |
| --- | --- | --- |
| `byte` → `float`/`double` | Yes | Yes |
| `short` → `float`/`double` | Yes | Yes |
| `char` → `float`/`double` | Yes | Yes (code unit values 0–65535) |
| `int` → `double` | Yes | **Yes** |
| `int` → `float` | Yes | **No** |
| `long` → `double` | Yes | **No** |
| `long` → `float` | Yes | **No** |

Important limits:

- `float` represents **every** integer from `-2^24` to `2^24` (±16,777,216).
- `double` represents **every** integer from `-2^53` to `2^53` (±9,007,199,254,740,992).
- Above these thresholds, **some** integers are still represented accurately (for example, an even number just above `2^24` may fit in `float`), but **not all consecutive integers**.

Therefore, every `int` value converts to `double` accurately, whereas converting `int` to `float` or `long` to `double` risks rounding.

## 3. The `2^24 + 1` boundary when converting `int` to `float`

~~~java
int first = 16_777_216;       // 2^24
int second = 16_777_217;      // 2^24 + 1
float a = first;
float b = second;
~~~

`a` equals 16,777,216 exactly. At this magnitude, the spacing between consecutive `float` values is **2**, so 16,777,217 lies halfway between 16,777,216 and 16,777,218. The ties-to-even rule rounds `b` to **16,777,216**.

Consequence:

~~~java
System.out.println(first == second); // false
System.out.println(a == b);          // true
~~~

`Math.ulp(a)` gives the spacing between `a` and the next `float` value at this magnitude: **2.0f**. If you need to store any `int` value accurately, keep `int` or convert to `double`, instead of converting to `float`.

## 4. The `2^53 + 1` boundary when converting `long` to `double`

~~~java
long first = 9_007_199_254_740_992L; // 2^53
long second = first + 1;              // 2^53 + 1
double a = first;
double b = second;
~~~

`a` and `b` become the **exact same `double` value**, 9,007,199,254,740,992, even though the two source integers differ. Notice the mixed comparison:

~~~java
System.out.println(second == b);       // true - easy to misread!
System.out.println(second == (long) b); // false
~~~

In `second == b`, Java performs **binary numeric promotion**: converting the `long second` to `double` before comparing. When both sides round to the same value, `==` returning true **does not prove data was preserved accurately**.

Casting `b` back to `long` in this example yields 9,007,199,254,740,992 and exposes the discrepancy of 1. However, casting floating-point to integer also has truncation and range-clamping rules; it is **not a general method** for checking whether a conversion was exact.

## 5. Runnable Java 17+ example

Create the file **IntegerFloatPrecisionDemo.java**:

~~~java
import java.math.BigDecimal;

public final class IntegerFloatPrecisionDemo {
    public static void main(String[] args) {
        int baseInt = 16_777_216;
        int nextInt = baseInt + 1;

        float fa = baseInt;
        float fb = nextInt;
        double preciseInt = nextInt;

        System.out.println("intNext=" + nextInt);
        System.out.println("floatAsInt=" + (int) fb);
        System.out.println("doubleIntAsInt=" + (int) preciseInt);
        System.out.println("floatEqual=" + (fa == fb));
        System.out.println("floatUlp=" + (int) Math.ulp(fa));

        long baseLong = 9_007_199_254_740_992L;
        long nextLong = baseLong + 1;
        double da = baseLong;
        double db = nextLong;

        System.out.println("longNext=" + nextLong);
        System.out.println("doubleAsLong=" + (long) db);
        System.out.println("doubleEqual=" + (da == db));
        System.out.println("mixedEqual=" + (nextLong == db));
        System.out.println("roundTripEqual=" + (nextLong == (long) db));
        System.out.println("doubleUlp=" + (int) Math.ulp(da));

        System.out.println("allIntToDoubleExact="
                + ((long) (double) Integer.MAX_VALUE
                        == Integer.MAX_VALUE));
        System.out.println("exactDecimal="
                + BigDecimal.valueOf(nextLong).toPlainString());
    }
}
~~~

Open a terminal in the directory containing the file (Bash, PowerShell, or Command Prompt) and run:

~~~bash
javac -encoding UTF-8 IntegerFloatPrecisionDemo.java
java IntegerFloatPrecisionDemo
~~~

**Exact expected output:**

~~~text
intNext=16777217
floatAsInt=16777216
doubleIntAsInt=16777217
floatEqual=true
floatUlp=2
longNext=9007199254740993
doubleAsLong=9007199254740992
doubleEqual=true
mixedEqual=true
roundTripEqual=false
doubleUlp=2
allIntToDoubleExact=true
exactDecimal=9007199254740993
~~~

The lines `floatAsInt` and `doubleAsLong` show the **value after rounding**, rather than the new type saving extra digits on its own. The two results `floatUlp=2` and `doubleUlp=2` demonstrate the step size between floating-point values at the examined thresholds (cast to `int` for readability). `BigDecimal.valueOf(nextLong)` takes the value **directly from the original integer**, preserving 9,007,199,254,740,993.

## 6. How to choose types when precision is required

| Need | Recommendation |
| --- | --- |
| IDs, quantities, integer timestamps, money stored in whole minor units | Use `int`/`long` if the value range fits |
| Converting the entire `int` range to floating-point without further calculation | `double` preserves every `int` value accurately |
| Large `long` values that **must not be off by even one unit** | Avoid converting to `double` for storage or comparison |
| Integers needing to exceed the `long` range | Use `BigInteger` |
| Decimals requiring accuracy per business rules | Use `BigDecimal` from `String` or original integer, with explicit scale/rounding |
| Measurements or graphics accepting approximations | `float`/`double` if error margin is acceptable |

**There is no way to “recover” lost bits** merely using `Math.round`, casting back, or creating a `BigDecimal` from an already-rounded `double`. If exact integers are required, keep the original integer type throughout the data flow and comparisons.

`int → double` is strictly exact **at the conversion step**, yet subsequent `double` operations can still introduce rounding error, `NaN`, or infinity. Precision of an assignment does not guarantee precision of the entire algorithm.

## 7. Check exercises

**Exercise 1.** Why does `(float) 16_777_216 == (float) 16_777_217` evaluate to true, even though the two integer literals are different?

**Exercise 2.** State why `int → double` is exact for every `int`, whereas `long → double` is not. Explain the role of the 53 significand bits.

**Exercise 3.** Given `long id = 9_007_199_254_740_993L; double d = id;`. Predict `id == d` and `id == (long) d`; point out the numeric promotion step.

**Exercise 4.** Change `BigDecimal.valueOf(id)` to `BigDecimal.valueOf((double) id)`. Compare the resulting decimal strings and explain why the lost portion cannot be restored.

**Exercise 5.** Design an application that stores exact 64-bit IDs and then outputs them as text. Propose a way to convert `long` directly to `String` without going through `double`.

### Takeaways

**Converting integers to floating-point is valid widening, but not always lossless.** `float` only has 24 bits of precision, `double` has 53 bits. Thus `int → float` and `long → double` can round; conversely, **every `int → double` is exact**. If you need to store every single unit of a large integer accurately, do not pass the value through an approximate floating-point type.