# NaN, Infinity, and Signs in Java Floating-Point Input

When receiving a string from keyboard input, forms, CSV, APIs, or configuration files, you cannot assume that **a successful *parse* means you have a finite, nonzero, business-valid number**. In Java, `Double.parseDouble` and `Float.parseFloat` accept several special floating-point values:

- `NaN` (*Not a Number*) — a value that is not a normal finite number.
- `Infinity` — positive infinity; `-Infinity` — negative infinity.
- Leading `+` and `-` signs on strings, including `+0.0` and `-0.0`. Both zeros compare equal under arithmetic comparison, but **differ in their sign bit**.
- Very large or very small numbers can **overflow to infinity** or **round to zero** even when the string has valid numeric syntax.

This lesson belongs to the **floating-point parsing** group, so the focus is on **how input strings are accepted, which values are produced, and how to validate the result**, rather than only discussing operations on existing `NaN`/`Infinity` values.

## 1. Two basic parsing APIs

Java provides:

```java
double d = Double.parseDouble("12.5");
float f = Float.parseFloat("-3.25");
```

These two `static` methods return primitives (`double` and `float`). The wrappers `Double.valueOf(String)` and `Float.valueOf(String)` create **wrapper objects** containing the corresponding values; the core string-parsing rules are equivalent.

| Syntax | Return Type | On invalid syntax | On `null` argument |
| --- | --- | --- | --- |
| `Double.parseDouble(String)` | `double` | `NumberFormatException` | `NullPointerException` |
| `Float.parseFloat(String)` | `float` | `NumberFormatException` | `NullPointerException` |
| `Double.valueOf(String)` | `Double` | `NumberFormatException` | `NullPointerException` |
| `Float.valueOf(String)` | `Float` | `NumberFormatException` | `NullPointerException` |

`NumberFormatException` indicates **a string that does not match the supported syntax**. Conversely, many values **outside the finite range** still have valid syntax and parse successfully into infinity or zero. Therefore `try/catch (NumberFormatException ...)` solves only **part** of data validation.

## 2. Special strings `NaN`, `Infinity`, and signs

In the grammar of the floating-point parsing methods, the strings `NaN` and `Infinity` use **exact letter casing**; they may carry a `+` or `-` sign prefix.

| Input | `Double.parseDouble` returns | Note |
| --- | --- | --- |
| `"NaN"` | `NaN` | No finite numerical value |
| `"+NaN"` | `NaN` | Sign does not create a comparable positive NaN |
| `"-NaN"` | `NaN` | Do not infer NaN sign semantics from the string sign |
| `"Infinity"` | `Infinity` | Positive infinity |
| `"+Infinity"` | `Infinity` | Positive infinity |
| `"-Infinity"` | `-Infinity` | Negative infinity |
| `"infinity"` | Error | Case-sensitive |
| `"Inf"` | Error | Not a standard special token of the API |
| `"nan"` | Error | Not `"NaN"` |
| `"∞"` | Error | Not a literal name recognized by this parser |

```java
System.out.println(Double.parseDouble("NaN"));       // NaN
System.out.println(Double.parseDouble("-NaN"));      // NaN
System.out.println(Double.parseDouble("+Infinity")); // Infinity
System.out.println(Double.parseDouble("-Infinity")); // -Infinity
```

**Do not treat `-NaN` as a "negative" number in the mathematical sense.** NaN has no normal arithmetic ordering. A sign in a NaN input does not supply a reliable business property; some NaN bit representations may have a sign bit, but that is not a positive/negative NaN classification rule for applications to rely on.

The strings above can be parsed into **special values**; if your API permits only finite numbers, you must actively **reject** them after parsing or validate the syntax before parsing.

## 3. `+`/`-` signs with normal numbers and signed zero

A sign preceding a valid decimal value:

```java
double a = Double.parseDouble("+12.5"); // 12.5
double b = Double.parseDouble("-12.5"); // -12.5
double c = Double.parseDouble("+0.0");  // +0.0
double d = Double.parseDouble("-0.0");  // -0.0
```

Notably, both `"-0"` and `"-0.0"` parse into **negative zero `double`**, even though `-0` does not differ from `0` for primitive integers.

```java
double positiveZero = Double.parseDouble("+0");
double negativeZero = Double.parseDouble("-0");

System.out.println(positiveZero == negativeZero); // true
System.out.println(1.0 / positiveZero);           // Infinity
System.out.println(1.0 / negativeZero);           // -Infinity
```

The two zeros are equal under the `==` operator because that is **floating-point arithmetic comparison**, yet dividing a finite nonzero number by them can produce infinities of opposite signs.

### Checking zero's sign at the bit level

```java
long positiveBits = Double.doubleToRawLongBits(+0.0); // 0
long negativeBits = Double.doubleToRawLongBits(-0.0); // 0x8000000000000000

boolean differentBits = positiveBits != negativeBits; // true
```

For `float`, use `Float.floatToRawIntBits`. **Do not use `x < 0.0` to detect negative zero**; `-0.0 < 0.0` is `false`.

When signed zero does not need to be distinguished in business logic, you can **intentionally** normalize `x == 0.0 ? 0.0 : x`. However, this normalization discards sign-bit information and can change the sign of a subsequent division by zero.

## 4. Signs, whitespace, and string grammar

`parseDouble` accepts a broader set of string formats than simple "numbers with a decimal point":

```java
Double.parseDouble("  +1.5  "); // 1.5: strips leading/trailing ASCII whitespace
Double.parseDouble(".5");       // 0.5
Double.parseDouble("5.");       // 5.0
Double.parseDouble("1e3");      // 1000.0
Double.parseDouble("-2.5E-2");  // -0.025
Double.parseDouble("0x1.8p1");  // 3.0: hex floating-point representation
Double.parseDouble("1.25f");    // 1.25: float literal suffix is still accepted
```

Things to note:

- The parser accepts **decimal exponent notation** `e`/`E` and **hex floating-point literals** `0x...p...`. When receiving JSON/CSV data with a strict schema, you may **not want to allow** the parser's entire grammar.
- The parser accepts certain leading/trailing spaces according to rules equivalent to `String.trim()` for ASCII/control characters `<= U+0020`; do not equate this with all kinds of Unicode whitespace.
- Floating-point strings **do not allow underscores** as in Java source literals. `"1_000.0"` is rejected by `Double.parseDouble`, even though `1_000.0` is a valid literal in source code.
- `"1,5"` does **not** become 1.5 under Vietnamese or another locale. `Double.parseDouble` has a locale-independent grammar and uses a dot.
- Empty strings, standalone signs, consecutive signs, or characters outside the grammar can cause `NumberFormatException`.

**Do not arbitrarily strip internal characters, replace every comma with a dot, or remove all whitespace**: for externally defined input formats, "fixing" data before parsing can turn invalid input into a different value that the sender never intended to provide.

## 5. Successful parsing can still yield infinity: overflow

The width of floating-point types is finite. For `double`, the largest finite value is approximately `1.7976931348623157E308`. Numeric strings with larger exponents can parse into infinity:

```java
double overflow = Double.parseDouble("1e400");
double negativeOverflow = Double.parseDouble("-1e400");

System.out.println(overflow);         // Infinity
System.out.println(negativeOverflow); // -Infinity
```

**There is no `NumberFormatException` in these two cases**, because the strings have valid floating-point syntax; the mathematical result exceeded the finite range of `double`.

`float` has a smaller finite range than `double`:

```java
float f = Float.parseFloat("1e40");   // Infinity
double d = Double.parseDouble("1e40"); // 1.0E40 (finite)
```

Thus, the exact same valid string can produce different results depending on the parsed type. If data must stay within specific bounds, check **the chosen type and the post-parse value**, not just the syntax.

## 6. Extremely small values can become ±0.0: underflow

At the small end, floating-point numbers very close to 0 can round to zero if their magnitude is smaller than the smallest positive value representable in the target format:

```java
double tiny = Double.parseDouble("1e-4000"); // 0.0
double negativeTiny = Double.parseDouble("-1e-4000"); // -0.0
```

`Double.MIN_VALUE` in Java is the **smallest positive nonzero `double`**, not the most negative number by magnitude. For `float`, the subnormal range also differs; a value still representable in `double` can become zero when parsed directly into `float`.

**Important:** `Double.isFinite(negativeTiny)` is still `true` because `-0.0` is a finite value. If business logic strictly requires preserving the distinction between nonzero input and zero, **checking `isFinite` is not enough**. You need a policy to reject underflow, use `BigDecimal` for exact decimal inputs, or enforce a minimum input magnitude.

Do not equate every zero result with the string `"0"`: `"-1e-4000"` is mathematically nonzero, yet rounds to `-0.0` in `double`.

## 7. Detecting NaN, Infinity, and finite numbers properly

The dedicated APIs:

| API | `NaN` | `+Infinity` | `-Infinity` | Finite values, including ±0.0 |
| --- | --- | --- | --- | --- |
| `Double.isNaN(x)` | `true` | `false` | `false` | `false` |
| `Double.isInfinite(x)` | `false` | `true` | `true` | `false` |
| `Double.isFinite(x)` | `false` | `false` | `false` | `true` |

`Float.isNaN`, `Float.isInfinite`, and `Float.isFinite` behave correspondingly for `float`.

```java
double x = Double.parseDouble("-Infinity");
System.out.println(Double.isInfinite(x)); // true
System.out.println(Double.isFinite(x));   // false

double y = Double.parseDouble("NaN");
System.out.println(Double.isNaN(y));     // true
System.out.println(Double.isFinite(y));  // false
```

**Do not check for NaN using `x == Double.NaN`.** Primitive comparisons with NaN are always `false`, even `Double.NaN == Double.NaN`. The right way is `Double.isNaN(x)`.

Being able to parse Infinity/NaN does not mean they are valid data in every system. Most systems calculating monetary totals, item quantities, or finite ratios must reject non-finite values. In scientific computing, special values may be accepted under controlled conditions. The data contract must state this clearly.

## 8. When input must consist only of finite decimal numbers

A parser used in business applications usually has **two validation layers**:

1. **Source grammar check:** does the application allow `NaN`, `Infinity`, hex literals, `f/d` suffixes, whitespace, `+` signs, `.5` forms, or exponents?
2. **Post-parse value check:** is the result finite, within the permitted range, rounded to zero, or subject to precision loss?

Example helper that **accepts only ASCII decimal syntax** with optional sign and exponent, then catches errors and rejects non-finite numbers:

```java
static double parseFiniteDecimal(String raw) {
    if (raw == null) {
        throw new IllegalArgumentException("Missing number");
    }

    String s = raw.trim();
    if (!s.matches("[+-]?(?:[0-9]+(?:\\.[0-9]*)?|\\.[0-9]+)(?:[eE][+-]?[0-9]+)?")) {
        throw new IllegalArgumentException("Invalid decimal syntax");
    }

    double value = Double.parseDouble(s);
    if (!Double.isFinite(value)) {
        throw new IllegalArgumentException("Non-finite number");
    }
    return value;
}
```

This is **an illustrative method to be placed inside a class**, not a standalone program. It intentionally **disallows** `NaN`, `Infinity`, hex syntax, and `f/d` suffixes. Strings `"+12.5"` and `"1e3"` are allowed; `"1,5"` is not.

**Limitation of the helper:** it can still accept `"1e-4000"` as `0.0`. That is fine if the contract only requires **a finite result**, but **not sufficient** if every nonzero input must be preserved accurately. To reject underflow, compare against the original decimal data using `BigDecimal` or define explicit range rules.

### If you need to preserve the exact original decimal

```java
java.math.BigDecimal exact =
        new java.math.BigDecimal("1e-4000");
// Still holds a nonzero positive number as a BigDecimal
```

`BigDecimal` does not directly accept `"NaN"` or `"Infinity"` as an ordinary decimal numeric value. If the domain is money or decimals requiring exactness, use `BigDecimal` constructed from a string or an integer model in the smallest unit, together with contract-defined precision/scale and rounding policies.

## 9. Difference between parsing and locale-based formatting

`Double.parseDouble("1.5")` gives 1.5 regardless of the machine locale. However, users may enter numbers according to local conventions, such as `"1,5"`, grouping separators, or non-ASCII digits.

If the contract genuinely allows localized formats, you can use `java.text.NumberFormat`/`DecimalFormat` with an explicitly specified `Locale`. However, those APIs have their own rules for signs, grouping, special characters, and NaN/Infinity values, and they can **parse part of a string and stop**. Applications should use `ParsePosition` or an equivalent mechanism to verify that **the entire input was consumed**, rather than treating returning a `Number` as sufficient.

Illustrative example:

```java
java.text.NumberFormat parser =
        java.text.NumberFormat.getNumberInstance(java.util.Locale.GERMANY);
java.text.ParsePosition pos = new java.text.ParsePosition(0);
String input = "1,5";
Number result = parser.parse(input, pos);

boolean complete = result != null && pos.getIndex() == input.length();
// complete == true; result.doubleValue() == 1.5
```

This is **an illustrative method snippet**, not a standalone program. Financial data still needs the right decimal parser, grouping, scale, and decimal policy; `NumberFormat` alone does not guarantee that every number is business-accurate.

## 10. Avoiding silent propagation of special values

If NaN/Infinity is accepted unintentionally, subsequent operations can produce more non-finite results:

```java
double rate = Double.parseDouble("Infinity");
double cost = rate * 10.0; // Infinity

double undefined = Double.parseDouble("NaN");
double total = undefined + 100.0; // NaN
```

Comparisons with NaN can also easily break logic:

```java
double x = Double.NaN;
System.out.println(x > 0.0);  // false
System.out.println(x <= 0.0); // false
System.out.println(x == x);   // false
```

If a rule only checks `x <= limit` to reject large values, NaN can **slip past the check** because ordinary less-than/greater-than comparisons with NaN are all false. Check `Double.isFinite(x)` before range comparisons.

When transmitting data via JSON or a database, do not assume every system accepts strings or special `NaN`/`Infinity` values directly. Protocols and schemas must explicitly define how to represent or reject them.

### `NaN` and signs are not comma errors

You should not "strip every character that isn't a digit or a dot" as a validation strategy. That approach can turn `"-Infinity"`, `"-1e-4000"`, or `"+1.5"` into different data that the user did not enter. Apply **a specific allowed grammar**, then validate the value range.

## 11. Standalone Java 17+ program

Create the file **`FloatingInputDemo.java`**:

```java
public class FloatingInputDemo {
    static double parseFiniteDecimal(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException("Missing number");
        }
        String s = raw.trim();
        if (!s.matches("[+-]?(?:[0-9]+(?:\\.[0-9]*)?|\\.[0-9]+)(?:[eE][+-]?[0-9]+)?")) {
            throw new IllegalArgumentException("Invalid decimal syntax");
        }
        double value = Double.parseDouble(s);
        if (!Double.isFinite(value)) {
            throw new IllegalArgumentException("Non-finite number");
        }
        return value;
    }

    static String status(String raw) {
        try {
            return Double.toString(parseFiniteDecimal(raw));
        } catch (IllegalArgumentException ex) {
            return "REJECTED";
        }
    }

    public static void main(String[] args) {
        System.out.println("nan=" + Double.parseDouble("NaN"));
        System.out.println("plusNan=" + Double.parseDouble("+NaN"));
        System.out.println("minusNan=" + Double.parseDouble("-NaN"));
        System.out.println("plusInfinity=" +
                Double.parseDouble("+Infinity"));
        System.out.println("minusInfinity=" +
                Double.parseDouble("-Infinity"));

        double plusZero = Double.parseDouble("+0");
        double minusZero = Double.parseDouble("-0");
        System.out.println("zeroEquals=" + (plusZero == minusZero));
        System.out.println("positiveReciprocal=" + (1.0 / plusZero));
        System.out.println("negativeReciprocal=" + (1.0 / minusZero));
        System.out.println("minusZeroBits=" +
                Long.toHexString(Double.doubleToRawLongBits(minusZero)));

        System.out.println("withWhitespace=" +
                Double.parseDouble("  +1.5  "));
        System.out.println("hexFloating=" +
                Double.parseDouble("0x1.8p1"));
        System.out.println("suffixFloat=" +
                Double.parseDouble("1.25f"));

        double large = Double.parseDouble("1e400");
        double tinyNegative = Double.parseDouble("-1e-4000");
        System.out.println("doubleOverflow=" + large);
        System.out.println("doubleUnderflow=" + tinyNegative);
        System.out.println("floatOverflow=" + Float.parseFloat("1e40"));
        System.out.println("doubleFinite=" +
                Double.isFinite(Double.parseDouble("1e40")));
        System.out.println("overflowIsFinite=" + Double.isFinite(large));
        System.out.println("nanDetected=" +
                Double.isNaN(Double.parseDouble("NaN")));
        System.out.println("underflowIsFinite=" +
                Double.isFinite(tinyNegative));

        System.out.println("validDecimal=" + status("+12.5"));
        System.out.println("validExponent=" + status("1e3"));
        System.out.println("rejectNan=" + status("NaN"));
        System.out.println("rejectInfinity=" + status("-Infinity"));
        System.out.println("rejectOverflow=" + status("1e400"));
        System.out.println("rejectComma=" + status("1,5"));
        System.out.println("rejectUnderscore=" + status("1_000.0"));
        System.out.println("rejectHex=" + status("0x1.8p1"));
        System.out.println("underflowAllowed=" + status("1e-4000"));
        System.out.println("nullInput=" + status(null));

        try {
            Double.parseDouble("infinity");
            System.out.println("lowercaseInfinity=ACCEPTED");
        } catch (NumberFormatException ex) {
            System.out.println("lowercaseInfinity=REJECTED");
        }
    }
}
```

Compile and run from the directory containing the file:

```bash
javac FloatingInputDemo.java
java FloatingInputDemo
```

Expected output:

```text
nan=NaN
plusNan=NaN
minusNan=NaN
plusInfinity=Infinity
minusInfinity=-Infinity
zeroEquals=true
positiveReciprocal=Infinity
negativeReciprocal=-Infinity
minusZeroBits=8000000000000000
withWhitespace=1.5
hexFloating=3.0
suffixFloat=1.25
doubleOverflow=Infinity
doubleUnderflow=-0.0
floatOverflow=Infinity
doubleFinite=true
overflowIsFinite=false
nanDetected=true
underflowIsFinite=true
validDecimal=12.5
validExponent=1000.0
rejectNan=REJECTED
rejectInfinity=REJECTED
rejectOverflow=REJECTED
rejectComma=REJECTED
rejectUnderscore=REJECTED
rejectHex=REJECTED
underflowAllowed=0.0
nullInput=REJECTED
lowercaseInfinity=REJECTED
```

The `doubleOverflow`/`doubleUnderflow` lines show that **valid syntax is not enough to guarantee the source value is preserved**. `rejectInfinity` and `rejectOverflow` demonstrate enforcing a "finite only" contract; the `underflowAllowed` line is an intentional limitation of the helper — avoiding loss of very small numbers requires an additional check.

## 12. Common pitfalls and checklist

| Misconception | Accurate explanation |
| --- | --- |
| “`Double.parseDouble` only accepts finite numbers.” | Accepts `NaN`, `±Infinity`, and values that overflow to Infinity. |
| “`NaN` must be written without a sign.” | `+NaN` and `-NaN` may be accepted, yet the result is still NaN with no numeric ordering. |
| “`infinity` or `Inf` is the same as `Infinity`.” | No; the parser enforces the exact defined syntax. |
| “`-0` parses into positive zero.” | With floating-point parsers, negative zero can be preserved, distinguishable in bits and division. |
| “Simply catching `NumberFormatException` guarantees a valid number.” | A syntactically valid string like `1e400` still produces Infinity. |
| “Checking `Double.isFinite` guarantees no data loss.” | Underflow can produce finite zero; precision can also cause rounding. |
| “`Double.isNaN(x)` and `x == Double.NaN` are equivalent.” | No; `==` with NaN is always false. |
| “`parseDouble` automatically reads comma-decimal numbers by locale.” | No; the parser uses dots and a locale-independent grammar. |
| “Both the Java literal `1_000.0` and the string `"1_000.0"` parse.” | Source literals allow underscores; the string parser does not. |
| “Seeing `-Infinity` lets you infer the error came from division by 0.” | No; overflow and other operations can also produce infinity. |
| “You can strip signs and non-digit characters before parsing.” | This can silently corrupt the meaning of input; validate with proper grammar and report errors clearly. |

Checklist when receiving floating-point data from external sources:

1. **Define the contract format**: allow `+/-` signs, exponents, whitespace, hex numbers, literal suffixes, grouping/locale, or special values?
2. **Choose the appropriate numeric type**: `float`, `double`, or `BigDecimal` if exact decimals are needed.
3. **Validate `null`, syntax, and allowed range** instead of assuming the parser handles everything.
4. **If only finite values are allowed**, use `Double.isFinite`/`Float.isFinite` after parsing.
5. **If nonzero inputs must be preserved**, detect cases where underflow becomes zero, e.g., via range checks or comparing with the original decimal.
6. **If zero's sign matters**, do not normalize negative zero unintentionally; if it does not matter, normalize consistently and document it.
7. **Do not let NaN slip past range comparisons**: check finiteness first, because `<`, `>`, `<=`, and `>=` with NaN are all false.
8. **When reformatting or sending to other systems**, check the protocol's definition for NaN/Infinity; do not assume every JSON schema or database allows them.

**Remember:** `Double.parseDouble` and `Float.parseFloat` parse **floating-point syntax**, not full **business validity**. `NaN`, `±Infinity`, `±0.0`, and rounding due to overflow/underflow are outcomes that require deliberate handling.