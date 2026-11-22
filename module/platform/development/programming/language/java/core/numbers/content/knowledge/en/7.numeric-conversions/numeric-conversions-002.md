# Widening Can Still Lose Precision When Converting to float or double in Java

In Java, **widening primitive conversion** is not synonymous with **preserving the mathematical value in all cases**. When converting an integer to `float` or `double`, the target type may have a wider value range yet **lack enough significand bits to represent every integer exactly** within that range.

Two important examples:

```java
int integer = 16_777_217;
float approximate = integer;  // Actual float value: 16_777_216.0f

long large = 9_007_199_254_740_993L;
double rounded = large;       // Actual double value: 9_007_199_254_740_992.0
```

These are valid code snippets inside a Java method. There is no compile error or `ArithmeticException`: the conversion is permitted, but the result **has been rounded**. If the numbers represent counts, identifiers, data versions, or monetary amounts in the smallest unit, losing even a single unit can break business logic.

This lesson belongs to the **Numeric Conversions** section of the **Java core – numbers** module, focusing on why it happens, when it occurs, comparison pitfalls, and how to preserve data when converting to floating-point types.

## 1. "Widening" and "exact" are two different properties

In Java, a primitive conversion is called *widening* if it belongs to the group of expansions permitted by the language, such as `int → long`, `int → float`, `int → double`, `long → float`, `long → double`, `float → double`. Most of these can happen automatically in assignments, method arguments, or arithmetic expressions.

However, the word "widening" describes **conversion rules and the supported value range**, not a guarantee of increasing the number of bits storing the **exact integer part**.

| Conversion | Preserves every source value exactly? | Explanation |
| --- | --- | --- |
| `byte → short/int/long` | Yes | The target integer represents the entire source range |
| `short → int/long` | Yes | Preserves every value |
| `char → int/long` | Yes | Every `char` value 0–65535 can be represented |
| `int → long` | Yes | 64 integer bits hold every `int` |
| `int → float` | **No** | `float` has only 24 bits of significand precision |
| `int → double` | **Yes** | `double` has 53 bits of significand precision, enough for every `int` |
| `long → float` | **No** | Many `long` values must be rounded when converted to `float` |
| `long → double` | **No** | 53 bits are not enough to represent every 64-bit integer |
| `float → double` | Yes, for finite values already stored in `float` | The binary value of `float` is represented exactly in `double`; **does not recover** previously lost information |

You must distinguish **maximum magnitude** from **resolution**. `float` can represent numbers with magnitudes far beyond `Long.MAX_VALUE`, but when numbers are large, the representable values are spaced far apart. A type with a larger range **does not necessarily** hold every integer smaller than that maximum threshold.

## 2. Mechanism: floating-point numbers store a significand and an exponent

`float` and `double` in Java use IEEE 754 binary floating-point representation:

- `float`: 32 bits total, **24 bits of significand precision** (including the implicit bit in normal numbers).
- `double`: 64 bits total, **53 bits of significand precision**.
- The remaining bits handle the sign and exponent; they expand the **magnitude range**, but do not give every integer in that range an exact representation.

One way to picture this: while there are enough significand bits, two consecutive integers like 100 and 101 can have two distinct representations. As values grow large, the gap between adjacent floating-point numbers increases to 2, 4, 8… units. Integers lying in between must be rounded to a neighboring value.

### The 2^24 threshold for float

```text
2^24 = 16_777_216

16_777_216 → float: exact
16_777_217 → float: 16_777_216
16_777_218 → float: exact
16_777_219 → float: 16_777_220 (rounded to nearest value)
```

Around `2^24`, consecutive `float` values are spaced by **2**. `16_777_217` lies halfway between `16_777_216` and `16_777_218`; the *round to nearest, ties to even* rule chooses `16_777_216` in this case.

**Every integer from `-2^24` to `2^24` is represented exactly by `float`**, but that **does not** mean every integer outside that range is inaccurate: for example, `16_777_218` is still represented exactly. This milestone is a threshold of **continuous guarantee**, not a threshold where "every larger value cannot be stored."

### The 2^53 threshold for double

```text
2^53 = 9_007_199_254_740_992

9_007_199_254_740_992 → double: exact
9_007_199_254_740_993 → double: 9_007_199_254_740_992
9_007_199_254_740_994 → double: exact
```

Similarly, every integer in `[-2^53, 2^53]` is represented exactly by `double`, but consecutive integers beyond this threshold no longer always have distinct representations. Because `long` holds integers larger than `2^53`, converting `long → double` can lose low-order digits.

`Number.MAX_SAFE_INTEGER` in JavaScript is `2^53 - 1`, which is related to binary64's ability to distinguish consecutive integers. That is especially relevant if a Java service outputs a `long` as a JSON number for JavaScript.

## 3. Why is int → double still exact, while int → float may not be?

Every Java `int` falls within the range:

```text
-2_147_483_648 ≤ int ≤ 2_147_483_647
```

A `double` has 53 significand bits, so it can represent every 32-bit integer. Therefore:

```java
int source = Integer.MAX_VALUE;
double widened = source;

boolean exact = (long) widened == source; // true
```

In this example, you can cast the result to `long` to inspect the integer value, though the property "every `int` lies within `double`'s precision" alone is enough to conclude the conversion is exact.

With `float`, although it has a very wide magnitude range, 24 significand bits are not enough to hold every `int`. For example:

```java
int source = 16_777_217;
float widened = source;

int recovered = (int) widened;   // 16_777_216
boolean equal = recovered == source; // false
```

**Key takeaway:** the total bit count of the target type does not directly indicate how many integer digits are preserved. `double` is 64 bits and `long` is also 64 bits, but `double` reserves bits for the exponent and sign, leaving only 53 bits of significand precision.

## 4. What does Java do when an integer cannot be represented exactly?

Converting `int` or `long` to `float`/`double` is a permitted conversion and is rounded to the nearest representable floating-point value according to Java's applicable rules. For exact ties between two neighboring numbers, the ties-to-even rule decides the result.

```java
int first = 16_777_216;
int second = 16_777_217;

float f1 = first;
float f2 = second;

// Two different integers produce the same float value:
boolean collision = f1 == f2; // true
```

This explains why an integer counter **should not be stored in a `float`** just because `float` can hold very large numbers. The target value may stop changing when adding 1 in large ranges:

```java
float count = 16_777_216f;
count = count + 1f;
// count is still 16_777_216f.
```

This is not because the addition was skipped, but because the mathematical result `16_777_217` cannot be represented exactly and gets rounded back to `16_777_216`.

These conversions do not automatically raise `ArithmeticException`, and there is no mandatory compiler warning. Therefore, you must analyze inputs, choose types carefully, and test boundary values rather than relying on compilation succeeding.

## 5. Comparison trap: int == float or long == double can still be true

A particularly subtle bug is comparing the original integer directly against the rounded floating-point value:

```java
int original = 16_777_217;
float converted = original;

System.out.println(original == converted);         // true
System.out.println(original == (int) converted);   // false
```

Why does the first comparison return `true`?

In the expression `original == converted`, Java applies **binary numeric promotion**: the `int` operand is converted to `float` to compare against `float`. During that conversion, `16_777_217` is also rounded to `16_777_216f`. Both operands are equal at comparison time, but **that does not prove `float` preserved the original integer**.

Similarly:

```java
long original = 9_007_199_254_740_993L;
double converted = original;

System.out.println(original == converted);        // true
System.out.println(original == (long) converted); // false
```

Do not use `original == (float) original` or `original == (double) original` as an exactness check. In mixed integer/floating-point comparisons, the integer operand itself can undergo lossy conversion before the comparison.

### Two distinct integers can become "equal" after conversion

```java
long a = 9_007_199_254_740_992L;
long b = 9_007_199_254_740_993L;

boolean integerDifferent = a != b; // true
boolean doubleSame = (double) a == (double) b; // true
```

If a system converts large IDs to `double` and uses them as keys for comparison, lookup, or deduplication, two different identifiers can collapse into one. The consequences can be more severe than errors in ordinary measurements.

## 6. Reverse-cast trap: round-trip checks require understanding the rules

A check that looks reasonable:

```java
double converted = (double) originalLong;
boolean unchanged = ((long) converted == originalLong);
```

For `originalLong = 9_007_199_254_740_993L`, this returns `false` and detects the loss of 1 unit. However, **this should not be treated as a valid check for every `long`**.

For example:

```java
long originalLong = Long.MAX_VALUE;
double converted = originalLong;

boolean appearsEqual = ((long) converted == originalLong); // true
```

Analysis:

- `Long.MAX_VALUE` is `9223372036854775807`.
- The nearest `double` value upon conversion has the mathematical value `9223372036854775808` (`2^63`), which is **greater than** `Long.MAX_VALUE`.
- When **narrowing** from `double` back to `long`, Java truncates any fractional part and handles out-of-range values under narrowing rules, where overly large positive values are clamped to `Long.MAX_VALUE`.
- Thus, casting back can yield `Long.MAX_VALUE` again even though the `double` was no longer equal to the original integer!

A check like `(long) d == original` can produce a **false positive** at the boundary. Casting from `double` to `long` is not itself a proof of exactness.

### Checking integer ↔ double values using an exact representation

When you need to know whether a specific `long` converts to `double` **without changing its mathematical value**, you can compare using an exact decimal type:

```java
import java.math.BigDecimal;

// Method placed inside a Java class:
static double toDoubleExact(long original) {
    double converted = (double) original;
    BigDecimal fromLong = BigDecimal.valueOf(original);
    BigDecimal exactDoubleValue = new BigDecimal(converted);

    if (fromLong.compareTo(exactDoubleValue) != 0) {
        throw new ArithmeticException("Precision lost converting long to double");
    }
    return converted;
}
```

Here, **`new BigDecimal(converted)` is used intentionally to capture the exact binary value of the `double`**, even when its decimal representation is long. This is completely different from constructing monetary amounts from `double`; for money, you should create `BigDecimal` from the **original decimal string** rather than relying on an already-rounded floating-point value.

`BigDecimal.valueOf(original)` preserves the `long` integer exactly. Comparing the two exact decimal values catches even the `Long.MAX_VALUE` case despite casting back to `long` appearing equal.

If the application requires supporting the entire `long` range without information loss, **do not use `double` to store those integers**. The check above is only appropriate where you intentionally want to accept or reject individual specific values.

## 7. float → double does not recover precision from the original input

This is an important distinction:

```java
float decimalLike = 0.1f;
double promoted = decimalLike;

System.out.println(promoted); // 0.10000000149011612
```

The `float → double` conversion itself **preserves the exact binary value already stored in the float**. However, the literal `0.1f` did not represent 1/10 exactly in binary to begin with; `double` simply represents the **already-rounded float value** more accurately, without turning it into the mathematical decimal 0.1.

Similarly, if an integer was previously stored through a `float` and only then converted to `double`:

```java
int original = 16_777_217;
float intermediate = original;
double later = intermediate;

// later holds 16_777_216.0; it no longer knows the original number was 16_777_217.
```

Once multiple distinct inputs have been rounded to the same `float` value, a subsequent widening step **has no information to recover them**.

## 8. ULP: the spacing between adjacent floating-point numbers

`Math.ulp(value)` (*unit in the last place*) tells you the magnitude of one unit at the least significant bit position of the significand around a floating-point value. It helps observe how **resolution** changes with magnitude.

```java
System.out.println(Math.ulp(16_777_216f));          // 2.0
System.out.println(Math.ulp(9_007_199_254_740_992d)); // 2.0
```

At these positions, the distance to the next representable floating-point number toward larger magnitudes is 2 units. As magnitude increases further, the ULP increases. That causes `float`/`double` to still hold large numbers while no longer distinguishing individual small units as before.

Note that ULP is information about resolution; it **does not by itself provide a business error tolerance**. In measurement problems, error tolerance depends on units and algorithmic requirements. In counting or identifier problems, losing even 1 unit may be unacceptable.

## 9. Standalone runnable Java 17+ program

Create the file **`WideningPrecisionDemo.java`**. The program tests the key pitfalls: `int → float`, `long → double`, mixed-type comparisons, ULP, `float → double`, reverse-casting at `Long.MAX_VALUE`, and a `long`-to-`double` conversion function with exactness checking.

```java
import java.math.BigDecimal;

public class WideningPrecisionDemo {
    static double toDoubleExact(long original) {
        double converted = (double) original;
        BigDecimal fromLong = BigDecimal.valueOf(original);
        BigDecimal exactDoubleValue = new BigDecimal(converted);

        if (fromLong.compareTo(exactDoubleValue) != 0) {
            throw new ArithmeticException("Precision lost");
        }
        return converted;
    }

    public static void main(String[] args) {
        int intSource = 16_777_217;
        float asFloat = intSource;
        System.out.println("int-original=" + intSource);
        System.out.println("float-as-int=" + (int) asFloat);
        System.out.println("int-float-round-trip=" +
                ((int) asFloat == intSource));
        System.out.println("int-equals-float=" + (intSource == asFloat));
        System.out.println("int-to-double-exact=" +
                ((long) (double) Integer.MAX_VALUE == Integer.MAX_VALUE));
        System.out.println("float-ulp-at-2pow24=" +
                Math.ulp(16_777_216f));

        long longSource = 9_007_199_254_740_993L;
        double asDouble = longSource;
        System.out.println("long-original=" + longSource);
        System.out.println("double-as-long=" + (long) asDouble);
        System.out.println("long-double-round-trip=" +
                ((long) asDouble == longSource));
        System.out.println("long-equals-double=" +
                (longSource == asDouble));
        System.out.println("double-ulp-at-2pow53=" +
                Math.ulp(9_007_199_254_740_992d));

        double promotedFloat = 0.1f;
        System.out.println("float-to-double=" + promotedFloat);

        double roundedMax = (double) Long.MAX_VALUE;
        System.out.println("long-max-cast-back-equal=" +
                ((long) roundedMax == Long.MAX_VALUE));
        System.out.println("long-max-double-exact-integer=" +
                new BigDecimal(roundedMax).toBigIntegerExact());

        System.out.println("exact-small-long=" + toDoubleExact(10L));
        try {
            toDoubleExact(longSource);
        } catch (ArithmeticException ex) {
            System.out.println("checked-widening=precision-lost");
        }
    }
}
```

Execution commands:

```bash
javac WideningPrecisionDemo.java
java WideningPrecisionDemo
```

Stdout output:

```text
int-original=16777217
float-as-int=16777216
int-float-round-trip=false
int-equals-float=true
int-to-double-exact=true
float-ulp-at-2pow24=2.0
long-original=9007199254740993
double-as-long=9007199254740992
long-double-round-trip=false
long-equals-double=true
double-ulp-at-2pow53=2.0
float-to-double=0.10000000149011612
long-max-cast-back-equal=true
long-max-double-exact-integer=9223372036854775808
exact-small-long=10.0
checked-widening=precision-lost
```

Point to note: the two lines `int-equals-float=true` and `long-equals-double=true` **do not prove the conversion is exact**. The integer value on the comparison side is also promoted to the floating-point type and rounded. The line `long-max-cast-back-equal=true` also does not prove exactness because narrowing casts from `double` to `long` use clamping at the boundary.

## 10. How to choose types when integers must be preserved

| Need | Suitable choice | Risk if using float/double |
| --- | --- | --- |
| Event counts, file sizes, total bytes | `int`/`long`, or `BigInteger` if needed | Loses odd/individual units in large ranges |
| Large numeric IDs, lookup keys, account numbers | Usually `String` if they are codes; `long`/`BigInteger` if arithmetic is needed | Two distinct IDs can collapse into one |
| Monetary amounts in integer cents | `long` with overflow checks; or a domain decimal solution | Losing 1 cent is unacceptable |
| Experimental measurements where error is acceptable | `double`, sometimes `float` per specification | Error is a property accounted for in the model |
| Money or exact decimal values | `BigDecimal` from original decimal data | `double` has binary representation error |
| Sending large `long` values to JavaScript | String in JSON or a protocol supporting exact integers | JavaScript Number (binary64) cannot distinguish all large integers |
| An API that requires receiving `double` from `long` | Check exactness or specify allowable error | Widening occurs silently with no exception |

Avoid assuming that a type with a **larger representable range** is always better for storing any integer data. Data semantics and preservation requirements should drive the design.

## 11. Conversions and calls that commonly cause confusion

### 11.1. Passing arguments to a method taking double

```java
static void record(double idOrMeasurement) {
    // ...
}

long id = 9_007_199_254_740_993L;
record(id); // Java automatically converts long to double, potentially losing precision.
```

Because no explicit cast is needed, bugs can creep in when refactoring method signatures or integrating libraries. If `id` is an identifier that must remain exact, a signature accepting `double` is a design issue, not just a formatting bug.

### 11.2. Mixed operands in expressions

```java
long count = 9_007_199_254_740_993L;
double average = count / 1.0; // count is promoted to double before division.
```

The output is `double`; conversion error can occur **before the division**. Do not assume an operation yielding a floating-point result preserves every single unit of a very large counter.

### 11.3. Computing in integers first, then converting to double

```java
long count = Long.MAX_VALUE;
double result = count + 1L;
```

In this snippet, `count + 1L` performs `long` addition **before converting to `double`**, which already overflowed to `Long.MIN_VALUE`. Those are **two separate risk classes**: overflow during integer arithmetic and precision loss when converting to floating-point. If the goal is a large floating-point number, convert at the right point for the calculation; if the goal is an exact integer, consider `BigInteger`.

### 11.4. Incrementing double in large ranges

```java
double count = 9_007_199_254_740_992d;
count = count + 1.0;
// count still equals 9_007_199_254_740_992d.
```

A `double` variable can stop changing when adding an amount smaller than its current resolution. This is why `float`/`double` are unsuitable as unbounded-range integer counters.

### 11.5. BigDecimal does not automatically restore lost values

```java
long id = 9_007_199_254_740_993L;
double rounded = id;
BigDecimal fromRounded = BigDecimal.valueOf(rounded);
```

`fromRounded` holds the value corresponding to the string representation of the already-rounded `double`; it cannot recover the original integer `id`. If you need an exact decimal from an integer, create **`BigDecimal.valueOf(id)` before converting through `double`**.

## 12. Verification and testing strategy

In practice, not every `long → double` conversion is wrong: many specific values are represented exactly. What matters is knowing the **system's contract**.

- If **every input must be exact**, pick a type that preserves the full range, such as `long` or `BigInteger`, and avoid converting through `float`/`double`.
- If inputs are constrained to a safe range, document and check the boundary limits. For instance, `|n| ≤ 2^24` guarantees exact integer-to-`float` conversion; `|n| ≤ 2^53` guarantees exact integer-to-`double` conversion. For `Long.MIN_VALUE`, avoid computing `Math.abs(n)` to check the range because `abs` has its own edge case.
- If only specific values are allowed, you can perform the conversion and compare against an **exact mathematical representation** as in the `toDoubleExact` example.
- If approximation is permitted, define the **acceptable error tolerance** and an appropriate comparison method; an absolute threshold used for small numbers does not necessarily make sense for very large numbers.

Test cases should include:

| Input | Conversion | What to verify |
| --- | --- | --- |
| `16_777_216` | `int → float` | Exact at `2^24` |
| `16_777_217` | `int → float` | Rounded down to `16_777_216` |
| `16_777_218` | `int → float` | Still exact despite exceeding `2^24` |
| `Integer.MAX_VALUE` | `int → double` | Exact |
| `9_007_199_254_740_992L` | `long → double` | Exact at `2^53` |
| `9_007_199_254_740_993L` | `long → double` | Loses 1 unit |
| `Long.MAX_VALUE` | `long → double → long` | Can appear equal due to saturating cast even though the double changed |
| `0.1f` | `float → double` | Preserves the approximated float value, does not become exact 0.1 |
| Two adjacent IDs around `2^53` | Compare after converting to `double` | Detect potential collision of two IDs |

A test suite that uses only small numbers easily misses bugs because conversions remain exact in that range. You should deliberately test **on both sides of the 2^24 and 2^53 thresholds** along with the boundary values of `int`/`long`.

## 13. Self-study questions

1. Why does `int → double` preserve every value exactly, while `long → double` does not? Explain in terms of significand bits rather than only total bit count.
2. Predict `(float) 16_777_217` and `(float) 16_777_218`. Why must one be rounded while the other is not?
3. Given `long a = 9_007_199_254_740_992L` and `long b = a + 1`, why is `a != b` yet `(double) a == (double) b`?
4. Predict `int i = 16_777_217; float f = i; i == f`. Why does `true` not prove that `int → float` preserved the value?
5. Explain the example where `Long.MAX_VALUE` is converted to `double` and cast back to `long`: why can the comparison be `true` while information was still lost?
6. Write a function that takes a `long` and only returns a `double` if the mathematical value does not change; test `10`, `2^53`, `2^53 + 1`, and `Long.MAX_VALUE`.
7. A DTO has an ID field of type `long`, while a JavaScript client receives it as a `Number`. Choose an appropriate transport format to preserve all ID values, along with a JSON example.
8. Why does `double d = 0.1f;` represent the stored float value accurately yet not mathematical 0.1? Can converting to `BigDecimal` afterward recover the original decimal intent?
9. A library takes `double` as input for statistics, while the data source consists of `long` counts. Would you accept the error, split the computation, or change the API? State the assumptions and required tests.

## 14. Key takeaways

- **Widening does not guarantee exact value preservation:** `int → float` and `long → float/double` can round silently.
- **`float` has 24 bits of precision and `double` has 53 bits**, so all integers up to `2^24` or `2^53` in magnitude respectively are preserved exactly, but beyond those thresholds not every integer can be represented.
- **`int → double` preserves every `int` exactly**, whereas `float → double` preserves the **existing float value** exactly and does not recover already-rounded data.
- **Mixed-type comparisons can deceive:** `int == float` or `long == double` can evaluate to true even when precision has been lost.
- **Casting back from double to long is not a general exactness check**, especially at `Long.MAX_VALUE` due to clamping rules on narrowing.
- For counts, identifiers, integer money amounts, and data requiring exactness, **keep integer types or an appropriate exact decimal type**; convert to floating-point only when the problem genuinely permits it.

Separate three questions when choosing types: *does the value fit in the representable range*, *is the value represented exactly*, and *do the conversion/comparison rules preserve business invariants*. A valid widening conversion only answers the first question.
