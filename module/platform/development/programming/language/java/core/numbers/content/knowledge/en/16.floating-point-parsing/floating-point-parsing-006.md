# Decimal Strings to `BigDecimal` to Preserve Decimal Meaning in Java

## 1. Why parse decimal strings with `BigDecimal`?

When a user enters `"0.1"`, the initial data is **a string representing one-tenth in base ten**. If a programmer converts that string to `double`, the stored value is usually only **the closest representable binary number**, not mathematically exact one-tenth.

Java offers two very different approaches:

~~~java
double binary = Double.parseDouble("0.1");
BigDecimal decimal = new BigDecimal("0.1");
~~~

This is an illustrative snippet; `import java.math.BigDecimal;` is needed when placed in a class.

- `binary` is the `double` value closest to `0.1` under binary64 rules.
- `decimal` is the **exact** decimal value `0.1`: the unscaled integer is 1 and `scale` is 1, equivalent to `1 × 10^-1`.

`BigDecimal` is especially useful for data that carries **decimal meaning from its source**: unit prices, monetary amounts, taxes, business rates, CSV/JSON exports containing decimal numbers, or requirements for exact digit-level comparison and auditing.

**Core rule:** If the source is a decimal string, construct it directly with **`new BigDecimal(text)`**. Do not force data through `double` when you need to preserve the original decimal meaning.

~~~java
BigDecimal sum = new BigDecimal("0.1")
        .add(new BigDecimal("0.2"));
// sum.toString() equals "0.3"
~~~

Addition here preserves exact decimal values because both inputs were parsed directly without intermediate binary rounding error. However, understand clearly that `BigDecimal` **does not automatically make every division finite**, nor can it restore a decimal value that was already altered earlier.

## 2. How does `BigDecimal` store numbers?

`java.math.BigDecimal` is an **immutable** class representing decimal numbers with arbitrary precision within resource limits and API constraints.

A `BigDecimal`'s value can be understood as:

\[
\text{value} = \text{unscaledValue} \times 10^{-\text{scale}}
\]

Where:

- `unscaledValue()` is a `BigInteger` holding all digits of the coefficient.
- `scale()` is an integer indicating **the number of digits to the right of the decimal point** when positive; `scale` can also be 0 or negative.
- `precision()` is **the number of significant decimal digits of the unscaled coefficient** as defined by `BigDecimal`, not the number of digits after the decimal point.

Examples:

| Input string | Decimal value | `unscaledValue()` | `scale()` | `precision()` |
|---|---:|---:|---:|---:|
| `"123.45"` | 123.45 | 12345 | 2 | 5 |
| `"0.1"` | 0.1 | 1 | 1 | 1 |
| `"1.20"` | 1.20 | 120 | 2 | 3 |
| `"1000"` | 1000 | 1000 | 0 | 4 |
| `"1E+3"` | 1000 | 1 | -3 | 1 |
| `"0.00"` | 0.00 | 0 | 2 | 1 |

**Important example:** `new BigDecimal("1.20")` and `new BigDecimal("1.2")` have the same **mathematical value 1.2**, yet have **different scales** (2 and 1), so they can differ in formatting and object equality.

`BigDecimal` is not an IEEE 754 floating-point type like `double`. It is based on an integer coefficient and powers of 10, so it can represent exactly many finite decimal fractions that binary64 cannot.

## 3. Three ways to construct from data — different outcomes

### 3.1. `new BigDecimal(String)`: the right way for decimal digit sources

~~~java
BigDecimal a = new BigDecimal("0.1");
BigDecimal b = new BigDecimal("12.3400");
BigDecimal c = new BigDecimal("-7.25");
~~~

Strings are parsed directly according to the decimal syntax supported by `BigDecimal`. `b` keeps a scale of 4, so `b.toString()` normally prints `12.3400`; the object does not arbitrarily drop trailing zeros.

### 3.2. `new BigDecimal(double)`: preserves the **exact existing binary value**

~~~java
BigDecimal fromBinary = new BigDecimal(0.1);
~~~

`double` holds a binary value close to 0.1 yet **not equal to** mathematical 0.1. The `double` constructor converts **the currently stored double value** into a `BigDecimal` exact for *that double*, exposing the binary discrepancy:

~~~text
0.1000000000000000055511151231257827021181583404541015625
~~~

This is not a `BigDecimal` bug. The data was already approximated when creating the `double`.

### 3.3. `BigDecimal.valueOf(double)`: based on the decimal representation of `double`

~~~java
BigDecimal fromValueOf = BigDecimal.valueOf(0.1);
~~~

`valueOf(double)` uses the string decimal representation produced by `Double.toString(double)` and converts it to `BigDecimal`. Since `Double.toString(0.1)` is `"0.1"`, the result in this example has `toString()` equal to `"0.1"`.

**However, `BigDecimal.valueOf(double)` cannot recover the original decimal data** if operations using `double` have already altered the value:

~~~java
double sum = 0.1 + 0.2;
BigDecimal afterDouble = BigDecimal.valueOf(sum);
// afterDouble is 0.30000000000000004, not exact 0.3
~~~

Remember the rule:

- **Source is a decimal `String`:** use `new BigDecimal(text)`.
- **Source is genuinely already a `double`:** understand the data already contains rounding/error; `valueOf(double)` usually creates a readable decimal form, yet does not undo arithmetic history.
- **`new BigDecimal(double)`:** choose only when you truly need to convert the exact **current binary64 value** to decimal, not because you want to "avoid error."

## 4. Standalone Java 17+ example: comparing the three construction methods

Create the file `DecimalConstructionDemo.java`:

~~~java
import java.math.BigDecimal;

public class DecimalConstructionDemo {
    public static void main(String[] args) {
        String source = "0.1";

        BigDecimal exact = new BigDecimal(source);
        BigDecimal fromDouble =
                new BigDecimal(Double.parseDouble(source));
        BigDecimal viaValueOf =
                BigDecimal.valueOf(Double.parseDouble(source));

        System.out.println("text=" + exact);
        System.out.println("doubleConstructor=" + fromDouble);
        System.out.println("valueOfDouble=" + viaValueOf);
        System.out.println("binarySum=" + (0.1 + 0.2));
        System.out.println("decimalSum="
                + new BigDecimal("0.1").add(new BigDecimal("0.2")));
        System.out.println("valueOfBinarySum="
                + BigDecimal.valueOf(0.1 + 0.2));
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac DecimalConstructionDemo.java
java DecimalConstructionDemo
~~~

Output:

~~~text
text=0.1
doubleConstructor=0.1000000000000000055511151231257827021181583404541015625
valueOfDouble=0.1
binarySum=0.30000000000000004
decimalSum=0.3
valueOfBinarySum=0.30000000000000004
~~~

The `decimalSum` line is the example that preserves **the decimal meaning of the two original strings**. The `valueOfBinarySum` line merely takes the string representation of **an already-computed double result**; it cannot fix the error of the addition performed earlier.

## 5. Valid string syntax for `BigDecimal`

`new BigDecimal(String)` accepts decimal number text conforming to `BigDecimal`'s grammar, including an optional sign, decimal point, and `e`/`E` exponent notation.

Valid examples:

~~~java
new BigDecimal("42");        // 42
new BigDecimal("+42.00");    // 42.00
new BigDecimal("-0.125");    // -0.125
new BigDecimal(".5");        // 0.5
new BigDecimal("5.");        // 5
new BigDecimal("1.23E+4");   // 12300
new BigDecimal("1e-3");     // 0.001
~~~

These are illustrative calls. The forms above can have different **scales**; for instance, `"1.23E+4"` has unscaled value 123 and scale -2, value 12300.

**Do not confuse** the runtime parser with Java literal expressions. The following forms are format errors if passed directly to `new BigDecimal(text)`:

- `"1_000.50"`: underscores are valid in some Java literals, **not** decimal digits in a parsed string.
- `"1,234.50"` or `"1.234,50"`: grouping separators or locale decimal commas **are not understood automatically** by this constructor.
- `" 12.34 "`: leading/trailing whitespace is not trimmed automatically.
- `""`, `"+"`, `"."`: no valid digit sequence.
- `"NaN"`, `"Infinity"`: not decimal values that `BigDecimal` can represent.
- `"0x1.8p2"`: not decimal syntax for this constructor.

Invalid strings typically lead to `NumberFormatException`. If the source may be `null`, check for `null` separately before parsing; do not treat it as equivalent to `"0"`.

### Can you use `trim()`?

If the data contract allows leading/trailing whitespace, you **can intentionally** call `text.trim()` or `strip()` before parsing. However, that is a **data normalization decision**. In systems requiring strict formatting (transaction codes, finance, digital signatures), you should reject malformed inputs rather than silently altering them.

Localized display strings need a separate handling step: explicitly specify the decimal point, thousands separator, digit grouping, and validation method. Do not arbitrarily replace every `,` with `.` because `"1,234"` can mean 1234 or 1.234 depending on locale.

## 6. Java 17+ example: parsing and reporting errors clearly

Create the file `DecimalInputValidationDemo.java`:

~~~java
import java.math.BigDecimal;

public class DecimalInputValidationDemo {
    static void parse(String input) {
        try {
            BigDecimal value = new BigDecimal(input);
            System.out.println("ok[" + input + "]="
                    + value.toPlainString());
        } catch (NumberFormatException ex) {
            System.out.println("bad[" + input + "]");
        }
    }

    public static void main(String[] args) {
        parse("42");
        parse("+42.00");
        parse("1.23E+4");
        parse("0.001");
        parse("1_000.50");
        parse("1,234.50");
        parse(" 12.34 ");
        parse("NaN");
        parse("");
    }
}
~~~

~~~bash
javac DecimalInputValidationDemo.java
java DecimalInputValidationDemo
~~~

Output:

~~~text
ok[42]=42
ok[+42.00]=42.00
ok[1.23E+4]=12300
ok[0.001]=0.001
bad[1_000.50]
bad[1,234.50]
bad[ 12.34 ]
bad[NaN]
bad[]
~~~

The `parse` method uses sample data so the input is always a non-`null` string. When handling external data, check `null` first and enforce length/digit-count/exponent limits appropriate to system requirements. `BigDecimal` is not constrained to 53-bit precision like `double`, yet still has **resource limits, an `int` range for scale, and computational length limits**.

When reporting input errors, state clearly which field failed and which format is allowed; do not mask errors with `catch (Exception)` and return a default 0.

## 7. From parsed strings to exact decimal arithmetic

`BigDecimal` supports operations via **methods** rather than using operators `+`, `-`, `*`, `/` directly on objects:

| Operation | `BigDecimal` example | Meaning |
|---|---|---|
| Addition | `a.add(b)` | Decimal sum |
| Subtraction | `a.subtract(b)` | Decimal difference |
| Multiplication | `a.multiply(b)` | Decimal product |
| Division | `a.divide(b)` | Exact quotient **only when representable as a finite decimal** if no rounding is specified |
| Numeric comparison | `a.compareTo(b)` | Compares **numeric value** |
| Negation | `a.negate()` | Additive inverse |
| Set scale | `a.setScale(2, RoundingMode.HALF_UP)` | Chooses digits after the decimal point with a rounding rule |

Methods such as `add`, `subtract`, and `multiply` **without a precision-limiting `MathContext`** produce exact decimal results within practical and API limits. If you supply a `MathContext` or call `setScale` with a rounding mode, the result **may be rounded according to the chosen policy**.

### Why can't you use operators directly?

~~~java
BigDecimal a = new BigDecimal("0.1");
BigDecimal b = new BigDecimal("0.2");
// BigDecimal wrong = a + b; // Compile error: no + operator for BigDecimal
BigDecimal right = a.add(b);
~~~

This is an illustrative snippet. `BigDecimal` is a class, not a primitive numeric type. A common pitfall is the `+` operator with `String` performing string concatenation, which is **not numeric addition**.

### `BigDecimal` is immutable

~~~java
BigDecimal total = new BigDecimal("1.20");
total.add(new BigDecimal("0.30"));  // Does not modify total!
total = total.add(new BigDecimal("0.30")); // total becomes 1.50
~~~

Every operation returns **a result object**. Forgetting to reassign is a common logic bug: a standalone `total.add(...)` statement does not change the `total` variable.

## 8. Division and rounding rules: a distinct concern with `BigDecimal`

The result of `1 ÷ 3` is a non-terminating repeating decimal. No finite `BigDecimal` exists that represents that entire quotient exactly. Therefore:

~~~java
BigDecimal one = new BigDecimal("1");
BigDecimal three = new BigDecimal("3");
// one.divide(three); // Throws ArithmeticException because expansion does not terminate.
~~~

To obtain a practical result, specify scale and `RoundingMode`:

~~~java
BigDecimal quotient = one.divide(three, 4, RoundingMode.HALF_UP);
// quotient = 0.3333
~~~

This is an illustrative snippet; `import java.math.RoundingMode;` is required.

**Crucial distinction:**

- **String parsing**: `new BigDecimal("0.1")` keeps the exact number the string represents.
- **Unbounded-precision add/subtract/multiply**: preserves the exact mathematical decimal value when representable.
- **Non-terminating division**: requires choosing rounding/precision or letting the API throw an error.
- **Business rounding**: requires explicit `scale`, `precision`, and `RoundingMode` policies; "using BigDecimal" **does not decide that policy on its own**.

### `setScale` and `MathContext` are not the same

- `setScale(2, HALF_UP)` sets **two digits after the decimal point**, which may round the value.
- `MathContext(4, HALF_UP)` limits to **4 significant digits of the entire coefficient**, which does not mean 4 digits after the decimal point.
- `RoundingMode.UNNECESSARY` asserts that no rounding is needed; if the operation would have to drop nonzero digits, it throws `ArithmeticException`.

Example with `"123.456"`:
- `setScale(2, HALF_UP)` gives `123.46`.
- `round(new MathContext(4, HALF_UP))` gives `123.5`.

Which rule is right depends on the business domain. For monetary amounts, teams normally standardize currency units, decimal places, tax/fee rounding mechanisms, and when rounding is applied.

## 9. Java 17+ example: addition, multiplication, division, and rounding

Create the file `DecimalArithmeticDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class DecimalArithmeticDemo {
    public static void main(String[] args) {
        BigDecimal price = new BigDecimal("19.95");
        BigDecimal quantity = new BigDecimal("3");
        BigDecimal total = price.multiply(quantity);

        System.out.println("total=" + total);
        System.out.println("sum="
                + new BigDecimal("0.1").add(new BigDecimal("0.2")));
        System.out.println("exactDivision="
                + new BigDecimal("1").divide(new BigDecimal("4")));
        System.out.println("roundedDivision="
                + new BigDecimal("1").divide(
                        new BigDecimal("3"), 4, RoundingMode.HALF_UP));

        BigDecimal sample = new BigDecimal("2.345");
        System.out.println("halfUp="
                + sample.setScale(2, RoundingMode.HALF_UP));
        System.out.println("halfEven="
                + sample.setScale(2, RoundingMode.HALF_EVEN));
        System.out.println("signAware="
                + new BigDecimal("-2.345").setScale(
                        2, RoundingMode.HALF_UP));

        BigDecimal precise = new BigDecimal("123.456");
        System.out.println("scale2="
                + precise.setScale(2, RoundingMode.HALF_UP));
        System.out.println("precision4="
                + precise.round(new MathContext(
                        4, RoundingMode.HALF_UP)));
    }
}
~~~

~~~bash
javac DecimalArithmeticDemo.java
java DecimalArithmeticDemo
~~~

Output:

~~~text
total=59.85
sum=0.3
exactDivision=0.25
roundedDivision=0.3333
halfUp=2.35
halfEven=2.34
signAware=-2.35
scale2=123.46
precision4=123.5
~~~

The `halfUp` and `halfEven` lines differ because of how ties halfway between two choices are handled. For `2.345` at scale 2, `HALF_UP` yields `2.35`, while `HALF_EVEN` yields `2.34` because the last digit of `2.34` is even.

**Do not assume "round to two decimal places" always defaults to `HALF_UP`**. If a system requires `HALF_EVEN`, `DOWN`, `CEILING`, or another rule, pass the appropriate `RoundingMode`.

## 10. `equals` and `compareTo`: differences due to scale

Two `BigDecimal` objects can have **equal numeric values** yet **different scales**:

~~~java
BigDecimal a = new BigDecimal("1.20");
BigDecimal b = new BigDecimal("1.2");

a.equals(b);                // false
a.compareTo(b) == 0;        // true
~~~

`equals` considers both **unscaled value and scale**, so here it returns `false`. `compareTo` compares only **numeric value**, so it returns 0.

| Check | `"1.20"` and `"1.2"` | Meaning |
|---|---|---|
| `a.equals(b)` | `false` | Different scales (2 vs. 1) |
| `a.compareTo(b) == 0` | `true` | Same decimal magnitude |
| `a.hashCode() == b.hashCode()` | Should not rely on it | `hashCode` aligns with `equals`, not a substitute for numeric comparison |
| `a.toString().equals(b.toString())` | `false` | Different string/scale, not a numeric check |

**Consequence for data structures:** `HashSet<BigDecimal>` uses `equals`/`hashCode`, so it can keep both `1.2` and `1.20` as two distinct elements. Meanwhile `TreeSet<BigDecimal>` uses `compareTo` by default for ordering and typically treats those two values as equivalent under its comparator.

### Java 17+ example: scale, comparison, and collections

Create the file `DecimalScaleEqualityDemo.java`:

~~~java
import java.math.BigDecimal;
import java.util.HashSet;
import java.util.Set;
import java.util.TreeSet;

public class DecimalScaleEqualityDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("1.20");
        BigDecimal b = new BigDecimal("1.2");

        System.out.println("aScale=" + a.scale());
        System.out.println("bScale=" + b.scale());
        System.out.println("equals=" + a.equals(b));
        System.out.println("numericEqual=" + (a.compareTo(b) == 0));

        Set<BigDecimal> hashes = new HashSet<>();
        hashes.add(a);
        hashes.add(b);

        Set<BigDecimal> sorted = new TreeSet<>();
        sorted.add(a);
        sorted.add(b);

        System.out.println("hashSetSize=" + hashes.size());
        System.out.println("treeSetSize=" + sorted.size());

        BigDecimal original = new BigDecimal("1000.00");
        BigDecimal normalized = original.stripTrailingZeros();
        System.out.println("original=" + original);
        System.out.println("normalized=" + normalized);
        System.out.println("normalizedScale=" + normalized.scale());
        System.out.println("plain=" + normalized.toPlainString());
    }
}
~~~

~~~bash
javac DecimalScaleEqualityDemo.java
java DecimalScaleEqualityDemo
~~~

Output:

~~~text
aScale=2
bScale=1
equals=false
numericEqual=true
hashSetSize=2
treeSetSize=1
original=1000.00
normalized=1E+3
normalizedScale=-3
plain=1000
~~~

`stripTrailingZeros()` removes unnecessary trailing zeros in the coefficient and can produce a **negative scale**. Do not call it indiscriminately if the stored scale carries business meaning, such as a system required to preserve `"1.20"` exactly as entered.

## 11. `toString`, `toPlainString`, and preserving **value** vs. preserving **original spelling**

When parsing a string, `BigDecimal` retains **the decimal value and corresponding scale**, yet **does not preserve every character of the input string**.

Example:

~~~java
BigDecimal a = new BigDecimal("0001.2300");
BigDecimal b = new BigDecimal("1.23E+4");

System.out.println(a);                  // 1.2300
System.out.println(b);                  // 1.23E+4
System.out.println(b.toPlainString());  // 12300
~~~

This is illustrative. Leading zeros in `"0001.2300"` are not necessarily reproduced; exponential notation may also be normalized. `BigDecimal` is not a tool for storing **the exact character-by-character original text token**.

- `toString()` generates `BigDecimal`'s standard decimal string representation, which may use scientific notation.
- `toPlainString()` outputs **without exponent notation**. It fits some UIs/CSVs, yet can produce very long strings if scale is large.
- `toEngineeringString()` may use exponents in multiples of 3, fitting some scientific/engineering applications.
- `stripTrailingZeros()` creates a **new `BigDecimal` value** after normalizing trailing zeros; it can change the scale.

If you need to store an audit record containing the exact form the user entered such as `"+0001.2300"`, store the **validated original input string** alongside the `BigDecimal` value when original retrieval is required. Do not expect `toString()` to restore a plus sign or leading zeros.

When building a round-trip, define clearly whether "preserve" means **same numeric value**, **same scale**, or **same character string**. These three goals are not identical.

## 12. Reading external data: CSV, JSON, and localized formats

### When the source is already a String

For decimal numeric strings in JSON/CSV such as `"123.4500"`, use `new BigDecimal(text)` after validating format. Avoid converting through `Double.parseDouble` or casting to `double` in the pipeline.

Example of a pipeline that **loses decimal meaning**:

~~~java
String input = "0.1";
double intermediate = Double.parseDouble(input);
BigDecimal result = new BigDecimal(intermediate); // carries binary approximation
~~~

Pipeline preserving value from string:

~~~java
String input = "0.1";
BigDecimal result = new BigDecimal(input);
~~~

### When the source is a JSON number

Many JSON libraries let you choose the numeric type when parsing. If a library parses every decimal number into `double` first, digits may already have been lost or rounded **before** creating `BigDecimal`. For monetary or decimal data requiring exactness, configure the parser to read numeric tokens directly into `BigDecimal` or strings via the library's specific API.

You cannot assume all JSON libraries behave the same by default; check the actual version, DTO model, and parser mechanism.

### When the source is a localized number

A user may enter `"1.234,56"` or `"1,234.56"`. These are two notations that can correspond to 1234.56 in different locales. `new BigDecimal(String)` **does not automatically understand locale thousands separators or decimal commas**. If the application requires localized number entry:

1. Determine and pin the input **locale**.
2. Use an appropriate locale-aware parser/formatter or validate the format per contract.
3. Convert the resulting number to `BigDecimal` **without passing through `double`** if exactness is required; certain `NumberFormat` APIs can be configured to parse into `BigDecimal`, or you can build a controlled token-normalization pipeline.
4. Write tests for ambiguous strings, negative signs, separators, and whitespace.

Do not swap separators via "replace all commas with dots" and claim locale support.

## 13. Limits you need to know

**`BigDecimal` being exact in base 10 does not mean every operation always keeps infinite digits.**

- `BigDecimal` is immutable: you must save the returned result of operations.
- The `BigDecimal(String)` constructor parses only valid text and does not accept `NaN`/infinity.
- `BigDecimal.divide` without specified rounding can throw `ArithmeticException` on repeating decimal fractions.
- `MathContext` limits precision and can round.
- `setScale` can round or throw an error when using `UNNECESSARY`.
- `doubleValue()` can lose precision or overflow to Infinity; `intValue()`/`longValue()` can lose information. Use the appropriate `...ValueExact()` method if exactness and range checks are needed.
- Scale magnitude uses `int`, and coefficient integer size and arithmetic operations remain bounded by memory/resources. Do not treat `BigDecimal` as infinite memory.
- Extremely long strings or extreme exponents from untrusted sources must be **bounded and validated** to mitigate excessive resource consumption risks.
- Scale/rounding policies when writing data must be defined consistently with business requirements.

### When to choose `BigDecimal`, `double`, or `long`?

| Use case | Usually appropriate choice |
|---|---|
| Currency, taxes, exact decimal prices | `BigDecimal` or smallest unit in `long` if design permits |
| Physics, graphics, simulations, statistics tolerating rounding | `double`/`float` depending on precision/performance |
| Integer quantities, exact counters within range | `int`/`long` with overflow checks when needed |
| Parsing inputs that are multi-digit decimal strings | `BigDecimal(String)` |
| Parsing sources already in binary `double` | Define the goal clearly; `valueOf(double)` and `BigDecimal(double)` have different semantics |
| Need to preserve every character of the entered token | Store original `String` alongside `BigDecimal` |

## 14. Common mistakes

| Misconception | Reality |
|---|---|
| “`new BigDecimal(0.1)` is the exact decimal 0.1.” | It takes **the approximated binary64 value of 0.1** and converts that value exactly. |
| “`BigDecimal.valueOf(0.1 + 0.2)` fixes double addition.” | No: it receives `0.30000000000000004` from the addition already performed. |
| “Simply using `BigDecimal` makes every division exact and finite.” | `1.divide(3)` without rounding throws `ArithmeticException`. |
| “`setScale(2)` only changes display formatting.” | When reducing scale, it may need to round or throw; it returns a new `BigDecimal`. |
| “`precision()` is the number of digits after the decimal point.” | `precision` is the count of significant digits in the coefficient; `scale` indicates decimal-point position. |
| “`equals` and `compareTo == 0` are always equivalent.” | `equals` cares about scale; `compareTo` compares numeric value. |
| “`stripTrailingZeros` always keeps a non-negative scale.” | It can produce a negative scale and display scientific notation. |
| “`toString` always returns the original input string.” | It normalizes the representation; plus signs and leading zeros can be lost. |
| “`new BigDecimal("1,23")` understands the Vietnamese locale automatically.” | No: the constructor does not automatically apply decimal locales. |
| “BigDecimal accepts `NaN` or `Infinity` like `double`.” | No. |
| “Calling `doubleValue()` always keeps the exact number.” | Converting to `double` can round or overflow range. |
| “BigDecimal arithmetic removes the need for tests and policies.” | You still must check format, rounding, scale, resources, and business rules. |

## 15. Project implementation checklist

1. **Preserve decimal string sources:** avoid converting to `double` before constructing `BigDecimal`.
2. **Validate input syntax:** sign, decimal point, exponent, whitespace, locale, allowed digit set.
3. **Limit untrusted inputs:** length, exponent, digit count, and business-domain values.
4. **Parse with `new BigDecimal(text)`** and catch `NumberFormatException` at boundaries.
5. **Choose expected units and scale:** e.g., money with two decimal places, without assuming every currency uses two decimal places.
6. **Use `add`/`subtract`/`multiply`/`divide`**, always reassigning the new result if updating.
7. **Specify rounding explicitly** where rounding is needed; distinguish scale from precision.
8. **Compare with `compareTo`** if numeric magnitude is the goal; use `equals` when scale is also part of identity.
9. **Choose serialization carefully:** `toString` can use exponent notation; `toPlainString` avoids exponents, yet does not reconstruct the exact original token.
10. **Do not revert to `double`** in steps requiring decimal exactness.
11. **Test edge cases:** `"0"`, `"-0.00"`, `"0.1"`, `"1.20"`, exponents, leading zeros, invalid data, division by 3, rounding ties, and negative scale.
12. **Mind collection APIs:** `HashSet<BigDecimal>` and `TreeSet<BigDecimal>` behave differently for equal values with different scales.

## 16. Self-check questions

1. How does `new BigDecimal("0.1")` differ from `new BigDecimal(0.1)`?
2. What does `BigDecimal.valueOf(0.1)` normally print? Can it fix the result of `0.1 + 0.2` already computed with `double`?
3. What is `new BigDecimal("1.20").scale()`? And `precision()`?
4. Are `"1.20"` and `"1.2"` equal under `equals`? Under `compareTo`?
5. What error can `new BigDecimal("1").divide(new BigDecimal("3"))` throw?
6. How does `setScale(2, HALF_UP)` differ in meaning from `round(new MathContext(2, HALF_UP))`?
7. Why is `new BigDecimal("1_000.50")` invalid even though `1_000.50` is a Java literal you can write?
8. What does `new BigDecimal("1.23E+4").toPlainString()` print?
9. How can `stripTrailingZeros` change `scale`?
10. If you must store the exact verbatim string `"+0001.2300"` entered by a user, is storing only `BigDecimal` enough?
11. When reading monetary amounts in JSON, what is the risk if a library parses numbers into `double` first?
12. Why does `BigDecimal` not automatically pick one rounding level suitable for every system?

**Suggested answers:** (1) The `String` constructor preserves exact decimal meaning; the `double` constructor preserves the existing approximated binary64 value. (2) `0.1`; no, prior `double` addition already produced `0.30000000000000004`. (3) Scale 2, precision 3. (4) `equals` false, `compareTo` 0. (5) `ArithmeticException` when the decimal expansion does not terminate without specifying rounding. (6) One sets digits after the decimal point, the other sets significant digits. (7) Runtime parsers do not read Java literal syntax with underscores. (8) `12300`. (9) It can strip trailing zeros and produce a negative scale. (10) No, you must keep the original `String` when verbatim text is required. (11) Loss of decimal accuracy before constructing `BigDecimal`. (12) Rounding is a business policy and must be chosen explicitly when needed.

**Remember:** For **decimal number strings**, use **`new BigDecimal(text)` right at the input boundary** to preserve exact decimal values. Distinguish `BigDecimal(String)`, `BigDecimal(double)`, and `BigDecimal.valueOf(double)`; understand **scale, precision, equals/compareTo, arithmetic operations, and rounding rules**. Avoid passing data through `double` in between when the problem requires decimal precision.