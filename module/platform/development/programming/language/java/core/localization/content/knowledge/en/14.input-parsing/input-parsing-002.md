# NumberFormat.parse Can Read Only the Prefix of a String in Java

## Lesson Objectives

When users enter numbers, `java.text.NumberFormat` can convert text formatted according to a `Locale` into a `Number`. However, the critical point is that **a successful parse does not mean the entire input string was read**. A parser can match a valid prefix and stop at the next non-matching character.

For example, with US English number formatting, `"1,234.50USD"` can be parsed as `1234.50`, leaving `"USD"` behind. This is completely different from requiring a field to **contain only a number**.

After this lesson, you will be able to:

- Distinguish `NumberFormat.parse(String)` from `NumberFormat.parse(String, ParsePosition)`.
- Use `ParsePosition.getIndex()` to check whether the parser consumed the **entire** input or only read a prefix.
- Understand the failure behavior of both overloads, `ParseException`, `null` results, and `getErrorIndex()`.
- Explain why even when the parser consumes the whole string, grouping syntax may still fail strict validation requirements.
- Separate locale-aware number parsing for **user interfaces** from parsing data in **APIs, databases, or interchange formats**.
- Design input validation functions, numeric types, and value ranges that fit business requirements.

This lesson focuses on `NumberFormat.parse`, especially stopping at a **valid prefix**. Broader validation rules are used to explain why you must evaluate the parse result rather than trusting a non-throwing call as sufficient.

## 1. Why Does a Parser Only Need to Read a Prefix?

`NumberFormat` is the abstract class representing locale-aware number formatters and parsers. In applications with human-facing input, the parser must recognize digits and symbols appropriate to the locale; for example:

- With `Locale.US`, `1,234.50` typically means one thousand two hundred thirty-four point five.
- With `Locale.GERMANY`, the equivalent value is typically written `1.234,50`.
- In some other locales, the grouping separator may be a space or non-breaking space, and the numeral system may not be ASCII.

When the parser encounters a matching prefix, it can stop as soon as it reaches something no longer recognized as part of a number. This is useful inside a **larger parser**: for instance, reading a quantity first and then processing the unit in the remainder. But if a form field or API expects a single number, any remainder is invalid data.

```text
Input:    1,234.50USD
          └──────┘└─┘
           parsed   remainder
Numeric result: 1234.50
```

Always ask: **“How many characters did the parser read?”** rather than merely **“Did the parser return a number?”**

## 2. Two Key Overloads of NumberFormat.parse

### parse(String)

```java
NumberFormat format = NumberFormat.getNumberInstance(Locale.US);
Number result = format.parse("1,234.50USD");
```

This is an illustrative snippet inside a method that handles or declares `java.text.ParseException` and imports `java.text.NumberFormat` and `java.util.Locale`.

The call can succeed and assign `result` the numeric value of the prefix `1,234.50`. **The API contract does not require consuming every character** of `source`. When parsing cannot start at all, this overload throws `ParseException`; do not confuse that with “ignoring trailing data.”

### parse(String, ParsePosition)

```java
ParsePosition pos = new ParsePosition(0);
Number value = format.parse("1,234.50USD", pos);
```

This snippet requires importing `java.text.ParsePosition` and assumes `format` already exists. Here:

- `new ParsePosition(0)` asks the parser to start at index 0.
- `value` is a `Number` if the parser recognizes a valid numeric segment.
- `pos.getIndex()` is the next position **after the successfully parsed segment**.
- `pos.getErrorIndex()` indicates the error position when parsing fails; by default it is typically `-1` when no error was recorded.

For `"1,234.50USD"` with `Locale.US`, the ending index is 8 out of 11 total characters. Thus **3 characters (`USD`) remain unconsumed**.

### Comparison Table

| Condition | `parse(String)` | `parse(String, ParsePosition)` |
| --- | --- | --- |
| Parses a prefix | May return `Number` even with a trailing suffix | Returns `Number`, provides index after parsed portion |
| Cannot parse from start position | Throws `ParseException` | Returns `null`, may record `errorIndex` |
| Checking if full input was read | Does not directly report ending position | Check `position.getIndex() == input.length()` |
| Can start at a non-zero index | No, parses from start of string | Yes, via `ParsePosition(startIndex)` |
| Validating an entire string | Insufficient on its own | Must check result, index, and additional rules |

**Do not rely on `parse(String)` as a validator for a string that must consist solely of a number.** This is a common logic bug in monetary inputs, quantity fields, and CSV imports.

## 3. Standalone Java 17+ Example

Create the file `NumberParsePrefixDemo.java`:

```java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParseException;
import java.text.ParsePosition;
import java.util.Locale;

public class NumberParsePrefixDemo {
    private static void check(DecimalFormat format, String input) {
        ParsePosition pos = new ParsePosition(0);
        Number value = format.parse(input, pos);

        boolean full = value != null
                && pos.getIndex() == input.length();

        System.out.println("[" + input + "] -> "
                + (value == null ? "INVALID" : value)
                + ", index=" + pos.getIndex()
                + "/" + input.length()
                + ", full=" + full);
    }

    public static void main(String[] args) throws ParseException {
        DecimalFormat us = (DecimalFormat)
                NumberFormat.getNumberInstance(Locale.US);
        us.setParseBigDecimal(true);

        check(us, "1,234.50");
        check(us, "1,234.50USD");
        check(us, "1234.50x");
        check(us, "1,23,4.50");
        check(us, "not-a-number");

        System.out.println("simple parse: "
                + us.parse("1,234.50USD"));

        try {
            us.parse("not-a-number");
        } catch (ParseException ex) {
            System.out.println("simple parse failed");
        }

        us.setParseIntegerOnly(true);
        ParsePosition pos = new ParsePosition(0);
        Number integer = us.parse("123.45", pos);

        System.out.println("integer-only: " + integer
                + ", index=" + pos.getIndex());
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 NumberParsePrefixDemo.java
java NumberParsePrefixDemo
```

Stdout with the configuration in the example:

```text
[1,234.50] -> 1234.50, index=8/8, full=true
[1,234.50USD] -> 1234.50, index=8/11, full=false
[1234.50x] -> 1234.50, index=7/8, full=false
[1,23,4.50] -> 1234.50, index=9/9, full=true
[not-a-number] -> INVALID, index=0/12, full=false
simple parse: 1234.50
simple parse failed
integer-only: 123, index=3
```

Explanation of key output lines:

1. `1,234.50` is parsed completely so `full=true`.
2. `1,234.50USD` consumes only 8 of 11 characters; `parse(String)` still returns the number if called via the simple overload.
3. `1234.50x` stops before the letter `x`, returning the number for the valid portion.
4. `1,23,4.50` uses digit grouping that violates standard en-US conventions, yet the `DecimalFormat` parser still accepts it and reads to the end. **Full consumption does not imply strict syntax**.
5. `not-a-number` does not begin with matching numeric syntax, so the `ParsePosition` overload returns `null`.
6. `setParseIntegerOnly(true)` tells the parser to stop before the decimal separator in `123.45`, returning `123` and index 3. This option does not automatically verify that “the whole string is an integer.”

The example explicitly uses `Locale.US` rather than depending on the JVM default locale. `setParseBigDecimal(true)` instructs `DecimalFormat` to return `BigDecimal` for finite numbers in the example, preserving parsed decimal digits instead of going through `double`. However, it **does not make the parser stricter about grouping syntax or trailing text**.

## 4. Using ParsePosition Properly

`ParsePosition` is a mutable object holding position state within a `String`:

```java
ParsePosition pos = new ParsePosition(0);
Number value = formatter.parse(input, pos);

if (value == null) {
    // Could not parse from the requested position.
}
if (value != null && pos.getIndex() != input.length()) {
    // Only read a portion; unconsumed characters remain in input.
}
```

This is an illustrative snippet inside a method where `formatter` (`NumberFormat`) and `input` (`String`) are already declared.

### Index Is a Java String Position, Not a Digit Count

`getIndex()` counts positions in the `String` (UTF-16 code units), just like `String.length()`. It does **not** report the number of decimal digits in the result, nor is it a monetary value. If the string contains special Unicode characters, do not infer the number of user-perceived characters directly from the index.

When checking “fully read,” comparing `pos.getIndex() == input.length()` is appropriate because both use the same `String` indexing unit.

### Parsing from a Non-Zero Position

You can read a number in the middle of an input string:

```java
String input = "qty=42kg";
ParsePosition pos = new ParsePosition(4);
Number quantity = NumberFormat
        .getIntegerInstance(Locale.US)
        .parse(input, pos);
```

This is an illustrative snippet inside a method. Index 4 is the character `'4'` after `qty=`. The parser can read `42` and stop at index 6, before `kg`. This is useful when a **higher-level parser** handles the `qty=` prefix, the `kg` unit, and the overall structure.

However, in a function whose sole job is reading one number, starting at index 0 and requiring full consumption is usually more appropriate.

### Error Index and the Difference Between Failure and Remainder

When `parse` fails right at the start position, the `ParsePosition` overload typically returns `null`; `getErrorIndex()` helps identify where the mismatch occurred.

Example:

```java
ParsePosition pos = new ParsePosition(0);
Number bad = NumberFormat
        .getNumberInstance(Locale.US)
        .parse("abc", pos);

System.out.println(bad == null);
System.out.println(pos.getIndex());
System.out.println(pos.getErrorIndex());
```

Inside a method with appropriate imports, stdout with the default `Locale.US` formatter is:

```text
true
0
0
```

Conversely, if the parser reads `123` and hits `'a'` in `123abc`, that can be a **partial parse result**, not a `null` failure. Use `getIndex()` to detect unconsumed data. Do not merely check whether `getErrorIndex()` has a value and assume any trailing suffix would be flagged as an error automatically.

In particular, a `ParsePosition` object can be used to continue reading subsequent components. If reusing it, explicitly set the index/error index as needed before starting a new parse instead of assuming it starts at 0.

## 5. Checking That the Entire Input Was Consumed

When an input field must contain **only a single number** with no other prefix or suffix, the baseline condition is:

```java
ParsePosition pos = new ParsePosition(0);
Number result = formatter.parse(raw, pos);

boolean fullyParsed = result != null
        && pos.getIndex() == raw.length();
```

This is a **necessary condition**, not the entire input validation system.

There are two reasonable ways to handle whitespace, as long as the contract states which one applies:

- **Strict input:** disallow leading/trailing whitespace, so `"123 "` is treated as not fully parsed; `" 123"` may fail to parse from the start.
- **Intentional trimming:** if the form allows surrounding whitespace, check `raw != null` and call `raw.strip()` before parsing. Stripping whitespace must be an explicit design decision, not an arbitrary “fix” for a string with a different meaning.

Do not automatically remove all spaces between digit groups. Some locales use spaces (potentially non-breaking spaces) as grouping separators; altering them arbitrarily can change the value or hide input errors.

### Complete Parse Function for UI Input

```java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

public final class LocalizedNumberInput {
    private LocalizedNumberInput() {}

    public static BigDecimal parseDecimal(
            String raw, Locale locale) {
        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException("A number is required");
        }

        DecimalFormat formatter = (DecimalFormat)
                NumberFormat.getNumberInstance(locale);
        formatter.setParseBigDecimal(true);

        ParsePosition pos = new ParsePosition(0);
        Number parsed = formatter.parse(raw, pos);

        if (!(parsed instanceof BigDecimal)
                || pos.getIndex() != raw.length()) {
            throw new IllegalArgumentException(
                    "Invalid number: incomplete parse");
        }
        return (BigDecimal) parsed;
    }
}
```

This is a utility class that compiles as `LocalizedNumberInput.java` on JDK 17+, though it has no `main` method to run standalone. The function intentionally **does not trim**: a string with trailing whitespace will be rejected if the parser does not consume all of it.

However, this function only checks:

1. That the string exists and is not blank.
2. Whether the parser returned an appropriate decimal value.
3. Whether the parser read the whole string.

The function **does not yet guarantee** exact grouping, precision/scale within limits, non-negativity, or adherence to application currency rules. Those checks must be added according to the contract. Never label a helper that merely checks the index as a “strict parser for all locales.”

## 6. Even Consuming the Entire String Can Accept Invalid Grouping

The subtlest aspect of this topic is distinguishing two questions:

- **Full consumption:** the entire string was accepted by the parser with no trailing suffix.
- **Strict lexical validation:** every character and the grouping separator structure follow the published input rules.

`DecimalFormat` parses digit grouping **relatively flexibly**. In US number formatting, standard grouping uses three digits: `1,234.50`. Yet the parser may still accept:

```text
1,23,4.50
```

and return `1234.50`, while reporting that the entire string was consumed.

This is a vital demonstration: `position.getIndex() == raw.length()` **does not prove** that grouping matches the UI pattern users were instructed to follow.

If the product requires strict syntax, define the rules explicitly:

- Are grouping separators allowed?
- Must each group have an exact length?
- Are `+` or `-` signs accepted?
- Is scientific notation allowed?
- Which decimal separator is valid for the requested locale?
- Is Unicode whitespace allowed at the start, end, or between groups?
- Are out-of-range numbers or numbers with too many fractional digits accepted?

A simple strategy for technical input systems is to **disallow grouping** and use a dedicated, published input grammar. You can then validate with an appropriate regex/syntax parser before converting to `BigDecimal`. However, if a product wants to support real grouping across multiple locales, do not write one ASCII regex and claim it applies correctly to all languages; use mechanisms and tests aligned with Unicode/locale rules.

### Why Not Just Re-Format and Compare Against Input?

The idea of “parse, format back, and compare to the original string” has drawbacks:

- The formatter may round or change the number of decimal places relative to input.
- The formatter may add or remove grouping separators.
- Signs, grouping characters, or Unicode digits may be normalized.
- Multiple valid input representations may denote the same value (`1`, `1.0`, `01` depending on contract).

Round-trip comparison only makes sense if the application **deliberately chooses a single canonical form** and accepts rejecting all other variants. It is not a general check for every internationalized numeric input field.

## 7. Locale Determines Character Meaning

The same string can be interpreted differently:

| Input | `Locale.US` | `Locale.GERMANY` |
| --- | --- | --- |
| `1,234` | Typically represents one thousand two hundred thirty-four | Typically represents one point two three four |
| `1.234` | Typically represents one point two three four | Typically represents one thousand two hundred thirty-four |
| `1,234.50` | Typical notation for `1234.50` | May parse a prefix; should not be treated as value 1234.50 |
| `1.234,50` | May parse a prefix `1.234` | Typical notation for `1234.50` |

This illustrates familiar locale conventions; behavior for individual strings must be tested with the formatter and JDK/provider used by your application.

**Do not guess the locale from commas or dots** when the contract has not specified it. For instance, `1,234` could mean 1234 or 1.234. A program that blindly replaces `,` with `.` can shrink a monetary amount by a factor of 1,000.

Determine the locale from user settings, form context, or published conventions before parsing. In machine-to-machine APIs, remove locale dependence and use a fixed numeric schema.

### The Default Locale Can Also Change Results

`NumberFormat.getNumberInstance()` without a locale argument uses the JVM's default formatting locale. That default can differ between development machines, CI runners, and production, and can even be changed by other code in the same JVM via `Locale.setDefault`.

When handling a request, pass an explicit `Locale` to that request's formatter. Do not call `Locale.setDefault` whenever a user switches languages; it is JVM-wide shared state and can affect other requests.

## 8. setParseIntegerOnly Does Not Mean Integer Validation

`NumberFormat.setParseIntegerOnly(true)` tells the parser to read only the integer portion during parsing. It does not necessarily reject a string containing a fractional part; instead, the parser may stop before the decimal separator.

Example with `Locale.US`:

```java
NumberFormat integers =
        NumberFormat.getIntegerInstance(Locale.US);

ParsePosition pos = new ParsePosition(0);
Number number = integers.parse("123.45", pos);

System.out.println(number);
System.out.println(pos.getIndex());
```

This is an illustrative snippet inside a method with appropriate imports. Stdout:

```text
123
3
```

If a field accepts integers only, you must check `pos.getIndex() == input.length()`. If the integer must fall within a defined range, check both range and result type.

Do not treat `NumberFormat.getIntegerInstance` as a complete integer syntax validator for untrusted input.

## 9. BigDecimal, the Number Type, and Precision Limits

`NumberFormat.parse` has return type `Number`, not always `Double` or `Long`. The actual runtime type depends on the formatter, options, and value. `DecimalFormat#setParseBigDecimal(true)` is an option when you need to read decimal strings into `BigDecimal`.

```java
DecimalFormat format = (DecimalFormat)
        NumberFormat.getNumberInstance(Locale.US);
format.setParseBigDecimal(true);
Number number = format.parse("123.450", new ParsePosition(0));
```

This is an illustrative snippet inside a method. When decimal precision must be preserved, read the supported exact numeric type rather than always calling `doubleValue()`, since converting to binary floating-point can lose precision.

However, **an exact value type does not by itself force the parser to read the whole string or validate grouping strictly**. Returning `BigDecimal` solves only one part of numeric representation.

Checks that should be kept separate include:

1. **Input syntax** (matches grammar).
2. **Full consumption** (no trailing text).
3. **Precision/scale** (total digits and digits after the decimal separator).
4. **Value domain** (non-negative, within limits, etc.).
5. **Unit** (currency, rate, weight).
6. **Rounding rules** when required by business logic.

Monetary example: after parsing `"123.456"` by locale, business logic may need to reject it if only two decimal places are allowed. Do not silently re-format it to `123.46` and save it, unless the contract **allows and specifies the rounding mode**.

### Parsing Number and Currency Formats Differs

`NumberFormat.getNumberInstance(locale)` is designed for plain numbers, `getPercentInstance(locale)` for percentages, and `getCurrencyInstance(locale)` for currency formats. They can use different patterns and symbols. A string containing a currency sign should not be parsed as a plain number while silently dropping the suffix or prefix.

If a user enters `"100 USD"`, determine whether the application wants:

- A **separate numeric field** `100` and a **separate currency field** `USD`.
- Or a combined input with a clear grammar fully recognized by a dedicated parser.

You must never extract `100` via prefix parsing and discard `USD` without validating the currency, especially for transactional data.

## 10. User Interfaces and Interchange Protocols Need Different Parsers

A multilingual UI form might accept `1.234,50` for a German user, while JSON or integrated CSV data usually needs a **separately specified number format** independent of the user's locale.

### Appropriate Processing Flow

```text
User input + specific Locale
                |
        Parse by Locale
                |
   Check full string + grammar
                |
   Check range / scale limits
                |
      BigDecimal / Number
            /       \
           v         v
  Display in      Store or exchange
  user Locale     per stable schema
```

For data from REST APIs, CSV imports, or message queues, the parser must follow that channel's schema. For instance, a JSON number contract uses no grouping separators and `.` as the decimal point; never use the JVM default locale to parse JSON numbers.

```json
{"quantity": 1234.5}
```

This is valid JSON with a numeric `quantity` field. Conversely, `{"quantity": 1,234.5}` **is not** a valid single JSON number; the grouping comma breaks JSON object syntax here.

If an API uses decimal strings to preserve exact values (such as money), publish that field as a decimal string under a stable grammar; it is not “whatever number string happens to be displayed in the UI.”

### Do Not Fix Ambiguous Input Ad Hoc

An anti-pattern:

```java
String standardized = raw.replace(",", "").replace(" ", "");
double value = Double.parseDouble(standardized);
```

This snippet illustrates what **not to do**. If a user enters `"1,23"` using a decimal comma, the code turns it into `123` instead of `1.23`. Grouping removal cannot be done via context-blind string replacement.

If the data source always uses a fixed machine-readable grammar, validate against that grammar and parse directly. If the source is a UI, determine the locale and process locale symbols with an appropriate parser accompanied by business validation.

## 11. Designing a Controlled Input-Parsing API

A safer parse function must accurately describe the scope of its guarantees. For instance, you can use the code below as an initial step to accept decimal input from a form, **without claiming that it validates all valid grouping structures**:

```java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

public final class PriceInput {
    private PriceInput() {}

    public static BigDecimal parseLocalized(
            String input, Locale locale) {
        if (input == null || input.isBlank()) {
            throw new IllegalArgumentException("Input is empty");
        }

        if (input.length() > 64) {
            throw new IllegalArgumentException("Input is too long");
        }

        DecimalFormat parser = (DecimalFormat)
                NumberFormat.getNumberInstance(locale);
        parser.setParseBigDecimal(true);

        ParsePosition pos = new ParsePosition(0);
        Number parsed = parser.parse(input, pos);

        if (!(parsed instanceof BigDecimal)
                || pos.getIndex() != input.length()) {
            throw new IllegalArgumentException(
                    "Invalid numeric input or trailing characters");
        }

        BigDecimal value = (BigDecimal) parsed;
        if (value.signum() < 0) {
            throw new IllegalArgumentException(
                    "Negative value is not allowed");
        }
        if (value.scale() > 2) {
            throw new IllegalArgumentException(
                    "Too many fractional digits");
        }
        return value;
    }
}
```

This class compiles as `PriceInput.java` on Java 17+, though it has no `main` method to run directly.

Notes:

- The 64-character limit, non-negativity, and maximum of 2 decimal places are **examples of application policy**, not general `NumberFormat` rules.
- The function does not strip whitespace automatically. Strings with trailing text are rejected via the index check.
- The function does not yet catch all forms of **invalid grouping separators**. If the application allows grouping but enforces standard digit groups, add an appropriate checker.
- If business logic also wants to reject values not written with standard ASCII digits, add an explicit rule; a locale parser may accept locale-specific digit characters.
- If the transaction currency has a minor unit other than two digits, do not assume every currency uses scale 2.
- Create a dedicated formatter/parser per operation or manage thread safety; `NumberFormat` instances typically hold mutable state and should not be shared unsynchronized across threads.

A function that clearly documents its limits is better than one named `strictParse` that silently accepts loose grammar.

## 12. Which Cases Should You Test?

A test suite for locale-aware numeric input should cover:

| Group | Test Case | What to Verify |
| --- | --- | --- |
| Valid | `1,234.50` with `Locale.US` | Correct value and full string consumption |
| Valid | `1.234,50` with `Locale.GERMANY` | Correct value in the chosen locale |
| Suffix | `1,234.50USD` | Detect that only a prefix was parsed |
| Suffix | `123.45abc` | Detect index smaller than length |
| Unexpected prefix | `abc123` | Fails to parse a number from index 0 |
| Whitespace | `123 ` and ` 123` | Matches trim/no-trim policy |
| Irregular grouping | `1,23,4.50` with `Locale.US` | Do not confuse full parse with strict grammar |
| Fractional part | `123.456` when max scale is 2 | Check scale, not just parse success |
| Negative and limits | `-1`, huge numbers | Verify business range |
| Cross-locale | `1,234` with US/Germany | Do not confuse decimal and grouping separators |
| Integer-only | `123.45` with parse-integer-only | Do not accept remaining fraction as a complete integer |
| Exact decimal | Multi-digit values | Do not lose precision through unnecessary `double` conversion |
| Unicode characters | Non-ASCII digits/grouping spaces | Verify against actual formatter/provider and font/UI |

If input affects money, limits, or units, write tests for **a number that could be multiplied/divided by 100 or 1,000 if a separator is misinterpreted**, because that error has severe real-world impact.

### Keeping Tests Independent of the JVM Environment

Do not write tests calling parameterless `NumberFormat.getInstance()` and expect every machine to share the same grouping/decimal separators. Choose an explicit `Locale`, such as `Locale.US` or `Locale.GERMANY`.

Do not hardcode specific error messages or indices tied to a single JDK provider without good reason: locale/provider data can change across Java versions. Tests should focus on the **specified parsing contract** and behaviors guaranteed by the API.

## 13. Common Mistakes

| Mistake | Problem | Correct Approach |
| --- | --- | --- |
| `format.parse(input)` throws no exception, so entire input is assumed valid | Simple overload can stop after a numeric prefix | Use `ParsePosition` and check ending index |
| Checking only `parsed != null` | A suffix may have been left behind | Check `pos.getIndex() == input.length()` |
| Checking only `pos.getErrorIndex()` | A partial parse may not report an error index | Detect trailing text using `getIndex()` |
| Assuming full consumption means standard grouping | `DecimalFormat` can parse flexible grouping | Check grammar if product requires strictness |
| Using `getIntegerInstance` to “validate integers” | Can read the integer part and stop before the decimal point | Check index and integer domain |
| Using `setParseBigDecimal(true)` to “catch every error” | Only changes return type/precision of parsed result | Separate syntax validation from value validation |
| Calling parse with an unclear default locale | Same string can carry different meanings | Pass locale explicitly |
| Blindly replacing `,` with `.` or stripping grouping separators | Can change the value by 1,000x | Identify source grammar and parse by its rules |
| Parsing strings with `USD` appended without checking currency | Ignores transaction currency unit | Use a separate currency field or dedicated parser |
| Allowing trailing text in a number-only field | Can store wrong values or accept malicious input | Check full consumption and schema |
| Parsing JSON protocol numbers with `NumberFormat` | Protocols have their own grammar | Use a JSON parser and schema numeric types |
| Sharing one mutable `NumberFormat` across threads | Can cause concurrency bugs | Use per-request instances or synchronize |

## 14. Self-Check Exercises

**Exercise 1 — trailing data.** Given `Locale.US` and input `"1,234.50USD"`, create `ParsePosition(0)`, call `parse`, and determine the value, index, and number of unread characters. Why does `parse(String)` not throw an error here?

**Exercise 2 — full-string check.** Write a function accepting a `String` and `Locale` that returns a `Number` only when the parser produces a result and `pos.getIndex() == input.length()`. Is that function already a strict parser for every kind of grouping? Why or why not?

**Exercise 3 — integers.** Why can `getIntegerInstance(Locale.US).parse("123.45", pos)` return `123`? What additional condition is needed to reject inputs containing a fractional part?

**Exercise 4 — ambiguous locale.** How does `"1,234"` differ in meaning between US and German locales? Why should you not rely on the presence of `,` to decide its meaning automatically?

**Exercise 5 — precision.** When parsing monetary amounts with many decimal digits, what is the benefit of `DecimalFormat#setParseBigDecimal(true)`? Does it automatically make parsing strict about syntax or value range?

**Exercise 6 — QA.** Write a test suite for `"123.45abc"`, `"abc123"`, `"123 "`, `"1,23,4.50"`, and `"123.456"` under a policy allowing at most two decimal places. Separately classify **trailing input**, **unparseable**, **grouping**, and **scale** errors.

## 15. Conclusion

`NumberFormat.parse` is designed to **read numbers according to a locale's conventions**, and it may consume only a **valid prefix** of the input. The `parse(String)` overload can return a number even when characters follow it; to know exactly how much was read, use `parse(String, ParsePosition)`.

The condition `parsed != null && pos.getIndex() == input.length()` rejects inputs that are not fully consumed, but that is only a **full-consumption check**, not a guarantee that grouping, numeric type, and value range are all valid. For user input, explicitly define locale, grammar, range, and scale. For machine-to-machine interchange, use a fixed numeric schema rather than a locale-aware display parser.

**Core principle:** *Partial parse ≠ valid input; full string parse ≠ all business rules checked.*

### API Reference

- [`NumberFormat` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html)
- [`DecimalFormat` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormat.html)
- [`ParsePosition` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/ParsePosition.html)
