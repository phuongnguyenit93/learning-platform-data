# Creating BigDecimal from String, BigInteger, long, and Unscaled Value in Java

`java.math.BigDecimal` is an arbitrary-precision decimal number type, well-suited when decimal values must be represented that `float`/`double` cannot hold accurately, such as monetary amounts, unit prices, rates, or decimal numeric data sent by external systems. When creating a `BigDecimal`, a seemingly minor constructor choice can **change the scale, precision, meaning of the data, and `equals` results**.

Four primary construction approaches in this lesson:

1. **From a decimal string:** `new BigDecimal("12.3400")` — preserves the exact entered decimal digits and scale.
2. **From a large integer `BigInteger`:** `new BigDecimal(new BigInteger("123400"))` — creates a decimal with scale equal to 0.
3. **From `long`:** `new BigDecimal(123400L)` or `BigDecimal.valueOf(123400L)` — also has scale equal to 0.
4. **From *unscaled value* and *scale*:** `new BigDecimal(new BigInteger("123400"), 4)` or `BigDecimal.valueOf(123400L, 4)` — creates the value `12.3400`.

The core point is the formula:

\[
\boxed{\text{BigDecimal value}=\text{unscaledValue}\times 10^{-\text{scale}}}
\]

**Preserving the numeric value** is not enough to preserve the `BigDecimal` model: two objects with the same mathematical value but different scales can yield `equals() == false`. Choose the construction method that fits the *semantics of the input data*, not just whatever compiles.

## 1. Internal Model: unscaledValue × 10^(-scale)

A `BigDecimal` essentially has two components:

- An **unscaled integer value** (*unscaled value*) with arbitrary precision, accessible via `unscaledValue()`.
- An `int` **scale**, accessible via `scale()`.

Examples:

| Representation | Unscaled value | Scale | Mathematical value |
| --- | ---: | ---: | ---: |
| `"12.34"` | 1234 | 2 | 12.34 |
| `"12.3400"` | 123400 | 4 | 12.3400 |
| `"1234"` | 1234 | 0 | 1234 |
| `"1.234E+3"` | 1234 | 0 | 1234 |
| `"1.23E+4"` | 123 | -2 | 12300 |
| `"0.000"` | 0 | 3 | 0.000 |
| `"-12.34"` | -1234 | 2 | -12.34 |

With `scale = 4`, take `123400 × 10^-4 = 12.3400`. With `scale = -2`, take `123 × 10^2 = 12300`. **Scale can be negative**, and is not always "the number of digits after the decimal point". This is a common inference error when reading data in scientific notation.

Direct observation:

```java
import java.math.BigDecimal;

BigDecimal x = new BigDecimal("12.3400");
System.out.println(x.unscaledValue()); // 123400
System.out.println(x.scale());         // 4
System.out.println(x.precision());     // 6
```

`precision()` is the number of significant digits of the **unscaled value** in decimal representation, distinct from `scale()`. `123400` has six digits, so precision is 6. Do not confuse precision with the total number of digits in the fractional part.

`BigDecimal` is **immutable**: constructors create new values, and addition/multiplication/`setScale` return new values without modifying the old object.

## 2. Creating from String: Preserving the Exact Entered Decimal Value

When the source is already a **decimal string**, the most direct choice is:

```java
BigDecimal price = new BigDecimal("12.3400");
BigDecimal tiny = new BigDecimal("0.000000001");
BigDecimal large = new BigDecimal("123456789012345678901234567890.123");
```

The `BigDecimal(String)` constructor **parses the exact decimal value** of the string; it does not pass through `double`, so it incurs no binary rounding error. Numbers with very many digits are still represented with the required precision within resource limits.

### The String Determines Scale

```java
BigDecimal a = new BigDecimal("12.34");
BigDecimal b = new BigDecimal("12.3400");

System.out.println(a.scale()); // 2
System.out.println(b.scale()); // 4
System.out.println(a.compareTo(b)); // 0: equal in numeric value
System.out.println(a.equals(b));    // false: different scales
```

Trailing zeros **can carry representation information**. If a system requires storing measurements to four decimal places or storing unit prices at a standard scale, the value `"12.3400"` differs from `"12.34"` in representation, even though the two numbers compare equal by `compareTo`.

### Decimal String Syntax

The following strings are supported:

```java
new BigDecimal("+12.5");
new BigDecimal("-0.25");
new BigDecimal(".5");
new BigDecimal("5.");
new BigDecimal("1.23E+4");
new BigDecimal("1e-7");
```

The `e`/`E` exponent suffix can produce a **negative or positive scale** depending on the decimal point position and exponent magnitude. Example:

```java
BigDecimal scientific = new BigDecimal("1.23E+4");
System.out.println(scientific.unscaledValue()); // 123
System.out.println(scientific.scale());         // -2
System.out.println(scientific.toString());      // 1.23E+4
System.out.println(scientific.toPlainString()); // 12300
```

The String constructor is **not a locale-aware number parser** and does not automatically sanitize arbitrary data:

- `new BigDecimal("1,5")` throws `NumberFormatException`, regardless of the machine's Locale.
- `new BigDecimal("1_000")` throws `NumberFormatException`; underscores may be valid in Java source literals, but **not** in BigDecimal strings.
- `new BigDecimal("NaN")` and `new BigDecimal("Infinity")` do not create special BigDecimal values; both are invalid syntax.
- `new BigDecimal(" 12.5 ")` does not automatically strip leading/trailing whitespace. If the contract allows whitespace, perform **controlled** normalization before parsing.
- A `null` String argument does not represent 0; check for null before parsing instead of silently treating it as 0.

**Do not silently strip signs, separators, or unexpected characters**. For input data from APIs/CSVs, define the allowed grammar explicitly and report an error when invalid.

## 3. Creating from BigInteger: Default Scale Is 0

`BigInteger` is a signed integer with arbitrary precision. Constructor:

```java
import java.math.BigInteger;

BigInteger integer = new BigInteger("123400");
BigDecimal decimal = new BigDecimal(integer);

System.out.println(decimal.toPlainString()); // 123400
System.out.println(decimal.unscaledValue()); // 123400
System.out.println(decimal.scale());         // 0
```

**Do not infer that the integer `123400` has an implicit decimal point.** `new BigDecimal(BigInteger)` sets **scale 0**, so it represents **123400**, not `12.3400`. If `BigInteger` stores monetary amounts in cents, micro-units, or scaled rates, you must **pass the scale per contract**.

Example where input data holds 123400 **smallest units of 1/10000**:

```java
BigInteger storedUnits = new BigInteger("123400");
BigDecimal restored = new BigDecimal(storedUnits, 4);
// 12.3400
```

Using a large integer is good when upstream data is already stored as an **unscaled integer**, such as micro-unit quantities exceeding the `long` range. That is an **integer + scale** model, not "rounding to a floating-point number".

### Difference Between toString(2) and a Decimal String

`new BigInteger("101101", 2)` creates the number 45 from a binary string; `new BigDecimal(theBigInteger)` gives decimal **45** with scale 0. `new BigDecimal("101101")` instead creates the decimal number one hundred one thousand one hundred one. **Radix** is part of the `BigInteger` constructor, not automatically applied to strings passed to `BigDecimal(String)`.

## 4. Creating from long: Exact Integer Value, Scale Equals 0

For an existing `long`:

```java
long units = 123400L;

BigDecimal fromConstructor = new BigDecimal(units);
BigDecimal fromFactory = BigDecimal.valueOf(units);
```

Both approaches produce the numeric value **123400** and `scale() == 0`. Because `long` holds an exact integer value in the range \([-2^{63}, 2^{63}-1]\), converting from `long` to `BigDecimal` loses no integer digits.

`BigDecimal.valueOf(long)` is a convenient factory and **may reuse cached objects**, so it is generally preferred when direct constructor invocation is not required. However, **do not rely on object identity** in business logic:

```java
BigDecimal a = BigDecimal.valueOf(7L);
BigDecimal b = BigDecimal.valueOf(7L);

System.out.println(a.equals(b)); // true
// Do not use a == b to check whether two numeric values are equal.
```

`BigDecimal` is an object. `a == b` asks whether they share the same reference, not whether the two numbers have the same value.

### If long Represents the Smallest Unit, You Must Pass Scale

Suppose 12345 is a number of cents and 1 main unit contains 100 cents:

```java
long cents = 12345L;
BigDecimal amount = BigDecimal.valueOf(cents, 2);
// 123.45
```

If you write `BigDecimal.valueOf(cents)` without passing scale, the result is `12345` — **off by a factor of 100** from the true value. This is a data error, not a rounding error.

Do not cast a huge number exceeding `long` into `long` just to call the factory; when an unscaled value exceeds the `long` range, keep it in `BigInteger`.

## 5. Creating from Unscaled Value: Passing the Right Scale

`BigDecimal` provides two convenient ways to attach a decimal scale to **an integer value**:

```java
// For BigInteger not limited by long range:
BigDecimal a = new BigDecimal(new BigInteger("123400"), 4);

// For an unscaled value already fitting in long:
BigDecimal b = BigDecimal.valueOf(123400L, 4);

System.out.println(a.toPlainString()); // 12.3400
System.out.println(b.toPlainString()); // 12.3400
```

With unscaled value `123400` and scale `4`:

\[
123400\times10^{-4}=12.3400.
\]

Treat `scale` as a **semantic parameter**, not an arbitrary formatting hint. Simply changing scale from 4 to 2 changes the mathematical value from `12.3400` to `1234.00` even though the unscaled value does not change.

| Unscaled | Scale | `toPlainString()` |
| ---: | ---: | --- |
| 123400 | 0 | `123400` |
| 123400 | 2 | `1234.00` |
| 123400 | 4 | `12.3400` |
| 123400 | 6 | `0.123400` |
| 123 | -2 | `12300` |
| -123400 | 4 | `-12.3400` |

`BigDecimal.valueOf(long unscaledVal, int scale)` also accepts **negative scales**. Example:

```java
BigDecimal x = BigDecimal.valueOf(123L, -2);
System.out.println(x.toString());      // 1.23E+4
System.out.println(x.toPlainString()); // 12300
System.out.println(x.unscaledValue()); // 123
System.out.println(x.scale());         // -2
```

**A negative scale is not an error**: it means multiplying by \(10^{|\text{scale}|}\). When outputting strings, `toString()` and `toPlainString()` may differ in format. If you must transmit values along with scale between systems, pass unscaled value + scale separately, or choose a text representation with clear round-trip rules.

## 6. Relationship with setScale and movePointLeft

Three operations can all yield `12.3400` yet carry **different inputs and purposes**:

```java
BigDecimal x = new BigDecimal(new BigInteger("123400"), 4);
BigDecimal y = BigDecimal.valueOf(123400L, 4);
BigDecimal z = BigDecimal.valueOf(123400L).movePointLeft(4);
```

For `x`, `y`, and `z`, the numeric result is `12.3400` in all three and in this specific case they share scale 4. However, the methods do not share a universal meaning for all inputs:

- **Constructor/factory with unscaled + scale:** interprets a stored data pair into the exact BigDecimal.
- **`movePointLeft(n)`:** transforms an existing numeric value by multiplying by \(10^{-n}\); the new scale also depends on the method's specification semantics, especially when a negative scale is already present.
- **`setScale(newScale, mode)`:** changes the **representation scale** while keeping the same mathematical value if possible; when significant digits must be dropped, a **rounding** policy is needed.

For example, do not equate `setScale(4)` with `movePointLeft(4)`:

```java
BigDecimal value = BigDecimal.valueOf(123400L);
BigDecimal changedScale = value.setScale(4); // 123400.0000
BigDecimal shiftedPoint = value.movePointLeft(4); // 12.3400
```

`setScale(4)` appends four fractional zeros to preserve the **value 123400**; `movePointLeft(4)` actually divides the value by \(10^4\).

If the goal is to reconstruct from an unscaled value, the clearest approach remains the **two-parameter** constructor or factory.

## 7. With MathContext: Constructors Can Round at Initialization Time

Overloads that accept `MathContext` such as `new BigDecimal(String, MathContext)`, `new BigDecimal(BigInteger, MathContext)`, and `new BigDecimal(long, MathContext)` **differ** from constructors without context: they can actively limit **precision** and round the value.

```java
import java.math.MathContext;
import java.math.RoundingMode;

MathContext context = new MathContext(3, RoundingMode.HALF_UP);
BigDecimal exact = new BigDecimal("12345");
BigDecimal rounded = new BigDecimal("12345", context);

System.out.println(exact.toString());   // 12345
System.out.println(rounded.toString()); // 1.23E+4
```

The new value `1.23E+4` is `12300`; **it no longer preserves the exact value 12345**. Thus a constructor call does not always merely "convert types" without altering the number.

| Constructor form | Scale without MathContext | Can round during creation? |
| --- | --- | --- |
| `BigDecimal(String)` | Inferred from decimal syntax | No, preserves exact decimal value |
| `BigDecimal(BigInteger)` | 0 | No |
| `BigDecimal(long)` | 0 | No |
| `BigDecimal(BigInteger, int)` | Passed-in scale | No |
| `BigDecimal(String, MathContext)` | Per post-rounding result | Yes |
| `BigDecimal(BigInteger, MathContext)` | Per post-rounding result | Yes |
| `BigDecimal(long, MathContext)` | Per post-rounding result | Yes |

`MathContext.precision()` is **not** the number of digits after the decimal point. It limits the number of **significant digits**. If the business goal is to round a monetary amount to 2 decimal places, do not casually use `new MathContext(2)` instead of `setScale(2, roundingMode)`.

If you need to store the exact original value and round only at the finalization step, create the exact BigDecimal first and separate the rounding step.

## 8. Equal BigDecimal Values Can Have Different Scales

`BigDecimal.compareTo` compares **numeric value**; `BigDecimal.equals` requires **same value and same scale**.

```java
BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

System.out.println(a.compareTo(b)); // 0
System.out.println(a.equals(b));    // false
System.out.println(a.scale());      // 1
System.out.println(b.scale());      // 2
```

This directly impacts using `BigDecimal` as a key in collections:

- `HashSet<BigDecimal>` uses `equals`/`hashCode`, so it can keep **two elements** `1.0` and `1.00`.
- `TreeSet<BigDecimal>` with natural ordering uses `compareTo` and typically treats those two values as **duplicates**.

If business logic wants to ignore trailing zeros when comparing keys, `stripTrailingZeros()` normalization can be used, but you must understand that **scale can become a negative number**:

```java
BigDecimal x = new BigDecimal("1000.00");
BigDecimal normalized = x.stripTrailingZeros();
System.out.println(normalized.toString()); // 1E+3
System.out.println(normalized.scale());    // -3
```

Normalization is a **business decision**, not a mandatory step after every constructor. If scale carries meaning such as measurement precision or currency units, do not accidentally strip it away.

## 9. Avoiding the Trap of Creating BigDecimal via double

A frequent reason `BigDecimal(String)` is needed is that many decimal fractions **cannot be represented accurately by double**.

```java
BigDecimal exact = new BigDecimal("0.1");
BigDecimal fromDoubleConstructor = new BigDecimal(0.1);
BigDecimal fromDoubleFactory = BigDecimal.valueOf(0.1);
```

The three ways are not fully equivalent:

- `new BigDecimal("0.1")`: decimal value equal to exactly one tenth.
- `new BigDecimal(0.1)`: represents **the exact binary approximation of 0.1** residing in `double`; typically has very many decimal digits.
- `BigDecimal.valueOf(0.1)`: uses the canonical string representation of `double` (`Double.toString`) to construct BigDecimal; for `0.1` it gives `0.1`, but **cannot recover any decimal digits already lost earlier**.

```java
System.out.println(new BigDecimal("0.1").toPlainString());
// 0.1
System.out.println(BigDecimal.valueOf(0.1).toPlainString());
// 0.1
System.out.println(new BigDecimal(0.1).toPlainString());
// 0.1000000000000000055511151231257827021181583404541015625
```

If the original data is decimal from JSON, database, or user strings, keep the **original data as string or integer + scale** until creating BigDecimal. Do not pass it through `double` and hope the `BigDecimal` constructor will reconstruct lost precision.

## 10. Zero, Negative Numbers, and Exponents

### Zero with Scale Still Carries Representation Meaning

```java
BigDecimal a = new BigDecimal("0");
BigDecimal b = new BigDecimal("0.00");
BigDecimal c = BigDecimal.valueOf(0L, 2);
```

All have **numeric value 0**, yet `a.scale() == 0`, while `b.scale() == 2` and `c.scale() == 2`. If the input is `"-0.00"`, `BigDecimal` does not preserve "negative zero" the way `double` does: the result has value **zero with signum() equal to 0**, while scale stays 2.

```java
BigDecimal negativeZeroText = new BigDecimal("-0.00");
System.out.println(negativeZeroText.toPlainString()); // 0.00
System.out.println(negativeZeroText.signum());        // 0
System.out.println(negativeZeroText.scale());         // 2
```

If the system needs to retain the **literal minus sign the user typed** on zero, store that text/sign information separately, not solely in BigDecimal.

### Exponents Affect Scale

```java
BigDecimal a = new BigDecimal("1.23E+4");
BigDecimal b = new BigDecimal("12300");

System.out.println(a.compareTo(b)); // 0
System.out.println(a.equals(b));    // false
System.out.println(a.scale());      // -2
System.out.println(b.scale());      // 0
```

Even though `a.toPlainString()` and `b.toPlainString()` can both print `"12300"`, variable `a` stores a negative scale. To round-trip both **value and scale**, `toString()` has canonical representation rules more suitable than `toPlainString()` in negative-scale cases. Or pass **unscaledValue and scale as two separate data fields**.

## 11. Standalone Runnable Java 17+ Program

Save as file **`BigDecimalConstructionDemo.java`**:

```java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.MathContext;
import java.math.RoundingMode;
import java.util.HashSet;
import java.util.Set;
import java.util.TreeSet;

public class BigDecimalConstructionDemo {
    public static void main(String[] args) {
        BigDecimal fromString = new BigDecimal("0012.3400");
        System.out.println("fromString=" + fromString.toPlainString());
        System.out.println("stringUnscaled=" + fromString.unscaledValue());
        System.out.println("stringScale=" + fromString.scale());
        System.out.println("stringPrecision=" + fromString.precision());

        BigInteger integer = new BigInteger("123400");
        BigDecimal fromBigInteger = new BigDecimal(integer);
        BigDecimal fromLong = new BigDecimal(123400L);
        BigDecimal fromLongFactory = BigDecimal.valueOf(123400L);
        System.out.println("fromBigInteger=" +
                fromBigInteger.toPlainString());
        System.out.println("fromLong=" + fromLong.toPlainString());
        System.out.println("fromLongFactory=" +
                fromLongFactory.toPlainString());
        System.out.println("integerScale=" + fromBigInteger.scale());

        BigDecimal fromUnscaledBig = new BigDecimal(integer, 4);
        BigDecimal fromUnscaledLong = BigDecimal.valueOf(123400L, 4);
        System.out.println("unscaledBig=" +
                fromUnscaledBig.toPlainString());
        System.out.println("unscaledLong=" +
                fromUnscaledLong.toPlainString());
        System.out.println("sameRepresentation=" +
                fromString.equals(fromUnscaledBig));

        BigDecimal negativeScale = BigDecimal.valueOf(123L, -2);
        System.out.println("negativeScaleText=" +
                negativeScale.toString());
        System.out.println("negativeScalePlain=" +
                negativeScale.toPlainString());
        System.out.println("negativeScaleValue=" +
                negativeScale.unscaledValue());
        System.out.println("negativeScaleScale=" +
                negativeScale.scale());

        BigDecimal fromScientific = new BigDecimal("1.23E+4");
        System.out.println("scientificUnscaled=" +
                fromScientific.unscaledValue());
        System.out.println("scientificScale=" +
                fromScientific.scale());
        System.out.println("scientificEqualsPlain=" +
                fromScientific.equals(new BigDecimal("12300")));
        System.out.println("scientificComparePlain=" +
                fromScientific.compareTo(new BigDecimal("12300")));

        BigDecimal differentScaleA = new BigDecimal("1.0");
        BigDecimal differentScaleB = new BigDecimal("1.00");
        System.out.println("equalsDifferentScale=" +
                differentScaleA.equals(differentScaleB));
        System.out.println("compareDifferentScale=" +
                differentScaleA.compareTo(differentScaleB));

        Set<BigDecimal> hashValues = new HashSet<>();
        hashValues.add(differentScaleA);
        hashValues.add(differentScaleB);
        Set<BigDecimal> sortedValues = new TreeSet<>();
        sortedValues.add(differentScaleA);
        sortedValues.add(differentScaleB);
        System.out.println("hashSetSize=" + hashValues.size());
        System.out.println("treeSetSize=" + sortedValues.size());

        BigDecimal zeroText = new BigDecimal("-0.00");
        System.out.println("zeroText=" + zeroText.toPlainString());
        System.out.println("zeroScale=" + zeroText.scale());
        System.out.println("zeroSignum=" + zeroText.signum());

        MathContext mc = new MathContext(3, RoundingMode.HALF_UP);
        BigDecimal exact = new BigDecimal("12345");
        BigDecimal rounded = new BigDecimal("12345", mc);
        System.out.println("contextExact=" + exact.toString());
        System.out.println("contextRounded=" + rounded.toString());
        System.out.println("contextScale=" + rounded.scale());

        System.out.println("scaledCents=" +
                BigDecimal.valueOf(12345L, 2).toPlainString());
        System.out.println("setScaleNotShift=" +
                BigDecimal.valueOf(123400L).setScale(4).toPlainString());
        System.out.println("movePoint=" +
                BigDecimal.valueOf(123400L).movePointLeft(4).toPlainString());

        BigDecimal normalized = new BigDecimal("1000.00")
                .stripTrailingZeros();
        System.out.println("stripTrailingZeros=" +
                normalized.toString());
        System.out.println("stripScale=" + normalized.scale());

        System.out.println("decimalFromString=" +
                new BigDecimal("0.1").toPlainString());
        System.out.println("decimalFromValueOfDouble=" +
                BigDecimal.valueOf(0.1).toPlainString());
        System.out.println("decimalFromDoubleConstructor=" +
                new BigDecimal(0.1).toPlainString());

        try {
            new BigDecimal("1,5");
            System.out.println("invalidComma=missed");
        } catch (NumberFormatException ex) {
            System.out.println("invalidComma=detected");
        }
    }
}
```

Compile and run:

```bash
javac BigDecimalConstructionDemo.java
java BigDecimalConstructionDemo
```

Output:

```text
fromString=12.3400
stringUnscaled=123400
stringScale=4
stringPrecision=6
fromBigInteger=123400
fromLong=123400
fromLongFactory=123400
integerScale=0
unscaledBig=12.3400
unscaledLong=12.3400
sameRepresentation=true
negativeScaleText=1.23E+4
negativeScalePlain=12300
negativeScaleValue=123
negativeScaleScale=-2
scientificUnscaled=123
scientificScale=-2
scientificEqualsPlain=false
scientificComparePlain=0
equalsDifferentScale=false
compareDifferentScale=0
hashSetSize=2
treeSetSize=1
zeroText=0.00
zeroScale=2
zeroSignum=0
contextExact=12345
contextRounded=1.23E+4
contextScale=-2
scaledCents=123.45
setScaleNotShift=123400.0000
movePoint=12.3400
stripTrailingZeros=1E+3
stripScale=-3
decimalFromString=0.1
decimalFromValueOfDouble=0.1
decimalFromDoubleConstructor=0.1000000000000000055511151231257827021181583404541015625
invalidComma=detected
```

The program demonstrates that **mathematical value**, **unscaled value**, **scale**, and **representation equality** are distinct concepts. Notice the pair `fromBigInteger=123400` and `unscaledBig=12.3400`: same `BigInteger("123400")` yet **different chosen scales**, resulting in values differing by a factor of \(10^4\).

## 12. Common Mistakes and Constructor Selection Checklist

| Misconception | Correct understanding |
| --- | --- |
| "`BigDecimal("12.3400")` automatically drops trailing zeros on creation." | The String constructor retains scale 4 per the original syntax. |
| "`new BigDecimal(BigInteger("123400"))` creates 12.3400." | No: without passing scale, the value is 123400, scale 0. |
| "`BigDecimal.valueOf(12345L)` treats it as cents and returns 123.45." | No: only `valueOf(12345L,2)` carries scale 2. |
| "Scale is always non-negative." | False: `BigDecimal.valueOf(123L,-2)` has value 12300 and scale -2. |
| "`setScale(4)` is like `movePointLeft(4)`." | False: `setScale` preserves numeric value (or rounds if needed); movePointLeft changes the value. |
| "`equals` and `compareTo` both only compare numeric value." | False: `equals` considers scale too; `compareTo` considers value. |
| "`precision=scale`." | No: precision is significant digits; scale is power-of-10 magnitude. |
| "BigDecimal stores negative zero like `double`." | No: `new BigDecimal("-0.00")` has `signum()==0` and prints `0.00`. |
| "Constructors with `MathContext` never round." | They can limit precision and round immediately upon creation. |
| "`new BigDecimal(0.1)` recreates the exact decimal 0.1." | It creates the exact value of the binary `double` approximation, not decimal 0.1. |
| "`BigDecimal.valueOf(0.1)` recovers any decimal lost earlier." | It goes through `Double.toString`; it cannot retrieve lost source precision. |
| "BigDecimal(String) parses using Vietnamese Locale by default." | No: it uses decimal syntax and does not automatically accept decimal commas. |
| "`toPlainString()` always round-trips scale as well." | For negative scales, the plain string can lose scale information when parsed back. |
| "`==` is suitable for comparing two BigDecimals." | `==` compares reference identity, not numeric equality. |

To choose the right construction approach:

1. **Source is an exact decimal String?** Use `new BigDecimal(text)`; validate syntax and preserve input precision.
2. **Source is a BigInteger with an actual integer value?** Use `new BigDecimal(integer)` to get scale 0.
3. **Source is an actual integer long?** Use `BigDecimal.valueOf(value)` or `new BigDecimal(value)`, scale 0.
4. **Source is an unscaled value with an implicit unit?** Use `new BigDecimal(bigInteger, scale)` or `BigDecimal.valueOf(longUnscaled, scale)`; **do not forget the scale**.
5. **Need to preserve trailing zeros or measurement resolution?** Inspect `scale()` and choose canonicalization intentionally.
6. **Need rounding during creation?** Pass `MathContext` only if that is a requirement; do not limit precision at the parsing step by default.
7. **Data already passed through double?** Determine whether precision loss is acceptable or if you must go back to the original decimal string.
8. **How is the value stored/transmitted to external systems?** Consider an `unscaledValue + scale` pair to preserve full semantics, and distinguish `toString` from `toPlainString`.
9. **Comparing or using as a collection key?** Understand the difference between `equals` and `compareTo`; if scale is part of data identity, do not automatically strip it.
10. **Data could be huge or malformed?** Enforce limits on string length and valid scale per application requirements to avoid resource-heavy processing.

**Takeaway:** `BigDecimal` is not just "a number with many digits", but an **unscaled integer together with a scale**. `String` preserves the decimal meaning of text, `BigInteger` and `long` create scale-0 integers unless specified otherwise, while overloads taking **unscaled value + scale** accurately interpret data according to the specified unit. Choosing the right constructor prevents factor-of-10 multiplication/division bugs, scale loss, and comparison confusion.

Reference: [Oracle Java 17 — BigDecimal Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html).