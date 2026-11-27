# float, double, and Binary Representation Rounding in Java 17

**Topic:** Java 17 → Floating-Point Numbers  
**Focus:** The two primitive floating-point types float and double, how they store values according to the IEEE 754 standard, why many decimal fractions are only represented approximately, and how rounding during calculation differs from rounding for display.

In Java 17, **float** and **double** are the two floating-point primitive types (*floating-point primitive types*). They store numbers in binary form with finite precision. Therefore, a seemingly simple decimal number like 0.1 may not have an exact binary representation. When a program performs calculations, the value is rounded to the nearest representable floating-point number according to IEEE 754 rules.

This is a characteristic of number representation, not a Java-specific bug. Understanding it helps you choose the right data type, write safe comparisons, explain rounding results, and avoid using float/double for calculations requiring absolute decimal accuracy such as monetary amounts.

## 1. What Are float and double?

Java provides two primitive floating-point types:

| Type | Size | IEEE 754 Format | Significand Precision | Approximate Decimal Precision |
| --- | ---: | --- | ---: | ---: |
| float | 32 bits | binary32 | 24 bits (23 fraction bits + implicit leading bit for normal numbers) | about 6–7 significant digits |
| double | 64 bits | binary64 | 53 bits (52 fraction bits + implicit leading bit for normal numbers) | about 15–17 significant digits |

double has a wider range and higher precision than float, so it is the default choice for most general floating-point calculations in Java.

Declaration examples:

~~~java
float temperature = 36.5f;
double distance = 12345.6789;
~~~

The f or F suffix specifies that the literal is of type float. If the suffix is omitted, a floating-point literal such as 36.5 defaults to type double.

~~~java
float a = 36.5f;  // Valid: literal is of type float.
double b = 36.5;  // Valid: literal is of type double.

// float c = 36.5; // Error: double does not automatically narrow to float.
float c = (float) 36.5; // Explicit cast, may lose precision.
~~~

When a float value is widened to double, the binary value held by float is represented exactly in double; this conversion does not recover any decimal precision lost earlier.

## 2. Floating-Point Numbers Are Stored in Binary

float and double use a representation consisting of three components:

1. **Sign bit:** indicates whether the number is positive or negative.
2. **Exponent:** adjusts the scale (magnitude) of the number.
3. **Significand/fraction:** contains the bits determining the precision of the value.

For a normal number (*normal number*), you can visualize the value in the form:

\[
(-1)^{sign} \times 1.fraction \times 2^{exponent-bias}
\]

This is a conceptual model; IEEE 754 also has subnormal numbers (*subnormal*), zero, infinity, and NaN with their own rules.

### 2.1. Bit Structure

| Format | Sign Bit | Exponent Bits | Fraction Bits | Significand Precision |
| --- | ---: | ---: | ---: | ---: |
| binary32 (float) | 1 | 8 | 23 | 24 bits for normal numbers |
| binary64 (double) | 1 | 11 | 52 | 53 bits for normal numbers |

The leading 1 bit of the significand in a normal number is implicit, so it does not need to be stored directly. This organization allows representing a very wide range of values with a finite number of bits, but it also means only a finite set of real values can be stored exactly.

### 2.2. Why Is 0.5 Exact While 0.1 Is Not?

A fraction has a finite binary representation if, after reduction, its denominator is a power of 2.

Examples:

| Decimal | Fraction | Binary Form | Can Be Represented Exactly and Finitely? |
| --- | --- | --- | --- |
| 0.5 | 1/2 | 0.1₂ | Yes |
| 0.25 | 1/4 | 0.01₂ | Yes |
| 0.125 | 1/8 | 0.001₂ | Yes |
| 0.75 | 3/4 | 0.11₂ | Yes |
| 0.1 | 1/10 | 0.0001100110011...₂ | No |
| 0.2 | 1/5 | 0.001100110011...₂ | No |

For example, 1/10 has a denominator of 10 = 2 × 5. After reducing, the factor of 5 remains, so the binary representation repeats infinitely. float or double can only retain a finite number of bits; the rest must be rounded.

This does not mean 0.1 is drastically wrong. The stored value is normally the binary number closest to 0.1; the error is tiny, yet observable in exact comparisons or across many consecutive operations.

## 3. Familiar Example: 0.1 + 0.2 Does Not Equal 0.3

Consider the program:

~~~java
public class FloatingPointIntro {
    public static void main(String[] args) {
        double a = 0.1;
        double b = 0.2;
        double sum = a + b;

        System.out.println(sum);
        System.out.println(sum == 0.3);

        System.out.println(Double.toHexString(a));
        System.out.println(Double.toHexString(b));
        System.out.println(Double.toHexString(sum));
        System.out.println(Double.toHexString(0.3));
    }
}
~~~

Compile and run with JDK 17:

~~~shell
javac --release 17 FloatingPointIntro.java
java FloatingPointIntro
~~~

Output:

~~~text
0.30000000000000004
false
0x1.999999999999ap-4
0x1.999999999999ap-3
0x1.3333333333334p-2
0x1.3333333333333p-2
~~~

Double.toHexString displays the hexadecimal representation of the floating-point value, making the underlying binary value clear. The result of a + b is the nearest representable number to the mathematical sum of the two stored values; the literal 0.3 is rounded separately. The two results differ by one unit in the last bit of the significand, so == returns false.

**Important distinction:** System.out.println(0.1) usually prints 0.1 because Java uses the shortest string representation that converts back to the exact same double value. That does not prove the stored bits represent the exact fraction 1/10.

## 4. Where Does Rounding Occur?

With finite-precision floating-point types, rounding can occur at several points:

- When a decimal literal is converted to a float or double value.
- When converting from double to float.
- After a floating-point operation such as addition, subtraction, multiplication, or division, the result must be represented back in the target format.
- When converting a floating-point value to an integer type or a decimal form with a limited number of digits.
- When formatting a value into a string for display or file output.

These operations are not the same thing. In particular, **rounding the value stored in binary32/binary64** is different from **rounding decimal digits when presenting output**.

### 4.1. Rounding When Storing Literals

~~~java
float f = 0.1f;
double d = 0.1;

System.out.println(f);
System.out.println(Double.toString((double) f));
System.out.println(d);
System.out.println(Float.toHexString(f));
System.out.println(Double.toHexString(d));
~~~

0.1f is rounded into the binary32 format. When widening that value to double, Java preserves the exact binary32 value stored, so Double.toString((double) f) may print 0.10000000149011612. Meanwhile, 0.1 is a double literal rounded independently into binary64.

### 4.2. Rounding When Converting double to float

~~~java
double original = 1.23456789012345;
float narrowed = (float) original;
double widenedAgain = narrowed;

System.out.println(original);
System.out.println(narrowed);
System.out.println(widenedAgain);
~~~

narrowed only retains binary32 precision. Converting float back to double cannot recover the lost bits; it only represents the existing float value exactly in a wider format.

### 4.3. Rounding After Operations

Each floating-point operation produces a result in its format, and that result must be rounded to a representable value. Therefore, error can appear at every step, not just when printing to the screen.

Example:

~~~java
double x = 0.1 + 0.2;
double y = x + 0.3;
double z = 0.1 + (0.2 + 0.3);

System.out.println(x);
System.out.println(y);
System.out.println(z);
~~~

Because operands and intermediate results are rounded, floating-point addition is not always associative like mathematical real addition:

\[
(a+b)+c \ne a+(b+c)
\]

in certain cases. If a program is sensitive to accumulated error, choose an appropriate algorithm and numeric type rather than assuming all evaluation orders yield the same result.

## 5. IEEE 754 Default Rounding Rule

Java's basic floating-point operations follow IEEE 754 rules. For normal operations, the default rounding mode is **round to nearest, ties to even**:

- Choose the representable value closest to the exact result.
- If the exact result lies halfway between two representable values (*tie*), choose the value whose lowest significand bit is even.

This rule is also known as *round half to even* or *banker's rounding* in decimal rounding contexts, but note that here it applies to the **binary value grid** of the floating-point format.

Do not confuse this rule with:

- Math.round, which has its own rules for rounding to an integer.
- RoundingMode.HALF_UP and HALF_EVEN of BigDecimal, used when rounding decimal values by scale or precision.
- Formatting strings with a fixed number of decimal places.

A double value may already have been rounded in binary64 before you ask to display two decimal places. Display rounding cannot recover original decimal digits that the binary type could not store.

## 6. float vs. double: How to Choose?

| Criterion | float | double |
| --- | --- | --- |
| Memory per value | 4 bytes | 8 bytes |
| Precision | Lower | Higher |
| Value range | Narrower | Wider |
| Default literal | Must add f/F | Default for decimal literals |
| Use in general computation | When justified by memory, bandwidth, or API requirements | Common default choice |
| Binary error for decimal fractions | Yes | Yes, though with higher precision |

Example of type choice:

~~~java
float[] sensorSamples = new float[1_000_000];
double average = 0.0;
~~~

float can save memory when data volume is large, such as certain sensor arrays, images, graphics, or numerical models. However, you must evaluate the required precision and the APIs in use. Without a specific reason, double is generally the simpler and safer choice for accuracy.

**Do not choose float just because input numbers have few digits after the decimal point.** The number of digits written in source code does not determine whether a number has an exact binary representation.

## 7. Do Not Use float/double to Store Money Requiring Decimal Exactness

Suppose you need to calculate the total of three items, each priced at 0.10:

~~~java
double price = 0.10;
double total = price + price + price;

System.out.println(total);
~~~

The program may display a result close to 0.3, but you should not rely on double to guarantee all monetary calculations are exact to each decimal place. Small errors can accumulate over many operations, affecting invoice totals, taxes, discounts, and reconciliation.

### 7.1. Use BigDecimal with Decimal Strings

Java provides java.math.BigDecimal to represent decimal numbers with arbitrary precision. When input values are decimal data, construct BigDecimal from a **string**:

~~~java
import java.math.BigDecimal;

public class MoneyExample {
    public static void main(String[] args) {
        BigDecimal price = new BigDecimal("0.10");
        BigDecimal quantity = new BigDecimal("3");
        BigDecimal total = price.multiply(quantity);

        System.out.println(total); // 0.30
    }
}
~~~

BigDecimal stores decimal values independently of whether the fraction has a finite binary representation. The string constructor with "0.10" understands the exact decimal value and preserves the scale of two digits after the decimal point.

### 7.2. Why Does new BigDecimal(0.1) Often Surprise Developers?

The following three ways of creating it are not identical:

~~~java
import java.math.BigDecimal;

BigDecimal fromString = new BigDecimal("0.1");
BigDecimal fromValueOf = BigDecimal.valueOf(0.1);
BigDecimal fromDouble = new BigDecimal(0.1);

System.out.println(fromString);
System.out.println(fromValueOf);
System.out.println(fromDouble);
~~~

Output:

~~~text
0.1
0.1
0.1000000000000000055511151231257827021181583404541015625
~~~

- new BigDecimal("0.1"): creates the exact decimal number written in the string.
- BigDecimal.valueOf(0.1): goes through the canonical string representation of double, producing the short decimal 0.1 in this example.
- new BigDecimal(0.1): represents the exact binary64 value of the literal 0.1, thus revealing the long binary discrepancy.

For monetary data or decimal inputs from users, files, APIs, or databases, prefer reading decimal strings and creating BigDecimal from strings. If the data is already a double, valueOf is usually more useful than the BigDecimal(double) constructor, though it cannot recover previously lost decimal information.

## 8. Rounding Decimal Numbers with BigDecimal and RoundingMode

Rounding to two decimal places requires a clearly defined policy. BigDecimal.setScale takes the desired number of decimal places and a RoundingMode.

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class DecimalRoundingDemo {
    public static void main(String[] args) {
        BigDecimal value = new BigDecimal("1.235");

        System.out.println(
            value.setScale(2, RoundingMode.HALF_UP)
        );
        System.out.println(
            value.setScale(2, RoundingMode.HALF_EVEN)
        );
    }
}
~~~

Output:

~~~text
1.24
1.24
~~~

In this example both modes produce 1.24. To see the difference in an exact tie case:

~~~java
BigDecimal value = new BigDecimal("1.245");

System.out.println(value.setScale(2, RoundingMode.HALF_UP));   // 1.25
System.out.println(value.setScale(2, RoundingMode.HALF_EVEN)); // 1.24
~~~

HALF_UP chooses the direction away from zero on a tie; HALF_EVEN chooses the side with an even last digit. The appropriate rule must be chosen according to business contracts, accounting rules, or applicable standards.

### 8.1. Common RoundingMode Options

| Mode | General Meaning |
| --- | --- |
| UP | Round away from 0 if any remainder must be discarded. |
| DOWN | Discard remainder toward 0. |
| CEILING | Round toward positive infinity. |
| FLOOR | Round toward negative infinity. |
| HALF_UP | Nearest neighbor; on a tie, round away from 0. |
| HALF_DOWN | Nearest neighbor; on a tie, round toward 0. |
| HALF_EVEN | Nearest neighbor; on a tie, choose the even last digit. |
| UNNECESSARY | Require no rounding; throw ArithmeticException if rounding is needed. |

setScale(2, ...) limits to **two digits after the decimal point**. This differs from MathContext, which limits the total number of significant digits.

## 9. Math.round, Casting, and Display Formatting Are Not the Same

Many bugs occur when using one operation for the purpose of another.

### 9.1. Math.round Rounds to an Integer

~~~java
System.out.println(Math.round(2.3));   // 2
System.out.println(Math.round(2.5));   // 3
System.out.println(Math.round(-2.5));  // -2
System.out.println(Math.round(-2.6));  // -3
~~~

Math.round(double) returns long; Math.round(float) returns int. The rule is equivalent to floor(x + 0.5) for finite values within representable range. Thus, the tie case for negative numbers is not the same as RoundingMode.HALF_UP: Math.round(-2.5) is -2, rounding toward positive infinity.

Math.round is not a general way to round money to two decimal places.

### 9.2. Casting to Integer Truncates Toward Zero

~~~java
System.out.println((int) 3.9);   // 3
System.out.println((int) -3.9);  // -3
~~~

This is a narrowing conversion to integer, not rounding to the nearest integer. It discards the fractional part toward 0 (exceptions for NaN/infinity and overflow are specified separately).

### 9.3. Formatting Only Rounds Presentation

If the goal is displaying a number with two decimal places, you can use DecimalFormat and specify a rounding mode:

~~~java
import java.text.DecimalFormat;
import java.math.RoundingMode;

DecimalFormat formatter = new DecimalFormat("0.00");
formatter.setRoundingMode(RoundingMode.HALF_UP);

System.out.println(formatter.format(12.3)); // 12.30
~~~

DecimalFormat produces a string for display. It **does not change the original double variable** into a value with two decimal places, nor can it recover original decimal digits if the binary value was already approximate. For data requiring exact computation, work with BigDecimal, apply scale and rounding policy, and then format the result.

## 10. Comparing float/double: Avoid Using == for Approximate Calculation Results

For integers, equality comparison == generally behaves as intended. For floating-point numbers produced by approximate calculations, two mathematically expected equal values may differ in the last bit.

Example:

~~~java
double result = 0.1 + 0.2;

if (result == 0.3) {
    System.out.println("Equal");
} else {
    System.out.println("Different in representation");
}
~~~

If the problem tolerates error, you can compare within a threshold:

~~~java
static boolean nearlyEqual(double a, double b, double tolerance) {
    return Math.abs(a - b) <= tolerance;
}
~~~

Example:

~~~java
double result = 0.1 + 0.2;
System.out.println(nearlyEqual(result, 0.3, 1e-12)); // true
~~~

tolerance must come from the required accuracy and scale of the data. A single fixed epsilon is not suitable for every value domain. For problems requiring exact decimal precision, use BigDecimal or integers in the smallest unit instead of approximate comparisons.

Additionally, NaN and infinity require separate handling:

~~~java
double value = Double.NaN;

System.out.println(value == value);         // false
System.out.println(Double.isNaN(value));    // true
System.out.println(Double.isFinite(value)); // false
~~~

NaN does not equal itself under ==; use Double.isNaN to check. Double.isFinite helps determine that a value is neither NaN nor infinite.

## 11. Negative Zero, Subnormal Numbers, and Representation Limits

IEEE 754 has two representations of zero: +0.0 and -0.0. In Java:

~~~java
double positiveZero = 0.0;
double negativeZero = -0.0;

System.out.println(positiveZero == negativeZero); // true
System.out.println(1.0 / positiveZero);           // Infinity
System.out.println(1.0 / negativeZero);          // -Infinity
~~~

Both zeros compare equal using ==, but the sign can affect the results of certain operations such as division. When you need to distinguish the sign of zero, you can use Double.doubleToRawLongBits or Double.compare.

At very small magnitudes, IEEE 754 supports **subnormal values** to gradually represent values approaching 0 with reduced precision. At very large magnitudes, results can overflow to infinity:

~~~java
System.out.println(Double.MAX_VALUE);
System.out.println(Double.MIN_VALUE);
System.out.println(1e308 * 1e308); // Infinity
~~~

Note that Double.MIN_VALUE is the smallest positive non-zero representable value, not the most negative value. The most negative finite value is -Double.MAX_VALUE.

For float, the corresponding constants are Float.MAX_VALUE, Float.MIN_VALUE, and the inspection methods Float.isFinite and Float.isNaN.

## 12. Java 17 and Floating-Point Operation Consistency

Starting in Java 17, **all floating-point operations have strict IEEE 754 semantics** thanks to JEP 306 (*Restore Always-Strict Floating-Point Semantics*). Results for float and double no longer depend on whether the JVM uses an intermediate extended-exponent mode as permitted under older rules.

This means:

- Basic operations adhere strictly to the semantics of float or double.
- Results do not change merely because the JVM runs on a different hardware architecture.
- strictfp is no longer required to enforce strict semantics in Java 17. The modifier may still appear in legacy code, but it no longer alters computation semantics.

Example:

~~~java
public strictfp class StrictFloatingPoint {
    public static double calculate(double a, double b) {
        return a + b;
    }
}
~~~

In Java 17, the strictfp keyword here is semantically redundant. When writing new code, there is no need to add strictfp to every numeric class or method.

**Strict semantics do not mean floating-point numbers become absolutely exact.** 0.1 + 0.2 can still be 0.30000000000000004, because that is the consistent result of operating on the stored binary values.

## 13. Comprehensive Program: Observing Multiple Types of Rounding

Create the file **FloatDoubleRoundingDemo.java**:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class FloatDoubleRoundingDemo {
    public static void main(String[] args) {
        double a = 0.1;
        double b = 0.2;
        double sum = a + b;

        System.out.println("0.1 + 0.2 = " + sum);
        System.out.println("sum == 0.3: " + (sum == 0.3));
        System.out.println("binary64 0.1: " + Double.toHexString(a));

        float f = 0.1f;
        System.out.println("float 0.1: " + f);
        System.out.println("float widened: " + (double) f);

        BigDecimal exact = new BigDecimal("0.1")
            .add(new BigDecimal("0.2"));
        BigDecimal rounded = exact.setScale(2, RoundingMode.HALF_EVEN);
        System.out.println("BigDecimal sum: " + exact);
        System.out.println("Rounded to 2 places: " + rounded);
    }
}
~~~

Compile and run:

~~~shell
javac --release 17 FloatDoubleRoundingDemo.java
java FloatDoubleRoundingDemo
~~~

Output:

~~~text
0.1 + 0.2 = 0.30000000000000004
sum == 0.3: false
binary64 0.1: 0x1.999999999999ap-4
float 0.1: 0.1
float widened: 0.10000000149011612
BigDecimal sum: 0.3
Rounded to 2 places: 0.30
~~~

The program illustrates three distinct layers of issues:

1. float and double store approximate values in finite binary formats.
2. double has more precision bits than float, yet still cannot represent every decimal fraction exactly.
3. BigDecimal constructed from decimal strings can preserve the exact intended decimal value and apply a specified rounding policy.

## 14. Choosing Tools by Goal

| Goal | Appropriate Approach | Reason |
| --- | --- | --- |
| Scientific, graphics, simulation floating-point math | double, or float when clearly justified | Good performance, wide range, error governed by IEEE 754. |
| Decimal data such as money, tax, prices | BigDecimal from strings or integers in smallest units | Avoids binary errors incompatible with business contracts. |
| Displaying numbers with fixed digits | DecimalFormat/Formatter with specified rounding rule | Controls presentation without confusing it with stored values. |
| Rounding floating-point to nearest integer | Math.round when matching business rules | Math.round tie-breaking differs from decimal RoundingModes. |
| Comparing approximate computation results | Reasoned tolerance-based comparison | Avoids demanding bitwise equality when approximate equality is needed. |
| Rounding to a specific number of decimal places | BigDecimal.setScale(scale, mode) | Explicitly specifies scale and rounding policy. |

No single numeric type fits every problem. Determine **precision, value range, rounding rules, and data contracts** before selecting a type.

## 15. Frequently Asked Questions

**Why does System.out.println(0.1) print 0.1 if the value is not strictly exact?**  
Because Java prints the shortest decimal form that parses back to the exact stored double value. The short display string is not a dump of all binary bits.

**Does using double eliminate the 0.1 + 0.2 issue?**  
No. double reduces error compared to float due to a longer significand, but it still cannot represent every decimal fraction exactly.

**Why does float f = 0.1 cause an error?**  
The literal 0.1 defaults to double; assigning it to float is a narrowing conversion that can lose information. Write 0.1f or cast explicitly if rounding is acceptable.

**Is Math.round the way to round money to two decimal places?**  
No. Math.round rounds to an integer and has specific rules for negative values. Use BigDecimal.setScale with a RoundingMode matching the application's decimal policy.

**Is BigDecimal.valueOf(double) the same as new BigDecimal(double)?**  
No. The BigDecimal(double) constructor represents the exact binary64 value. valueOf uses the canonical string representation of double; for decimal input data, creating directly from a String remains clearest.

**Does Java 17 still need strictfp?**  
Not to obtain strict floating-point semantics. Since Java 17, all float and double operations are always strict under JEP 306.

**Can == be used to compare two doubles?**  
Yes, when the intent is exact comparison of two stored values, though for approximate computed results tolerance comparison is generally preferred, or an exact decimal type if required by business rules.

## 16. Official References

- [Java Language Specification 17 — Floating-Point Types, Formats, and Values (§4.2.3)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.3): float and double types, formats, and special values.
- [Java Language Specification 17 — Floating-Point Operations (§15.4)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.4): semantics for evaluating floating-point operations.
- [JEP 306 — Restore Always-Strict Floating-Point Semantics](https://openjdk.org/jeps/306): change applied starting in Java 17.
- [Java SE 17 API — java.math.BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): exact decimal numbers, scale, precision, and rounding.
- [Java SE 17 API — java.math.RoundingMode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html): rounding policies.
- [Java SE 17 API — java.lang.Math](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html): round, abs, math functions, and value checks.
- [Java SE 17 API — java.text.DecimalFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormat.html): number formatting and setting rounding modes.

**Guiding Principle:** float and double store numbers in finite-precision binary representation, so some decimal numbers are stored approximately and each operation can introduce rounding. Use double for general floating-point work when higher precision than float is needed; use BigDecimal or integer units for decimal data requiring exactness; and separate computational rounding from display formatting.
