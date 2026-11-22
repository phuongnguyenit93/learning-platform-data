# MessageFormat number, date, time, and choice Types in Java

## 1. What Does MessageFormat Do?

`java.text.MessageFormat` combines a **message pattern** with arguments to produce a user-facing string. Instead of hardcoding `"There are " + count + " orders"`, translators can decide word order and how numbers, dates, and times are represented according to the `Locale`.

`MessageFormat` uses curly braces to declare *format elements*:

```text
{argumentIndex}
{argumentIndex,formatType}
{argumentIndex,formatType,formatStyle}
```

Where:

- `argumentIndex`: the 0-based argument position in the array passed to `format(...)`.
- `formatType`: one of `number`, `date`, `time`, `choice`; omitting the type formats the argument according to its default style.
- `formatStyle`: a predefined style name (such as `integer`, `currency`, `short`) or a custom pattern string appropriate for that type.

Example of an English pattern:

```text
"You bought {0,number,integer} items on {1,date,long}."
```

Argument `0` is a number, and argument `1` must be a suitable date/time value (typically `java.util.Date`). `MessageFormat` inserts them into the message according to the rules of the configured locale.

**Lesson scope:** the four types `number`, `date`, `time`, and `choice`, boundary checking, locale, time zone, and common pitfalls when combining them. This lesson does not treat `choice` as a complete solution for all plural rules across all languages.

## 2. API Structure and the Effect of Locale

To create a formatter for a fixed locale:

```java
Locale locale = Locale.forLanguageTag("en-US");
MessageFormat mf = new MessageFormat(
        "Total: {0,number,currency}", locale);
String text = mf.format(new Object[] {1234.5});
```

*This illustrative snippet is placed inside a Java method; it requires importing `java.text.MessageFormat` and `java.util.Locale`.*

`MessageFormat` holds the pattern and `Locale` set via the constructor or `setLocale(...)`. The pattern is compiled into literal segments and formatters for each argument position. When changing the locale, you may need to reapply the pattern to recreate the formatters for the new locale; the simplest approach is to **instantiate a separate `MessageFormat` for each locale**.

Two easily confused points:

1. `new MessageFormat(pattern, Locale.US)` controls the language/formatting rules. `MessageFormat.format(pattern, args...)` is a convenience static method that uses the JVM's default `FORMAT` locale, making it less predictable in environment-dependent tests.
2. `MessageFormat` is a **mutable** object and is not guaranteed to be safe when used concurrently across multiple threads if configuration changes occur. Do not share one instance and call `applyPattern(...)`, `setFormat(...)`, or `setLocale(...)` from multiple unsynchronized requests. The simplest approach in web code is to create a formatter per request or use a safe instance-management strategy.

Arguments are passed as an `Object[]` array. When the pattern specifies a type, the argument must be compatible: `number` requires a `Number`, and `date`/`time` require a `Date` or a temporal type accepted by the formatting API. Specifically, `LocalDate` or `Instant` from `java.time` is not automatically handled like `Date` in `MessageFormat`'s `date`/`time` format elements; convert intentionally or use a separate `DateTimeFormatter`.

## 3. The `number` Format Type

`number` uses the `NumberFormat`/`DecimalFormat` mechanism to display numeric arguments. The same value can have different representations:

| Pattern element | Meaning | Example with `Locale.US` |
| --- | --- | --- |
| `{0,number}` | General number format per locale | `1,234.5` for `1234.5` |
| `{0,number,integer}` | Integer using formatting/rounding rules | `1,234` for `1234` |
| `{0,number,currency}` | Currency format per locale and formatter rules | `$1,234.50` for `1234.5` |
| `{0,number,percent}` | Value multiplied by 100 with a percent sign | `26%` for `0.256` when rounded by the formatter |
| `{0,number,#,##0.00}` | Custom `DecimalFormat` pattern | `1,234.50` for `1234.5` |

### 3.1. General Numbers and `integer`

With `{0,number,integer}`, Java uses an integer-style `NumberFormat`, which may **round** when the argument has a fractional part. Therefore, do not use this style as a way to cast to `int`, check whether a value is an integer, or preserve decimals. Perform business validation before deciding how to format.

Separators and grouping depend on the locale. Do not manually replace periods with commas or call `String.format` with the default locale and pass the result back into `MessageFormat`.

### 3.2. Currency Does Not Mean Currency Conversion

`{0,number,currency}` produces a value using the locale's currency format—for instance, `Locale.US` typically displays the `$` symbol. It **does not convert 1234.5 USD to 1234.5 VND**, nor does it look up exchange rates. Actual currency units and exchange rates belong to business data.

If a transaction is recorded in a specific currency different from the currency normally associated with the locale, create `NumberFormat.getCurrencyInstance(locale)`, call `setCurrency(Currency.getInstance("EUR"))` based on the transaction's currency, and attach the formatter via `setFormatByArgumentIndex(...)` or format the money separately before inserting. Do not equate formatting with currency conversion.

### 3.3. `percent` Multiplies the Value by 100

`{0,number,percent}` interprets `0.256` as a ratio of `25.6%` and, with the locale's default fraction digits, may display `26%`. If the business argument is already stored as `25.6` in percentage units, using `percent` directly will multiply by 100 a second time. Agree consistently on whether source data is a **0–1 fraction** or **0–100 percentage points**.

### 3.4. Custom Number Patterns

`{0,number,#,##0.00}` uses `DecimalFormat` pattern syntax: `0` is a required digit, `#` is an optional digit, the comma in the pattern denotes grouping, and the period in the pattern denotes the decimal boundary. **The actual displayed symbols are still determined by the locale.** Complex number patterns with parentheses, literals, and currency signs must be read according to `DecimalFormat` rules rather than assuming every comma inside a format element is an argument delimiter.

For accurate money formatting, source numbers should usually use `BigDecimal` with explicit business rounding rules; `MessageFormat` only handles presentation.

## 4. The `date` Format Type

`{0,date,...}` chooses how to display the date of a temporal argument based on `DateFormat`. Standard styles:

| Style | Pattern | Meaning |
| --- | --- | --- |
| Default | `{0,date}` | Uses the default style for dates. |
| Short | `{0,date,short}` | Short date, usually numeric. |
| Medium | `{0,date,medium}` | Medium-length date. |
| Long | `{0,date,long}` | Long date, may include month name. |
| Full | `{0,date,full}` | Full date, may include day of week. |
| Custom | `{0,date,yyyy-MM-dd}` | Custom `SimpleDateFormat` pattern. |

The `short`/`medium`/`long`/`full` styles **are not fixed date strings**. Day/month/year order, separators, month text, and weekday names depend on the locale and the JDK's locale data. This is suitable for localized UI, but unsuitable for encoding dates in APIs or databases. When exchanging data, use date types or an explicit serialization standard such as ISO 8601.

**Important point:** `MessageFormat` uses the `java.text.DateFormat` hierarchy based on `Date` instants/dates. To format `LocalDate` in modern Java, use `java.time.format.DateTimeFormatter` (with an explicit `Locale`) and pass the resulting string into the message, or convert to `Date` using time zone rules if `java.text` compatibility is truly needed.

A custom pattern like `yyyy-MM-dd` in `MessageFormat` is interpreted by `SimpleDateFormat`. Symbols such as `y`, `M`, and `d` have specific meanings; do not confuse them with `DateTimeFormatter` patterns in `java.time`, as the two APIs differ in some pattern letters and handling rules.

## 5. The `time` Format Type

`{0,time,...}` formats the time portion from the same `DateFormat`-compatible argument types. Common styles:

| Style | Pattern | Meaning |
| --- | --- | --- |
| Default | `{0,time}` | Uses the default style for times. |
| Short | `{0,time,short}` | Hours and minutes in short locale layout. |
| Medium | `{0,time,medium}` | May include seconds. |
| Long | `{0,time,long}` | May include zone or offset. |
| Full | `{0,time,full}` | Full representation per locale/JDK data. |
| Custom | `{0,time,HH:mm:ss}` | 24-hour clock, minutes, and seconds with `SimpleDateFormat`. |

**Locale is different from time zone.** Locale can affect time presentation (12h/24h, names, symbols), whereas `TimeZone`/`ZoneId` determines the local wall-clock time of an instant. If you create a `MessageFormat` using default formatters without setting a time zone, date/time output can differ between a developer's machine and CI.

To get deterministic results for a `Date` representing an `Instant`, set the time zone on the `DateFormat` formatters inside `MessageFormat`:

```java
MessageFormat message = new MessageFormat(
        "day={0,date,yyyy-MM-dd}; time={0,time,HH:mm:ss}",
        Locale.US);

for (java.text.Format format : message.getFormats()) {
    if (format instanceof java.text.DateFormat dateFormat) {
        dateFormat.setTimeZone(java.util.TimeZone.getTimeZone("UTC"));
    }
}

System.out.println(message.format(new Object[] {new java.util.Date(0L)}));
// day=1970-01-01; time=00:00:00
```

This is a code snippet placed in a Java method with imports or fully qualified class names. `getFormats()` returns the formatter of each format element in order of appearance; because the same argument `0` is used in both `date` and `time`, iterating over **all of `getFormats()`** sets the time zone on both formatters. Do not change the JVM-wide default time zone just to run a formatting test.

Date/time formatters may be recreated after `applyPattern(...)` or pattern/locale changes. When using custom format objects, configure them first and attach them to `MessageFormat` via the appropriate API to avoid relying on default settings.

## 6. The `choice` Format Type

`choice` selects a message fragment based on a numeric value, using `ChoiceFormat` syntax:

```text
{0,choice,0#no files|1#one file|1<more than one file}
```

- `0#no files`: applies when the value is from lower bound 0 up to just before the next bound.
- `1#one file`: applies at exact value 1 according to the bounded branches.
- `1<more than one file`: applies when the value is **greater than 1**.
- The `|` character separates branches.
- The `#` symbol denotes an **inclusive** bound at the preceding value; `<` denotes an **exclusive** bound (strictly greater).
- Numeric limits must be ordered strictly ascending and branches designed to fit the input dataset.

**Note on bounds and out-of-range values:** `ChoiceFormat` relies on numeric limits, and for values smaller than the first bound it still falls back to the first branch's message. For example, a pattern starting at 0 can display `no files` for negative numbers. Do not use this to validate negative counts; validate input separately before formatting.

### 6.1. Branch Selection and Nested Formatting

A choice branch's result can contain another format element to re-insert the number itself:

```text
{0,choice,0#no files|1#one file|1<{0,number,integer} files}
```

For values `0`, `1`, and `2`, the results are `no files`, `one file`, and `2 files`, respectively. `MessageFormat` can parse a subpattern inside a `choice` result when that result contains format element braces; therefore, be especially careful with single quotes, curly braces, and nested strings.

### 6.2. When Is `choice` Insufficient?

`ChoiceFormat` selects by **numeric thresholds**, which is well-suited for explaining message selection or handling a few simple cases. However:

- Plural rules across languages can depend on 0, 1, 2, 3–4, multiple grammatical classes, or fractional parts, rather than simple fixed thresholds.
- Some languages require singular/plural morphology that varies with vocabulary and sentence type.
- `choice` cannot automatically infer full plural rules for every locale from `Locale` alone.
- For complex i18n requirements, consider a message system with locale-aware plural/select support such as ICU4J; use translations tested with each target language.

**Do not hardcode English branches and assume they remain correct when switching the locale to Vietnamese, Russian, Arabic, etc.** Branch text still needs to be translated according to the language and product rules.

## 7. Complete Java 17+ Example: `number`, `date`, `time`, `choice`

Create a file **`MessageFormatTypesDemo.java`** with the following content. The example explicitly selects `Locale.US` and sets the UTC time zone only on date/time formatters. It does not mutate the JVM-wide default locale or time zone.

```java
import java.text.DateFormat;
import java.text.Format;
import java.text.MessageFormat;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;

public class MessageFormatTypesDemo {

    private static void useUtcForDates(MessageFormat message) {
        TimeZone utc = TimeZone.getTimeZone("UTC");

        for (Format format : message.getFormats()) {
            if (format instanceof DateFormat dateFormat) {
                dateFormat.setTimeZone(utc);
            }
        }
    }

    public static void main(String[] args) {
        Locale locale = Locale.US;

        String summaryPattern =
                "count={0,number,integer}; "
                + "money={1,number,currency}; "
                + "ratio={2,number,percent}; "
                + "day={3,date,yyyy-MM-dd}; "
                + "time={3,time,HH:mm:ss}";

        MessageFormat summary =
                new MessageFormat(summaryPattern, locale);
        useUtcForDates(summary);

        Object[] values = {
                1234, 1234.5, 0.256, new Date(0L)
        };
        System.out.println(summary.format(values));

        MessageFormat files = new MessageFormat(
                "{0,choice,0#no files|1#one file"
                + "|1<{0,number,integer} files}",
                locale);

        for (int count : new int[] {0, 1, 2}) {
            System.out.println("files-" + count + "="
                    + files.format(new Object[] {count}));
        }

        MessageFormat apostrophe = new MessageFormat(
                "You''ve got {0,number,integer} files.", locale);
        System.out.println(apostrophe.format(new Object[] {2}));
    }
}
```

Run in the directory containing the file, using JDK 17 or later:

```bash
javac -encoding UTF-8 MessageFormatTypesDemo.java
java MessageFormatTypesDemo
```

**Exact stdout with Java 17 and standard locale data for `Locale.US`:**

```text
count=1,234; money=$1,234.50; ratio=26%; day=1970-01-01; time=00:00:00
files-0=no files
files-1=one file
files-2=2 files
You've got 2 files.
```

Explanation:

1. `count={0,number,integer}` formats `1234` with `Locale.US` grouping as `1,234`.
2. `money={1,number,currency}` uses `Locale.US` currency formatting, producing `$1,234.50`; no exchange rate conversion occurs.
3. `ratio={2,number,percent}` takes `0.256`, multiplies by 100, and rounds per the default style, producing `26%`.
4. `day` and `time` both read `Date(0L)`, the Unix epoch, and thanks to UTC configured on each `DateFormat`, yield `1970-01-01` and `00:00:00`.
5. `choice` selects branches based on 0, 1, and greater than 1; the last branch has a nested numeric format element.
6. The pattern `"You''ve"` uses **two single quotes** in the pattern to produce one visible apostrophe `You've`; if only one `'` were written, the parser would treat the rest as quoted text and ignore the placeholder.

For default number/currency styles, month names, and CLDR conventions, output may vary slightly across JDK versions or locale data. Custom date and time fields were pinned using patterns and UTC to minimize sources of variation in the example.

## 8. Single Quotes, Curly Braces, and Commas Syntax

In `MessageFormat`, the single quote `'` is a quoting character of the **pattern language**, not merely ordinary punctuation:

- To print an apostrophe in literal text, write `''` in the message pattern.
- To print curly braces as literal characters, quote the braces: `'{'` and `'}'`; do not place a bare `{` in a message pattern if you only want it as text.
- With an unclosed quote, the parser may handle the end of the pattern per its quoting rules, causing placeholders to go unrecognized. Do not expect it to auto-correct the content.
- When a pattern has nested formats, escaping can pass through multiple parser layers; directly test expected output for each locale, especially if patterns come from translation files.

Examples:

| Pattern literal | Desired result |
| --- | --- |
| `You''ve got {0} files.` | Prints the apostrophe and inserts the argument. |
| `'{'{0}'}'` | Displays curly braces surrounding the argument value. |
| `{0,number,#,##0.00}` | Uses comma/decimal according to **`DecimalFormat` syntax**, not splitting format elements in the wrong place. |

Do not use string concatenation to "dodge" quoting, because concatenation can force the same word order across all languages. Proper message design and escaping preserve translators' ability to adjust phrasing.

## 9. Repeated Argument Formatting, Missing Arguments, and Wrong Types

### 9.1. Same Argument in Multiple Format Elements

In the pattern:

```text
"Date={0,date,yyyy-MM-dd}; Time={0,time,HH:mm:ss}"
```

Argument `0` is used **twice**, each time with a different formatter. When configuring a time zone, do not assume `getFormatsByArgumentIndex()[0]` represents both format elements; use `getFormats()` to iterate over every element, or configure via `setFormat(...)` in format element order.

### 9.2. Missing Arguments

`MessageFormat` expects indices to match the argument array. If an index is referenced in the pattern but missing from the array, an unsubstituted placeholder may be displayed. Do not treat that as a safe translation fallback. Test argument completeness and manage key/argument contracts in the application.

### 9.3. Wrong Types

If a pattern expects `number` but a non-numeric `String` is passed, or expects `date` but an invalid object is passed, the formatter may throw `IllegalArgumentException`. During code review, distinguish three errors:

- Missing translation key (`MissingResourceException`) when loading a message from a bundle.
- Invalid pattern syntax when constructing or calling `applyPattern`.
- Incompatible argument value when calling `format`.

These errors require different fixes; avoid catching them generically and returning an empty string that discards diagnostic information.

## 10. Integration with ResourceBundle and Business Data

Typically you store each pattern by key:

```properties
cart.summary=You have {0,number,integer} items.
invoice.paidAt=Paid at {0,date,short} {0,time,short}.
file.count={0,choice,0#No files|1#One file|1<{0,number,integer} files}
```

After loading a `ResourceBundle`, pass the exact chosen locale to `MessageFormat`:

```java
Locale locale = Locale.US;
ResourceBundle bundle = ResourceBundle.getBundle("messages", locale);

MessageFormat message =
        new MessageFormat(bundle.getString("cart.summary"), locale);
String result = message.format(new Object[] {3});
```

This snippet needs the resource file and imports for `ResourceBundle`, `Locale`, and `MessageFormat` to run in a real program.

Be mindful when the application uses bundle fallback: the loaded bundle may be the root or a parent bundle; the pattern string must satisfy `MessageFormat` grammar for that translation's language. The same key across different locales may reorder arguments (e.g., `{1}` appearing before `{0}`), yet **must still preserve the type and semantic contract of arguments**. Do not assume that just because patterns in two locales use the same indices, the grammar is right.

For temporal data in modern business logic, store `Instant`, `LocalDate`, or `ZonedDateTime` according to true semantics; at the presentation layer, convert to a compatible argument or format with `java.time` and use `MessageFormat` to assemble the message. Language (`locale`) and time zone (`zone`) are two distinct choices; pass them explicitly to avoid relying on server configuration.

## 11. Performance, Reverse Parsing, and Testing Notes

- `MessageFormat` stores the parsed pattern structure and component formatters; if formatting thousands of times with the same pattern, you can prepare and reuse it in a **state- and concurrency-controlled** way. Do not mutate the same instance from multiple threads.
- `MessageFormat.parse(...)` is not a reliable general-purpose parser for every formatted string, especially with `choice`, repeated text, locale-dependent formatting, or nested formats. Use a parser with an explicit data contract for user input.
- Patterns in bundles may be edited by translators; in CI, validate brace/quote balance, parameter indices, and type compatibility across locales.
- With `choice`, test **below, equal to, and above** each threshold; also test negative numbers, decimals, and large numbers per real domain expectations.
- Test `date/time` with a fixed time zone and boundary dates (near midnight, date rollovers). Do not use display formatting as a business data key or API exchange format.
- Do not assume the time zone changes just because `Locale` changes; `DateFormat` and `TimeZone` are separate mechanisms.

### Suggested Test Matrix

| Case | Expectation |
| --- | --- |
| `{0,number,integer}` with `1234` | Locale-appropriate grouping, accurate integer. |
| `{0,number,percent}` with `0.256` | Formatted percentage display without altering source number. |
| `{0,number,currency}` | Appropriate currency symbol/style and controlled business currency. |
| `{0,date,short}`, `{0,time,short}` | Output matching explicit locale/zone. |
| `choice` with `0, 1, 2` | Selects exact boundary branch. |
| `choice` with `-1, 1.5` | Identifies out-of-domain behavior, validates input beforehand. |
| Apostrophes in pattern | Literal `'` is printed, placeholders still work. |
| Missing argument or wrong type | Tests detect failure behavior; not treated as a complete translated string. |
| Same index appearing multiple times | Each format element is configured properly. |

## 12. Common Pitfalls and Fixes

| Mistake | Why it causes issues | What to do |
| --- | --- | --- |
| Using `{0,number,percent}` with `25` to represent 25% | Formatter multiplies by 100, skewing units. | Store ratio `0.25` or choose another domain formatter. |
| Assuming `{0,number,currency}` knows the transaction currency | Locale is not necessarily the business currency code. | Attach the actual `Currency` and format explicitly. |
| Passing `LocalDate` directly to `{0,date}` | `DateFormat` uses `Date`-based APIs, not automatically supporting all `java.time` types. | Use `DateTimeFormatter` or convert with an appropriate zone. |
| Forgetting time zone when formatting `Date(0L)` | Different JVMs may display different dates/times. | Configure `DateFormat.setTimeZone(...)` explicitly. |
| Writing `You've {0}` in a pattern | Single `'` acts as a quote, causing placeholders to be misparsed. | Write `You''ve {0}`. |
| Assuming `choice` handles all global plurals | Plural rules can be complex per locale. | Use a language-appropriate plural mechanism when needed. |
| Not testing negative numbers below `choice`'s first branch | Still selects the first branch, producing nonsensical text. | Validate value domain before formatting. |
| Configuring time zone via `getFormatsByArgumentIndex()` when index repeats | Can miss distinct format elements. | Iterate `getFormats()` or configure per occurrence. |
| Using static `MessageFormat.format(...)` in locale-sensitive tests | Can pick up the JVM's default `FORMAT` locale. | Instantiate `MessageFormat(pattern, locale)`. |
| Sharing mutable formatters across requests | Risk of concurrency bugs and cross-request state leakage. | Create per use or apply safe cloning/synchronization. |

## 13. Self-Practice Exercises

**Exercise 1 — Comparing numeric types:** pass `1234.567` and `0.256` into `number`, `integer`, `currency`, and `percent` patterns. Try `Locale.US` and `Locale.forLanguageTag("vi-VN")`; record differences in grouping, decimal separator, currency symbol, and rounding results. Do not alter source values to match display strings.

**Exercise 2 — Time zones:** given `Instant.parse("2026-01-01T00:00:00Z")`. Create `Date.from(instant)` and format in UTC and `Asia/Ho_Chi_Minh`; explain the difference between the two outputs without changing the `Instant`. Observe how the local calendar date can differ when changing time zones.

**Exercise 3 — Choice boundaries:** write a pattern for inventory levels: 0 = out of stock, 1 = one left, greater than 1 = N left. Test `0`, `1`, `2`, `-1`, and `1.5`. Distinguish the responsibility of **message selection** from **validating valid input**.

**Exercise 4 — Apostrophes and literal braces:** create a message containing `'` and literal curly braces while still inserting `{0,number,integer}`. Verify exact output, especially when the pattern comes from a `.properties` file.

**Exercise 5 — Per-language bundles:** create `messages_en.properties` and `messages_vi.properties` with the same key but different parameter ordering. Load the bundle by locale, format two number/date types, and verify the parameter contract in both. If a language requires complex plurals, explain why you should move to a locale-aware plural solution.

### Takeaway

- `number` formats numbers, integers, currency, percentages, or custom `DecimalFormat` patterns.
- `date` and `time` use `DateFormat` with locale and time zone; arguments are typically `java.util.Date`.
- `choice` selects a branch by numeric thresholds; `#` includes the threshold, `<` excludes it.
- `Locale` controls presentation; time zone, transaction currency, and business validation rules require separate control.
- Misplacing one or two `'` characters in a pattern can alter the meaning of the entire message; always test actual formatted strings.
