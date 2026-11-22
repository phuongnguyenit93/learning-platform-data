# Locale-Aware Input Parsing with Full-String Validation in Java

## 1. Practical Problem: Successful Parsing Does Not Guarantee Valid Input

Users in different regions may enter **the same numeric value** using different strings: `1,234.50` under `en-US` conventions, yet `1.234,50` under `de-DE`. A date might also be written `29/02/2024`, `02/29/2024`, or with a language-specific month name. A multilingual Java application needs to interpret **text input** according to the selected rules while confirming **the user entered one complete valid value**, not merely a prefix that a parser happened to understand.

For instance, some parsers parse the `123` portion of `123abc` and stop at `a`. If the application only asks "did `parse` return a `Number`?", it can inadvertently accept a string containing trailing garbage. Conversely, even when a parser **consumes the entire string**, it may still accept grouping separator placements that business rules forbid.

This hands-on guide addresses **two independent validation layers**:

1. **Full-string validation (full consumption):** the parser must process up to the exact end of the input, leaving no leftover characters.
2. **Syntactic and semantic policy validation:** formatting, grouping separators, fractional digit count, value range, calendar validity, and currency unit must satisfy the designed contract.

**Do not treat these two steps as one.** `ParsePosition` lets you check how far the parser advanced; `ResolverStyle.STRICT` enforces valid calendar resolution; yet a financial system still requires its own rules for grouping, precision, and monetary bounds.

## 2. Deciding the Data Format Before Parsing

A multilingual application typically handles at least two kinds of input:

| Input Source | Example | How It Should Be Handled |
| --- | --- | --- |
| **Locale-aware UI input box** | `12,50` in `de-DE` | Select supported locale, validate syntax, parse per locale, validate business rules |
| **Machine-to-machine field with fixed schema** | JSON number `12.50` | Use a standard JSON parser; independent of `Accept-Language` |
| **CSV imported under a source contract** | `12.50` with fixed `.` decimal | Follow source dialect/schema, do not guess locale from reader |
| **Calendar date entered in UI** | `29/02/2024` matching published pattern | Parse `LocalDate` using pattern/locale and strict resolver |
| **API timestamp exchange** | `2024-02-29T10:00:00Z` | Parse ISO instant/offset per contract, not UI date format |
| **Monetary amount with currency** | amount `12,50` + currency `EUR` | Parse decimal, validate currency separately, apply scale/range rules |
| **Technical identifier** | `INV-00125` | Do not process with `NumberFormat`, which can drop leading zeros and code characters |

`Locale` is a parameter governing **text reading/display rules**—it does not verify payment source, currency unit, time zone, or legal jurisdiction. User-selected locales and machine data contracts must be managed separately.

### 2.1. What Happens If the Wrong Locale Is Chosen?

In US locales, comma is typically the grouping separator and dot is the decimal separator. In Germany, their roles reverse. The string `1,23` may mean "one point two three" to a user accustomed to decimal commas; however, an `en-US` parser can interpret it as **123** because the comma is treated as a grouping separator.

Do not check merely whether "the parser didn't throw"; ensure the locale is accurately chosen from the UI context or import source configuration. Never try parsing sequentially across multiple locales and take the first success: the same string can have **multiple valid parses with different values**.

## 3. NumberFormat and DecimalFormat in Java 17

`java.text.NumberFormat` is the locale-aware number formatting and parsing API:

~~~java
NumberFormat formatter = NumberFormat.getNumberInstance(Locale.US);
~~~

This is an **illustrative snippet inside a method**, requiring `import java.text.NumberFormat;` and `import java.util.Locale;`. Key points:

- `getNumberInstance(locale)` retrieves a formatter/parser configured with locale data from the runtime.
- `NumberFormat.parse(String, ParsePosition)` returns the parsed value and updates the index of consumed characters.
- `DecimalFormat` is the common implementation offering `setParseBigDecimal(true)`.
- `DecimalFormat` is **mutable** and should not be shared and reconfigured across threads.
- Locale/CLDR data and locale providers can change across JDKs; do not hardcode punctuation outcomes for every locale without checking the target runtime.

For monetary handling needing precision, use `BigDecimal` instead of `double` arithmetic. In standard Java environments, `NumberFormat.getNumberInstance(Locale.US)` is typically a `DecimalFormat`; if another locale provider returns a different subtype, handle that explicitly instead of casting blindly.

### 3.1. Understanding ParsePosition Properly

~~~java
ParsePosition pos = new ParsePosition(0);
Number result = formatter.parse(text, pos);
~~~

These two illustrative statements assume `formatter` and `text` exist. Their fields:

- `pos.getIndex()`: the UTF-16 index immediately following the portion successfully consumed by the parser.
- `text.length()`: total number of UTF-16 code units in the input.
- `pos.getErrorIndex()`: the index where the parser recorded an error on failure, if any. It can remain `-1` when the parser **partially succeeds** and stops before a suffix.
- `result`: the parsed value, or `null` if nothing could be parsed at the starting position.

Basic condition:

~~~java
boolean fullyConsumed = result != null
        && pos.getIndex() == text.length();
~~~

This is a **necessary** condition to accept a numeric value, not automatically a **sufficient** condition for all input rules.

When starting with `ParsePosition(0)`, never check merely `pos.getIndex() > 0`; that proves only that a prefix was consumed. Always compare the index against `length()` and check `result != null`.

**The index is in UTF-16 code units**, not byte offsets or code-point ordinals. For strings containing surrogate pairs, `length()` remains the right end boundary because `ParsePosition` also operates on `String` indices.

### 3.2. Why Doesn't parse(String) Guarantee Full-String Consumption?

The convenience overload `NumberFormat.parse(String)` can accept a **valid prefix**, depending on the pattern and parser. It does not expose a direct full-consumption check to the caller like `ParsePosition`.

If the user types `1,234.50oops`, the `en-US` parser can parse the numeric portion and leave `oops` behind. Validation code must reject such input.

The standalone program in Section 8 explicitly tests a suffixed input and prints `en suffix=REJECTED`.

### 3.3. BigDecimal and Exact Parsing

With `DecimalFormat`, call `setParseBigDecimal(true)` before parsing:

~~~java
DecimalFormat decimal = (DecimalFormat)
        NumberFormat.getNumberInstance(Locale.US);
decimal.setParseBigDecimal(true);
~~~

This snippet reflects common provider behavior; the complete example in Section 8 **checks `instanceof`** before casting. When this mode is enabled, finite numbers in the example return `BigDecimal`. Never use `new BigDecimal(Double.toString(...))` as a casual workaround if the parser already lost precision via `double`.

`BigDecimal` preserves exact decimal values; however, valid monetary validation still requires business logic: positive/non-negative checks, bounds, scale, currency, rounding policy, and persistence limits.

## 4. Full Consumption Is Not Enough: Grouping Separators and Width

Consider the string:

~~~text
Input en-US: "1,23"
~~~

In tested Java environments, the `DecimalFormat` returned by `NumberFormat.getNumberInstance(Locale.US)` **reads the entire string** and returns `123`. The parser is lenient with grouping-separator placement; it does not necessarily reject non-standard grouping.

Therefore:

~~~text
parse succeeds + pos.index == input.length
DOES NOT IMPLY
valid grouping per UI or accounting rules.
~~~

Depending on requirements, you may choose to:

- **Accept flexible grouping** for casual input and clearly echo the parsed value at confirmation.
- **Forbid grouping** in a monetary input box to prevent ambiguity; accept only digits and the locale's decimal separator.
- **Allow strict grouping** matching a defined pattern, enforcing leading group, middle group, and specific separator rules.
- **Require a fixed protocol format** (e.g., a dot-decimal JSON string) for machine data, independent of locale.

In this hands-on example, `parseMoneyNoGrouping` implements an **intentionally narrow policy**:

1. Accept only ASCII digits `0`–`9`.
2. Reject grouping separators, minus signs, plus signs, and whitespace.
3. Accept an optional fractional part with **one or two digits** after the locale's decimal separator.
4. Even after passing the regex, parse the number and verify full consumption.

This is a **policy example** for a non-negative amount field, not a universal definition of "valid number in every locale." It does not support localized digits such as Arabic-Indic numerals and does not apply to all grouping conventions worldwide. If your product needs localized digits, define the allowed digit set and digitization rules explicitly, and test each locale.

### 4.1. Retrieving the Locale's Decimal Separator

~~~java
char separator = DecimalFormatSymbols.getInstance(locale)
        .getDecimalSeparator();
~~~

This snippet assumes `locale` is defined and `DecimalFormatSymbols` is imported. Combine it with `Pattern.quote(String.valueOf(separator))` so that characters like `.` are treated as **literal characters in regex**, not the "any character" metacharacter.

Do not replace all commas with dots and parse via `BigDecimal` when input can contain grouping separators. For example, German `1.234,50` uses `.` for grouping and `,` for decimals; naive replacement produces wrong numbers or confusing failures.

### 4.2. Should You Compare Round-Trip format(parse(s)) Against s?

Comparing `format(parse(input)).equals(input)` can catch discrepancies if you **mandate a single canonical display form**, but it is not a general-purpose locale-input validator:

- A user may enter `12,5` instead of `12,50`, both representing the same value.
- Parsers/formatters may insert or strip grouping separators based on patterns.
- Formatters may round, pad zeros, or use different spaces/Unicode spacing.
- Locale providers can vary formatting across JDK versions.

If business rules demand one exact pattern, define that pattern/syntax upfront and validate it. If multiple valid input forms are permitted, do not use formatted-string equality as the sole criterion.

## 5. Date Parsing: Strict in Both Syntax and Calendar Rules

Numbers and dates follow different models. `LocalDate` is a **calendar date**, requiring validation of months, days, leap years, and input boundaries. Java 17 provides the modern `java.time` API:

~~~java
DateTimeFormatter dateFormatter = DateTimeFormatter
        .ofPattern("dd/MM/uuuu", locale)
        .withResolverStyle(ResolverStyle.STRICT);

LocalDate date = LocalDate.parse(text, dateFormatter);
~~~

This snippet lives inside a method and requires importing `DateTimeFormatter`, `ResolverStyle`, and `LocalDate`, with `locale` and `text` supplied. `LocalDate.parse` uses the formatter to parse the **entire input** and throws `DateTimeParseException` on trailing suffixes or invalid dates.

### 5.1. Why Use uuuu Instead of yyyy?

In `DateTimeFormatter`:

- `u` is **proleptic year**.
- `y` is **year-of-era**, which can require `ERA` context to resolve completely under `ResolverStyle.STRICT`.
- `M` is month-of-year.
- `d` is day-of-month.

For a simple ISO date field requiring strict resolution, `dd/MM/uuuu` is more convenient than `dd/MM/yyyy`. Using `yyyy` with `STRICT` without providing an era can trigger unexpected resolution errors. Do not replace `uuuu` with `yyyy` just because both patterns look similar on screen.

### 5.2. STRICT, SMART, and LENIENT

`ResolverStyle.STRICT` requires date fields to be valid within the calendar chronology. For example:

~~~text
29/02/2024 -> valid (2024 is a leap year)
29/02/2023 -> invalid (2023 is not a leap year)
31/04/2024 -> invalid (April has only 30 days)
~~~

`ResolverStyle.SMART` can clamp certain out-of-range days during resolution, such as adjusting day 31 to the last day of the month; `LENIENT` can even overflow fields into subsequent months/years. **Never** use `SMART` or `LENIENT` for user-entered dates that must match exact calendar validity.

Technical note: `ResolverStyle` governs the **calendar-field resolution phase**, not the entire lexical grammar. If you need exact field widths, digit sets, separators, or case folding, use a `DateTimeFormatterBuilder` or additional lexical checks. `LocalDate.parse` already enforces full consumption, though that does not automatically check language policy, business date ranges, or time zones.

### 5.3. DateTimeFormatter Is Immutable; DecimalFormat Is Not

`DateTimeFormatter` is **immutable** and thread-safe, so instances for a fixed pattern/locale can be prebuilt and safely reused. `DecimalFormat` is **mutable** and should not be shared across threads without dedicated synchronization. In the example below, creating a fresh `DecimalFormat` per parse prevents shared state mutation.

When caching formatters by locale, the cache key must include every component affecting output—such as locale, pattern, resolver style, zone (if any), chronology, decimal style, and other design options. Never cache a single `DateTimeFormatter` and share it across all locales.

### 5.4. UI Dates Differ from Machine Timestamps

The string `29/02/2024` is a calendar date in the input pattern. It implies neither a time zone nor an absolute `Instant`. For APIs transmitting instants, use `Instant.parse` or an explicit ISO formatter; for birthdays, `LocalDate` is usually appropriate. Never convert a calendar date into a `00:00 UTC` timestamp without an explicit business-domain definition.

## 6. Decisions About Whitespace, Unicode, and Dirty Input

### 6.1. Trimming Can Alter Input Meaning

Some forms tolerate accidental leading/trailing spaces. If policy permits, the application can perform **controlled normalization** before parsing. However, for strict full-string validation of raw input, never silently `trim()` beforehand and claim the original string was "100% valid."

Example:

~~~text
"12.50"  -> valid under the narrow policy
"12.50 " -> must be rejected if policy forbids whitespace
~~~

If your product **accepts** whitespace, document the normalization rule explicitly. `String.trim()` strips a narrower character set than `String.strip()`, and neither handles every Unicode separator or non-breaking space cleanly by itself.

### 6.2. Grouping Separators Can Be Subtle Invisible Characters

Many locales use regular spaces, non-breaking space `U+00A0`, narrow no-break space `U+202F`, or other characters as separators. Two strings can look identical while holding different code points, yielding different parser behavior.

When debugging:

- Print code points (e.g., via `String.codePoints()`) instead of trusting visual glyphs alone.
- Confirm which locale and provider were selected.
- Document policies for grouping, whitespace, and Unicode digits.
- Avoid blindly replacing `U+00A0` with ASCII space across all inputs unless your contract allows it.

### 6.3. Locale Is Not a Security Mechanism

`Accept-Language` and user language settings should **not** be relied on to verify legal jurisdiction, currency unit, or access permissions. Machine data such as JSON numbers, ISO timestamps, IDs, and error codes must be parsed under fixed schemas. For free-form user input, validate length, charset, bounds, and field type according to business policy rather than relying solely on whether a formatter parsed it.

## 7. A Testable Validation Flow

Diagram:

~~~text
Raw UI input + supported Locale
               |
               v
  Select field policy:
  number, money, date, decimal, percent?
               |
               v
  Validate lexical input (if field requires narrow syntax)
               |
               v
  Parse using selected Locale / pattern
               |
               v
  Verify full consumption or use full-parse API
               |
               v
  Validate business constraints + typed value
               |
               v
  Store BigDecimal / LocalDate / domain value
               |
               v
  Serialize machine data using a stable schema
~~~

On invalid input, the UI should report an error with a **technical code and localized message**, rather than exposing raw `ParseException.toString()` text to end users. Technical details such as `position`/`errorIndex` can help logs and diagnostics, though sensitive input data must not be leaked into logs.

### 7.1. Things ParsePosition Does Not Do Automatically

`ParsePosition` does **not**:

- Enforce that a monetary amount is positive.
- Validate that a currency code is accepted.
- Prevent non-standard grouping if the parser accepts it.
- Reject excessive decimal places if the parser can parse them.
- Verify that a `BigDecimal` fits database column limits.
- Validate year/month/day ordering of a `LocalDate` field.
- Replace a schema-driven JSON/CSV parser.

Those are separate validation layers applied before or after parsing depending on the field's contract.

## 8. Complete Java 17 Program

This program demonstrates:

- Parsing `en-US` and `de-DE` numbers with `DecimalFormat` returning `BigDecimal`.
- Using `ParsePosition` to **reject trailing characters at the end of the string**.
- Showing that `1,23` in `en-US` is still parsed as `123` by the general parser.
- Using a regex built from the locale's decimal separator to enforce **no grouping, at most two fractional digits**.
- Using `LocalDate.parse` and `ResolverStyle.STRICT` to reject invalid dates and trailing suffixes.

**Save the file `LocaleInputValidationDemo.java`:**

~~~java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;
import java.util.regex.Pattern;

public class LocaleInputValidationDemo {
    static BigDecimal parseWholeDecimal(String text, Locale locale) {
        NumberFormat format = NumberFormat.getNumberInstance(locale);
        if (!(format instanceof DecimalFormat decimal)) {
            throw new IllegalStateException(
                    "DecimalFormat provider required");
        }
        decimal.setParseBigDecimal(true);
        ParsePosition pos = new ParsePosition(0);
        Number number = decimal.parse(text, pos);
        if (number == null || pos.getIndex() != text.length()) {
            throw new IllegalArgumentException(
                    "Invalid number, consumed=" + pos.getIndex()
                    + ", length=" + text.length()
                    + ", errorIndex=" + pos.getErrorIndex());
        }
        return (BigDecimal) number;
    }

    static BigDecimal parseMoneyNoGrouping(String text, Locale locale) {
        char decimal = DecimalFormatSymbols.getInstance(locale)
                .getDecimalSeparator();
        String rule = "[0-9]+(?:"
                + Pattern.quote(String.valueOf(decimal))
                + "[0-9]{1,2})?";
        if (!Pattern.matches(rule, text)) {
            throw new IllegalArgumentException("Invalid money syntax");
        }
        return parseWholeDecimal(text, locale);
    }

    static LocalDate parseStrictDate(String text, Locale locale) {
        DateTimeFormatter formatter = DateTimeFormatter
                .ofPattern("dd/MM/uuuu", locale)
                .withResolverStyle(ResolverStyle.STRICT);
        return LocalDate.parse(text, formatter);
    }

    public static void main(String[] args) {
        Locale en = Locale.US;
        Locale de = Locale.GERMANY;

        System.out.println("en full=" +
                parseWholeDecimal("1,234.50", en).toPlainString());
        System.out.println("de full=" +
                parseWholeDecimal("1.234,50", de).toPlainString());

        try {
            parseWholeDecimal("1,234.50oops", en);
            System.out.println("en suffix=ACCEPTED");
        } catch (IllegalArgumentException e) {
            System.out.println("en suffix=REJECTED");
        }

        System.out.println("en odd grouping parses=" +
                parseWholeDecimal("1,23", en).toPlainString());
        try {
            parseMoneyNoGrouping("1,23", en);
            System.out.println("strict en grouping=ACCEPTED");
        } catch (IllegalArgumentException e) {
            System.out.println("strict en grouping=REJECTED");
        }

        System.out.println("money en=" +
                parseMoneyNoGrouping("12.50", en).toPlainString());
        System.out.println("money de=" +
                parseMoneyNoGrouping("12,50", de).toPlainString());
        System.out.println("leap date=" +
                parseStrictDate("29/02/2024", en));

        for (String input : new String[] {
                "29/02/2023", "29/02/2024extra"
        }) {
            try {
                parseStrictDate(input, en);
                System.out.println("date " + input + "=ACCEPTED");
            } catch (DateTimeParseException e) {
                System.out.println("date " + input + "=REJECTED");
            }
        }
    }
}
~~~

**Compile and run on JDK 17+**:

~~~bash
javac -encoding UTF-8 LocaleInputValidationDemo.java
java LocaleInputValidationDemo
~~~

**Stdout verified with Java:**

~~~text
en full=1234.50
de full=1234.50
en suffix=REJECTED
en odd grouping parses=123
strict en grouping=REJECTED
money en=12.50
money de=12.50
leap date=2024-02-29
date 29/02/2023=REJECTED
date 29/02/2024extra=REJECTED
~~~

**Analysis of each result group:**

1. `en full=1234.50`: US string `1,234.50` parses to decimal value `1234.50`.
2. `de full=1234.50`: German string `1.234,50` represents the same value despite **different punctuation in the input**.
3. `en suffix=REJECTED`: the general parser can parse the prefix, but `pos.getIndex() != text.length()`, so the validator rejects it.
4. `en odd grouping parses=123`: the parser consumed all of `1,23` without enforcing strict grouping. This proves full consumption alone is insufficient.
5. `strict en grouping=REJECTED`: the custom policy **forbids grouping separators**; the comma in US input is rejected before parsing.
6. `money en=12.50` and `money de=12.50`: identical value, while US input uses `.` and German input uses `,`.
7. `leap date=2024-02-29`: February 29 in 2024 is valid.
8. `date 29/02/2023=REJECTED`: 2023 is not a leap year, and `ResolverStyle.STRICT` does not silently adjust it to another date.
9. `date 29/02/2024extra=REJECTED`: `LocalDate.parse` does not ignore trailing suffixes.
10. The program prints results from the **parsed typed values**, never storing locale-formatted strings as monetary amounts in the domain.

This is a learning example with an intentionally narrow ASCII regex policy, not a universal parser for every language. If your product supports localized digits, Indian grouping patterns, percentages, accounting negative signs, currency symbols, or zoned date-time strings, design dedicated parsers and corresponding test suites for each type.

## 9. How to Extend Safely

### 9.1. Strict Grouping Policies

If grouping separators must be permitted, do not allow them in arbitrary positions. Define the supported pattern—for example, a field accepting only three-digit grouping:

~~~text
en-US allowed : 1,234.50
en-US rejected: 1,23
en-US rejected: 12,34,567.89  (if policy is three-digit grouping)
~~~

Other languages and regions may use non-uniform grouping (such as lakhs) or different separators. Policies should reflect the **field contract** and supported locales rather than forcing a three-digit regex on every country.

One implementation approach is a locale-specific lexical validator followed by `ParsePosition` and parsed-value checks. When only a few locales are supported, define explicit rules and test each locale. If all Unicode locales are required, consider a proven i18n parsing solution instead of simple regexes.

### 9.2. Adding Negative Signs or Percentages

The demo intentionally omits `-12.50`. If your domain permits negative numbers, define:

- Are ASCII hyphens or Unicode minus signs accepted?
- Are negative signs leading, trailing, or accounting parentheses?
- Is `+12.50` accepted?
- What are min/max bounds, and is negative zero allowed?
- Does `12%` mean `12` or `0.12` in the domain?

`NumberFormat.getPercentInstance(locale)` can parse and format percentages with scaling according to formatter rules. **Never** confuse a UI percentage with an unspecified domain decimal. Separate parsers per field type.

### 9.3. Checking Scale and Precision

Even when `DecimalFormat` returns `BigDecimal`, still inspect `value.scale()`, `value.precision()`, and currency unit rules:

~~~java
if (value.signum() < 0 || value.scale() > 2) {
    throw new IllegalArgumentException("Amount outside contract");
}
~~~

This snippet assumes a `BigDecimal value` inside a method. The `scale <= 2` check applies only when business rules dictate at most two fractional digits; currencies can have different minor-unit counts. For rounded amounts, specify an explicit `RoundingMode` instead of silently truncating excess digits.

### 9.4. Supporting Textual Date Input

If the UI permits month names (e.g., `29 February 2024`), use `DateTimeFormatter` with an appropriate `Locale` and pattern. When business rules require strictly `dd/MM/uuuu`, do not silently accept `02/29/2024` merely because the user switched locales; the input pattern is also part of the field contract.

To prevent ambiguous dates like `03/04/2024`, prefer a **date picker** or display the expected pattern clearly. Never try to "auto-detect" day vs. month from ambiguous input.

## 10. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Checking only `parse(text) != null` | Accepts prefix and ignores suffix | Check `ParsePosition` reaches the end |
| Checking only `pos.getIndex() > 0` | Trailing suffix goes unchecked | Compare against `text.length()` |
| Reading only `pos.getErrorIndex()` | Partial parse can stop without setting error index | Check both returned value and consumed index |
| Assuming full consumption implies standard grouping | `en-US` still parses `1,23` as `123` | Add a lexical policy |
| Parsing UI input with `Double.parseDouble` | Ignores locale decimal separators | Use a locale-aware parser |
| Parsing JSON numbers with `NumberFormat` | Breaks machine contract based on locale | Use a standard JSON parser |
| Trying multiple locales and taking the first success | Same string can have two valid meanings | Select the source locale intentionally |
| Using `double` for money | Precision errors | Use `BigDecimal` + business policy |
| Using `yyyy` arbitrarily with `ResolverStyle.STRICT` | Year-of-era lacks `ERA` | Use `uuuu` where appropriate |
| Using a lenient date formatter | Invalid dates silently shift to other dates | Use `ResolverStyle.STRICT` |
| Assuming `ResolverStyle` enforces all lexical rules | Spaces/extra characters may still satisfy parser rules | Validate syntax/pattern separately |
| Calling `trim()` and reporting original string valid | Silently mutates input | Specify normalization policy explicitly |
| Sharing static mutable `DecimalFormat` in thread pools | Race conditions, corrupted configuration | Create per call or clone safely |
| Using `LocalDate` instead of an instant | Missing time-zone context | Pick the proper domain type |
| Guessing comma vs. dot without grouping rules | Can misparse values | Use the right locale and explicit policy |
| Using `format(parse(s)) == s` as the sole check | Rejects valid inputs differing from canonical output | Design purposeful grammar and validation |

## 11. Test Suite and Locale QA

A multilingual input module needs tests at two levels: **parse/validation rules** and **UI/API contracts**.

### 11.1. Number Matrix

| Locale and Input | Expected Behavior for Demo Parser/Policy |
| --- | --- |
| `en-US`: `1,234.50` | General parser returns `1234.50` |
| `de-DE`: `1.234,50` | General parser returns `1234.50` |
| `en-US`: `1,234.50oops` | Rejected due to incomplete consumption |
| `en-US`: `1,23` | General parser accepts `123`; money policy rejects |
| `en-US`: `12.50` | Money policy accepts `12.50` |
| `de-DE`: `12,50` | Money policy accepts `12.50` |
| `de-DE`: `12.50` | Money policy rejects due to wrong decimal separator under narrow rule |
| `en-US`: `12.50 ` | Money policy rejects trailing space |
| `en-US`: `12.345` | Money policy rejects three fractional digits |
| `en-US`: `-12.50` | Money policy rejects minus sign because demo contract forbids it |

These outcomes reflect **the defined policy and locales**, not a guarantee that Java behaves identically for all similar inputs across every CLDR version.

### 11.2. Date Matrix

- Leap year: `29/02/2024` is valid.
- Non-leap year: `29/02/2023` is invalid.
- 30-day month: `31/04/2024` is invalid.
- Month outside `1..12`: rejected.
- Suffix `29/02/2024extra`: rejected.
- Leading/trailing whitespace: explicit policy, never silently accepted.
- Year-of-era vs. proleptic year: test `uuuu` for strict dates.
- Locales with month names or non-ASCII digits: test against real locale data and supported formatters.

### 11.3. Invariants to Preserve During Integration

1. Client supplies a locale **chosen from the supported list**; never parse incorrectly due to a different server default locale.
2. Parsers accept only inputs permitted by the validation policy.
3. The same domain value may be entered in different locale formats, yet **is stored in one canonical machine type**, never as a display-formatted string.
4. No leftover characters remain after a successful parse unless a formal grammar permits them.
5. Every error is represented with a stable error code/field path and a localized message.
6. Concurrency tests do not share mutable `DecimalFormat` instances across threads.
7. Test JDK/CLDR upgrades across all truly supported locales, not only `Locale.US`.

### 11.4. How Should Invalid Input Be Handled?

The UI should preserve the user's raw input string for correction (when appropriate for security), highlight the corresponding field, and show the **expected format example**. Never silently coerce an ambiguous string like `1,234` into another number and persist it without clear confirmation.

Never log raw inputs containing sensitive data; for debugging, log parser error codes, error indices, and controlled metadata, or anonymized code points for non-sensitive fields.

## 12. Practice Exercises

1. Build an `amount` input form supporting `en-US` and `de-DE`. Switch languages and enter `12,50`, explaining why the parsed value differs if the wrong locale is used.
2. Remove `pos.getIndex() == text.length()`, test `1,234.50oops`, and document the consequence.
3. Keep full consumption enabled, test `1,23` under `en-US`, and explain why an extra lexical policy is required.
4. Add an option **allowing valid grouping separators** for `en-US` and compare it with the demo's no-grouping policy.
5. Modify the demo regex to accept negative signs and a different fractional digit count; state the monetary domain rules clearly.
6. Write tests asserting `value.scale()`, `value.precision()`, and min/max bounds after parsing `BigDecimal`.
7. Add `31/04/2024` to a `LocalDate.parse` test with `STRICT` and verify the exception.
8. Test `ResolverStyle.SMART` on invalid dates and compare with `STRICT`, noting why `SMART` should not validate legal dates.
9. Test `dd/MM/yyyy` with `ResolverStyle.STRICT` and explain the `YEAR_OF_ERA` issue.
10. Test `Locale.forLanguageTag("vi-VN")` and inspect its separators and behavior on your active JDK without assuming parity with other environments.
11. Write a test that changes `Locale.setDefault` in an isolated test environment; code passing `Locale` explicitly must produce unchanged results.
12. Build an API DTO with `BigDecimal amount` and `LocalDate date`; serialize to JSON under a fixed schema rather than sending UI-formatted strings.
13. Test parsing with `NumberFormat.getPercentInstance` in a separate test and explain the scale of the returned value.
14. Define `INPUT_FORMAT_INVALID` and `INPUT_OUT_OF_RANGE` error types with a technical field path; translate messages without translating error codes.

## 13. Summary

In Java localization, **locale-aware parsing** must be paired with **full-string verification and business validation**. For `NumberFormat`, use `ParsePosition` to verify `result != null` and `position == input.length()`; however, never equate full consumption with valid grouping or strict syntax. With `DecimalFormat` and exact money, enable `setParseBigDecimal(true)`, pick the locale explicitly, check scale/range, and avoid unsafe sharing of mutable formatters.

For calendar dates, `LocalDate.parse` with `DateTimeFormatter` and `ResolverStyle.STRICT` rejects invalid dates and trailing suffixes; prefer `uuuu` over `yyyy` for ISO proleptic years. After parsing succeeds, keep typed `BigDecimal`/`LocalDate` values in the domain rather than treating display strings as machine data.

**References:**

- Java SE 17, `NumberFormat`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html
- Java SE 17, `DecimalFormat`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormat.html
- Java SE 17, `DecimalFormatSymbols`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormatSymbols.html
- Java SE 17, `ParsePosition`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/ParsePosition.html
- Java SE 17, `BigDecimal`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html
- Java SE 17, `DateTimeFormatter`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html
- Java SE 17, `ResolverStyle`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/ResolverStyle.html
- Java SE 17, `LocalDate`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html
