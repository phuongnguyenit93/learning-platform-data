# Unscaled Value, Scale, and the Value Formula of BigDecimal in Java

`java.math.BigDecimal` is an **immutable arbitrary-precision decimal** number type, very useful when decimal values must be represented in a controlled manner. The most important point when learning `BigDecimal` is not just "it has more digits than `double`", but **how Java determines the value of each object from an integer and a scale**.

A `BigDecimal` has two core components:

- **Unscaled value**: a signed integer, representable exactly by `BigInteger`.
- **Scale**: an integer of type `int`; indicates the power of 10 used in interpreting the unscaled value.

The formula defining the value is:

~~~text
value = unscaledValue × 10^(-scale)
~~~

Thus `unscaledValue = 12345`, `scale = 2` yields `123.45`; however, the same unscaled value with `scale = -2` yields `1,234,500`. **Scale is not always the number of digits after the decimal point**, because scale can be positive, zero, or negative.

This lesson belongs to the **BigDecimal Model** section and explains how to read both components, their relationship with `precision`, operations that change scale, the difference between equality by value and by representation, and how to use it safely in practical calculations with Java 17+.

## 1. Analyzing the Formula with Examples

With `new BigDecimal("123.45")`, Java can describe the value as:

~~~text
unscaledValue = 12345
scale         = 2
value         = 12345 × 10^(-2) = 123.45
~~~

Some other representations:

| Unscaled value | Scale | Calculation | Numeric value |
| ---: | ---: | --- | ---: |
| `12345` | `2` | `12345 × 10^-2` | `123.45` |
| `12345` | `0` | `12345 × 10^0` | `12345` |
| `123` | `-2` | `123 × 10^2` | `12300` |
| `-12345` | `3` | `-12345 × 10^-3` | `-12.345` |
| `12` | `2` | `12 × 10^-2` | `0.12` |
| `0` | `4` | `0 × 10^-4` | `0` |

In the case where unscaled value equals 0, **every scale gives the same mathematical value of zero**, but the object can still hold different scales; for example, `new BigDecimal("0.000")` has scale equal to 3.

Do not call `scale` "precision", because it does not count the total number of significant digits and does not express the physical reliability of data. Scale is only the **decimal exponent in the value model**.

## 2. Reading Directly with `unscaledValue()` and `scale()`

~~~java
BigDecimal amount = new BigDecimal("123.4500");

System.out.println(amount);                // 123.4500
System.out.println(amount.unscaledValue()); // 1234500
System.out.println(amount.scale());         // 4
System.out.println(amount.precision());     // 7
~~~

`unscaledValue()` returns `BigInteger`, not `long`. Therefore, a very large decimal number is not necessarily limited to 64 bits. `scale()` returns `int`, representing the decimal exponent used in the formula. `precision()` counts the number of significant decimal digits in the **unscaled value**; for `1234500` that is 7 digits.

The values `123.4500` and `123.45` are **equal in mathematical value**, but have different structures:

| Input text | Unscaled value | Scale | Precision |
| --- | ---: | ---: | ---: |
| `"123.4500"` | `1234500` | `4` | `7` |
| `"123.45"` | `12345` | `2` | `5` |
| `"1.23E+4"` | `123` | `-2` | `3` |
| `"0.000"` | `0` | `3` | `1` |

**Counting precision of zero:** according to the `BigDecimal` contract, `precision()` of a zero value is 1, not 0, regardless of the scale of the zero representation created. Keeping extra 0 digits in a decimal number affects scale and can affect precision in many cases, but does not turn input data into a "more reliable" measurement.

## 3. Positive, Zero, and Negative Scale

### Positive Scale

With `new BigDecimal("12.345")`, the unscaled value is `12345` and scale is `3`: value `12345 × 10^-3 = 12.345`. This is the familiar case that makes beginners think scale always means "three digits after the decimal point".

### Zero Scale

`new BigDecimal("12345")` has unscaled value `12345` and scale `0`. The value is the integer 12345, yet it is still a `BigDecimal` object, a different type from `BigInteger` or `Long`.

### Negative Scale

`new BigDecimal("1.23E+4")` has:

~~~java
BigDecimal scientific = new BigDecimal("1.23E+4");
System.out.println(scientific);                 // 1.23E+4
System.out.println(scientific.unscaledValue()); // 123
System.out.println(scientific.scale());         // -2
System.out.println(scientific.toPlainString()); // 12300
~~~

Because `123 × 10^2 = 12300`, a negative scale is completely valid. The `toString()` form may use scientific notation, whereas `toPlainString()` expresses the value as ordinary decimal digits without exponent notation. **Do not infer that `scale < 0` is an error or a negative number.** The sign of the number resides in the unscaled value; the sign of scale indicates the position of the decimal point.

You can construct directly from an unscaled/scale pair:

~~~java
new BigDecimal(BigInteger.valueOf(12345), 2); // 123.45
new BigDecimal(BigInteger.valueOf(123), -2);  // 1.23E+4
BigDecimal.valueOf(12L, 2);                    // 0.12
~~~

The overload `BigDecimal.valueOf(long unscaledVal, int scale)` differs from `BigDecimal.valueOf(double)`. Do not confuse overloads just because they share the same method name.

## 4. Same Value, Different Representation: `equals` and `compareTo`

Two numbers:

~~~java
BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");
~~~

are both mathematically equal to 1, but `a` has unscaled = 10, scale = 1; `b` has unscaled = 100, scale = 2. Therefore:

~~~java
System.out.println(a.equals(b));        // false
System.out.println(a.compareTo(b));     // 0
~~~

- **`equals`** considers two `BigDecimal` objects equal when both *numeric value* and *scale* match; the example above returns false.
- **`compareTo`** compares numeric value, so it returns 0 for the two representations `1.0` and `1.00`.

Consequences for collections:

~~~java
Set<BigDecimal> hashed = new HashSet<>(Arrays.asList(a, b));
Set<BigDecimal> ordered = new TreeSet<>(Arrays.asList(a, b));
// hashed.size() = 2, ordered.size() = 1
~~~

`HashSet` relies on `equals`/`hashCode`, whereas `TreeSet` by default uses `compareTo` for ordering, so **the two collections can deduplicate elements according to different policies**. If using monetary amounts or decimal numbers as keys, determine whether scale has business meaning, and normalize representations before storing keys when needed.

**Do not arbitrarily alter `equals`/`hashCode`** or use "approximately equal" comparison by epsilon as a `TreeSet` comparator; the comparison relation must preserve a consistent and transitive contract.

## 5. `stripTrailingZeros()` Changes Structure While Preserving Numeric Value

`stripTrailingZeros()` removes trailing zeros in the **decimal representation** without changing the mathematical value:

~~~java
BigDecimal original = new BigDecimal("123.4500");
BigDecimal stripped = original.stripTrailingZeros();

System.out.println(stripped);                 // 123.45
System.out.println(stripped.unscaledValue()); // 12345
System.out.println(stripped.scale());         // 2
~~~

The `original` object **does not change**, because `BigDecimal` is immutable. For an integer with many trailing zeros, the resulting scale can even become **negative**; for example, `new BigDecimal("1200.0").stripTrailingZeros()` may be presented with an exponent to express the negative scale while still keeping the value 1200.

For zero, `stripTrailingZeros` produces the canonical zero form with scale 0:

~~~java
BigDecimal z = new BigDecimal("0.000");
System.out.println(z.unscaledValue());                 // 0
System.out.println(z.scale());                         // 3
System.out.println(z.precision());                     // 1
System.out.println(z.stripTrailingZeros().scale());    // 0
~~~

**Do not use `stripTrailingZeros` if business logic requires keeping the entered number of digits as separate information.** In price quotes or measurements, `1.20` sometimes needs to be displayed with exactly two fractional digits; normalizing to `1.2` drops the original scale even though it does not lose mathematical value.

## 6. `setScale`: Changing Scale and Sometimes Needing Value Rounding

`setScale(newScale)` creates a new `BigDecimal` with the requested scale.

**Increasing scale** (adding decimal places) can generally be performed exactly by multiplying the unscaled value by a power of 10:

~~~java
BigDecimal initial = new BigDecimal("12.3");
BigDecimal padded = initial.setScale(3);
// padded = 12.300, unscaled = 12300, scale = 3
~~~

**Decreasing scale** often requires dropping significant digits and may need rounding:

~~~java
BigDecimal amount = new BigDecimal("12.35");
BigDecimal rounded = amount.setScale(1, RoundingMode.HALF_UP);
// rounded = 12.4
~~~

When using the `setScale(int)` overload without a rounding mode, Java requires the scale change to **occur exactly**. If non-zero digits would need to be dropped, it throws `ArithmeticException`. To detect operations where rounding is not allowed, you can explicitly choose `RoundingMode.UNNECESSARY`.

Important differences:

- `setScale` changes **scale and may change the mathematical value** when rounding is required.
- `stripTrailingZeros` changes **the representation, not the mathematical value**.
- `DecimalFormat.format` creates a **display string**, without changing the source object.
- `BigDecimal` is immutable: you must save the returned result, rather than expecting the original object to be mutated.

**Rounding mode** must follow business requirements. `HALF_UP`, `HALF_EVEN`, `DOWN`, `CEILING`, and `FLOOR` handle boundaries and negative numbers differently; there is no default mode that is "right for every invoice".

## 7. `scaleByPowerOfTen` and `movePointLeft/Right`

From the formula `unscaled × 10^-scale`, multiplying or dividing by a power of 10 can be performed with decimal-point shifting APIs:

~~~java
BigDecimal input = new BigDecimal("12.30");
BigDecimal scaled = input.scaleByPowerOfTen(2);
BigDecimal moved = input.movePointRight(3);

// scaled = 1230, moved = 12300
~~~

With `scaleByPowerOfTen(n)`, in terms of the `BigDecimal` model, the new scale is in principle `scale - n`. `movePointRight(n)` and `movePointLeft(n)` carry decimal-point shifting semantics, and their results have a **non-negative** scale by contract. Thus, in negative-scale cases, the two API groups can yield **different representations even though their mathematical values are equal**.

Do not use the formatted string representation as the criterion to tell whether an operation changed the value. Check:

~~~text
New value = Old value × 10^n      (shift right / scaleByPowerOfTen)
New value = Old value × 10^(-n)   (shift left)
~~~

These operations are also subject to `int` scale limits and resources. For overly large/small scales, the transformation may throw an exception or fail to be represented within execution limits; do not use an untrusted `n` value without validation.

## 8. Operations Can Produce New Scales According to Rules

`BigDecimal` does not just preserve initial unscaled value and scale: **operation results also have their own unscaled/scale pair**.

### Addition and Subtraction

For exact addition/subtraction, the *preferred scale* is the **larger of the two operands' scales**:

~~~java
BigDecimal x = new BigDecimal("1.20"); // scale 2
BigDecimal y = new BigDecimal("3.4");  // scale 1

BigDecimal sum = x.add(y); // 4.60, scale 2
~~~

Because the two numbers must be added at the same decimal unit, the system can append zeros to the internal representation before adding the unscaled integers.

### Multiplication

The preferred scale of exact multiplication is the **sum of the two scales**:

~~~java
BigDecimal product = new BigDecimal("1.20")
        .multiply(new BigDecimal("3.4"));
// product = 4.080, scale 3 = 2 + 1
~~~

The two numbers `4.080` and `4.08` are equal by `compareTo` but have different scales. When multiplying money by rates or quantities, specify the output scale and when to round according to business rules.

### Division

The preferred scale of division is the **dividend's scale minus the divisor's scale**, though the exact result may require additional fractional digits. Example:

~~~java
BigDecimal quotient = new BigDecimal("1.00")
        .divide(new BigDecimal("4"));
// quotient = 0.25, scale 2
~~~

A division like `BigDecimal.ONE.divide(new BigDecimal("3"))` has an infinite decimal expansion, so the exact division overload without rounding can throw `ArithmeticException`. When business logic permits approximation, pass `scale` and `RoundingMode` or `MathContext`, and document the precision criteria explicitly.

**Note:** When using overloads with `MathContext` and limited precision, operations may round, causing the actual scale to differ from the preferred scale. Do not predict result scale without considering the overload and rounding context.

## 9. `MathContext.precision` Differs from `BigDecimal.scale`

`MathContext` limits the **total number of significant digits of the result**, not the number of digits after the decimal point.

~~~java
BigDecimal value = new BigDecimal("12345.67");
BigDecimal rounded = value.round(
        new MathContext(3, RoundingMode.HALF_UP));
// rounded = 1.23E+4: three significant digits, negative scale
~~~

Conversely, `setScale(2, RoundingMode.HALF_UP)` requires two decimal places after the separator in the result. The two operations can yield very different results for the same input.

| Method | Question to answer |
| --- | --- |
| `scale()` | What is the decimal exponent of this object? |
| `precision()` | How many significant decimal digits does the unscaled value have? |
| `setScale(2, mode)` | Do you want the result to keep an exact scale of 2, allowing rounding per mode? |
| `round(new MathContext(3, mode))` | Do you want to keep three significant digits of the result? |
| `format(...)` | Which presentation rules do you want for the display string? |

`MathContext.UNLIMITED` has precision equal to 0 by `MathContext` contract (meaning "unlimited"), which differs from `BigDecimal.precision() == 0`; a `BigDecimal` with value zero still has precision equal to 1. Avoid confusing the two kinds of "precision".

## 10. Constructors, String, and double: Input Source Determines Unscaled Value

If you require the **exact decimal as entered by the user**, create the object directly from a decimal string:

~~~java
BigDecimal exact = new BigDecimal("0.1");
// unscaled 1, scale 1
~~~

If passing through `double`, the value has already been rounded to binary64 before the `BigDecimal(double)` constructor receives it:

~~~java
BigDecimal fromDouble = new BigDecimal(0.1);
// 0.1000000000000000055511151231257827021181583404541015625
~~~

`new BigDecimal(0.1)` represents **the exact binary64 value currently stored**, not the exact decimal value 1/10 intended by the literal. `BigDecimal.valueOf(0.1)` uses the canonical string produced by `Double.toString(0.1)` and in this example returns decimal `0.1`, but that factory does not know how to recover original decimal data if it has already gone through a chain of `double` operations.

To preserve both the **value and scale of decimal input**, accepting the original string is the clear approach:

~~~java
new BigDecimal("1.20"); // unscaled 120, scale 2
new BigDecimal("1.2");  // unscaled 12, scale 1
~~~

If you convert both strings to `double` and back to decimal, information about the two notations and original scales can be lost. When parsing input from CSV/JSON/forms, validate decimal syntax, locale, value range, and precision/scale limits explicitly.

## 11. Complete Java 17+ Program and Verification Stdout

Save as file `BigDecimalModelDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.MathContext;
import java.math.RoundingMode;
import java.util.Arrays;
import java.util.HashSet;
import java.util.TreeSet;

public class BigDecimalModelDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("123.4500");
        System.out.println("a = " + a);
        System.out.println("a.unscaledValue = " + a.unscaledValue());
        System.out.println("a.scale = " + a.scale());
        System.out.println("a.precision = " + a.precision());

        BigDecimal stripped = a.stripTrailingZeros();
        System.out.println("stripped = " + stripped);
        System.out.println("stripped unscaled = "
                + stripped.unscaledValue());
        System.out.println("stripped scale = " + stripped.scale());

        BigDecimal e = new BigDecimal("1.23E+4");
        System.out.println("e = " + e);
        System.out.println("e unscaled = " + e.unscaledValue());
        System.out.println("e scale = " + e.scale());
        System.out.println("e plain = " + e.toPlainString());
        System.out.println("construct (123,-2) = "
                + new BigDecimal(BigInteger.valueOf(123), -2));
        System.out.println("construct (12345,2) = "
                + new BigDecimal(BigInteger.valueOf(12345), 2));
        System.out.println("valueOf(12,2) = "
                + BigDecimal.valueOf(12L, 2));

        BigDecimal z = new BigDecimal("0.000");
        System.out.println("zero unscaled,scale,precision = "
                + z.unscaledValue() + "," + z.scale()
                + "," + z.precision());
        System.out.println("zero stripped scale = "
                + z.stripTrailingZeros().scale());

        System.out.println("upscale = "
                + new BigDecimal("12.3").setScale(3));
        System.out.println("downscale HALF_UP = "
                + new BigDecimal("12.35")
                .setScale(1, RoundingMode.HALF_UP));
        System.out.println("sum = "
                + new BigDecimal("1.20")
                .add(new BigDecimal("3.4")));
        System.out.println("product = "
                + new BigDecimal("1.20")
                .multiply(new BigDecimal("3.4")));
        System.out.println("division = "
                + new BigDecimal("1.00")
                .divide(new BigDecimal("4")));

        System.out.println("scaleByPowerOfTen = "
                + new BigDecimal("12.30").scaleByPowerOfTen(2));
        System.out.println("movePointRight = "
                + new BigDecimal("12.30").movePointRight(3));
        System.out.println("negative zero = "
                + new BigDecimal("-0.00"));
        System.out.println("negative zero scale = "
                + new BigDecimal("-0.00").scale());

        BigDecimal x = new BigDecimal("1.0");
        BigDecimal y = new BigDecimal("1.00");
        System.out.println("equals different scales = " + x.equals(y));
        System.out.println("compareTo different scales = " + x.compareTo(y));
        System.out.println("HashSet size = "
                + new HashSet<>(Arrays.asList(x, y)).size());
        System.out.println("TreeSet size = "
                + new TreeSet<>(Arrays.asList(x, y)).size());
        System.out.println("round MathContext(3) = "
                + new BigDecimal("12345.67")
                .round(new MathContext(3, RoundingMode.HALF_UP)));
        System.out.println("0.1 from string = "
                + new BigDecimal("0.1"));
        System.out.println("0.1 from double = "
                + new BigDecimal(0.1));

        try {
            new BigDecimal("1.23")
                    .setScale(1, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException ex) {
            System.out.println("UNNECESSARY catches rounding");
        }
    }
}
~~~

Compile and run:

~~~bash
javac BigDecimalModelDemo.java
java BigDecimalModelDemo
~~~

Stdout:

~~~text
a = 123.4500
a.unscaledValue = 1234500
a.scale = 4
a.precision = 7
stripped = 123.45
stripped unscaled = 12345
stripped scale = 2
e = 1.23E+4
e unscaled = 123
e scale = -2
e plain = 12300
construct (123,-2) = 1.23E+4
construct (12345,2) = 123.45
valueOf(12,2) = 0.12
zero unscaled,scale,precision = 0,3,1
zero stripped scale = 0
upscale = 12.300
downscale HALF_UP = 12.4
sum = 4.60
product = 4.080
division = 0.25
scaleByPowerOfTen = 1230
movePointRight = 12300
negative zero = 0.00
negative zero scale = 2
equals different scales = false
compareTo different scales = 0
HashSet size = 2
TreeSet size = 1
round MathContext(3) = 1.23E+4
0.1 from string = 0.1
0.1 from double = 0.1000000000000000055511151231257827021181583404541015625
UNNECESSARY catches rounding
~~~

This output illustrates unscaled/scale pairs **in both negative scale and zero cases**, scale-changing operations with/without rounding, operation scales, zero normalization, and the effect of scale on collections.

## 12. String Forms `toString` and `toPlainString`

`BigDecimal.toString()` produces a canonical string form that may contain scientific notation when needed. `toPlainString()` produces a representation **without using exponents**, suitable if the receiver requires ordinary decimal display.

~~~java
BigDecimal big = new BigDecimal("1.23E+4");
big.toString();      // "1.23E+4"
big.toPlainString(); // "12300"
~~~

**Do not confuse output formatting with number structure:** the two strings above describe the same value, yet if `"12300"` is parsed back, the new object can have a different scale from the original object (`"1.23E+4"` has scale -2; `"12300"` has scale 0). If both **value and scale** must be preserved when serializing, you must specify a format capable of round-tripping both, such as using `toString` per the `BigDecimal` contract or passing unscaled/scale separately.

Some business workflows prefer not to use scientific notation when displaying money, yet `toPlainString()` should also not be used indiscriminately on data with huge negative scales because the string can bloat and consume excessive resources.

## 13. Edge Cases and Practical Limits

### Zero and Negative Sign

`new BigDecimal("-0.00")` has numeric value zero, unscaled value 0, and scale 2. `BigDecimal` **does not maintain a distinct negative zero value** like IEEE 754 `double -0.0`. The `toString()` string normally renders as `0.00`, even though the original text had a minus sign.

### Scale and Precision Have Different Limits

The unscaled value is stored as an arbitrary-precision integer but **is subject to practical resources**; scale remains an `int`, so arbitrarily huge decimal exponents cannot be used. Operations may encounter `ArithmeticException` when a desired scale cannot be represented or rounding is forbidden, and can consume heavy memory when expanding values or building long strings.

### No NaN or Infinity

`BigDecimal` does not represent NaN or `Infinity` like `double`. When converting unusual inputs to decimal, a separate validation policy is required. If receiving a `double`, check `Double.isFinite(value)` first if the application only accepts finite numbers.

### Financial Data Fields

If storing amounts to two decimal places, you can enforce `setScale(2, mode)` at the storage boundary; however, do not **automatically** normalize with `stripTrailingZeros` if scale still carries the meaning of currency units, presentation rules, or auditing. Being "numerically equal" and being "the right decimal representation" are two different contracts.

## 14. Common Mistakes

1. **Assuming scale is always the number of digits after the decimal point.** Scale can be negative, e.g., `1.23E+4` has scale -2.
2. **Confusing scale with precision.** `123.4500` has scale 4 and precision 7, not both 4.
3. **Thinking `stripTrailingZeros` changes numeric value.** It preserves the value, but changes unscaled/scale and can make scale negative.
4. **Using `equals` to check decimal values regardless of scale.** `1.0` and `1.00` are not `equals`, though `compareTo` is 0.
5. **Using `BigDecimal` as a collection key without deciding a scale policy.** `HashSet` and `TreeSet` can group data differently.
6. **Calling `setScale` and thinking the original object changed.** `BigDecimal` is immutable; you must capture the returned object.
7. **Reducing scale without considering rounding.** It may require a rounding mode or throw an exception if exact conversion fails.
8. **Assuming `MathContext(3)` means three digits after the decimal point.** It sets three significant digits in total.
9. **Assuming an operation's result scale always equals an operand's scale.** Addition/multiplication/division have their own scale rules, and rounding context can alter scale.
10. **Going through `double` when needing to preserve exact decimals from string input.** Binary64 rounds many decimal fractions before creating `BigDecimal`.
11. **Equating the printed string with the object's structure.** `toPlainString` can lose negative scale information if parsed back.
12. **Ignoring zero with multiple scales or signed input.** All zeros are equal in value, yet object equality still checks scale; BigDecimal does not store a separate signed zero.
13. **Overlooking scale overflow and resource limits.** "Arbitrary precision" does not mean processing infinitely large strings/exponents in real memory.
14. **Treating scale as the reliability of a measurement.** Scale is only a property of decimal representation; physical uncertainty must be described by other business data.

## 15. Self-Practice Questions

**Question 1.** What value do unscaled value 12345 and scale 3 represent?

**Answer:** `12345 × 10^-3 = 12.345`.

**Question 2.** What are the unscaled value and scale of `new BigDecimal("1.23E+4")`? Why is the scale negative?

**Answer:** Unscaled = 123, scale = -2 because `123 × 10^2 = 12300`. A negative scale is notation for increasing magnitude by powers of 10, not the negative sign of the number.

**Question 3.** Why is `new BigDecimal("1.0").equals(new BigDecimal("1.00"))` false while `compareTo` returns 0?

**Answer:** `equals` checks scale as well, whereas `compareTo` only compares the decimal numeric value.

**Question 4.** What does `new BigDecimal("123.4500").stripTrailingZeros()` change?

**Answer:** It preserves the value 123.45, while unscaled changes from 1234500 to 12345 and scale from 4 to 2; the source object remains unchanged.

**Question 5.** How does `new BigDecimal("12.3").setScale(3)` differ from `new BigDecimal("12.35").setScale(1, HALF_UP)`?

**Answer:** The first pads with zeros, preserving the exact value as 12.300; the second requires rounding to 12.4 under the HALF_UP rule.

**Question 6.** Why does `new BigDecimal("1.20").multiply(new BigDecimal("3.4"))` return `4.080` instead of forcing `4.08`?

**Answer:** Exact multiplication has a preferred scale equal to the sum of the two operands' scales: 2 + 1 = 3. The two representations have the same numeric value but different scales.

**Question 7.** Is `BigDecimal.ZERO.precision()` equal to 0 because zero has no significant digits?

**Answer:** False. By `BigDecimal` definition, the precision of zero is 1. Do not confuse it with `MathContext.UNLIMITED`, which has precision 0 to indicate unlimited.

**Question 8.** When should `toString()` be used instead of `toPlainString()` for serialization?

**Answer:** If you want to round-trip both value **and scale**, the canonical form of `toString` is more suitable. `toPlainString` drops scientific notation; parsing it back can alter the scale of original data that had a negative scale.

## References

- [Oracle Java SE 21 — BigDecimal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html): value formula, unscaled value, scale, precision, preferred scale, equals/compareTo, setScale, and stripTrailingZeros.
- [Oracle Java SE 21 — BigInteger](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigInteger.html): arbitrary-width integer representation used as unscaled value.
- [Oracle Java SE 21 — MathContext](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/MathContext.html): precision, rounding mode, and UNLIMITED.
- [Oracle Java SE 21 — RoundingMode](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/RoundingMode.html): meaning of each rounding rule.
