# Testing Locale Formatting and Round-Trip Encoding in Java

Java applications frequently format numbers, dates, and text according to language/region (**Locale**) while converting between **String (Unicode characters)** and **byte[] (Charset-encoded data)**. Both conversions cause silent bugs easily: strings render properly on a developer's machine yet break on another; decimal separators are misread; Vietnamese characters or emojis turn into question marks; or input is only partially parsed while the program still treats it as valid.

This lesson focuses on **reproducible testing**, **round-trip conversion (converting forward and back)**, and distinguishing **exact original data recovery**, **semantic value recovery**, and **irreversible information loss**. Examples use Java 17+ and explicitly specify Locale/Charset to avoid depending on machine defaults.

## 1. Two Kinds of Conversions to Test Separately

| Pipeline | Common Java APIs | Input and Output | What to Test |
| --- | --- | --- | --- |
| Number → localized text | NumberFormat, DecimalFormat, String.format(Locale, ...) | Number/BigDecimal → String | Decimal separator, grouping, rounding, digit count, minus sign |
| Localized text → number | NumberFormat.parse, DecimalFormat.parse | String → Number | Right Locale, full input consumed, precision, invalid input |
| Date → localized text | DateTimeFormatter.withLocale(...) | LocalDate/... → String | Day-month order, month names, length, and locale |
| Date text → date | LocalDate.parse(..., formatter) | String → LocalDate | Valid date, matching formatter, no required info lost |
| Unicode string → bytes | String.getBytes(Charset), CharsetEncoder | String → byte[] | Target charset supports characters, replacement behavior |
| Bytes → Unicode string | new String(bytes, Charset), CharsetDecoder | byte[] → String | Right decoding charset, malformed bytes, no silent data loss |

**Locale is not Charset.** Locale governs text formatting and interpretation by language and region (e.g., 1.234,50 vs. 1,234.50). Charset defines how character content maps to bytes and back (e.g., UTF-8 or ISO-8859-1). Choosing Locale.GERMANY does not automatically pick any character encoding; choosing UTF-8 does not decide how decimal numbers are formatted.

## 2. Choosing Reproducible Test Conditions

A good test avoids depending on the runtime environment. Make explicit:

1. **Specific Locale:** e.g., Locale.US, Locale.GERMANY, Locale.FRANCE, or Locale.forLanguageTag("vi-VN"), instead of casually reading Locale.getDefault().
2. **Specific Charset:** e.g., StandardCharsets.UTF_8, StandardCharsets.ISO_8859_1, StandardCharsets.US_ASCII; avoid default encodings when testing protocols or files.
3. **Formatting rules:** decimal digits, thousands grouping, rounding mode, date format, and timezone when absolute instants are involved.
4. **Data domain:** zero, negative numbers, large bounds, fractional values, grouping separators, Vietnamese accented strings, non-BMP characters (emojis), empty strings, and malformed input.
5. **Round-trip contract:** must equality hold **character-for-character**, **byte-for-byte**, or only for **numeric/date value**?

Java APIs draw regional data from the JDK (including locale data providers). Exact rendered strings, month names, or grouping spaces can vary across Locales, configurations, and JDK versions. Therefore, contract tests should combine: data with fixed application-controlled formats; and **round-trip** checks instead of hardcoding every localized string.

## 3. Testing Number Formatting and Parsing by Locale

In the US, formatted numbers can use a comma for grouping and a dot for the decimal separator; in Germany, those two symbols are reversed. If a string formatted in one Locale is parsed under another, the program may misread the value or consume only a prefix of the string.

For currency or critical decimal precision, **BigDecimal** is usually safer than double in calculations requiring exact decimal values. DecimalFormat can be configured to parse into BigDecimal.

### Java 17 Example: format → parse and verifying full input consumption

Create **LocaleNumberRoundTrip.java**:

~~~java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParsePosition;
import java.util.Locale;

public class LocaleNumberRoundTrip {
    private static void verify(Locale locale, BigDecimal original) {
        DecimalFormat format = new DecimalFormat(
                "#,##0.00",
                DecimalFormatSymbols.getInstance(locale)
        );
        format.setParseBigDecimal(true);

        String rendered = format.format(original);
        ParsePosition position = new ParsePosition(0);
        Number parsed = format.parse(rendered, position);

        boolean consumedAll = parsed != null
                && position.getErrorIndex() < 0
                && position.getIndex() == rendered.length();

        boolean sameValue = parsed instanceof BigDecimal value
                && value.compareTo(original) == 0;

        System.out.println(locale.toLanguageTag() + ": " + rendered);
        System.out.println("full parse: " + consumedAll);
        System.out.println("same value: " + sameValue);
    }

    public static void main(String[] args) {
        BigDecimal number = new BigDecimal("1234.50");
        verify(Locale.US, number);
        verify(Locale.GERMANY, number);
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 LocaleNumberRoundTrip.java
java LocaleNumberRoundTrip
~~~

Output with Locale.US and Locale.GERMANY separators:

~~~text
en-US: 1,234.50
full parse: true
same value: true
de-DE: 1.234,50
full parse: true
same value: true
~~~

**Explanation:** DecimalFormatSymbols determines decimal/grouping separators for each Locale; the pattern "#,##0.00" requires two fractional digits when formatting. ParsePosition tracks how far the parser read. Checking **position.getIndex() == rendered.length()** prevents partial prefix parses from passing silently.

**BigDecimal.compareTo(...) == 0** confirms mathematical value equality. BigDecimal.equals(...) also compares scale, so 1.0 and 1.00 are numerically equal yet equals returns false. In systems that must preserve exact input scale, format → parse may violate that contract if formatting rounds or changes decimal digit count.

### Why Must You Verify the Whole String Was Consumed?

Some number parsers accept a valid prefix and stop before trailing characters. Suppose input is "1,234.50abc": the parser can read 1,234.50 while ignoring "abc". Returning a non-null Number **does not prove** the entire string was valid.

The illustrative snippet below (not a standalone program) reuses the same configured DecimalFormat:

~~~java
String input = "1,234.50abc";
ParsePosition position = new ParsePosition(0);
Number number = format.parse(input, position);
boolean valid = number != null
        && position.getErrorIndex() < 0
        && position.getIndex() == input.length();
~~~

Here valid is **false** because the parser only read a numeric prefix. Depending on application policy, you may need stricter checks on grouping separators, negative signs, whitespace, or normalization before accepting input. Checking full input consumption **still does not guarantee** every presentation rule is met, because some parsers are lenient.

## 4. Not Every format → parse Preserves the Exact Value

If DecimalFormat displays only two fractional digits, values with more digits can be rounded:

~~~java
BigDecimal original = new BigDecimal("1.2345");
DecimalFormat format = new DecimalFormat(
        "0.00",
        DecimalFormatSymbols.getInstance(Locale.US)
);
format.setParseBigDecimal(true);

String text = format.format(original);  // "1.23" under default rounding in this case
Number parsed = format.parse(text);    // 1.23, not 1.2345
~~~

This snippet illustrates precision loss caused by formatting. Whenever specific rounding behavior is required, **explicitly set RoundingMode** instead of relying on formatter defaults.

Choose the contract explicitly:

- **Exact round-trip:** parse(format(x)) equals x for every accepted x; only achievable within lossless input domains and formats.
- **Round-trip within tolerance:** results may differ within business bounds when rounding is permitted; use appropriate range assertions for floating-point values.
- **Canonicalizing round-trip:** format(parse(text)) converts a string to canonical form; exact character-by-character match with original input is not required.
- **Display only:** if formatting intentionally rounds or rescales units, do not feed rendered display strings back as primary calculation data.

**Avoid converting business data to strings and parsing back just to pass values between layers.** Keep numeric and date values in proper data types, formatting only at display boundaries or explicit export contracts.

## 5. String.format and DateTimeFormatter Also Need Explicit Locales

String.format(Locale, ...) formats numbers according to a Locale. For example:

~~~java
String us = String.format(Locale.US, "%,.2f", 1234.5);
String de = String.format(Locale.GERMANY, "%,.2f", 1234.5);
~~~

For those two Locales, typical outputs are **1,234.50** and **1.234,50**, respectively. However, **String.format** produces text and does not provide a built-in inverse parser for its format syntax; round-tripping requires defining an appropriate parser.

For dates, **java.time.format.DateTimeFormatter** lets you create a localized formatter and reuse it for parsing. Full example, **LocaleDateRoundTrip.java**:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public class LocaleDateRoundTrip {
    public static void main(String[] args) {
        LocalDate original = LocalDate.of(2026, 10, 23);
        DateTimeFormatter formatter =
                DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG)
                        .withLocale(Locale.FRANCE);

        String text = formatter.format(original);
        LocalDate parsed = LocalDate.parse(text, formatter);

        System.out.println("date round-trip: " + original.equals(parsed));
    }
}
~~~

~~~bash
javac -encoding UTF-8 LocaleDateRoundTrip.java
java LocaleDateRoundTrip
~~~

~~~text
date round-trip: true
~~~

Avoid hardcoding exact French month spelling in sample output assertions since environment locale data can vary rendering; this example checks **the parsed date value** instead. For zoned timestamps, specify ZoneId and the exact temporal type (Instant, ZonedDateTime, LocalDateTime...), because a date-only or time-only string may lack enough data to recover an Instant. For language-independent data interchange, prefer ISO formats or explicit protocol formats.

## 6. Two-Way Transcoding: String ⇄ byte[]

**Charset** defines the mapping from character strings to bytes and from bytes back to characters. Two common operations:

~~~java
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
String decoded = new String(bytes, StandardCharsets.UTF_8);
~~~

This is an illustrative snippet; variables and imports must be declared in the enclosing program. **The same charset must be used in both directions.** If a sender encodes in UTF-8 while the receiver decodes in ISO-8859-1, multi-byte characters become garbled text (mojibake).

For **UTF-8**, a String consisting of valid Unicode scalar values (no unpaired surrogates) round-trips losslessly: **decode(encode(s, UTF-8), UTF-8).equals(s)**. Do not treat that as guaranteed for every possible Java char sequence, since String can hold malformed surrogates.

File **CharsetRoundTripDemo.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public class CharsetRoundTripDemo {
    public static void main(String[] args) {
        String original = "Tiếng Việt 😀";
        byte[] utf8 = original.getBytes(StandardCharsets.UTF_8);
        String decoded = new String(utf8, StandardCharsets.UTF_8);

        System.out.println("UTF-8 round-trip: "
                + original.equals(decoded));
        System.out.println("bytes stable: "
                + Arrays.equals(utf8, decoded.getBytes(StandardCharsets.UTF_8)));

        String word = "café";
        byte[] encoded = word.getBytes(StandardCharsets.UTF_8);
        String wrong = new String(encoded, StandardCharsets.ISO_8859_1);
        System.out.println("wrong charset preserved: "
                + word.equals(wrong));
    }
}
~~~

~~~bash
javac -encoding UTF-8 CharsetRoundTripDemo.java
java CharsetRoundTripDemo
~~~

~~~text
UTF-8 round-trip: true
bytes stable: true
wrong charset preserved: false
~~~

Here accented characters and an emoji exercise the multi-byte path. The third check intentionally decodes with the wrong charset and verifies failure; that is a negative test. Checking bytes after re-encoding is also helpful when the contract requires a **byte-level round-trip**, though if strings are normalized or a format allows multiple equivalent encodings, test criteria must be adjusted accordingly.

## 7. Lossy Transcoding and Strict Error Mode

Some charsets cannot represent all Unicode characters. For instance, **US_ASCII** represents only the ASCII set; it cannot directly encode all Vietnamese letters. Convenience methods like String.getBytes(Charset) typically **replace unmappable characters with replacement bytes**, making encoding appear to succeed while original data is lost.

Never call encode and assume success means safety: **verify round-trips** or use **CharsetEncoder** with CodingErrorAction.REPORT to demand errors.

Create **StrictCharsetDemo.java**:

~~~java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CharsetDecoder;
import java.nio.charset.CharsetEncoder;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class StrictCharsetDemo {
    public static void main(String[] args) {
        String original = "Tiếng Việt";

        byte[] lossyBytes = original.getBytes(StandardCharsets.US_ASCII);
        String lossy = new String(lossyBytes, StandardCharsets.US_ASCII);
        System.out.println("ASCII round-trip equal: "
                + original.equals(lossy));

        CharsetEncoder asciiEncoder = StandardCharsets.US_ASCII.newEncoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);

        try {
            asciiEncoder.encode(CharBuffer.wrap(original));
            System.out.println("strict ASCII rejected: false");
        } catch (CharacterCodingException ex) {
            System.out.println("strict ASCII rejected: true");
        }

        byte[] malformedUtf8 = {(byte) 0xC3, (byte) 0x28};
        CharsetDecoder utf8Decoder = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);

        try {
            utf8Decoder.decode(ByteBuffer.wrap(malformedUtf8));
            System.out.println("malformed UTF-8 rejected: false");
        } catch (CharacterCodingException ex) {
            System.out.println("malformed UTF-8 rejected: true");
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 StrictCharsetDemo.java
java StrictCharsetDemo
~~~

~~~text
ASCII round-trip equal: false
strict ASCII rejected: true
malformed UTF-8 rejected: true
~~~

**Explanation:** an ASCII round-trip fails to recover accented text. In strict mode, CharsetEncoder fails on unmappable characters; CharsetDecoder fails on syntactically invalid UTF-8 bytes. When data integrity is required, define how errors are handled: notify the user, reject the record, or replace with explicit logging. Do not silently switch charsets assuming data will always be repaired.

**Malformed and unmappable are different:** malformed indicates an input byte/char sequence that is invalid in the encoding itself; unmappable means a valid character that the target charset cannot represent. CharsetEncoder and CharsetDecoder can be configured independently for REPORT, REPLACE, or IGNORE per data contract. When preserving text is required, REPLACE/IGNORE loses information.

## 8. Two-Way Transcoding Does Not Merge Equivalent Text Forms

Two strings can look alike without sharing the same Unicode units. For instance, é can be represented as a single code point **U+00E9**, or as letter e **U+0065** plus combining acute accent **U+0301**. A UTF-8 round-trip preserves the **exact original representation** of any valid string; it **does not perform Unicode normalization automatically**.

Example file **NormalizationDemo.java**:

~~~java
import java.text.Normalizer;
import java.nio.charset.StandardCharsets;

public class NormalizationDemo {
    public static void main(String[] args) {
        String composed = "\u00E9";
        String decomposed = "e\u0301";

        System.out.println("equal initially: "
                + composed.equals(decomposed));
        System.out.println("equal after NFC: "
                + Normalizer.normalize(composed, Normalizer.Form.NFC)
                        .equals(Normalizer.normalize(
                                decomposed, Normalizer.Form.NFC)));

        String decoded = new String(
                decomposed.getBytes(StandardCharsets.UTF_8),
                StandardCharsets.UTF_8
        );
        System.out.println("UTF-8 keeps representation: "
                + decomposed.equals(decoded));
    }
}
~~~

~~~bash
javac -encoding UTF-8 NormalizationDemo.java
java NormalizationDemo
~~~

~~~text
equal initially: false
equal after NFC: true
UTF-8 keeps representation: true
~~~

These are three distinct checks: **equality under Java String.equals**, **equivalence after NFC normalization**, and **exact code unit preservation across UTF-8 encode/decode**. Do not normalize data arbitrarily without a business requirement: normalization alters raw representations that matter for digital signatures, byte comparisons, or wire formats.

When testing accent-insensitive or case-insensitive search, you must also specify Locale-specific collation/case-folding rules; changing charsets alone never solves linguistic comparison.

## 9. Property- and Boundary-Driven Test Design

Rather than snapshotting a single formatted output string, establish clear invariants:

| Test Category | Invariant Worth Verifying | Boundary Cases |
| --- | --- | --- |
| Safe-domain number format/parse | parse(format(x)) preserves numeric value and consumes full string | Negative numbers, zero, very large values, decimals, rounding |
| Full-info date format/parse | parse(format(date)) equals date | Leap days, end of month, changing Locale |
| UTF-8 round-trip | decode(encode(s)) equals s for valid Unicode | Vietnamese text, emojis, empty string, combining characters |
| Byte-level round-trip | encode(decode(bytes)) restores valid bytes when guaranteed by charset/contract | Boundary byte sequences, BOM, malformed input |
| Encoding negative tests | Unsupported charset throws error or clearly fails round-trip | US_ASCII with accented characters, unpaired surrogates |
| Parse negative tests | Invalid strings are rejected, not accepted via a prefix | Trailing garbage, wrong separators, invalid numbers |
| Normalization | Equal after normalization rule when required by contract | Precomposed vs. decomposed characters |

With random inputs or property-based testing, restrict generated data to the **actual contract domain**. For example, you cannot demand every BigDecimal round-trips exactly through a two-decimal-place format; you cannot demand US_ASCII preserves every Unicode character. Suites should deliberately include both **success cases** and **expected failure cases**.

### A Framework-Free Java 17 Integration Test

File **LocaleCharsetContractTest.java**:

~~~java
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParsePosition;
import java.util.Locale;

public class LocaleCharsetContractTest {
    private static void check(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        DecimalFormat format = new DecimalFormat(
                "#,##0.00",
                DecimalFormatSymbols.getInstance(Locale.US)
        );
        format.setParseBigDecimal(true);

        BigDecimal value = new BigDecimal("1234.50");
        String formatted = format.format(value);
        ParsePosition pos = new ParsePosition(0);
        Number parsed = format.parse(formatted, pos);

        check(parsed instanceof BigDecimal, "Expected BigDecimal");
        check(pos.getIndex() == formatted.length(), "Partial parse");
        check(((BigDecimal) parsed).compareTo(value) == 0, "Value changed");

        String text = "Hà Nội 😀";
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        check(text.equals(new String(bytes, StandardCharsets.UTF_8)),
                "UTF-8 round-trip failed");

        String wrong = new String(
                text.getBytes(StandardCharsets.US_ASCII),
                StandardCharsets.US_ASCII
        );
        check(!text.equals(wrong), "Expected lossy ASCII conversion");

        System.out.println("PASS: locale numeric round-trip");
        System.out.println("PASS: UTF-8 text round-trip");
        System.out.println("PASS: negative ASCII test");
    }
}
~~~

~~~bash
javac -encoding UTF-8 LocaleCharsetContractTest.java
java LocaleCharsetContractTest
~~~

~~~text
PASS: locale numeric round-trip
PASS: UTF-8 text round-trip
PASS: negative ASCII test
~~~

check throws AssertionError on contract violations, so the test works regardless of Java's -ea option. Once a project uses JUnit, these checks can become assertEquals/assertThrows parameterized across multiple Locales, Charsets, and negative cases; the core remains **defining acceptance criteria clearly**.

## 10. Common Bugs in Production Systems

| Symptom | Likely Root Cause | How to Test and Fix |
| --- | --- | --- |
| Number format changes by machine | Relying on default Locale or different locale data | Pass Locale explicitly; lock formatter to contract |
| Numeric string misread or truncated | Mismatched format/parse Locales; prefix-only parser | Check sign, ParsePosition, and whole-string validity |
| Fractional digits lost in round-trip | Formatting rounds or caps decimal places | Define round-trip domain; use BigDecimal and explicit rounding |
| Date wording changes across JDKs | Localized month/formatting data differs | Test parsed date value; only freeze exact text if spec demands |
| Vietnamese text becomes question marks | Target charset cannot encode characters and silently replaces | Use UTF-8 where appropriate; enable REPORT when lossless required |
| Garbled mojibake text | Encoder and decoder use mismatched Charsets | Inspect raw bytes at boundaries; standardize Charset end-to-end |
| Invalid bytes yet program keeps running | Default decoder replaces malformed sequences | Use CharsetDecoder with CodingErrorAction.REPORT when strict |
| Emojis or surrogates fail | String holds unpaired surrogates or downstream lacks support | Build valid Unicode test sets; test malformed input separately |
| Visually identical strings return equals false | Different code point composition, e.g. NFC vs. NFD | Define normalization policy; do not confuse with charset |
| Tests pass locally yet fail in CI | Different default Locale/charset/timezone or JDK locale data | Specify every parameter, pin needed environment settings, test invariants |
| Data differs after format then parse | Display string is inherently lossy | Pass structured types directly; never calculate from display text |

## 11. Safe Implementation Principles

- **Use localized formats for UI, not as default interchange formats.** Protocols should define explicit standards such as canonical numbers or ISO-8601 dates; UIs format for the user's Locale.
- **Specify Charset right where text is read from files or APIs.** If a file or protocol specifies UTF-8, pass UTF-8 on both write and read instead of relying on OS defaults.
- **Separate formatting errors from encoding errors.** A wrong decimal/grouping separator is different from undecodable bytes; detection and remediation differ too.
- **Never rely on lenient parsing as sole validation.** Verify full input consumption, valid ranges, and business syntax rules.
- **Establish explicit error-handling rules.** When data preservation matters, prefer REPORT mode with exception handling over REPLACE/IGNORE.
- **Never assume round-trips preserve every property.** Formatting can round, drop timezones, or alter scale; Unicode normalization and charset loss can change bytes or content.

## 12. Self-Check Questions

**Question 1.** A number is formatted with Locale.GERMANY as 1.234,50. Should it be parsed back with Locale.US?

**Answer:** No, unless an explicit conversion contract exists. Dots and commas swap roles. Use the same Locale/format or a standardized interchange format, and verify the parser consumes the whole input.

**Question 2.** Does parsing "123abc" and getting 123 prove the input is valid?

**Answer:** No. You must check that the entire string was consumed, along with any business syntax and domain constraints.

**Question 3.** Why can encoding and decoding Vietnamese text with US_ASCII produce a different String than the original?

**Answer:** US_ASCII cannot represent many accented characters. Convenience APIs substitute replacement characters; to reject data loss, use strict encoders/decoders with REPORT.

**Question 4.** Precomposed é and e + combining accent may look identical, yet String.equals returns false. Does a UTF-8 round-trip make them equal?

**Answer:** No. UTF-8 preserves whatever valid Unicode representation you already had; normalization must be applied intentionally per contract.

## 13. Takeaway

Testing round-trip conversions requires defining **what must remain invariant**. For numbers and dates, the **semantic value** after format-then-parse usually matters most, while controlling rounding, Locale, precision, and full-string parsing. For text, what matters is whether **Unicode characters** or even **raw bytes** are recovered, whether Charsets match on both ends, and what data might be silently replaced.

Locale governs **regional presentation and interpretation of text**; Charset governs **how content encodes into bytes**. Specifying Locale/Charset explicitly, testing both valid and invalid inputs, and asserting clear round-trip invariants keeps tests reliable across developer machines, servers, and CI.
