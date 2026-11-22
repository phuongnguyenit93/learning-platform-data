# Reference Table for Parsing, Formatting, and Exact Conversion in Java Core Numbers

## 1. Three Distinct Operations That Cannot Be Used Interchangeably

When working with numbers in Java, distinguish between:

1. **Parse (reading/decoding):** from a `String` or text source into a numeric value. For example, `Integer.parseInt("42")`.
2. **Format (presentation):** from a numeric value into a `String` by radix, digit count, separators, or `Locale`. For example, `number.toPlainString()` or `DecimalFormat.format(...)`.
3. **Convert (type conversion):** from one numeric type to another. Some conversions preserve the value; others **truncate the fractional part, overflow, round, or lose precision**. For example, `BigDecimal.intValueExact()` is completely different from `BigDecimal.intValue()`.

The keyword **exact** here has a specific meaning: the conversion or operation must **not lose mathematical value**, or else it will **throw an exception** when it cannot preserve it under the API's conditions. Exact does not mean "preserving the display string", "preserving the scale" in all cases, or "all floating-point operations are exact".

Quick lookup questions:

- Is the string decimal or base 2/8/16? Does it have a `+`/`-` sign, `0x` prefix, or thousands separators?
- Is the target type `int`/`long`, `BigInteger`, `double`, or `BigDecimal`?
- Can the input be `null`, blank, `NaN`/`Infinity`, or out of numeric range?
- Does the result require an **exact value**, a **decimal with a fixed scale**, or **locale-specific formatting**?
- If an exact conversion is impossible, should it throw an error, apply a specified rounding, or use a larger type?

## 2. String → Numeric Type Parse Table

| Target Type | How to Parse | Example | Important Notes |
|---|---|---|---|
| `byte` | `Byte.parseByte(s)` | `"127" → 127` | Only within range [-128, 127] |
| `short` | `Short.parseShort(s)` | `"32000" → 32000` | Only within range [-32768, 32767] |
| `int` | `Integer.parseInt(s)` | `"42" → 42` | Signed decimal by default; syntax error/out of range → `NumberFormatException` |
| `long` | `Long.parseLong(s)` | `"9000000000" → 9000000000L` | Needs matching `long` literal/method |
| `float` | `Float.parseFloat(s)` | `"1.25" → 1.25f` | IEEE 754; may round, supports `NaN`/Infinity |
| `double` | `Double.parseDouble(s)` | `"1.25e2" → 125.0` | IEEE 754; syntactically finite strings can still overflow to Infinity |
| `BigInteger` | `new BigInteger(s)` | `"12345678901234567890"` | Arbitrary-magnitude integer limited by machine resources; rejects fractional parts |
| `BigDecimal` | `new BigDecimal(s)` | `"123.4500"` | Preserves the written decimal value and expressed scale |
| Wrapper object | `Integer.valueOf(s)`, `Long.valueOf(s)`... | `Integer.valueOf("42")` | Returns wrapper; not inherently `null`-safe |

For `Integer.parseInt`/`Long.parseLong`, strings with a plus or minus sign are supported when syntactically valid:

~~~java
int positive = Integer.parseInt("+42"); // 42
int negative = Integer.parseInt("-42"); // -42
~~~

However, grouping separators are not automatically accepted:

~~~java
// Integer.parseInt("1,234"); // NumberFormatException
// Integer.parseInt("42.0");  // NumberFormatException
// Integer.parseInt(" 42 ");  // NumberFormatException
~~~

To accept strings with whitespace, normalize according to the contract:

~~~java
String raw = " 42 ";
int number = Integer.parseInt(raw.trim()); // 42
~~~

Note: `trim()` modifies the input string and is not equivalent to handling every kind of Unicode whitespace. The input contract must specify whether whitespace may be stripped; do not silently normalize when strict formatting is required.

**Important:** `Double.parseDouble("NaN")` can return NaN **without throwing an exception**. `Double.parseDouble("Infinity")` returns positive infinity; `Double.parseDouble("1e400")` can become infinity by exceeding `double`'s finite range. When an application permits only finite numbers, check `Double.isFinite(result)` after parsing.

## 3. Parsing by Radix: 2, 8, 10, 16

There are two easily confused API groups.

### 3.1. parseInt(s, radix), parseLong(s, radix)

~~~java
int binary = Integer.parseInt("101010", 2); // 42
int octal = Integer.parseInt("52", 8);      // 42
int hex = Integer.parseInt("2A", 16);       // 42
long l = Long.parseLong("FF", 16);          // 255L
~~~

The `radix` parameter lies in `Character.MIN_RADIX` to `Character.MAX_RADIX` (2 to 36). Letters A–Z/a–z represent digits from 10 to 35 when applicable. Note that `parseInt("0x2A", 16)` does **not** accept the `0x` prefix as valid hex digits; to parse strings with prefixes, you can use `Integer.decode(...)` when appropriate.

~~~java
int hex = Integer.decode("0x2A"); // 42
int oct = Integer.decode("052");  // 42 in base 8
~~~

### 3.2. decode Handles Prefixes Differently from parseInt(radix)

| String | `Integer.parseInt(s)` | `Integer.decode(s)` | Explanation |
|---|---|---|---|
| `"42"` | 42 | 42 | Standard decimal |
| `"0x2A"` | Error | 42 | `decode` accepts `0x`/`0X` or `#` |
| `"#2A"` | Error | 42 | Hex prefix of `decode` |
| `"052"` | 52 | 42 | `decode` treats numbers starting with 0 as octal |
| `"08"` | 8 | Error | `8` is not an octal digit |
| `"-0x2A"` | Error | -42 | `decode` supports sign before prefix |

`Long.decode` works similarly for `Long`. Use `decode` only when the source format genuinely adopts legacy prefix and octal rules. If the goal is decimal integers where `"052"` means 52, `Integer.parseInt(s, 10)` is clearer.

### 3.3. BigInteger with Radix

~~~java
BigInteger a = new BigInteger("FF", 16);  // 255
BigInteger b = new BigInteger("1010", 2); // 10

System.out.println(a.toString(16)); // ff
System.out.println(b.toString(2));  // 1010
~~~

`BigInteger(String, radix)` decodes digits in the specified radix; `toString(radix)` outputs in the corresponding radix. The constructor does not automatically accept a `0x` prefix like `decode`. `BigInteger` supports integers exceeding `long` without pretending to be a 64-bit signed integer.

## 4. Unsigned Integers: parseUnsignedInt/parseUnsignedLong

Java's `int` and `long` remain **signed** primitive types. The "unsigned" APIs interpret bit patterns in the unsigned range without creating a new primitive type:

~~~java
int bits = Integer.parseUnsignedInt("4294967295");
System.out.println(bits);                          // -1 (if printed as a signed int)
System.out.println(Integer.toUnsignedString(bits)); // 4294967295
System.out.println(Integer.toUnsignedLong(bits));   // 4294967295
~~~

| API | Meaning |
|---|---|
| `Integer.parseUnsignedInt(s)` | Parses a 32-bit decimal unsigned integer into an `int` bit pattern |
| `Integer.parseUnsignedInt(s, radix)` | Parses an unsigned integer in a given radix |
| `Integer.toUnsignedString(int)` | Prints an `int` bit pattern as a value in 0..2^32−1 |
| `Integer.toUnsignedLong(int)` | Widens an unsigned `int` value to positive `long`, preserving 0..2^32−1 |
| `Long.parseUnsignedLong(s)` | Parses a 64-bit unsigned number into a `long` bit pattern |
| `Long.toUnsignedString(long)` | Prints a `long` bit pattern as an unsigned value in 0..2^64−1 |

For example, with `Long.parseUnsignedLong("18446744073709551615")`, the resulting bit pattern looks like `-1L` when viewed as a signed `long`; `Long.toUnsignedString(...)` prints `18446744073709551615` back. If you want to manipulate integers beyond the signed `long` range by **numerical value** rather than just bit patterns, `BigInteger` is usually clearer.

Do not use `parseUnsignedInt` and assume an `int` will represent 4,294,967,295 as a positive `int`: that is impossible because `int` has only 32 bits and its signed maximum is 2,147,483,647.

## 5. Number → String Conversion Table (Non-Locale Formatting)

| Goal | API | Example / Result | Notes |
|---|---|---|---|
| Any primitive → default string | `String.valueOf(value)` | `String.valueOf(42) → "42"` | Overloaded for primitives; adds no grouping separators |
| `int` → decimal | `Integer.toString(42)` | `"42"` | Does not alter value |
| `long` → decimal | `Long.toString(42L)` | `"42"` | No grouping |
| `int` → hex | `Integer.toHexString(255)` | `"ff"` | For negatives, shows two's complement bit pattern; understand semantics |
| `int` → binary | `Integer.toBinaryString(10)` | `"1010"` | Shows bits per API rules |
| `int` → octal | `Integer.toOctalString(8)` | `"10"` | Does not automatically prepend `0` |
| `BigInteger` → decimal | `bigInteger.toString()` | Decimal integer string | Not limited to `int/long` |
| `BigInteger` → radix | `bigInteger.toString(16)` | `255 → "ff"` | Lowercase letters |
| `BigDecimal` → canonical | `value.toString()` | `1E+4 → "1E+4"` | Re-parsing with `BigDecimal(String)` preserves both value and scale |
| `BigDecimal` → plain | `value.toPlainString()` | `1E+4 → "10000"` | No `E`; re-parsing can lose negative scale |
| `BigDecimal` → engineering | `value.toEngineeringString()` | `1E+4 → "10E+3"` | If using exponent, exponent is a multiple of 3; re-parsing can change scale |
| `double` → canonical | `Double.toString(value)` | `125.0 → "125.0"` | May use `E` notation, `NaN`, `Infinity` |
| `float` → canonical | `Float.toString(value)` | `1.5f → "1.5"` | Short representation for the binary value per Java rules |

Example distinguishing `BigDecimal`'s three methods:

~~~java
BigDecimal x = new BigDecimal("1E+4");

System.out.println(x.toString());            // 1E+4
System.out.println(x.toEngineeringString()); // 10E+3
System.out.println(x.toPlainString());       // 10000
~~~

All three strings represent the same value `10000`, yet **there is no guarantee that all three will preserve the same scale when re-parsed**:

~~~java
BigDecimal original = new BigDecimal("1E+4"); // scale -4
BigDecimal fromPlain = new BigDecimal(original.toPlainString()); // scale 0

System.out.println(original.compareTo(fromPlain) == 0); // true
System.out.println(original.equals(fromPlain));          // false
~~~

`compareTo` compares value; `equals` compares both value and scale. If you need to serialize and re-parse while preserving `BigDecimal` representation, `toString()` is more suitable than `toPlainString()`/`toEngineeringString()`.

## 6. Locale Formatting, Decimal Places, and Grouping Separators

**Default parsing/formatting of `Integer.parseInt`, `BigDecimal(String)`, and `toString()` does not use locale separators**, typically using `.` as the decimal point in Java strings. However, user interfaces may require region-specific grouping and decimal separators.

### 6.1. String.format with Explicit Locale

~~~java
import java.util.Locale;

String text = String.format(Locale.US, "%,.2f", 12345.67);
// "12,345.67"
~~~

In format strings, `%,.2f` means display a floating-point number with locale grouping separators and two digits after the decimal point. `%.2f` is not the primary mechanism for defining **financial rounding rules**; when business rounding modes are needed, select and control rounding explicitly before output.

Some common conversions:

| Format Specifier | Example | Meaning |
|---|---|---|
| `%d` | `String.format(Locale.US, "%d", 42)` | Decimal integer |
| `%x` | `String.format(Locale.US, "%x", 255)` | Lowercase hex |
| `%o` | `String.format(Locale.US, "%o", 8)` | Octal |
| `%.2f` | Format real number with 2 decimal digits | Fixed-point form, subject to Formatter rules |
| `%e` | Format real number in exponential form | Scientific notation per Formatter |
| `%,.2f` | `12,345.67` | Grouping and 2 decimal digits per locale |
| `%s` | `String.format("%s", value)` | Object string representation, not specialized numeric formatting |

Note that `%d` does not apply to `Double`; argument types and conversions must match. `String.format` has an overload accepting `Locale`; omitting `Locale` makes output depend on the JVM's default locale.

### 6.2. DecimalFormat / NumberFormat

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.util.Locale;

DecimalFormat format = (DecimalFormat)
        NumberFormat.getNumberInstance(Locale.US);

format.setGroupingUsed(true);
format.setMinimumFractionDigits(2);
format.setMaximumFractionDigits(2);
format.setRoundingMode(RoundingMode.HALF_UP);

String output = format.format(new BigDecimal("12345.675"));
// "12,345.68"
~~~

Here `RoundingMode.HALF_UP` is explicitly specified. `setMinimumFractionDigits(2)` pads to two decimal places when needed; `setMaximumFractionDigits(2)` limits fractional digits in the output. **Formatting does not mutate the original `BigDecimal` object.**

`NumberFormat` and `DecimalFormat` are **mutable** objects and are generally not thread-safe for concurrent use without proper coordination. In multithreaded request handling, use per-context instances or an appropriate design rather than freely sharing one formatter and mutating its settings.

To format currency, you can use `NumberFormat.getCurrencyInstance(locale)`, but currency symbols, grouping, and decimal places are **display rules**, insufficient on their own to fully define monetary calculations, currency units, transaction rounding, or exchange-rate conversion.

## 7. Parsing Locale-Formatted Numbers: Different from Technical Parsing

The string `"1,234.50"` uses a comma thousands separator under `Locale.US`:

~~~java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.util.Locale;

DecimalFormat parser = (DecimalFormat)
        NumberFormat.getNumberInstance(Locale.US);
parser.setParseBigDecimal(true);

Number value = parser.parse("1,234.50"); // May throw ParseException.
BigDecimal decimal = (BigDecimal) value; // 1234.50 in this finite example.
~~~

**Do not use** `new BigDecimal("1,234.50")`: `BigDecimal`'s constructor does not parse locale grouping separators. And `Integer.parseInt("1,234")` does not accept grouping either.

### 7.1. Locale Parsing May Accept a String Prefix — Must Check Full Input

`NumberFormat.parse(String)` can be more lenient than technical number parsers and does not necessarily reject an entire string containing trailing invalid characters. For strictly validated input, use `ParsePosition`:

~~~java
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

String input = "1,234.50";
NumberFormat parser = NumberFormat.getNumberInstance(Locale.US);
ParsePosition position = new ParsePosition(0);

Number parsed = parser.parse(input, position);
if (parsed == null || position.getIndex() != input.length()) {
    throw new IllegalArgumentException("Invalid numeric input");
}
~~~

Checking `getIndex()` ensures **all characters were consumed**. However, that is **still not enough** if the contract also requires strictly exact grouping formatting: locale parsers can allow flexible forms. In that case, add schema syntax validation before parsing, while explicitly choosing decimal/grouping separator rules.

When using `setParseBigDecimal(true)`, do not blindly cast the result on all special inputs: some inputs such as NaN/Infinity may be handled by the parser's own rules and not return a `BigDecimal`. Check the result type and validity if the data is not guaranteed finite.

### 7.2. Formatting Does Not Always Have a Perfect Inverse

For example, formatting `12345.675` as `"12,345.68"` **loses five thousandths** due to rounding. Parsing that string back yields only the rounded value and cannot recover `12345.675`.

Rules:

- **Use canonical strings to store/transmit exact numeric data** when round-trip fidelity is needed, not pretty UI strings.
- **Use formatters for presentation**, which may round, pad zeros, or insert grouping separators.
- **Persist units, scale, and rounding policy** as well if they are essential parts of the business contract.

## 8. Conversion Table from Primitives/Wrappers: Widening, Narrowing, and Exact

| Conversion | Example | Preserves Every Source Value? | Notes |
|---|---|---|---|
| `int → long` | `long l = i;` | **Yes** | Integer widening |
| `int → double` | `double d = i;` | **Yes** | Every `int` is represented exactly by `double` |
| `long → double` | `double d = l;` | **No** | Integers above the `2^53` exact threshold may be rounded |
| `long → int` | `int i = (int) l;` | **No** | Drops high bits if outside `int` range |
| `double → int` | `int i = (int) d;` | **No** | Truncates fraction toward 0 with special saturation/NaN rules |
| `double → long` | `long l = (long) d;` | **No** | May truncate/lose precision; must validate first |
| `float → double` | `double d = f;` | **Yes for the stored float value** | Does not turn an already-rounded original decimal exact |
| `double → float` | `float f = (float) d;` | **No** | May overflow to infinity or lose precision |
| `Integer → int` | `int i = wrapper;` | When wrapper is non-null | Null throws `NullPointerException` |
| `BigInteger → long` | `bi.longValue()` | No | May lose high bits |
| `BigDecimal → int` | `bd.intValue()` | No | Drops fraction and may lose data due to overflow |
| `BigDecimal → double` | `bd.doubleValue()` | No | May round, underflow/overflow to 0/Infinity |

Casts and `intValue()`-style methods without `Exact` in their name are **lossy conversions** in certain situations. You cannot look merely at whether code compiles to conclude the value was preserved.

Example:

~~~java
int truncated = new BigDecimal("12.9").intValue(); // 12

// Can differ significantly from the original data when outside the int range:
int wrapped = new BigInteger("4294967296").intValue(); // 0 (low 32 bits of 2^32 are 0)
~~~

`(int) Double.NaN` gives 0 per primitive narrowing rules; `(int) Double.POSITIVE_INFINITY` gives `Integer.MAX_VALUE`. These are language conversion rules, **not** "valid value" checks. If NaN/Infinity are unacceptable, reject them **before** casting.

## 9. Exact Conversion API Table

This is the most important reference table when rules require "no value loss":

| Source → Target | Primary API | When It Succeeds | If Not Exact |
|---|---|---|---|
| `long → int` | `Math.toIntExact(long)` | Within signed int range | `ArithmeticException` |
| `BigInteger → int` | `bigInteger.intValueExact()` | Within signed int range | `ArithmeticException` |
| `BigInteger → long` | `bigInteger.longValueExact()` | Within signed long range | `ArithmeticException` |
| `BigInteger → short` | `bigInteger.shortValueExact()` | Within short range | `ArithmeticException` |
| `BigInteger → byte` | `bigInteger.byteValueExact()` | Within byte range | `ArithmeticException` |
| `BigDecimal → int` | `bd.intValueExact()` | No nonzero fraction and within int range | `ArithmeticException` |
| `BigDecimal → long` | `bd.longValueExact()` | No nonzero fraction and within long range | `ArithmeticException` |
| `BigDecimal → short/byte` | `bd.shortValueExact()` / `bd.byteValueExact()` | Integer within target range | `ArithmeticException` |
| `BigDecimal → BigInteger` | `bd.toBigIntegerExact()` | Mathematical value is an integer | `ArithmeticException` |
| `BigInteger → BigDecimal` | `new BigDecimal(bi)` | Always preserves corresponding integer value | No precision loss at this step |
| `long → BigInteger` | `BigInteger.valueOf(l)` | Entire signed long range | No value loss |
| `long → BigDecimal` | `BigDecimal.valueOf(l)` | Entire signed long range | No value loss |
| Unscaled long + scale → BigDecimal | `BigDecimal.valueOf(unscaled, scale)` | Exact value `unscaled × 10^-scale` | No rounding |
| `BigDecimal → smaller-scale BigDecimal` | `bd.setScale(n, UNNECESSARY)` | Drops no digits affecting value | `ArithmeticException` |

Example:

~~~java
BigDecimal one = new BigDecimal("12.000");
int exact = one.intValueExact(); // 12 because all fractional digits are 0.

// These two cases must be rejected when exact conversion is required:
// new BigDecimal("12.9").intValueExact();        // ArithmeticException
// new BigInteger("2147483648").intValueExact();  // ArithmeticException

long value = 2147483648L;
// Math.toIntExact(value); // ArithmeticException
~~~

**Exactness is measured by value**, not necessarily by string form. `new BigDecimal("12.000").intValueExact()` returns 12 even though the original scale was 3. Converting to `int` does not preserve scale, because `int` has no scale.

Example of `toBigIntegerExact` with a negative number:

~~~java
BigDecimal value = new BigDecimal("-8.000");
BigInteger exact = value.toBigIntegerExact(); // -8

// new BigDecimal("-8.001").toBigIntegerExact();
// ArithmeticException: has a nonzero fractional part.
~~~

### Is There an Exact API for BigDecimal → double?

There is no `BigDecimal.doubleValueExact()` in the standard API. `doubleValue()` can lose precision, overflow to infinity, or underflow. If business rules **mandate** exact representation in `double`, define a dedicated check suited to your range and application rules; do not treat casting and then parsing/formatting back as sufficient proof in every case.

For example, `BigDecimal("0.1")` is an exact decimal number, yet cannot be represented exactly as a binary `double` value. Converting to `double` is usually only an approximation.

## 10. Exact Arithmetic: Overflow-Free Addition/Multiplication and Division

Exact conversion does not replace checking **exact arithmetic**. Signed primitive `int`/`long` operations can overflow and wrap when using standard operators:

~~~java
int max = Integer.MAX_VALUE;
int wrapped = max + 1; // -2147483648

// Math.addExact(max, 1); // ArithmeticException
~~~

Overflow-checking math methods include:

| Operation | API | Fails When |
|---|---|---|
| `int/long` addition | `Math.addExact(a, b)` | Sum outside target type range |
| `int/long` subtraction | `Math.subtractExact(a, b)` | Difference outside range |
| `int/long` multiplication | `Math.multiplyExact(a, b)` | Product outside range |
| `int/long` increment/decrement | `Math.incrementExact(x)` / `decrementExact(x)` | Exceeds bounds |
| `int/long` negation | `Math.negateExact(x)` | E.g., negating MIN_VALUE |
| `long → int` conversion | `Math.toIntExact(x)` | Outside int range |

`BigInteger` is often the solution when integer results must exceed `long` limits. Still, huge numbers consume memory and time; exact APIs do not make resources infinite.

### BigDecimal.divide and Exactness

~~~java
BigDecimal exact = BigDecimal.ONE.divide(new BigDecimal("8"));
// 0.125: finite decimal expansion.

// BigDecimal.ONE.divide(new BigDecimal("3"));
// ArithmeticException: infinite decimal representation if no rounding is chosen.
~~~

To get an approximate result under an explicit rule:

~~~java
BigDecimal quotient = BigDecimal.ONE.divide(
        new BigDecimal("3"),
        4,
        RoundingMode.HALF_UP); // 0.3333, scale = 4
~~~

Or using precision by significant digits:

~~~java
BigDecimal q = BigDecimal.ONE.divide(
        new BigDecimal("3"),
        new MathContext(4, RoundingMode.HALF_EVEN)); // 0.3333
~~~

**Difference:** `setScale(4)` / `divide(..., 4, mode)` refers to **4 digits after the decimal point**, whereas `MathContext(4)` refers to **4 significant digits**. These are two independent kinds of requirements.

## 11. BigDecimal(String), valueOf(double), and new BigDecimal(double)

Three ways to create a `BigDecimal` from decimal intent are easily confused:

| Construction | Example | Behavior |
|---|---|---|
| `new BigDecimal("0.1")` | Decimal 0.1 | Stores the exact decimal value written |
| `BigDecimal.valueOf(0.1)` | `double` value 0.1 converted via `Double.toString` | Produces the short `0.1` representation, usually suitable when the source is already a double |
| `new BigDecimal(0.1)` | Constructor taking `double` | Represents **the exact binary double value stored**, often having many decimal digits |

Illustration:

~~~java
System.out.println(new BigDecimal("0.1"));
// 0.1

System.out.println(BigDecimal.valueOf(0.1));
// 0.1

System.out.println(new BigDecimal(0.1));
// 0.1000000000000000055511151231257827021181583404541015625
~~~

The first two `0.1` strings do not prove that a `double 0.1` input can represent decimal 0.1 exactly. `BigDecimal.valueOf(double)` follows the string representation chosen by `Double.toString` to round-trip the double value; `new BigDecimal(double)` exposes the stored binary value as an exact decimal.

For money or purely decimal business values, it is best to receive data directly as validated strings or a decimal source of suitable precision and construct `BigDecimal(String)`. Do not convert `BigDecimal` to `double` and back just to "normalize", as precision can be lost.

### NaN and Infinity Values

`BigDecimal` has no NaN/Infinity:

~~~java
// BigDecimal.valueOf(Double.NaN); // NumberFormatException
// BigDecimal.valueOf(Double.POSITIVE_INFINITY); // NumberFormatException
~~~

With a `double` source that only permits finite numbers:

~~~java
static BigDecimal requireFiniteDecimal(double value) {
    if (!Double.isFinite(value)) {
        throw new IllegalArgumentException("non-finite number");
    }
    return BigDecimal.valueOf(value);
}
~~~

## 12. Exact Conversion Does Not Mean Rounding

When a number has a fractional part, there are at least three policies:

1. **Reject data loss:** use `intValueExact()` / `toBigIntegerExact()`.
2. **Truncate fraction:** intentionally use `intValue()` / `toBigInteger()`. This is not nearest rounding.
3. **Round then convert:** choose `setScale(0, roundingMode)`, then `intValueExact()` to detect overflow.

~~~java
BigDecimal source = new BigDecimal("12.6");

// 1. Exact: rejected.
// source.intValueExact(); // ArithmeticException

// 2. Truncate toward 0:
int truncated = source.intValue(); // 12

// 3. Round by policy then check int range:
int rounded = source.setScale(0, RoundingMode.HALF_UP)
        .intValueExact(); // 13
~~~

The model in option 3 is transparent: **rounding is a business decision**, while `intValueExact` checks whether the post-rounding conversion still fits in the `int` range.

With negative numbers:

~~~java
BigDecimal minus = new BigDecimal("-12.6");

int towardZero = minus.intValue(); // -12
int floor = minus.setScale(0, RoundingMode.FLOOR)
        .intValueExact(); // -13
~~~

Truncating toward 0 differs from `FLOOR` when numbers are negative. Do not use the vague phrase "round down" when the two behaviors must be distinguished.

## 13. Distinguishing precision and scale During Lookup

`BigDecimal` represents values according to:

~~~text
value = unscaledValue × 10^(-scale)
~~~

- `scale()`: decimal scaling factor; can be positive, 0, or negative.
- `precision()`: number of digits in the unscaled value, excluding sign.
- `setScale(n, mode)`: changes scale to `n`, rounding if necessary.
- `round(new MathContext(p, mode))`: limits to at most `p` significant digits, without fixing digits after the decimal point.

Example:

~~~java
BigDecimal amount = new BigDecimal("123.4500");
System.out.println(amount.precision()); // 7
System.out.println(amount.scale());     // 4
~~~

| Requirement | Appropriate API |
|---|---|
| Display exactly two decimal places per business rules | Round/normalize using `setScale(2, mode)` before formatting |
| Keep three significant digits | `round(new MathContext(3, mode))` |
| Strip only trailing zeros that do not affect value | `stripTrailingZeros()`, noting it can change scale |
| Reduce scale while strictly forbidding value change | `setScale(newScale, RoundingMode.UNNECESSARY)` |
| Divide to exactly two digits after the decimal point | `divide(divisor, 2, mode)` |
| Divide by significant digits | `divide(divisor, new MathContext(p, mode))` |

`stripTrailingZeros()` preserves value, yet can alter `equals()` because scale changes. For example, `new BigDecimal("1000.00").stripTrailingZeros()` can turn into `1E+3`. Do not apply it if the contract must keep the exact original scale.

### HALF_UP and HALF_EVEN

~~~java
BigDecimal x = new BigDecimal("1.245");

System.out.println(x.setScale(2, RoundingMode.HALF_UP));
// 1.25

System.out.println(x.setScale(2, RoundingMode.HALF_EVEN));
// 1.24
~~~

`HALF_UP` chooses away from 0 at exact midpoints; `HALF_EVEN` chooses the kept last digit to be even at exact midpoints. Which policy is right depends on calculation requirements, not which produces a "nicer-looking" string.

## 14. Complete Java 17+ Example: Parse, Format, and Exact Lookup

Create the file `NumericConversionReference.java`:

~~~java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParseException;
import java.util.Locale;

public class NumericConversionReference {
    static void expectedFailure(String name, Runnable operation) {
        try {
            operation.run();
            System.out.println(name + ": unexpectedly succeeded");
        } catch (ArithmeticException | NumberFormatException ex) {
            System.out.println(name + ": " + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) throws ParseException {
        System.out.println("parse int radix: " +
                Integer.parseInt("7F", 16));
        System.out.println("decode: " + Integer.decode("0x2A"));
        System.out.println("unsigned: " + Integer.toUnsignedString(
                Integer.parseUnsignedInt("4294967295")));
        System.out.println("parse long: " +
                Long.parseLong("9000000000"));
        System.out.println("parse double NaN: " + Double.isNaN(
                Double.parseDouble("NaN")));
        System.out.println("big integer: " +
                new BigInteger("FF", 16));

        BigDecimal decimal = new BigDecimal("123.4500");
        System.out.println("decimal: " + decimal.toPlainString()
                + ", precision=" + decimal.precision()
                + ", scale=" + decimal.scale());

        BigDecimal scientific = new BigDecimal("1E+4");
        System.out.println("strings: " + scientific
                + " | " + scientific.toEngineeringString()
                + " | " + scientific.toPlainString());

        System.out.println("exact int: " +
                new BigDecimal("12.000").intValueExact());
        System.out.println("truncating int: " +
                new BigDecimal("12.9").intValue());

        expectedFailure("fraction", () ->
                new BigDecimal("12.9").intValueExact());
        expectedFailure("out-of-range", () ->
                Math.toIntExact(2147483648L));
        expectedFailure("big-integer range", () ->
                new BigInteger("2147483648").intValueExact());

        System.out.println("HALF_UP: " +
                new BigDecimal("1.245").setScale(2, RoundingMode.HALF_UP));
        System.out.println("HALF_EVEN: " +
                new BigDecimal("1.245").setScale(2, RoundingMode.HALF_EVEN));

        DecimalFormat format = (DecimalFormat)
                NumberFormat.getNumberInstance(Locale.US);
        format.setGroupingUsed(true);
        format.setMinimumFractionDigits(2);
        format.setMaximumFractionDigits(2);
        format.setRoundingMode(RoundingMode.HALF_UP);

        System.out.println("formatted: " +
                format.format(new BigDecimal("12345.675")));

        format.setParseBigDecimal(true);
        BigDecimal parsed = (BigDecimal) format.parse("1,234.50");
        System.out.println("localized parse: " + parsed.toPlainString());

        System.out.println("valueOf double: " +
                BigDecimal.valueOf(0.1));
        System.out.println("binary constructor: " +
                new BigDecimal(0.1));
    }
}
~~~

Run:

~~~bash
javac NumericConversionReference.java
java NumericConversionReference
~~~

Stdout:

~~~text
parse int radix: 127
decode: 42
unsigned: 4294967295
parse long: 9000000000
parse double NaN: true
big integer: 255
decimal: 123.4500, precision=7, scale=4
strings: 1E+4 | 10E+3 | 10000
exact int: 12
truncating int: 12
fraction: ArithmeticException
out-of-range: ArithmeticException
big-integer range: ArithmeticException
HALF_UP: 1.25
HALF_EVEN: 1.24
formatted: 12,345.68
localized parse: 1234.50
valueOf double: 0.1
binary constructor: 0.1000000000000000055511151231257827021181583404541015625
~~~

The output ties to the following rules:

- `Integer.parseInt("7F",16)` is 127; `decode("0x2A")` accepts the hex prefix and returns 42.
- `Integer.parseUnsignedInt("4294967295")` stores the bit pattern; `toUnsignedString` displays it back as an unsigned value.
- `new BigDecimal("123.4500")` preserves precision 7, scale 4.
- `1E+4` in engineering notation becomes `10E+3`, while plain is `10000`.
- `intValueExact` accepts 12.000 because it has no nonzero fractional part, and rejects 12.9 and out-of-range numbers.
- `HALF_UP` and `HALF_EVEN` differ at the midpoint 1.245.
- `DecimalFormat` uses `Locale.US` and `HALF_UP` explicitly; parsing back the formatted string yields the rounded value.
- `new BigDecimal(0.1)` exposes the binary value of `double`, unlike the two short decimal string approaches above.

`expectedFailure` is used only in the demo to turn expected exceptions into testable output lines. In business code, do not catch `ArithmeticException`/`NumberFormatException` and silently continue unhandled; return an appropriate error or process input per the contract.

## 15. Quick Selection Table by Need

| Practical Need | Choose | Avoid |
|---|---|---|
| Read small decimal integer within int range | `Integer.parseInt(s, 10)` | `Double.parseDouble` then cast |
| Read integer exceeding long | `new BigInteger(s)` | Parsing long then trying to fix overflow |
| Read exact money/decimal | `new BigDecimal(validatedString)` | `new BigDecimal(double)` from decimal input |
| Read hex with `0x` prefix | `Integer.decode(s)` if octal policy fits | `parseInt(s,16)` directly on `0x...` |
| Read hex without prefix | `Integer.parseInt(s,16)` or `new BigInteger(s,16)` | Using `decode` and ignoring source syntax |
| Read unsigned 32-bit | `Integer.parseUnsignedInt` and output `toUnsignedString` | Treating resulting `int` as a positive signed number |
| Exact long-to-int conversion | `Math.toIntExact` | `(int) longValue` if overflow is possible |
| Exact BigDecimal-to-int conversion | `intValueExact()` | `intValue()` or casting via double |
| Exact BigDecimal-to-BigInteger conversion | `toBigIntegerExact()` | `toBigInteger()` if fractional truncation is unwanted |
| Round decimal to 2 places | `setScale(2, mode)` | `intValue()`; `MathContext(2)` when 2 fractional digits are meant |
| Print number without `E` | `toPlainString()` | Assuming it preserves negative scale after re-parsing |
| Print number for BigDecimal scale round-trip | `toString()` | `toEngineeringString()` as mandatory storage format |
| Display grouping and decimal separators | `DecimalFormat`/`NumberFormat` with `Locale` | Ad-hoc string insertion of separators |
| Parse number with locale grouping | `NumberFormat.parse` + full-string check | `BigDecimal(String)` directly on `1,234.50` |
| Parse double accepting only finite values | `Double.parseDouble` then `Double.isFinite` | Relying solely on parse exceptions |
| Parse null/blank | Define missing or invalid policy first | Unboxing/casting null to primitive |
| Sum integers that may overflow | `Math.addExact`/`BigInteger` or suitable wide type | Adding ints then casting the result afterward |
| Output JSON for cross-system exchange | Finite/decimal numbers per schema, handle nonfinite separately | Emitting `NaN`/`Infinity` directly as standard JSON numbers |

## 16. Common Traps

### 16.1. Parsing Numbers That Look Right but Have the Wrong Format

~~~java
// "01" with decimal parseInt is 1.
// "01" with Integer.decode is octal, though the value is also 1.
// "010" with parseInt decimal is 10.
// "010" with Integer.decode is 8.
~~~

If data contains numbers with leading zeros, do not replace `parseInt` with `decode` unless the contract genuinely allows octal.

### 16.2. Fast Conversion That Silently Drops Fractions

`BigDecimal.intValue()` does not throw an error just because `.9` is present. If rules require the entire value to be exact, use `intValueExact()`. If rounding is desired, round according to policy first and then convert exact.

### 16.3. Using DecimalFormat to Normalize Internal Values

Formatting is a **presentation** step; it can round and depends on locale. Do not convert numbers to strings with grouping separators and re-parse them inside core calculation logic just to look "prettier." Keep `BigDecimal` as the numeric type in algorithms and format at the output boundary.

### 16.4. Confusing Value Exactness with Representation Exactness

`BigDecimal("1.20").compareTo(BigDecimal("1.2")) == 0`, yet `equals` is false because the scales differ. `intValueExact()` only guarantees the integer suffers no value loss; it does not preserve the original "two decimal digits." If scale is part of the contract, store/check scale separately.

### 16.5. Not Distinguishing Parse Errors from Range Errors

`Integer.parseInt("abc")` throws `NumberFormatException` due to invalid syntax. `Integer.parseInt("2147483648")` also throws `NumberFormatException` because it exceeds `int` range. If an API needs distinct error messages, validate syntax first, then parse into `BigInteger` or check ranges systematically; do not assume every `NumberFormatException` is a bad-character error.

### 16.6. Dividing by 0 or Infinite Decimal Division Without a Policy

`BigDecimal.ONE.divide(BigDecimal.ZERO)` fails; `BigDecimal.ONE.divide(new BigDecimal("3"))` can also fail because there is no finite decimal expansion. Yet the causes differ. If the result is allowed to be rounded, explicitly specify precision/scale and rounding mode.

### 16.7. Using Default Formatting for Interchange Contracts

The default locale or separator settings can vary across machines. Pass an explicit `Locale` when displaying, and use a protocol-invariant format when serializing. Do not treat UI grouping separators as a required part of Java's canonical number representation.

### 16.8. Locale Parsers May Ignore Trailing Text

Use `ParsePosition` and check `getIndex() == input.length()`. For strict formatting requirements, combine with an additional validation step, because the parser can be lenient with grouping.

### 16.9. Boxing and Null

`Integer.valueOf(s)` returns a wrapper; `Integer.parseInt(s)` returns a primitive. An `Integer` can be null, and auto-assigning it to `int` causes `NullPointerException`. Parsing/conversion should handle nullable input explicitly before performing arithmetic.

## 17. Reference Exercises and Answers

**Question 1.** Parse the string `"7F"` to 127 in base 16.

**Answer:**

~~~java
int value = Integer.parseInt("7F", 16); // 127
~~~

**Question 2.** Convert `new BigDecimal("20.000")` to `int` while rejecting any case of value loss.

**Answer:**

~~~java
int exact = new BigDecimal("20.000").intValueExact(); // 20
~~~

The scale may be nonzero, but the fractional digits must all be 0.

**Question 3.** Why is `new BigDecimal("20.3").intValue()` unsuitable if the input must be an exact integer?

**Answer:** Because it truncates the fractional part and yields 20. Use `intValueExact()` to throw `ArithmeticException`.

**Question 4.** What does `Math.toIntExact(2147483648L)` do?

**Answer:** Throws `ArithmeticException` because 2,147,483,648 is outside the signed `int` range.

**Question 5.** You need to read `"1,234.50"` using `Locale.US` rules. Can you use `new BigDecimal(String)` directly?

**Answer:** No; the string contains grouping separators. Use a locale parser such as `NumberFormat`/`DecimalFormat` with `Locale.US`, enable BigDecimal parsing as appropriate, and validate full-string consumption per strict requirements.

**Question 6.** Compare `new BigDecimal("0.1")` with `new BigDecimal(0.1)`.

**Answer:** The `String` form represents decimal 0.1 exactly. The `double` constructor stores the exact binary double value, which is typically displayed with many decimal digits.

**Question 7.** You want to print `new BigDecimal("1E+4")` in plain form without `E` and still preserve scale -4 when re-parsed: is a `toPlainString()` string sufficient?

**Answer:** No; `toPlainString()` produces `"10000"`, which parses back with scale 0. If scale must be preserved, `toString()` is the appropriate canonical format.

**Question 8.** After `Integer.parseUnsignedInt("4294967295")`, why does `System.out.println(value)` print -1?

**Answer:** The 32-bit all-ones value is stored in a signed `int`. Printing as signed produces -1; use `Integer.toUnsignedString(value)` to display the unsigned number.

**Question 9.** Does parsing `"NaN"` into a double throw an error? How do you reject it?

**Answer:** `Double.parseDouble("NaN")` returns NaN. Check `Double.isFinite(value)` and reject if false.

**Question 10.** You need to round `1.245` to two decimal places using HALF_EVEN and then convert exact if the result is an integer; how many steps are involved?

**Answer:** First, `setScale(2, RoundingMode.HALF_EVEN)` yields `1.24`. Second, `intValueExact()` throws `ArithmeticException` because the result still has a nonzero fractional part. Rounding to two decimal places does **not** automatically make a value an integer.

---

**Takeaway:** Choose the API by the question: **parse** from strings with the right radix/locale, **format** numbers to strings per display requirements, and **convert exact** when no value loss is allowed. When rounding control is needed, perform it with `BigDecimal` using an explicit scale/precision and `RoundingMode`; then use `...Exact()` APIs to detect values that cannot fit in the target type. Never substitute silent truncation, wrap-around, or reformatting for an error without a business contract.
