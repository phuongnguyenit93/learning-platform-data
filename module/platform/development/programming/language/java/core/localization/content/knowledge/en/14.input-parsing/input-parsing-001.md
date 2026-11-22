# Distinguishing Formatting, Parsing, and Data Validation in Java

## 1. Three Distinct Operations in Locale-Aware Data Processing

In a multilingual application, users may see the number `1,234.50` in an English interface or another notation according to their locale. It is important to clearly distinguish three operations that are often lumped together:

1. **Format:** converting a value that already has a type and meaning into a **display string**, according to locale, digit count rules, currency, and date/time conventions.
2. **Parse:** attempting to read a string and produce a **typed value**, such as `BigDecimal` or `LocalDate`. A parser may consume only a prefix or accept lenient syntax.
3. **Validate:** confirming that a value satisfies **syntactic rules, full input consumption, and business rules**: non-negative amount, maximum number of decimal places, value within range, valid calendar date, and no trailing data.

**Remember: succeeding at formatting does not mean that string is the only accepted input form; succeeding at parsing does not mean the data is valid according to business rules.**

A simple example:

```text
BigDecimal(1234.50)
       |
       | FORMAT with Locale.US
       v
"1,234.50"                 -> display string
       |
       | PARSE (if input data)
       v
BigDecimal(1234.50)        -> interpreted value
       |
       | VALIDATE
       v
valid syntax, fully consumed, <= limit, >= 0, ...
       |
       v
allow storage/business processing
```

For data from APIs, databases, or integrated systems, do not pass values through a UI formatter and then parse them back to “normalize” them. Keep values in typed numeric/date forms, and use formatting only at the display boundary.

## 2. Comparing Formatting, Parsing, and Validation

| Processing Direction | Input | Output | Commonly Used Java APIs | Not Guaranteed |
| --- | --- | --- | --- | --- |
| Format | `Number`, `BigDecimal`, `Date`, `LocalDate`... | `String` | `NumberFormat.format`, `DecimalFormat.format`, `DateTimeFormatter.format` | Business currency unit, exchange rate, original numeric precision, or data validity. |
| Parse | `String` and pattern/locale configuration | `Number`, `BigDecimal`, `LocalDate`... or error | `DecimalFormat.parse`, `DateTimeFormatter.parse`, `LocalDate.parse` | Domain-appropriate value, strict input rules, or absence of trailing data across all APIs. |
| Validate | String and/or parsed value, plus policy | Accept/reject with reason | `Pattern`, `ParsePosition`, range checks, `BigDecimal.compareTo`, business conditions | Automatic translation/formatting of data or detection of any rule that is not explicitly encoded. |

All three steps may appear together in a single business flow, but they **do not replace one another**. The actual sequence depends on the domain: sometimes the entire grammar must be checked before parsing; for other formats, you parse first, check how many characters were consumed, and finally validate the value. In all cases, acceptance criteria must be written explicitly.

### Who Is Responsible for Which Rules?

- **Locale and formatter:** separators, digit grouping, display order of day/month/year, numeric symbols, and display language.
- **Parser:** converting text into data and reporting syntax errors according to the API's contract.
- **Application/domain:** minimum/maximum values, whether negative amounts are allowed, whether a date falls within a booking window, whether fractional parts are allowed, past or future date constraints, actual currency, and safety limits.
- **System boundary:** knowing whether input is a human-facing format or machine-to-machine data; deciding how to handle whitespace, Unicode normalization, decimal places, error messages, and retry behavior.

## 3. Locale-Based Number Formatting: Display String Only

Example using `DecimalFormat` with `Locale.US`:

```java
DecimalFormatSymbols symbols =
        DecimalFormatSymbols.getInstance(Locale.US);
DecimalFormat formatter =
        new DecimalFormat("#,##0.00", symbols);

String view = formatter.format(new BigDecimal("1234.5"));
// "1,234.50"
```

This is a snippet placed inside a Java method and requires importing `java.text.DecimalFormat`, `java.text.DecimalFormatSymbols`, `java.util.Locale`, and `java.math.BigDecimal`. It rounds/pads zeros and applies grouping separators according to the pattern/symbols; it **does not modify** the `BigDecimal("1234.5")` value.

Important notes:

- `format` can **round** when the source number has more digits than the pattern allows. The string `"1.23"` can be produced from different underlying values; full precision is not preserved.
- The pattern `"#,##0.00"` uses standard pattern syntax characters; the displayed decimal and grouping separators are determined by `DecimalFormatSymbols`.
- `DecimalFormat` does not verify whether an amount is negative, what the currency exchange rate is, or whether transaction limits are satisfied.
- To print numbers in a user's locale, pass an explicit locale. Do not change `Locale.setDefault(...)` per request; that is shared JVM-wide state.
- Do not use `format` to produce strings for storing monetary amounts in a database, identifier keys, or canonical JSON values. Machine-to-machine data should have its own schema, such as a locale-invariant decimal representation.

## 4. Number Parsing: More Permissive Than Expected

`DecimalFormat.parse(String)` can return a `Number` if it reads a valid prefix at the start of the string. Some parsers do not automatically enforce that the entire input was consumed. Therefore, a syntactically parsed result **is not necessarily valid according to the input screen's requirements**.

For example, assuming a parser configured with `Locale.US` and pattern `"#,##0.00"`:

```text
"1,234.50"       -> parsed as 1234.50
"1,234.50abc"    -> may parse 1234.50 and stop before "abc"
"12,34.50"       -> may parse 1234.50, even though digit grouping violates UI conventions
```

The last two strings should not be treated as valid by default if the form requires standard grouping and forbids trailing characters.

### Using ParsePosition to Check Full Consumption

`java.text.ParsePosition` lets you see at which character index the parser stopped:

```java
ParsePosition pos = new ParsePosition(0);
Number parsed = parser.parse(input, pos);

boolean completelyParsed =
        parsed != null && pos.getIndex() == input.length();
```

This is an illustrative Java snippet inside a method where `parser` and `input` are already created, not a standalone program.

- `parsed == null` means no value could be read.
- `pos.getIndex() == input.length()` proves the parser consumed the entire input string.
- However, **consuming the whole string is not enough**: for example, `"12,34.50"` may be read completely by `DecimalFormat` while still violating the form's three-digit grouping policy. Stricter grammar checks are needed when the UI requires them.
- `ParsePosition.getErrorIndex()` can help diagnose the error location; do not rely solely on the error index to conclude a value is valid, because full consumption and domain conditions still matter.

When parsing returns a value despite trailing characters, the parser may return a number without throwing `ParseException`. Do not treat a non-throwing `parse` call as proof that the entire input was accepted.

### Why Is BigDecimal Needed When Reading Exact Decimals?

`DecimalFormat` can be configured as follows:

```java
DecimalFormat parser = new DecimalFormat(
        "#,##0.00",
        DecimalFormatSymbols.getInstance(Locale.US));
parser.setParseBigDecimal(true);
```

In this mode, ordinary numeric values returned by `parse` can be handled as `BigDecimal`, avoiding binary floating-point inaccuracies of `double` in monetary logic. However, special values like NaN/infinity and specific parse conditions must still be accounted for; do not cast arbitrarily after receiving out-of-domain input. Using `BigDecimal` **does not automatically verify** that a number has at most two decimal places or falls within allowed limits.

## 5. Validation Consists of at Least Three Layers

An amount input screen might require: `Locale.US` formatting, a non-negative number, at most two digits after the decimal separator, a maximum of `10,000.00`, and no trailing content. This requires three layers of checks:

1. **Grammar (lexical/syntax):** does the string match the allowed shape? For example, disallow unexpected spaces, disallow grouping like `"12,34"`, disallow more than two fractional digits, and disallow letters.
2. **Conversion/parsing:** can it be read as an exact number, does the parser consume the entire input, and does it avoid producing special values?
3. **Domain/semantic:** is the value within `[0,10000]`, and does it satisfy rounding rules, limits, scale, currency unit, or specific business conditions?

Example classification table:

| Input | Meaning | Illustrative Policy Result |
| --- | --- | --- |
| `1,234.50` | Valid grouping, two decimal places | Valid; number `1234.50` |
| `10.00` | No grouping, two decimal places | Valid |
| `1,234.50abc` | Trailing letters | Invalid grammar |
| `12,34.50` | Incorrect grouping | Invalid grammar |
| `5.555` | Three decimal places | Invalid grammar |
| `-2.00` | Negative number | Parsed, but invalid in domain |
| `10,000.01` | Exceeds `10,000.00` limit | Invalid in domain |
| `abc` | Not a number | Invalid grammar / parse error |

Regular expressions can express a fixed UI grammar, but **do not apply a US regex to every locale**. In locales that use a decimal comma or whitespace grouping, the grammar must be designed for the rules accepted by the product. Some locales use non-breaking space (NBSP) or narrow non-breaking space (narrow NBSP); do not replace all of them with ASCII spaces without defining the requirement.

### Choosing a Whitespace Policy

A practical decision that must be documented is whether `" 1,234.50 "` is allowed. If so, define which characters are stripped, where, and inform the user. `String.trim()` does not handle all Unicode whitespace. Even though `strip()` handles more characters, that does not mean it handles every kind of space used in number formatting across all languages. For money and sensitive data, arbitrary normalization can mask invalid input.

### Do Not Confuse Validation with Sanitization

Sanitization/normalization can help handle Unicode differences or harmless characters, but it **does not replace validation**. In particular, do not simply delete separators, letters, currency symbols, or minus signs and then parse what remains: doing so can turn malformed input into a completely different number that the user never confirmed.

## 6. Standalone Java 17+ Example: Format, Parse, Validate

Create the file **`LocalizedInputDemo.java`** below. The example fixes `Locale.US` for monetary amounts and uses `BigDecimal`, `ParsePosition`, and an explicit grammar. The date section uses `DateTimeFormatter` in strict mode to distinguish parsing a real date from “fixing” a nonexistent date.

Business assumptions **for this example only**: accept an optional minus sign in the grammar to demonstrate that parsing differs from domain rules; after parsing, only accept **non-negative** numbers with at most two decimal places and not exceeding `10000.00`. If a minus sign appears even on `-0.00`, it is rejected by the policy that disallows negative signs. Grouping convention: either no grouping or exact three-digit grouping per `Locale.US`.

```java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParsePosition;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;
import java.util.regex.Pattern;

public class LocalizedInputDemo {

    private static final BigDecimal MAX =
            new BigDecimal("10000.00");

    // Accepted syntax of the sample form, not a general
    // grammar for every Locale.
    private static final Pattern US_AMOUNT = Pattern.compile(
            "-?(?:0|[1-9][0-9]*|[1-9][0-9]{0,2}"
            + "(?:,[0-9]{3})+)(?:\\.[0-9]{1,2})?");

    private static DecimalFormat createParser() {
        DecimalFormat parser = new DecimalFormat(
                "#,##0.00",
                DecimalFormatSymbols.getInstance(Locale.US));
        parser.setParseBigDecimal(true);
        return parser;
    }

    private static void checkAmount(String input,
                                    DecimalFormat parser) {
        if (!US_AMOUNT.matcher(input).matches()) {
            System.out.println(input + " -> INVALID_GRAMMAR");
            return;
        }

        ParsePosition position = new ParsePosition(0);
        Number parsed = parser.parse(input, position);
        if (!(parsed instanceof BigDecimal amount)
                || position.getIndex() != input.length()) {
            System.out.println(input + " -> PARSE_ERROR");
            return;
        }

        if (input.startsWith("-") || amount.signum() < 0
                || amount.compareTo(MAX) > 0) {
            System.out.println(input + " -> DOMAIN_ERROR");
            return;
        }

        System.out.println(input + " -> OK:"
                + amount.toPlainString());
    }

    private static void showPermissiveParse(String input,
                                            DecimalFormat parser) {
        ParsePosition position = new ParsePosition(0);
        Number number = parser.parse(input, position);
        System.out.println("lenient=" + input + " -> " + number
                + "; consumed=" + position.getIndex()
                + "/" + input.length());
    }

    private static void checkDate(String input,
                                  DateTimeFormatter formatter) {
        try {
            LocalDate date = LocalDate.parse(input, formatter);
            System.out.println("date=" + input + " -> " + date);
        } catch (DateTimeParseException ex) {
            System.out.println("date=" + input + " -> INVALID_DATE");
        }
    }

    public static void main(String[] args) {
        DecimalFormat parser = createParser();
        System.out.println("format="
                + parser.format(new BigDecimal("1234.5")));

        showPermissiveParse("12,34.50", parser);
        showPermissiveParse("1,234.50abc", parser);

        String[] amounts = {
                "1,234.50", "1,234.50abc",
                "12,34.50", "-2.00",
                "5.555", "abc", "10.00",
                "10,000.01"
        };
        for (String input : amounts) {
            checkAmount(input, parser);
        }

        DateTimeFormatter dates = DateTimeFormatter
                .ofPattern("dd/MM/uuuu",
                        Locale.forLanguageTag("vi-VN"))
                .withResolverStyle(ResolverStyle.STRICT);

        for (String input : new String[] {
                "29/02/2024", "31/02/2024", "29/02/2023"
        }) {
            checkDate(input, dates);
        }
    }
}
```

Compile and run with JDK 17+ in the directory containing the file:

```bash
javac -encoding UTF-8 LocalizedInputDemo.java
java LocalizedInputDemo
```

**Expected stdout with the configuration in the example:**

```text
format=1,234.50
lenient=12,34.50 -> 1234.50; consumed=8/8
lenient=1,234.50abc -> 1234.50; consumed=8/11
1,234.50 -> OK:1234.50
1,234.50abc -> INVALID_GRAMMAR
12,34.50 -> INVALID_GRAMMAR
-2.00 -> DOMAIN_ERROR
5.555 -> INVALID_GRAMMAR
abc -> INVALID_GRAMMAR
10.00 -> OK:10.00
10,000.01 -> DOMAIN_ERROR
date=29/02/2024 -> 2024-02-29
date=31/02/2024 -> INVALID_DATE
date=29/02/2023 -> INVALID_DATE
```

### Analyzing the Three Types of Results

**Format:** `new BigDecimal("1234.5")` is formatted as `1,234.50`, adding grouping separators and decimal digits according to the pattern. The underlying data remains a `BigDecimal`.

**Parse:** the two `lenient` lines show that the parser can consume an entire grouping syntax that the form does not accept, or stop before a trailing string. This is lenient conversion behavior, not a validation conclusion.

**Validate:** the regex rules reject inputs with invalid grammar; `ParsePosition` and type checks catch parse/consumption failures; `BigDecimal.compareTo` and sign rules enforce domain rules. `10,000.01` is syntactically valid but exceeds the limit.

**Dates:** `29/02/2024` is a valid leap day. `31/02/2024` and `29/02/2023` do not exist and are rejected by `ResolverStyle.STRICT`. Notably, the pattern uses `uuuu` (proleptic year) instead of `yyyy` (year-of-era), avoiding a common pitfall with the strict resolver when no era is provided.

The example intentionally does not alter the JVM default locale and does not modify project files. If your product needs multiple locales, build a corresponding grammar for each locale rather than applying the `Locale.US` regex directly to all of them.

## 7. Date/Time: Parsed Dates Must Be Valid Calendar Dates

For dates and times, two commonly encountered APIs are:

- `java.text.SimpleDateFormat`: legacy, mutable API with lenient configuration; you must explicitly call `setLenient(false)` when you want strict calendar parsing and verify full string consumption.
- `java.time.format.DateTimeFormatter` (Java 8+): modern, immutable API supporting `ResolverStyle.STRICT`, explicit locale, and patterns.

Example:

```java
DateTimeFormatter formatter = DateTimeFormatter
        .ofPattern("dd/MM/uuuu", Locale.forLanguageTag("vi-VN"))
        .withResolverStyle(ResolverStyle.STRICT);

LocalDate date = LocalDate.parse("29/02/2024", formatter);
// 2024-02-29
```

The snippet above sits inside a Java method and is not a complete program; a runnable example was already shown in Section 6.

With `DateTimeFormatter`, distinguish **text representation** from **date value**:

- `format(LocalDate)` returns a display string according to the pattern and locale.
- `LocalDate.parse(...)` creates a typed date and may throw `DateTimeParseException` when the string does not match or the date does not exist.
- Business validation also checks whether the date falls within the allowed range; for example, whether an order date can be in the past, whether bookings are capped at 90 days, or whether a birth date satisfies policy.
- `LocalDate` does not represent an instant in a time zone. For appointment/scheduling times, specify a `ZoneId` and account for daylight saving time transitions or nonexistent/repeated local times.

### Pitfalls in Legacy Date APIs

`SimpleDateFormat` can “roll over” a nonexistent date into another date when lenient. If you need accurate input validation, set `setLenient(false)` and do not ignore trailing suffixes. `DateFormat.parse(String)` does not replace domain date validation. Furthermore, patterns in `SimpleDateFormat` and `DateTimeFormatter` have differences, especially around `y`/`u`, week-of-year, and time zones; do not port patterns between the two APIs without testing.

## 8. Context-Aware Business Validation

### 8.1. A Number Is Not Money

An input `1234.50` does not by itself tell you whether it is USD, VND, EUR, or another quantity. If a system manages money, store the **amount and currency code separately**, then validate that the currency belongs to the allowed list. `NumberFormat.getCurrencyInstance(locale)` helps with display, but it does not verify exchange rates or transaction units.

A product quantity may have to be an integer; a monetary amount may allow two decimal places; a weight may allow three; an interest rate may allow more. Do not apply a single regex or scale across all business domains.

### 8.2. Integer Value, Fractional Part, and Precision

A `BigDecimal` has two important concepts:

- **Value:** checked using `compareTo(...)` when determining greater-than/less-than.
- **Scale:** the number of digits to the right of the decimal point in the BigDecimal representation, which can be used for precision-limiting policies, though you must decide whether trailing insignificant zeros are permitted.

For example, `1.0` and `1.00` have equal numeric value under `compareTo`, but differ in `scale()` and input appearance. If a contract requires at most two decimal places, you can control the textual shape before parsing and check the scale afterward. Do not treat `BigDecimal.equals` as numeric value equality in all situations, because it also compares scale.

### 8.3. Digits and Unicode Characters

Users may enter ASCII digits, digits from other numeral systems, Unicode minus signs, or special whitespace characters. Parsers and regexes may handle them differently; do not assume `[0-9]` matches all Unicode digits or that `\\d` means the same thing under every regex configuration. When local digits must be supported, base the design on product requirements, `Locale`, and appropriate parsers/normalizers, backed by dedicated tests.

Numeric fields carrying important values should not silently strip unfamiliar characters. If converting digits to a canonical form is allowed, it must follow well-defined rules and preserve an audit trail when needed.

### 8.4. Length, Resource, and Magnitude Limits

Validation is not just about separators and numeric ranges. A numeric input millions of characters long can bog down parsers or downstream code. Enforce reasonable length, precision, and magnitude limits **before** executing expensive operations. On API servers, combine payload limits with error handling to defend against malformed or abusive input.

### 8.5. Separating Checks for Accurate Error Reporting

Instead of a single `"Invalid input"` message for everything, you can categorize failures:

- `INVALID_GRAMMAR`: disallowed characters, grouping, decimal digits, or syntax.
- `PARSE_ERROR`: cannot convert to a typed value or trailing unparsed suffix remains.
- `DOMAIN_ERROR`: parsed number/value violates limits, sign, unit, or business conditions.

These labels in the demo are technical labels. The user interface should translate them into short, helpful messages in the product's locale. Do not expose raw technical exception messages or stack traces directly to end users.

## 9. When Should You Use Which API?

| Scenario | Recommendation |
| --- | --- |
| Displaying numbers in the user's language | `NumberFormat` or `DecimalFormat` with an explicit `Locale`. |
| Displaying dates and times | `DateTimeFormatter`, `Locale`, and `ZoneId` appropriate to context. |
| Parsing numbers from a locale-specific form | Appropriate `DecimalFormat`/`NumberFormat`, checking `ParsePosition` and form grammar rules. |
| Parsing exact monetary strings | Parse into `BigDecimal` and validate scale, range, and currency; never route through `double`. |
| Parsing dates from input with a fixed pattern | `LocalDate.parse` with `DateTimeFormatter` and `ResolverStyle.STRICT`. |
| Receiving numbers from a JSON API | Use a consistent numeric/decimal schema independent of UI locale; do not apply US regex across all countries. |
| Receiving input in a canonical format | Parse according to the specified canonical format rather than guessing the locale from each string. |
| Checking non-negative amount with a 10,000 limit | Domain validation after determining the value; do not expect the formatter to enforce it. |
| Reporting input errors to users | Structured error codes with messages localized via `ResourceBundle`/translation mechanisms. |

### Parsing and Regex: Not an Either/Or Choice

A good regex can verify a **specific input shape**; a parser understands numeric/locale rules, produces typed data, and reports status. However:

- A single regex for the entire world easily becomes overly complex and misses valid characters.
- A parser may be too permissive relative to the input screen's policy.
- Both still require business range validation.

For diverse locale data, you can choose an input component tested for each market and use a well-designed input-normalization API. Avoid building a universal regex based on the assumption that “every language uses a comma for thousands grouping.”

## 10. Immutability, Concurrency, and Shared Objects

`DecimalFormat` and `SimpleDateFormat` are **mutable** and are not safe when arbitrarily shared across multiple threads. Do not keep a `static DecimalFormat` and mutate its `Locale`, pattern, or suffix per request. Create a new formatter per operation, clone a template, or synchronize properly.

`DateTimeFormatter` from `java.time` is immutable and generally suitable for sharing across threads once configured. Reusing a formatter does not make unvalidated input safe; dates must still undergo domain validation.

Multithreaded environments should also never change `Locale.setDefault(...)` to parse per request; that setter mutates JVM-wide state and can affect other users. Pass `Locale` explicitly to parsers/formatters.

## 11. Common Mistakes and How to Avoid Them

| Mistake | Why It Is Wrong | How to Fix |
| --- | --- | --- |
| Using `format(parse(text))` string equality as the sole validation | Formatter can alter grouping, precision, and reject other valid input forms. | Design grammar, parse completely, and run domain validation. |
| Assuming `DecimalFormat.parse` always consumes the entire input | It can read a prefix and ignore the tail. | Use `ParsePosition` and compare against full string length. |
| Assuming the parser always checks grouping strictly | It may accept `12,34.50` as 1234.50. | Validate grouping according to form policy. |
| Deleting commas, minus signs, and unfamiliar characters before parsing | Invalid data can turn into a different number. | Normalize according to explicit rules, then validate. |
| Using `double` for money and exact equality comparisons | Binary rounding errors easily cause rounding/comparison bugs. | Use `BigDecimal` with explicit rounding/scale policies. |
| Applying a `Locale.US` regex to strings of all locales | Decimal/grouping separators, digits, and whitespace differ. | Choose parser/grammar according to the actual locale. |
| Assuming `parse("31/02/2024")` is always rejected | Some lenient calendar parsers automatically roll dates forward. | Use `ResolverStyle.STRICT` or disable lenient mode. |
| Using `yyyy` without understanding year-of-era in strict mode | Date parsing can fail due to missing era. | Use `uuuu` when the pattern expects a proleptic year. |
| Validating only with regex and skipping limits | `999999...` may match the shape but violate the domain. | Enforce length, range, precision, and unit limits. |
| Treating currency formatting as currency conversion | It only changes representation. | Separate currency/FX logic from UI formatting. |
| Sharing a mutable parser across threads | Race conditions and inconsistent results. | Create per-request instances or synchronize. |
| Displaying raw exception messages | Confusing to users and may leak technical details. | Map error codes to appropriate localized messages. |

## 12. Testing Input: Positive, Negative, and Boundary Cases

A solid test suite needs to test **every layer**. For the amount form in the demo:

| Group | Example | Expectation |
| --- | --- | --- |
| Basic valid | `0`, `10.00`, `1,234.50` | Accept. |
| Invalid grouping | `1,23`, `12,34.50` | Reject at grammar check. |
| Trailing characters | `1,234.50abc`, `10.00 USD` | Reject if policy forbids suffixes. |
| Negative numbers | `-2.00`, `-0.00` | Reject per no-negative-sign policy. |
| Too many decimal places | `5.555` | Reject for grammar/precision. |
| Boundary limits | `10,000.00`, `10,000.01` | Accept at limit, reject above limit. |
| Unicode characters | Non-ASCII digits, NBSP, Unicode minus | Accept/reject per documented policy. |
| Null/empty | `null`, `""`, whitespace-only strings | Produce a clear validation result without unexpected exceptions. |
| Excessive length | Strings with tens of thousands of digits | Reject early before heavy parsing. |
| Calendar | `29/02/2024`, `29/02/2023`, `31/02/2024` | Only real calendar dates parse successfully. |

Note: the demo passes input to `Pattern.matcher(input)` and expects `input` to be non-null. In a real form or API, check for null and length limits **before calling the matcher**.

### Default-Locale-Independent Tests

On different machines, `Locale.getDefault()` may be `vi-VN`, `en-US`, or something else. Do not write tests that assume the JVM default always matches the developer's machine. In unit tests, pass an explicit `Locale`, choose a fixed `ZoneId` if needed, and test strings designed specifically for that locale.

## 13. Hands-On Exercises

**Exercise 1 — Distinguish the three stages:** take `BigDecimal("1234.567")`, format it with `DecimalFormat("#,##0.00", Locale.US symbols)`, and then parse the formatted string. Compare the original value with the re-parsed value. Explain why the format → parse pipeline does not preserve precision.

**Exercise 2 — Fix the trailing input gap:** call `DecimalFormat.parse` on `"123abc"`, recording the `Number` result and the `ParsePosition` index. Write a check that rejects the input if the parser did not consume the full string, instead of only checking that the result is non-null.

**Exercise 3 — Form-specific grouping:** extend the grammar to accept negative numbers on a different screen; test `12,345.67`, `12,34.67`, `-0.00`, and strings containing Unicode separators. Document which policies are syntactic and which are domain-level.

**Exercise 4 — Nonexistent dates:** compare lenient `SimpleDateFormat` against strict `DateTimeFormatter` for `"31/02/2024"`. Then add validation rejecting past dates in a booking feature. Observe clearly that **parsing a valid date** and **being allowed to book** are two separate questions.

**Exercise 5 — Multi-locale:** design a quantity or monetary input form for `Locale.US` and `Locale.forLanguageTag("vi-VN")`. Choose policies for grouping, decimal separator, Unicode characters, and error reporting. Run tests on CI under different JVM default locales while always configuring parsers/formatters explicitly.

**Exercise 6 — Domain validation:** require values from `0` to `10000`, at most two fractional digits, no negative sign, and currency `USD`. Design a DTO with separate amount and currency fields. Test cases that pass syntax checks but fail limits/currency, as well as cases with a valid amount prefix where the full input was not parsed.

## 14. Checklist and Conclusion

- [ ] Correctly state the direction of **format** (typed value → string) and **parse** (string → typed value).
- [ ] Know why a successful parse does not automatically mean the entire input was consumed or the grouping structure is valid.
- [ ] Use `ParsePosition` when detecting trailing text is needed, and handle nulls/exceptions appropriately.
- [ ] Distinguish grammar checks, conversion checks, and domain checks; enforce length limits before parsing.
- [ ] For money/decimals, understand why `BigDecimal` is used, validate range/scale, and manage currency separately.
- [ ] For dates, know how to enforce strict parsing, avoid silently rolling nonexistent dates, and add business rules.
- [ ] Avoid relying on JVM-wide default locale/timezone, and avoid unsafe sharing of mutable formatters/parsers.
- [ ] Include tests for valid input, invalid syntax, negative zero, Unicode characters, trailing input, boundaries, and value ranges.

**Core rule:** **format to present, parse to interpret data, validate to decide acceptance.** These three operations serve different purposes; the right approach is to define a clear input contract and verify all layers before using the value in business logic.
