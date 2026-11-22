# `ParsePosition` and Whole-String Validation When Parsing by Locale in Java

## 1. Goal: parsing a prefix does not guarantee valid data

When receiving a numeric string formatted under regional conventions (locale), `NumberFormat` or `DecimalFormat` can **successfully read a leading portion of the string and then stop**. A non-`null` `Number` result **does not guarantee the entire input string was consumed**.

For example, under German conventions, where dots separate thousands and commas mark decimals:

~~~text
Input:     "1.234,56 kg"
            └──────┘└─┘
             Number  Remainder

Numeric result: 1234.56
Consumed:       8 characters out of 11 characters
~~~

If software accepts a field that "may only contain a number", accepting `1234.56` and ignoring `" kg"` is a validation bug. The core tool for detecting this case is `java.text.ParsePosition`.

After this lesson, you will know how to:

- Use `NumberFormat.parse(String, ParsePosition)` and `DecimalFormat` to parse by `Locale`.
- Distinguish a successful **prefix** parse from consuming the **entire string**.
- Properly understand `getIndex()`, `getErrorIndex()`, `null`, starting indices, and `ParsePosition` state.
- Write strict parsing methods in Java 17: verifying numeric type, whole-string consumption, and business range.
- Distinguish the limits of whole-string checking from grouping syntax validation, whitespace characters, `NaN`/`Infinity`, precision, and out-of-range values.

## 2. `Locale` changes the meaning of number separators

Java provides different number representations depending on `Locale`. Common examples:

| Locale | String representing one thousand two hundred thirty-four point five six |
| --- | --- |
| `Locale.US` | `"1,234.56"` |
| `Locale.GERMANY` | `"1.234,56"` |

The same character `,` or `.` can be interpreted as a decimal separator, a grouping separator, or invalid relative to the expected representation. Therefore, do not rely on the OS default locale when formatting or parsing exchange data with a fixed contract.

~~~java
NumberFormat german = NumberFormat.getNumberInstance(Locale.GERMANY);
NumberFormat american = NumberFormat.getNumberInstance(Locale.US);
~~~

This snippet assumes `java.text.NumberFormat` and `java.util.Locale` are imported, and is placed inside a method.

Factors to distinguish:

- **Locale of the data:** how the string was generated or entered by the user, e.g., German or US.
- **Process default locale:** can change depending on the machine, deployment environment, or other code.
- **Formatting contract:** beyond locale, the application must also specify whether grouping, whitespace, minus signs, exponents, or unit suffixes are allowed.

`NumberFormat.getNumberInstance(Locale.GERMANY)` helps read numbers under the German locale; it **does not** automatically turn the parser into a strict validator of all business rules.

## 3. `NumberFormat.parse(String)` and `parse(String, ParsePosition)`

`NumberFormat` has two important usage patterns.

**Convenience form:**

~~~java
NumberFormat format = NumberFormat.getNumberInstance(Locale.GERMANY);
Number value = format.parse("1.234,56 kg"); // May accept a number from a prefix.
~~~

This is an illustrative snippet inside a method declaring `throws ParseException` or a `try/catch`. The `parse(String)` overload throws `ParseException` when it cannot parse from the start position, yet **has no contract requiring it to consume the entire string**. Do not treat the absence of an exception as "whole-input validation".

**Position-tracking form:**

~~~java
NumberFormat format = NumberFormat.getNumberInstance(Locale.GERMANY);
ParsePosition pos = new ParsePosition(0);
Number value = format.parse("1.234,56 kg", pos);

System.out.println(value);          // 1234.56
System.out.println(pos.getIndex()); // 8
~~~

In the `ParsePosition` overload:

- The return value is a `Number` if an acceptable leading portion was parsed.
- It can return `null` when no number is recognized.
- `pos.getIndex()` reflects the position immediately after the successfully parsed portion.
- `pos.getErrorIndex()` can provide error position info when parsing fails; it **does not** replace checking whether the entire input was consumed.

For a number-only form field, basic logic must simultaneously check **`value != null`** and **`pos.getIndex() == input.length()`**.

## 4. What does `ParsePosition` store?

`java.text.ParsePosition` is a mutable state object carrying two main pieces of information:

| API | Meaning |
| --- | --- |
| `new ParsePosition(startIndex)` | Starts parsing at the specified UTF-16 index |
| `getIndex()` | Start/current index; upon successful parse, the position immediately after the consumed portion |
| `setIndex(index)` | Selects a new starting position |
| `getErrorIndex()` | Error index reported by the parser; may be -1 if no error info is set |
| `setErrorIndex(index)` | Allows changing the error index state |

`ParsePosition` does not hold the source string and does not specify a locale; the locale is configured on `NumberFormat`/`DecimalFormat`.

### Java `String` indexing convention

Position indices use **UTF-16 code units**, the same indexing unit as `String.length()`. Consequently, the end-of-string check is:

~~~java
pos.getIndex() == input.length()
~~~

Do not compare `ParsePosition` against Unicode code point counts (`codePointCount`) or UTF-8 byte lengths. If the input contains supplementary characters outside the BMP, the UTF-16 code unit count and code point count can differ; `String.length()` remains the matching unit for parser indices.

### `ParsePosition` is not a Boolean success flag

An example where a prefix parses yet invalid trailing characters remain:

~~~java
String text = "1.234,56 kg";
ParsePosition pos = new ParsePosition(0);
Number parsed = NumberFormat.getNumberInstance(Locale.GERMANY).parse(text, pos);

boolean hasNumber = parsed != null;               // true
boolean consumedAll = pos.getIndex() == text.length(); // false
~~~

Relying only on `hasNumber` causes the program to accept bad data. Checking only `getErrorIndex() == -1` also risks accepting bad data: recording no error when the parser **intentionally stops after a valid prefix** does not mean the remainder was validated.

## 5. Recipe for whole-string validation

For data that must begin at the first character and allow no trailing remainder, the basic pattern is:

~~~java
static Number parseEntire(String text, Locale locale) {
    if (text == null || text.isEmpty()) {
        throw new IllegalArgumentException("Missing numeric text");
    }

    NumberFormat parser = NumberFormat.getNumberInstance(locale);
    ParsePosition pos = new ParsePosition(0);
    Number number = parser.parse(text, pos);

    if (number == null || pos.getIndex() != text.length()) {
        throw new IllegalArgumentException("Invalid or trailing characters");
    }
    return number;
}
~~~

This is an **illustrative method** placed in a Java class, requiring imports for `NumberFormat`, `ParsePosition`, and `Locale`.

The condition has two mandatory parts:

1. `number != null` — a value was parsed.
2. `pos.getIndex() == text.length()` — the parser read right up to the end of the string.

Do not increment the index manually. Do not strip suffixes before comparing, because doing so destroys evidence that the input string contained extra data.

**The definition of "whole string" must be decided upfront.** If the application permits leading/trailing whitespace around numbers, you can apply `trim()` per contract before parsing and compare against the **length of the normalized string**. If whitespace is disallowed, keep `text` untouched and require every character to be consumed.

## 6. Distinguishing parse failure, prefix success, and whole-input success

With a German number parser:

| Text | Expected prefix result | Whole string read? | Conclusion when field allows only a number |
| --- | --- | --- | --- |
| `"1.234,56"` | 1234.56 | Yes | Accept if business rules are met |
| `"1.234,56 kg"` | 1234.56 | No | Reject trailing remainder |
| `"12,5abc"` | 12.5 | No | Reject trailing remainder |
| `"abc"` | Fails from start | No | Reject |
| `""` | No number | No | Reject |
| `"-5"` | −5 | Yes | Still must validate value range |
| `"1.234,56"` under US locale | May be misread or stop early | Intent cannot be inferred | Use the locale matching the contract |

The table intentionally avoids equating "parsed a number" with "valid". A string can be fully consumed yet still be **out of range**, or accepted by the parser under relatively lenient grouping rules.

## 7. `NumberFormat` returns `Number`: watch type and precision

`NumberFormat.parse` returns the abstract type `Number`. Depending on format and value, the result may be represented by an integer or floating-point wrapper. Do not assume every result is always `Double` and cast blindly:

~~~java
Number value = NumberFormat.getNumberInstance(Locale.GERMANY)
        .parse("123", new ParsePosition(0));
double asDouble = value.doubleValue(); // retrieves the value as a double
~~~

The example above illustrates reading a value; by itself it **does not validate the whole string**. Moreover, `doubleValue()` can lose precision for large integers or decimal values with many digits.

For money or decimal data needing exact digits, on standard JDKs `NumberFormat.getNumberInstance(Locale.GERMANY)` returns a `DecimalFormat`. You can configure:

~~~java
DecimalFormat parser =
        (DecimalFormat) NumberFormat.getNumberInstance(Locale.GERMANY);
parser.setParseBigDecimal(true);
~~~

When parsing normal decimal numbers, `DecimalFormat` can return `BigDecimal`, avoiding an intermediate conversion through binary64 before validating and using the decimal result. However, **do not blindly cast every result to `BigDecimal`**: special values like `NaN`/`Infinity` may be represented by another type under the `DecimalFormat` contract. Check `instanceof BigDecimal` before using it.

Only cast with `(DecimalFormat)` when you know the implementation provides `DecimalFormat` (common numeric locales in standard JDKs). In environments integrating custom providers, check `instanceof` and reject unsupported formatter types to prevent `ClassCastException`.

## 8. Complete decimal parser example: whole string, numeric range, and result type

Suppose an application accepts decimal quantities under German conventions, allowing:

- Values from **0 to 10,000**, inclusive.
- German locale grouping and decimal comma.
- No trailing characters or units at the end.
- No `NaN`/`Infinity`.
- Retaining `BigDecimal` representation to inspect decimals and avoid binary64 rounding before validation.

Applicable method:

~~~java
static BigDecimal parseGermanAmount(String input) {
    if (input == null || input.isEmpty()) {
        throw new IllegalArgumentException("Missing number");
    }

    NumberFormat base = NumberFormat.getNumberInstance(Locale.GERMANY);
    if (!(base instanceof DecimalFormat parser)) {
        throw new IllegalStateException("DecimalFormat is required");
    }
    parser.setParseBigDecimal(true);

    ParsePosition pos = new ParsePosition(0);
    Number result = parser.parse(input, pos);

    if (!(result instanceof BigDecimal value)
            || pos.getIndex() != input.length()) {
        throw new IllegalArgumentException("Invalid number or trailing text");
    }

    if (value.signum() < 0
            || value.compareTo(new BigDecimal("10000")) > 0) {
        throw new IllegalArgumentException("Out of allowed range");
    }
    return value;
}
~~~

This is a **member method** to place inside a Java 17+ class, requiring imports for `BigDecimal`, `DecimalFormat`, `NumberFormat`, `ParsePosition`, and `Locale`.

Key points:

1. The `input` parameter must not be null or empty.
2. Create the parser **with an explicit locale**, independent of the default locale.
3. Enable `setParseBigDecimal(true)` before parsing.
4. Start from index **0**.
5. Require a `BigDecimal` return and an end position equal to `input.length()`.
6. Only afterward check the decimal range `[0, 10000]` using `signum` and `compareTo`.

`value.compareTo(new BigDecimal("10000"))` compares arithmetic value regardless of the `BigDecimal`'s scale. `new BigDecimal("10000")` takes the exact decimal number 10000 from the string.

Creating a new `NumberFormat` per call avoids sharing a stateful `DecimalFormat` across multiple threads. `NumberFormat` should not be shared between threads without separate synchronization per Java API guidance.

## 9. Complete Java 17+ program

Save as `LocaleParsePositionDemo.java`:

~~~java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

public class LocaleParsePositionDemo {
    static BigDecimal parseGermanAmount(String input) {
        if (input == null || input.isEmpty()) {
            throw new IllegalArgumentException("Missing number");
        }

        NumberFormat base = NumberFormat.getNumberInstance(Locale.GERMANY);
        if (!(base instanceof DecimalFormat parser)) {
            throw new IllegalStateException("DecimalFormat is required");
        }
        parser.setParseBigDecimal(true);

        ParsePosition pos = new ParsePosition(0);
        Number result = parser.parse(input, pos);

        if (!(result instanceof BigDecimal value)
                || pos.getIndex() != input.length()) {
            throw new IllegalArgumentException("Invalid or trailing text");
        }
        if (value.signum() < 0
                || value.compareTo(new BigDecimal("10000")) > 0) {
            throw new IllegalArgumentException("Outside [0, 10000]");
        }
        return value;
    }

    public static void main(String[] args) {
        NumberFormat german = NumberFormat.getNumberInstance(Locale.GERMANY);
        String withSuffix = "1.234,56 kg";
        ParsePosition pos = new ParsePosition(0);
        Number prefix = german.parse(withSuffix, pos);

        System.out.println("prefix=" + prefix);
        System.out.println("consumed=" + pos.getIndex() + "/" + withSuffix.length());
        System.out.println("full=" + (pos.getIndex() == withSuffix.length()));

        System.out.println("strict=" + parseGermanAmount("1.234,56"));
        System.out.println("plain=" + parseGermanAmount("1234,56"));
        System.out.println("zero=" + parseGermanAmount("0"));

        String[] invalid = {
            "1.234,56 kg", "12,5abc", "abc", "", "-5", "20.000,00"
        };
        for (String text : invalid) {
            try {
                parseGermanAmount(text);
                System.out.println("accepted=" + text);
            } catch (IllegalArgumentException ex) {
                System.out.println("rejected=" + text);
            }
        }

        ParsePosition badPos = new ParsePosition(0);
        Number bad = german.parse("abc", badPos);
        System.out.println("failed=" + (bad == null));
        System.out.println("errorIndex=" + badPos.getErrorIndex());
    }
}
~~~

Compile/run on JDK 17 or newer:

~~~bash
javac --release 17 LocaleParsePositionDemo.java
java LocaleParsePositionDemo
~~~

Expected stdout on the standard locale data provider of JDK 17+:

~~~text
prefix=1234.56
consumed=8/11
full=false
strict=1234.56
plain=1234.56
zero=0
rejected=1.234,56 kg
rejected=12,5abc
rejected=abc
rejected=
rejected=-5
rejected=20.000,00
failed=true
errorIndex=0
~~~

Explanation:

- `NumberFormat.parse(withSuffix, pos)` reads a number from the leading `"1.234,56"` and stops at index 8, before `" kg"`.
- `parseGermanAmount` uses `setParseBigDecimal(true)` and requires the parser to consume the **entire string**, thus rejecting suffixes, units, and trailing characters.
- `"abc"` produces no value from index 0; `getErrorIndex()` is printed for inspection, yet does not replace `value != null` and position comparison.
- Negative `"-5"` and `"20.000,00"` parse as numbers but lie outside the business range `[0, 10000]`, so they are rejected.
- Empty strings are rejected before parsing.

If the JVM uses a customized locale provider, locale representations/properties may differ from the standard dataset; systems should pin environments and test actual locale rules when strict compatibility is required.

## 10. When is `getErrorIndex()` used?

`ParsePosition.getErrorIndex()` is meaningful when the parser **cannot recognize a number** and wants to indicate the suspected failure index. For instance, if the German number parser hits `"abc"` at index 0, the result can be `null` and the error index set to 0.

However, distinguish:

- **Fails from the start:** `value == null`. The success index may stay unchanged, and `getErrorIndex()` may point to where it failed.
- **Parses a prefix:** `value != null`, `index < length`. The parser does not necessarily treat the remainder as an error; `errorIndex` may still be -1.
- **Parsed completely:** `value != null` and `index == length`. Only this satisfies the basic "whole input" validation requirement.

Do not write:

~~~java
// Insufficient to guarantee the entire string is valid:
boolean valid = pos.getErrorIndex() == -1;
~~~

Do not check `getErrorIndex() >= 0` in place of `pos.getIndex() != text.length()`. `getErrorIndex()` is neither a global lexical error report nor a business-rule validator.

If you want to report the position of trailing junk after a successful prefix parse, use:

~~~java
int firstUnconsumed = pos.getIndex();
if (firstUnconsumed < input.length()) {
    // Can report: unaccepted characters starting at firstUnconsumed.
}
~~~

This is an illustrative snippet after parsing, not a standalone program. Distinguish UTF-16 indices from display indices in user interfaces that may count code points or grapheme clusters.

## 11. Starting at a non-zero index, reusing `ParsePosition`, and end checks

`ParsePosition` allows parsing a number starting in the **middle** of a string. This is useful when an application has a protocol with a fixed prefix:

~~~java
String text = "qty=1.234,56";
ParsePosition pos = new ParsePosition(4);

Number n = NumberFormat.getNumberInstance(Locale.GERMANY).parse(text, pos);
System.out.println(n);              // 1234.56
System.out.println(pos.getIndex()); // 12
~~~

In this case, you **intentionally skipped the first four characters** `"qty="`. Checking `pos.getIndex() == text.length()` only proves consumption from the starting position to the end of the string; it does not verify the prefix itself. Separately validate `text.startsWith("qty=")` (or the protocol grammar) and choose index 4 deliberately.

For a field containing only a number, **always start from index 0**; do not pick another index and call it "whole-string parsing".

### `ParsePosition` is a stateful object

If you reuse the same `ParsePosition` instance, a subsequent parse may **start from the old index**. Error state may also linger or change depending on parser behavior. The easiest pattern to control is creating a `new ParsePosition(0)` for **each input string**.

~~~java
ParsePosition first = new ParsePosition(0);
ParsePosition second = new ParsePosition(0);
~~~

Do not share the same mutable `ParsePosition` across threads without managing synchronization yourself.

## 12. Whole-string checks are still not strict syntax validation

`NumberFormat`/`DecimalFormat` is designed to handle locale number formatting; in many configurations, the parser can be **lenient** with grouping or notations an application does not want to accept. The condition `index == length` only guarantees the parser consumed all characters according to **the grammar accepted by that parser**.

For example, requiring currency data to match `"1.234,56"` strictly without accepting arbitrary grouping positions may need an extra format validation step.

Options:

1. **Relatively flexible locale number contract:** parse with `NumberFormat`, check whole-input, type, and range. Suitable when parser-accepted variations are fine.
2. **Disallow grouping separators:** create a `DecimalFormat`, set `setGroupingUsed(false)`, and check whole-input; still test accepted special forms.
3. **Require exact grouping placement and strict syntax:** validate grammar with dedicated locale-tested rules; `DecimalFormat` parsing afterward is solely the value-extraction step. Do not expect `index == length` alone to enforce thousands-grouping structure.
4. **Machine-to-machine data exchange:** better to use a **locale-invariant** format, such as ASCII decimal with `.` and explicit rules, instead of depending on user display languages.

### Why not just round-trip format and compare against input?

One idea is to parse, then `format(value)`, and compare with the input string. That approach can **reject valid strings** because the formatter dictates fractional digits, grouping, leading zeros, plus signs, and pattern rounding. If strict exact formatting is desired, define **one unique canonical form** and build matching validation; you cannot assume every user string must equal formatter output.

## 13. Distinguishing `NumberFormat` from `Double.parseDouble`

| Aspect | `Locale`-based `NumberFormat` | `Double.parseDouble` |
| --- | --- | --- |
| Decimal separator | Locale-dependent, e.g., Germany uses `,` | Java syntax uses `.` |
| Grouping separator | Can handle per locale | Does not support grouping like `1,234.56` |
| Invalid suffix | Can parse a prefix and stop | Typically throws `NumberFormatException` if string breaks grammar |
| Whole-string check mechanism | `ParsePosition` and `getIndex()` | Parser validates whole-string syntax per Java grammar |
| Return value | `Number`; `DecimalFormat` can be configured for `BigDecimal` | Primitive `double` |
| NaN/Infinity | Handled per locale symbols and implementation | `"NaN"`, `"Infinity"` per Java syntax |
| Decimal exactness | Use `setParseBigDecimal(true)` with `DecimalFormat` | Binary64, subject to rounding |

Choose the API based on the **source format**. If users enter localized numbers, `NumberFormat` is the right tool but requires complete validation. If the system receives a decimal protocol with a uniform dot, `Double.parseDouble` or `BigDecimal(String)` can be simpler; business data must still be checked (value range, `NaN`/`Infinity`, precision).

## 14. Notes on special numbers, negatives, and `BigDecimal`

`DecimalFormat.setParseBigDecimal(true)` does not mean **every** result is a `BigDecimal`. Non-ordinary numeric values, especially localized `NaN`/`Infinity`, may be returned as `Double`. Hence:

~~~java
if (!(result instanceof BigDecimal amount)) {
    throw new IllegalArgumentException("Expected a finite decimal value");
}
~~~

is a deliberate check when the contract allows only finite decimals. It also prevents `ClassCastException`.

On the other hand, `BigDecimal` supports negatives, zero, and tiny decimals; enforcing a range (such as ≥0) is **another validation step**. Requirements like "exact two decimal digits", "at most three fractional digits", "no negatives", or "must lie in `[0, 10000]`" do not arise automatically from locale configuration.

For money or ratios needing decimal precision, store `BigDecimal` and use `compareTo` for range checks. Do not convert to `double` just to check bounds and then convert back to `BigDecimal`: that round-trip can lose digits.

## 15. Trimming, whitespace, and Unicode characters

A user form may submit `" 1.234,56 "`. There are at least two reasonable designs:

- **Strict raw input:** do not allow leading/trailing whitespace; keep the text as-is and force the parser to consume all of it.
- **Normalize then strict:** if the contract permits boundary whitespace, normalize the input first (e.g., `strip()` or `trim()` per character rules) and then parse the entire **normalized** string.

Do not call `trim()` merely out of convenience: for protocols, digital signatures, or archival data, altering input may be disallowed. `String.strip()` and `String.trim()` do not treat all Unicode space characters identically; non-breaking spaces used for grouping in some locales may need special handling.

Also distinguish:

- **Boundary whitespace:** before/after the entire number.
- **Grouping separator:** valid locale digit-group delimiter, which may resemble a space.
- **Trailing units:** e.g., `" kg"`, which should not be ignored in a number-only field.
- **Unicode digit-like characters:** do not silently normalize to ASCII if the system has not specified it.

For whole-string validation, the string after any normalization step is the one used for `length()`; do not compare the original raw length against an index from a modified string.

## 16. Performance, thread safety, and input security

`NumberFormat`/`DecimalFormat` are stateful configuration objects (pattern, symbols, grouping, `parseBigDecimal`). When running concurrently:

- Do not share a single mutable formatter across threads without proper synchronization.
- Create a **new** formatter per request, or use a thread-confined mechanism if profiling shows optimization is needed.
- `ParsePosition` is also mutable; creating a fresh one per parse prevents unintended reuse of index and error index.

For external data:

- Enforce reasonable input length limits to prevent excessive parsing cost.
- Do not accept abnormally long inputs just because the parser can extract a prefix at the start.
- Explicitly define locale, separators, negative sign rules, and value ranges.
- If error messages include user text, escape/log per policy to prevent log injection and sensitive data exposure.
- For financial and precision-critical data, do not coerce to `double` unnecessarily.

## 17. Common mistakes

| Mistake | Consequence | Proper fix |
| --- | --- | --- |
| Using only `NumberFormat.parse(text)` | Can ignore trailing suffixes | `parse(text, new ParsePosition(0))` then check index |
| Checking only `number != null` | Valid prefix still slips through | Also require `index == text.length()` |
| Checking only `getErrorIndex() == -1` | Misses unconsumed trailing characters | Check consumed index |
| Using `new ParsePosition(4)` for a number-only field | Skips the first 4 characters | Start at index 0 |
| Reusing an old `ParsePosition` without resetting | Next parse starts at the wrong index | Create a new one per parse |
| Comparing with `String.codePointCount` or byte length | Wrong index unit | Use `String.length()` |
| Parsing with the server's default locale | Different machines interpret marks differently | Specify `Locale` explicitly |
| Casting every `Number` to `Double` | Potential `ClassCastException` | Use `Number`/`instanceof` and convert deliberately |
| Casting every `DecimalFormat` result to `BigDecimal` | `NaN`/`Infinity` may use another type | Check `instanceof BigDecimal` |
| Thinking full consumption proves valid grouping | Parser may accept flexible grouping forms | Add lexical/pattern validation |
| Thinking successful parse means valid range | Negatives or huge values still parse | Validate business range |
| Calling `doubleValue()` for decimal money | Can lose precision | Use `BigDecimal` directly |
| Sharing formatters across threads | Mutable state, race bugs | Create per scope or synchronize properly |
| Calling `trim()` without updating comparison length | Mismatched text and index | Compare against length of the actually parsed string |

## 18. Self-check questions

**Question 1.** Why can `parse("1.234,56 kg")` succeed under the German locale even though the data is invalid?

**Answer:** The parser reads the prefix `"1.234,56"` as 1234.56, without necessarily consuming `" kg"`. A number-only field must check `ParsePosition.getIndex() == text.length()`.

**Question 2.** If `getErrorIndex() == -1`, is the entire string guaranteed to have been parsed?

**Answer:** No. After parsing a prefix, the parser can stop without recording an error; you must check `getIndex()`.

**Question 3.** If `NumberFormat.parse(String, ParsePosition)` returns `null`, can it be accepted if `index` equals `length`?

**Answer:** No. Acceptance requires **both** `result != null` and `index == length`. If `null`, there is no valid number.

**Question 4.** Is a `ParsePosition` created with `new ParsePosition(4)` suitable for whole-string validation of a numeric field?

**Answer:** No. It skips the beginning. Only use a non-zero start when a prefix is validated separately by the application grammar.

**Question 5.** Why does `DecimalFormat.setParseBigDecimal(true)` still require checking `instanceof BigDecimal`?

**Answer:** Special values like `NaN` or `Infinity` may not produce a `BigDecimal`. If the contract accepts only finite decimals, reject them and avoid invalid casts.

**Question 6.** Why does whole-input parsing not automatically guarantee "clean and standard" thousands grouping?

**Answer:** `NumberFormat` can accept lenient grouping forms. `index == length` only proves the parser consumed the whole input, not that the string conforms to a strict application-defined input template.

**Question 7.** If a string is normalized before parsing, which length must be compared with `getIndex()`?

**Answer:** `length()` of the **exact string passed into the parser**, not the length of the original raw string.

## 19. Summary and references

Key points to remember:

- Locale-based `NumberFormat` is designed to read numeric strings **under regional conventions**, yet parsing a number does not guarantee the entire input is valid.
- **Mandatory check pair** for a number-only field: `result != null` and `pos.getIndex() == text.length()`, using `new ParsePosition(0)`.
- `getErrorIndex()` helps locate parse failures; it **does not** replace checking the ending position.
- Whole-string validation is just **one validation layer**; you still need to check type, value range, precision, and other format constraints.
- For decimal data requiring precision, use `DecimalFormat.setParseBigDecimal(true)` and verify `instanceof BigDecimal`.
- Explicitly specify locale, grouping, whitespace, and separator validity in your input contract instead of leaving them to the default locale.

Official references (Java 17):

- [NumberFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html): `parse(String)`, `parse(String, ParsePosition)`, `Locale`-based formatters, and thread-safety notes.
- [DecimalFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormat.html): `setParseBigDecimal`, patterns, grouping, and decimal symbols.
- [ParsePosition](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/ParsePosition.html): `getIndex()`, `setIndex()`, `getErrorIndex()`.
- [Locale](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html): locale model in the Java API.
- [BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): exact decimal numbers and `compareTo()`.