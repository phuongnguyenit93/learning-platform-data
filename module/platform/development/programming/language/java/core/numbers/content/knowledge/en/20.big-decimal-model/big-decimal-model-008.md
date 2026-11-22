# Preserving Significant Trailing Zeros with BigDecimal (Java)

## 1. Why Is "1.20" Not Simply "1.2"?

Mathematically, **1.20 and 1.2 are equal in value**. Yet in many systems, the decimal string `"1.20"` carries another piece of information: the input provided the value to **two digits after the decimal point**, rather than one. This can be meaningful for currency, listed prices, measurement data, report files, or storage requirements.

`java.math.BigDecimal` stores not only the arithmetic value but also a **scale** component. Because of that:

~~~java
BigDecimal a = new BigDecimal("1.20");
BigDecimal b = new BigDecimal("1.2");

System.out.println(a);         // 1.20
System.out.println(b);         // 1.2
System.out.println(a.scale()); // 2
System.out.println(b.scale()); // 1
~~~

This is a code snippet placed inside a method and requires `import java.math.BigDecimal;`. Both represent the same mathematical number while holding **two different decimal representations**.

Lesson goals:

- Understand `unscaledValue`, `scale`, and `precision` of `BigDecimal`.
- Know how to **preserve trailing zeros** when reading, computing, storing, and outputting strings.
- Avoid using `stripTrailingZeros()` when trailing zero digits are significant.
- Distinguish `equals()` from `compareTo()` and their impact on `HashMap`/`TreeSet`.
- Understand `setScale()` when adding/removing zeros, rounding rules, and representation changes caused by operations.
- Avoid losing information when passing through `double`, JSON, JDBC, or formatters.
- Recognize limitations: scale can express **recorded resolution**, yet does not by itself prove the physical accuracy of a measurement.

The examples use **Java 17+**, preferring to construct BigDecimal from **original decimal strings**.

## 2. The unscaled value × 10^(-scale) Model

The mathematical value of a `BigDecimal` is represented by:

\[
\text{value}=\text{unscaledValue}\times10^{-\text{scale}}
\]

- **Unscaled value** is a `BigInteger` containing the significant digits in the current representation.
- **Scale** is the number of digits to the right of the decimal point when scale is positive; scale can also be 0 or negative.
- **Precision** is the number of digits of the unscaled value (per API definition), with a special rule when the value equals 0.

| String creating BigDecimal | Unscaled value | Scale | Precision | Mathematical value |
| --- | ---: | ---: | ---: | --- |
| `"1.2"` | 12 | 1 | 2 | 1.2 |
| `"1.20"` | 120 | 2 | 3 | 1.2 |
| `"1.200"` | 1200 | 3 | 4 | 1.2 |
| `"0.00"` | 0 | 2 | 1 | 0 |
| `"1200"` | 1200 | 0 | 4 | 1200 |
| `"1E+3"` | 1 | −3 | 1 | 1000 |

Verification example:

~~~java
BigDecimal amount = new BigDecimal("1.20");

System.out.println(amount.unscaledValue()); // 120
System.out.println(amount.scale());         // 2
System.out.println(amount.precision());     // 3
~~~

**Core point:** the trailing zeros of `1.20` are not just a `println` detail. They are tied to `scale=2` and `unscaledValue=120` in the object's data model.

Do not confuse `precision` with `scale`. `1.20` has precision 3, scale 2; `1200` has precision 4, scale 0. One value can have multiple valid representations with different precisions and scales.

## 3. "Significant" Is a Data Contract Requirement

There are at least three scenarios to distinguish.

### 3.1. Monetary Amounts with Two Decimal Places

An invoice displaying `"12.30"` may be required to show **two digits after the dot** due to currency units and document issuance standards. Even though the numeric value of `12.30` equals `12.3`, the formats are not fully interchangeable in printouts or APIs.

### 3.2. Measurements Recorded with Resolution

A length measurement `"1.20 m"` might be reported to 0.01 m. Turning it into `"1.2 m"` can lose **information about the recorded level of detail**.

However, a string with two decimal places **does not itself prove the sensor is accurate to ±0.01 m**. If measurement uncertainty, instrument accuracy, standard error, or units are needed, store them in separate metadata/contracts.

### 3.3. Purely Mathematical Values

In an algorithm that only needs to compare numeric values and does not care about representation, `1.20` and `1.2` can be considered equivalent. In that case, stripping trailing zeros can be acceptable, or even helpful when normalizing data.

**Design principle:** determine whether the system needs to **keep the exact original number**, **keep a standard scale**, or only **keep the arithmetic value**. These three goals are not completely identical.

## 4. Creating BigDecimal from String to Preserve Decimal Representation

Reliable approach when receiving decimal text:

~~~java
BigDecimal a = new BigDecimal("1.20");
BigDecimal b = new BigDecimal("0.000");
BigDecimal c = new BigDecimal("125.00");

System.out.println(a.toPlainString()); // 1.20
System.out.println(b.toPlainString()); // 0.000
System.out.println(c.toPlainString()); // 125.00
~~~

`BigDecimal(String)` parses the decimal text and sets unscaled value and scale according to the provided numeric representation. It does not call `stripTrailingZeros` by default.

When input is a decimal field with a fixed format, store the **original string**, or at least `BigDecimal` along with a specific scale contract, depending on reconstruction requirements. If you need to preserve every character such as a leading plus sign, uppercase/lowercase `E`, or leading zeros in the integer part, **BigDecimal alone is not enough**: it stores numeric structure, not the entire original text.

### Do Not Pass Through double to "Keep 1.20"

~~~java
BigDecimal text = new BigDecimal("1.20");
BigDecimal fromDouble = BigDecimal.valueOf(1.20);

System.out.println(text);       // 1.20
System.out.println(fromDouble); // 1.2
~~~

Reason: Java already treats the literal `1.20` as a `double` value; the spelling `1.20` vs `1.2` is not kept as text metadata. `BigDecimal.valueOf(double)` obtains the decimal representation from `Double.toString(double)`, so it cannot recover lost trailing zeros.

`new BigDecimal(1.20)` brings another issue: the constructor from `double` interprets the exact **approximated binary value**, which can result in a long fractional part. When entered decimal data must be preserved, read directly from a string or a dedicated decimal type.

## 5. equals and compareTo: Numerically Equal Does Not Mean Object Equal

`BigDecimal` has two important comparison methods.

**`compareTo()`** compares **arithmetic value**:

~~~java
BigDecimal a = new BigDecimal("1.20");
BigDecimal b = new BigDecimal("1.2");

System.out.println(a.compareTo(b)); // 0
~~~

**`equals()`** requires both **numeric value** and **scale** to match (same numeric representation per BigDecimal's definition):

~~~java
System.out.println(a.equals(b)); // false
~~~

Therefore, if business logic only wants to know "same amount of money" or "same value", use `compareTo(b) == 0`. If it wants to know "same number and same scale", `equals()` is more accurate to that intent.

### HashCode and Collections

`hashCode()` must be consistent with `equals()`, but **not necessarily** consistent with `compareTo() == 0`. Therefore:

~~~java
java.util.Map<BigDecimal, String> map = new java.util.HashMap<>();
map.put(new BigDecimal("1.20"), "two decimal places");

System.out.println(map.get(new BigDecimal("1.20"))); // two decimal places
System.out.println(map.get(new BigDecimal("1.2")));  // null
~~~

In a `HashMap`, two keys with the same mathematical value yet different scales **are not treated as the same key** because `equals()` returns false.

Conversely, `TreeSet<BigDecimal>` uses natural ordering based on `compareTo()`, so it can treat two numeric representations as the same element:

~~~java
java.util.Set<BigDecimal> sorted =
        new java.util.TreeSet<>();
sorted.add(new BigDecimal("1.20"));
sorted.add(new BigDecimal("1.2"));

System.out.println(sorted.size()); // 1
~~~

This is a real difference between collections based on `equals/hashCode` and ordered collections. If scale carries business meaning, think very carefully before using `TreeSet` as a unique store of records that need to preserve distinct representations.

## 6. setScale: Retaining or Enforcing the Number of Digits After the Decimal Point

`setScale(newScale)` returns a `BigDecimal` with the new scale; **it does not modify the source object**.

~~~java
BigDecimal original = new BigDecimal("1.2");
BigDecimal fixed = original.setScale(2);

System.out.println(original); // 1.2
System.out.println(fixed);    // 1.20
~~~

Because only zeros are added, the mathematical value does not change and no rounding is needed.

Similarly:

~~~java
BigDecimal twoPlaces = new BigDecimal("1.20");
BigDecimal threePlaces = twoPlaces.setScale(3);

System.out.println(threePlaces); // 1.200
~~~

When **reducing scale**, non-zero digits may need to be dropped. If calling `setScale(int)` without specifying a rounding mode and the operation cannot be exact, Java throws `ArithmeticException`:

~~~java
BigDecimal value = new BigDecimal("1.234");

// value.setScale(2); // ArithmeticException: non-zero digits must be dropped.
~~~

If business rules permit rounding, specify the mode explicitly:

~~~java
BigDecimal rounded = value.setScale(2, RoundingMode.HALF_UP);
System.out.println(rounded); // 1.23
~~~

This snippet requires importing `java.math.RoundingMode`. `setScale` does not turn the result into a `double`; the result remains a BigDecimal capable of keeping the exact trailing zeros for the desired scale.

## 7. Rounding Is Not Just Adding Zeros

Two cases need to be separated:

| Operation | Before value | Target scale | Result | Rounds value? |
| --- | --- | ---: | --- | --- |
| Increase scale | `1.2` | 2 | `1.20` | No |
| Increase scale | `1.20` | 3 | `1.200` | No |
| Reduce scale when dropped digits are all 0 | `1.200` | 2 | `1.20` | No |
| Reduce scale when non-zero digits must be dropped | `1.235` | 2 with `HALF_UP` | `1.24` | Yes |
| Reduce scale, exactness required | `1.235` | 2 with `UNNECESSARY` | Exception | Rounding not accepted |

~~~java
BigDecimal a = new BigDecimal("1.200");
BigDecimal b = new BigDecimal("1.235");

System.out.println(a.setScale(2, RoundingMode.UNNECESSARY)); // 1.20
System.out.println(b.setScale(2, RoundingMode.HALF_UP));     // 1.24
~~~

**Recommendation:** if input requirements allow no more than two significant decimal places, use `setScale(2, RoundingMode.UNNECESSARY)` or check scale/grammar per rules. If the original digit count (including zeros) must be preserved, do not use `setScale(2)` unconditionally because doing so can erase resolution information.

For example, reducing `1.200` to `1.20` does not change the mathematical value, yet **it has changed the original representation**.

## 8. stripTrailingZeros: Useful for Normalization, Unsuitable When Representation Must Be Kept

`stripTrailingZeros()` produces a value-equivalent representation while dropping redundant trailing zeros in base 10.

~~~java
BigDecimal original = new BigDecimal("1.2000");
BigDecimal stripped = original.stripTrailingZeros();

System.out.println(original); // 1.2000
System.out.println(stripped); // 1.2
~~~

The result has the same arithmetic value, yet the new scale may be smaller. If trailing zeros represent reporting standards, **do not call this method before storing or outputting data**.

### The Case of 1000.00: May Switch to Scientific Notation

~~~java
BigDecimal original = new BigDecimal("1000.00");
BigDecimal stripped = original.stripTrailingZeros();

System.out.println(original);                 // 1000.00
System.out.println(stripped);                 // 1E+3
System.out.println(stripped.scale());         // -3
System.out.println(stripped.toPlainString()); // 1000
~~~

This is an important result: removing trailing zeros **does not necessarily** produce a string that looks like the original text only shorter. `BigDecimal` allows negative scales, and `toString()` may use exponent notation.

### Zero Can Also Lose Scale

~~~java
BigDecimal measuredZero = new BigDecimal("0.000");
BigDecimal strippedZero = measuredZero.stripTrailingZeros();

System.out.println(measuredZero);       // 0.000
System.out.println(strippedZero);       // 0
System.out.println(strippedZero.scale()); // 0
~~~

For a measurement recorded to three decimal places, `0.000` and `0` have the same mathematical value but not the same display information. Hence, do not normalize every BigDecimal with `stripTrailingZeros()` if business logic depends on scale.

## 9. toString, toPlainString, and toEngineeringString

The same BigDecimal can be represented in different text formats.

- `toString()` generates a representation per standard API rules and may use scientific notation depending on scale and adjusted exponent.
- `toPlainString()` outputs decimal form without using exponent notation.
- `toEngineeringString()`, when exponent notation is needed, uses exponents that are multiples of 3, suited to certain engineering contexts.

Safe example:

~~~java
BigDecimal thousand = new BigDecimal("1000.00")
        .stripTrailingZeros();

System.out.println(thousand.toString());      // 1E+3
System.out.println(thousand.toPlainString()); // 1000
~~~

**Do not assume `toPlainString()` recovers stripped trailing zeros.** It only changes how the **current BigDecimal** is printed. Once `stripTrailingZeros()` has been called, the string `"1000.00"` cannot be restored merely via `toPlainString()`.

Conversely, for a BigDecimal holding a normal positive scale like `new BigDecimal("1.20")`, both `toString()` and `toPlainString()` return `"1.20"`.

**Resource warning:** for numbers with a very large absolute scale, `toPlainString()` can produce a huge string. Do not use it indiscriminately on unbounded-size data.

## 10. How Do Operations Affect Scale?

`BigDecimal` has its own rules for result scale. Therefore, even if **inputs preserve trailing zeros**, the result after a calculation may have a different scale.

### Addition/Subtraction: Usually Picks the Larger Scale

For exact addition or subtraction without rounding `MathContext`, the preferred scale is:

\[
\text{scale(result)}=\max(\text{scale}(a),\text{scale}(b)).
\]

~~~java
BigDecimal a = new BigDecimal("1.20");
BigDecimal b = new BigDecimal("2.30");

System.out.println(a.add(b));      // 3.50
System.out.println(a.subtract(b)); // -1.10
~~~

Trailing zeros in the result are preserved to match the largest scale of the two numbers.

### Multiplication: Scales Usually Add Up

For exact multiplication:

\[
\text{scale(result)}=\text{scale}(a)+\text{scale}(b)
\]

~~~java
BigDecimal length = new BigDecimal("1.20");
BigDecimal factor = new BigDecimal("2.0");

System.out.println(length.multiply(factor)); // 2.400
~~~

The numeric value is 2.4, yet the resulting scale is 3, because `2 + 1 = 3`. However, **do not automatically infer that the result scale is the actual physical accuracy of a measurement**. In metrology, multiplication usually follows its own significant-figure rules and requires knowing input uncertainty.

### Division: Has More Cases

`divide(BigDecimal divisor)` does not automatically round when the decimal result is infinite. It returns the exact result if a finite representation exists, or throws `ArithmeticException` if it cannot be represented exactly.

~~~java
BigDecimal amount = new BigDecimal("1.20");

System.out.println(amount.divide(new BigDecimal("2"))); // 0.60
// amount.divide(new BigDecimal("7")); // ArithmeticException
~~~

For exact division, the preferred scale starts from `scale(a) - scale(b)`, though scale adjustments may be needed to express the exact result. When choosing an overload taking scale and `RoundingMode` or `MathContext`, scale/precision rules depend on the overload and rounding.

### Do Not Rely on Natural Scale to Determine Output Digit Count

After operations, if the contract requires **always two decimal places**, apply an explicit policy at the data boundary:

~~~java
BigDecimal result = new BigDecimal("1.20")
        .multiply(new BigDecimal("2.0"));

System.out.println(result); // 2.400

BigDecimal displayed = result.setScale(2, RoundingMode.UNNECESSARY);
System.out.println(displayed); // 2.40
~~~

This is a case of dropping one zero digit without rounding the value. If the result had non-zero digits past two decimal places, `UNNECESSARY` would reject it, helping detect violated data rules.

## 11. Complete Java 17+ Program

Create file `BigDecimalTrailingZerosDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.HashMap;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

public class BigDecimalTrailingZerosDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("1.20");
        BigDecimal b = new BigDecimal("1.2");

        System.out.println("a=" + a
                + " scale=" + a.scale()
                + " precision=" + a.precision());
        System.out.println("b=" + b
                + " scale=" + b.scale()
                + " precision=" + b.precision());
        System.out.println("unscaled=" + a.unscaledValue());
        System.out.println("numeric equal=" + (a.compareTo(b) == 0));
        System.out.println("object equal=" + a.equals(b));

        System.out.println("scale up=" + b.setScale(2));
        System.out.println("trim=" + a.stripTrailingZeros());
        System.out.println("sum=" + a.add(new BigDecimal("2.30")));
        System.out.println("product=" + a.multiply(new BigDecimal("2.0")));
        System.out.println("quotient=" + a.divide(new BigDecimal("2")));

        BigDecimal thousand = new BigDecimal("1000.00")
                .stripTrailingZeros();
        System.out.println("thousands=" + thousand
                + " scale=" + thousand.scale()
                + " plain=" + thousand.toPlainString());

        BigDecimal zero = new BigDecimal("0.000")
                .stripTrailingZeros();
        System.out.println("zero=" + zero + " scale=" + zero.scale());

        BigDecimal rounded = new BigDecimal("1.235")
                .setScale(2, RoundingMode.HALF_UP);
        System.out.println("rounded=" + rounded);

        System.out.println("from double=" + BigDecimal.valueOf(1.20));
        System.out.println("negative zero=" + new BigDecimal("-0.00"));

        Map<BigDecimal, String> map = new HashMap<>();
        map.put(a, "two places");
        System.out.println("hash map same scale=" + map.get(a));
        System.out.println("hash map different scale=" + map.get(b));

        Set<BigDecimal> set = new TreeSet<>();
        set.add(a);
        set.add(b);
        System.out.println("tree set size=" + set.size());
    }
}
~~~

Run with JDK 17 or higher:

~~~bash
javac --release 17 BigDecimalTrailingZerosDemo.java
java BigDecimalTrailingZerosDemo
~~~

Stdout (verified operations against the JDK):

~~~text
a=1.20 scale=2 precision=3
b=1.2 scale=1 precision=2
unscaled=120
numeric equal=true
object equal=false
scale up=1.20
trim=1.2
sum=3.50
product=2.400
quotient=0.60
thousands=1E+3 scale=-3 plain=1000
zero=0 scale=0
rounded=1.24
from double=1.2
negative zero=0.00
hash map same scale=two places
hash map different scale=null
tree set size=1
~~~

Explanation:

1. The two numbers have the same value yet different `scale` and `precision`; `compareTo` returns 0, while `equals` returns false.
2. `setScale(2)` adds a 0 digit without changing value; `stripTrailingZeros` drops the trailing 0.
3. Exact addition/multiplication/division preserve scale per BigDecimal arithmetic rules, not per a universal display standard.
4. `1000.00` after stripping becomes a number with negative scale, printing as `1E+3` yet `toPlainString` is `1000`.
5. `0.000` after stripping becomes `0` with scale 0; the original representation is gone.
6. `HALF_UP` at `1.235` to two digits produces `1.24`.
7. `BigDecimal.valueOf(1.20)` cannot know the source literal had an extra zero written.
8. `BigDecimal("-0.00")` represents zero with scale 2; the minus sign of zero **is not preserved** as a BigDecimal value property.
9. `HashMap` and `TreeSet` can treat two representations of the same number as different or identical under different equality/ordering contracts.

## 12. Signed Zero and Trailing Zeros Are Two Different Concepts

`BigDecimal` stores integer values without a separate signed zero form like `double`. Therefore:

~~~java
BigDecimal negativeZero = new BigDecimal("-0.00");
BigDecimal positiveZero = new BigDecimal("0.00");

System.out.println(negativeZero);                    // 0.00
System.out.println(negativeZero.equals(positiveZero)); // true
~~~

**Scale is still preserved**, yet the minus sign of zero in the **original text** is no longer an arithmetic property of BigDecimal. If a scientific application genuinely needs to know the user entered `"-0.00"` instead of `"0.00"`, store the original text or separate metadata.

Do not confuse this with `-0.0` of IEEE 754 binary floating point, which has a sign bit. `BigDecimal` does not use the binary64 floating-point value model to store a zero sign.

## 13. Input Policy: Keep Original Scale or Normalize?

You must define the requirements before writing a parser.

**Option A — keep original scale:** use `new BigDecimal(text)` and keep the object without stripping. Suitable when the number of digits after the decimal point is part of the information to store.

**Option B — normalize everything to 2 digits:** use `setScale(2, mode)`, optionally choosing `RoundingMode.UNNECESSARY` to reject data that cannot be represented exactly with two digits.

**Option C — keep only mathematical value:** use numeric comparison or intentional normalization; do not promise to restore the input string.

A validation method following the policy **two digits allowing trailing zero padding but no rounding**:

~~~java
static BigDecimal requireTwoDecimalPlaces(String input) {
    if (input == null) {
        throw new IllegalArgumentException("Missing amount");
    }

    final BigDecimal value;
    try {
        value = new BigDecimal(input);
    } catch (NumberFormatException ex) {
        throw new IllegalArgumentException("Malformed decimal amount", ex);
    }

    try {
        return value.setScale(2, RoundingMode.UNNECESSARY);
    } catch (ArithmeticException ex) {
        throw new IllegalArgumentException("More than two significant fractional digits", ex);
    }
}
~~~

This is a method placed inside a class importing `BigDecimal` and `RoundingMode`. It accepts `"1.2"` and turns it into `1.20`, accepts `"1.200"` and returns `1.20`, yet rejects `"1.234"`. It **does not preserve the exact original zero count**; it only ensures the result has scale = 2.

If the contract demands that **input must be written with exactly two digits after the dot**, even `"1.2"` must be rejected by an **original grammar/scale** check before normalization. These are two different requirements.

## 14. Checking Input Scale When Trailing Zeros Must Be Significant

If the input rule says "must be exactly 2 decimal digits", you can check the scale of the BigDecimal parsed from the string:

~~~java
BigDecimal amount = new BigDecimal("1.20");

if (amount.scale() != 2) {
    throw new IllegalArgumentException("Expected scale 2");
}
~~~

However, checking scale **does not replace checking original syntax**:

- `new BigDecimal("1.20")` has scale 2.
- `new BigDecimal("1.2E+0")` has scale 1.
- `new BigDecimal("120E-2")` has scale 2 and the same value 1.20, yet is written differently from `"1.20"`.
- `new BigDecimal("001.20")` has the same value and scale as `"1.20"`, yet preserving leading zeros if needed is a **string** issue, not a BigDecimal one.

If the system requires a **single canonical string form**, validate raw input against an explicitly defined grammar (e.g., no exponent, `.` as decimal point, exactly two fractional digits), then parse into BigDecimal. If the exact user-entered characters must be preserved, store the raw input as well.

**Do not infer that scale is a reliable measure of measurement uncertainty.** When information about error bounds, measurement significant figures, or resolution is needed, express them explicitly in the domain model.

## 15. Display Formatting Differs from Changing Data

If internal data is stored as `BigDecimal("1.2")` while the screen must display `"1.20"`, there are two approaches:

1. **Normalize the output value:** `value.setScale(2, RoundingMode.UNNECESSARY).toPlainString()`, when policy requires exactly 2 digits and forbids rounding.
2. **Format with a formatter:** use `NumberFormat`/`DecimalFormat` with locale and fixed fraction digits if regional display is needed.

~~~java
BigDecimal value = new BigDecimal("1.2");
String output = value.setScale(2, RoundingMode.UNNECESSARY)
        .toPlainString();

System.out.println(output); // 1.20
~~~

Do not confuse `toString()` / `toPlainString()` with locale-aware formatters. They use Java decimal number syntax and do not automatically replace the decimal point with a comma for Vietnamese/German.

When formatting currency by locale, `NumberFormat.getCurrencyInstance(locale)` may apply grouping, currency symbols, and the currency's fractional digit rules. Using a formatter can **differ from preserving original input representation**; choose according to the goal.

### Do Not "Preserve Zeros" Using String.format on double

~~~java
// This only produces a formatted string, without preserving original scale:
String display = String.format(java.util.Locale.US, "%.2f", 1.2);
System.out.println(display); // 1.20
~~~

This line allows displaying two digits after the decimal point, yet the original value is `double` and stores no information about how many digits were entered. If scale must be preserved across multiple business steps, use BigDecimal or corresponding metadata.

## 16. JSON, Database, CSV: Where Do Trailing Zeros Get Lost?

Holding BigDecimal in RAM does not guarantee **every data transfer step** will preserve scale.

### JSON

A JSON number can be written like:

~~~json
{"amount": 1.20}
~~~

However, many parsers/serializers treat the number field as a **numeric value** and may convert it through floating point, normalize it, or output `1.2`. JSON does not require every piece of software to preserve the exact original lexical representation of a number.

If formatting carries mandatory meaning, you can design the API to store decimals as **strings**:

~~~json
{"amount": "1.20"}
~~~

Document clearly in the schema/API that this field is a validated decimal string, rather than arbitrarily turning numbers into text across different systems. If clients require JSON numbers instead of strings, test the specific serializer with `BigDecimal` and explicitly define round-trip guarantees regarding scale.

### JDBC and DECIMAL Columns

When using `DECIMAL(p, s)` or `NUMERIC(p, s)` in a database, the column may have a configured scale. The DBMS, JDBC driver, and ORM mapping may **normalize the value to the column's scale** or apply other storage rules.

- Writing `1.2` into a scale-2 column may read back as `1.20`.
- Writing `1.200` into a scale-2 column may be normalized/adjusted according to DBMS rules.
- If you need to preserve an **originally entered scale that varies per record**, a fixed-scale decimal column may not suffice; consider storing metadata or the original text.

Do not claim every database automatically preserves verbatim trailing zeros. You must verify the schema, driver, read-back data, and business requirements.

### CSV and Text Files

With CSV, if the writer outputs `BigDecimal.toPlainString()` from an object still holding the appropriate scale, the string `1.20` can be preserved. However, if the import step parsed into `double` and then constructed BigDecimal from that value, trailing zero information may already have vanished.

**Round-trip rule:** verify scale state at each boundary — input → parse → calculation → storage → read → serialize → display.

## 17. Function to Output Exact Value with Fixed Scale

An easily testable helper for decimal results with exact scale:

~~~java
static String toFixedScale(BigDecimal value, int scale) {
    if (value == null || scale < 0) {
        throw new IllegalArgumentException("Invalid value or scale");
    }
    return value.setScale(scale, RoundingMode.UNNECESSARY)
            .toPlainString();
}
~~~

Example:

~~~java
System.out.println(toFixedScale(new BigDecimal("10"), 2));    // 10.00
System.out.println(toFixedScale(new BigDecimal("10.50"), 2)); // 10.50
// toFixedScale(new BigDecimal("10.501"), 2); // ArithmeticException
~~~

**Limits:** the scale parameter and output size must fit within the application's budget. `setScale(1_000_000)` can create a huge value/string or consume heavy resources, even though the numeric value does not change. Intentionally allowing only non-negative scales is a **policy of the helper**, not a limitation of BigDecimal, which permits negative scales.

If rounding values is permitted, you can use a helper overload accepting `RoundingMode`. However, document the policy explicitly, because `HALF_EVEN`, `HALF_UP`, `DOWN`, etc. yield different results at midpoints.

## 18. Normalization for Comparison and Canonicalization

Some systems want to treat `1.20`, `1.200`, and `1.2` as a single value for keying or comparison. When **scale is not part of the business key**, you can use:

~~~java
BigDecimal canonical = new BigDecimal("1.200")
        .stripTrailingZeros();
System.out.println(canonical); // 1.2
~~~

Remember, though, that `1000.00` after stripping can become `1E+3`. When building a textual canonical key, consider `stripTrailingZeros().toPlainString()`, along with a length budget and a specific rule for zero.

If the system needs to distinguish the recorded level of detail, this canonicalization is **wrong**. Two records `"1.2"` and `"1.20"` must be kept distinct at the appropriate data layer.

With `HashMap<BigDecimal, ...>`, you can normalize on both write and read if lookup by numeric value is genuinely needed. With `TreeMap`/`TreeSet`, understand that `compareTo` does not distinguish scale, so the choice of collection type itself affects how elements are identified.

## 19. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Creating from `new BigDecimal(1.20)` to keep `"1.20"` | Literal is already double; trailing 0 is lost, binary error may be added | `new BigDecimal("1.20")` |
| Using `BigDecimal.valueOf(1.20)` to keep original fraction length | `Double.toString` does not store literal spelling | Parse from String |
| Calling `stripTrailingZeros` before saving every number | Loses scale, may convert to `1E+3` | Only strip when the goal is canonicalization |
| Believing `toPlainString` restores `1000.00` after stripping | Scale already changed | Keep original object or metadata |
| Using `equals` to compare **only numeric value** | `1.2` differs from `1.20` | `compareTo(b) == 0` |
| Using `TreeSet<BigDecimal>` when two scales are needed as two distinct records | `compareTo` treats values as equal | Choose key/record with explicit scale |
| Using `HashMap<BigDecimal,...>` yet querying with a different scale | `equals` differs, get may return null | Unify scale or canonical key |
| Checking only `precision()` when needing 2 fractional digits | Precision differs from scale | Check `scale()` and grammar |
| Calling `setScale(2)` on a number with non-zero fractional digits dropped | Throws `ArithmeticException` | Choose rounding policy or reject explicitly |
| Rounding at multiple steps without a policy | Results change, error accumulates | Choose explicit rounding boundaries |
| Trusting JSON numbers to always keep `1.20` | Serializer may normalize | Test round-trip or use decimal string |
| Trusting a DECIMAL column to automatically keep original input scale | DB schema may fix scale | Store scale/raw input separately when needed |
| Thinking trailing zeros alone prove measurement error bounds | Missing uncertainty/unit metadata | Store resolution, error, and unit separately |
| Trusting `BigDecimal("-0.00")` to keep the minus sign | BigDecimal represents zero without a separate negative sign | Keep raw text if needed |
| Using `toPlainString` with unbounded scale | Can produce huge output | Limit scale and string size |

## 20. Self-Check Questions

**1.** What are `new BigDecimal("1.20").scale()` and `precision()`?

**Answer:** Scale 2, precision 3; unscaled value is 120.

**2.** Is `new BigDecimal("1.20").equals(new BigDecimal("1.2"))` true?

**Answer:** No, because scales differ. Their `compareTo()` returns 0 because they share the same mathematical value.

**3.** Why might `stripTrailingZeros()` be unsuitable for measurement data recorded as `"0.000"`?

**Answer:** It creates an equivalent BigDecimal with zero at scale 0 and prints as `"0"`, losing the resolution expressed in the original representation.

**4.** What can `new BigDecimal("1000.00").stripTrailingZeros().toString()` display?

**Answer:** `1E+3`. After stripping, scale is −3; `toPlainString()` is `"1000"`, not `"1000.00"`.

**5.** What does `new BigDecimal("1.20").multiply(new BigDecimal("2.0"))` print?

**Answer:** `2.400` because the result scale of exact multiplication is the sum of scales 2+1 = 3.

**6.** To output `1.2` as a string with exactly two digits after the decimal point without rounding the value, what should be used?

**Answer:** `new BigDecimal("1.2").setScale(2, RoundingMode.UNNECESSARY).toPlainString()` → `"1.20"`.

**7.** If required to store *every exact character* of `"+001.20"`, is BigDecimal sufficient?

**Answer:** No. BigDecimal retains the decimal value along with scale, not every lexical character like a plus sign or leading zeros. Original text must also be stored.

**8.** Why does `new BigDecimal("1.235").setScale(2, RoundingMode.UNNECESSARY)` fail?

**Answer:** Dropping the non-zero digit 5 would change the value. `UNNECESSARY` requires the scale change to be exact; if rounding is needed, choose a business-approved `RoundingMode`.

## 21. Summary and References

- `BigDecimal` represents numbers using **unscaled value × 10^(-scale)**. **Scale** helps preserve trailing zeros after the decimal point when created directly from a string.
- **Equal arithmetic values** do not imply `equals()` equality: `compareTo() == 0` compares only value; `equals()` also considers scale.
- `setScale()` can **add zeros**, **remove zeros**, or **round**, depending on target scale and rounding mode.
- **`stripTrailingZeros()` actively discards representation information**: `1.200 → 1.2`, `1000.00 → 1E+3`, and `0.000 → 0`.
- Addition, multiplication, and division have scale rules; **output should have an explicit format/scale policy** if consistency is required.
- **Do not pass through double** to keep trailing zeros of decimal data. If every original character or measurement uncertainty must be kept, store metadata/source text alongside BigDecimal.
- Verify round-trips across JSON, database, CSV, and formatters when scale carries business meaning.

Official documentation (Java 17):

- [BigDecimal API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): `scale()`, `unscaledValue()`, `precision()`, `equals()`, `compareTo()`, `setScale()`, `stripTrailingZeros()`, `toString()`, and `toPlainString()`.
- [RoundingMode API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html): choosing decimal rounding rules.
- [BigDecimal — preferred scales for operations](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): scale rules for exact addition, subtraction, multiplication, and division.
- [NumberFormat API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html): locale-based display, limiting fractional digits.