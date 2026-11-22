# Full-String Validation and Handling Invalid Data When Converting String in Java

## 1. Why Is Full-String Validation Important?

A value received from the keyboard, a form, a file, configuration, or an API initially arrives as a `String`. Before converting it to `int`, `long`, `BigDecimal`, `boolean`, or `LocalDate`, the program must determine whether the **entire string** conforms to the required valid format. You should not merely find **a substring that looks valid** and treat the whole input as valid.

For example, the string `"order=42x"` contains `42`, yet it is not a pure decimal integer. If an input field requires a quantity, values like `"42kg"`, `"12 3"`, `"7;DELETE"`, or `"19.95 USD"` must be evaluated against the **contract of the entire field**, rather than arbitrarily extracting the numeric part and ignoring the rest.

Thorough validation has two layers:

1. **Format and input policy:** Are leading/trailing whitespace, `+`/`-` signs, leading zeros, decimal points, exponents, Unicode digits, or empty strings allowed?
2. **Actual convertibility:** Does the value fall within the target type's range, represent a valid calendar date, or satisfy business constraints?

Regex can verify syntax, yet it **cannot completely replace the parse and range-checking steps**. Conversely, some parse APIs have rules broader than the application's policy; therefore, succeeding at the parse step does not always mean the data meets requirements.

## 2. `matches()` Validates the Entire String; `find()` Only Searches for a Substring

In `java.util.regex`:

- `pattern.matcher(input).matches()` returns `true` only if **the Matcher's entire input region** matches the regex.
- `pattern.matcher(input).find()` only needs to locate **a matching substring**, not necessarily covering the whole string.
- `input.matches(regex)` performs equivalent whole-string matching when applying that regex via `Pattern`; for patterns used repeatedly, compile `Pattern` once.

Example:

```java
import java.util.regex.Pattern;

Pattern digits = Pattern.compile("[0-9]+");
System.out.println(digits.matcher("42").matches());      // true
System.out.println(digits.matcher("id=42x").matches());   // false
System.out.println(digits.matcher("id=42x").find());      // true
```

This is an illustrative snippet inside a method or JShell environment, not a standalone program. The regex `[0-9]+` here accepts only ASCII digits `0`–`9`. The fact that `find()` returns `true` for `"id=42x"` **does not confirm the input is a number**.

With `Matcher.matches()`, there is no need to add `^...$` to force whole-string matching. Furthermore, `^` and `$` carry line-boundary rules and regex flags; using `matches()` directly expresses the "whole string" intent. If `Matcher.region(...)` has been changed, `matches()` checks the entire **currently selected region**, not necessarily the entire original string; the examples here always use a fresh `Matcher` over the full input.

## 3. A Reliable Data Conversion Pipeline

The recommended pipeline for `String` input is:

1. **Distinguish missing data:** Decide whether `null` means "not provided", `""` means "empty", or both are invalid. Do not call `strip()` directly when `input == null`.
2. **Controlled normalization:** Only trim whitespace at both ends if the data contract allows it. Java 11+ has `strip()` based on `Character.isWhitespace`; `trim()` uses an older mechanism, and not every Unicode whitespace character is removed by `strip()`. Never silently remove characters in the middle unless permitted.
3. **Validate full-string syntax:** For example, `[+-]?[0-9]+` for integers, `[0-9]{4}-[0-9]{2}-[0-9]{2}` for ISO dates, or the set `true`/`false`.
4. **Parse to the right type:** Use `Integer.parseInt`, `Long.parseLong`, `new BigDecimal`, `LocalDate.parse`, etc., and catch the appropriate possible exceptions. Regex cannot check `int` overflow or February 29 in a non-leap year.
5. **Validate business rules:** For example, age within valid bounds, non-negative amount, start date not after end date. Valid syntax does not imply valid business data.
6. **Return a result with clear status:** Do not turn all invalid data into `0`, `false`, or today's date. For simple examples `Optional<T>` can work; applications needing detailed messages should use a result type or error codes distinguishing missing/format/range errors.

**Order matters:** When normalization or parsing can alter data, state the contract explicitly. For example, with an identifier `"00123"`, converting to `int` drops the two leading zeros; if leading zeros are part of the identifier, keep it as a `String` instead of converting to a numeric type just because it contains only digits.

## 4. Complete Java 17+ Example: Numbers, Booleans, and Dates

Save to `StrictConversionDemo.java`:

```java
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.Optional;
import java.util.regex.Pattern;

public class StrictConversionDemo {
    // Policy: ASCII digits, optional +/- sign.
    private static final Pattern INTEGER =
            Pattern.compile("[+-]?[0-9]+");

    // Policy: dot-decimal numbers, disallowing 00.5 or scientific exponent.
    private static final Pattern DECIMAL =
            Pattern.compile("[+-]?(?:0|[1-9][0-9]*)(?:\\.[0-9]+)?");

    // Require exact 10-character ISO date, then validate calendar existence.
    private static final Pattern DATE =
            Pattern.compile("[0-9]{4}-[0-9]{2}-[0-9]{2}");

    static Optional<Integer> integer(String input) {
        if (input == null) return Optional.empty();
        String value = input.strip();
        if (!INTEGER.matcher(value).matches()) return Optional.empty();

        try {
            return Optional.of(Integer.parseInt(value));
        } catch (NumberFormatException ex) {
            // For example, a number exceeding int range, even though whole-string syntax is valid.
            return Optional.empty();
        }
    }

    static Optional<BigDecimal> decimal(String input) {
        if (input == null) return Optional.empty();
        String value = input.strip();
        if (!DECIMAL.matcher(value).matches()) return Optional.empty();

        try {
            return Optional.of(new BigDecimal(value));
        } catch (NumberFormatException ex) {
            return Optional.empty();
        }
    }

    static Optional<Boolean> booleanValue(String input) {
        if (input == null) return Optional.empty();
        String value = input.strip();
        if ("true".equalsIgnoreCase(value)) return Optional.of(true);
        if ("false".equalsIgnoreCase(value)) return Optional.of(false);
        return Optional.empty();
    }

    static Optional<LocalDate> date(String input) {
        if (input == null) return Optional.empty();
        String value = input.strip();
        if (!DATE.matcher(value).matches()) return Optional.empty();

        try {
            return Optional.of(
                    LocalDate.parse(value, DateTimeFormatter.ISO_LOCAL_DATE));
        } catch (DateTimeParseException ex) {
            return Optional.empty();
        }
    }

    public static void main(String[] args) {
        System.out.println("Integer 42: "
                + integer(" 42 ").map(Object::toString).orElse("INVALID"));
        System.out.println("Integer 12x: "
                + integer("12x").map(Object::toString).orElse("INVALID"));
        System.out.println("Integer overflow: "
                + integer("2147483648").map(Object::toString).orElse("INVALID"));
        System.out.println("Integer empty: "
                + integer("   ").map(Object::toString).orElse("INVALID"));

        System.out.println("Decimal 19.95: "
                + decimal("19.95").map(Object::toString).orElse("INVALID"));
        System.out.println("Decimal suffix: "
                + decimal("19.95 USD").map(Object::toString).orElse("INVALID"));
        System.out.println("Decimal leading zero: "
                + decimal("00.5").map(Object::toString).orElse("INVALID"));

        System.out.println("Boolean TRUE: "
                + booleanValue("TRUE").map(Object::toString).orElse("INVALID"));
        System.out.println("Boolean yes: "
                + booleanValue("yes").map(Object::toString).orElse("INVALID"));

        System.out.println("Date leap: "
                + date("2024-02-29").map(Object::toString).orElse("INVALID"));
        System.out.println("Date invalid: "
                + date("2023-02-29").map(Object::toString).orElse("INVALID"));

        Pattern digits = Pattern.compile("[0-9]+");
        System.out.println("Partial find: "
                + digits.matcher("id=42x").find());
        System.out.println("Whole matches: "
                + digits.matcher("id=42x").matches());
    }
}
```

Compile and run:

```bash
javac StrictConversionDemo.java
java StrictConversionDemo
```

Output:

```text
Integer 42: 42
Integer 12x: INVALID
Integer overflow: INVALID
Integer empty: INVALID
Decimal 19.95: 19.95
Decimal suffix: INVALID
Decimal leading zero: INVALID
Boolean TRUE: true
Boolean yes: INVALID
Date leap: 2024-02-29
Date invalid: INVALID
Partial find: true
Whole matches: false
```

The results illustrate two validation layers. `"2147483648"` exceeds `Integer.MAX_VALUE` (2,147,483,647) despite matching the integer regex. `"2023-02-29"` matches `yyyy-MM-dd` in shape, yet that date does not exist; `LocalDate.parse` with `ISO_LOCAL_DATE` checks calendar validity. `"00.5"` might be accepted by some parsers, but **this lesson's** `DECIMAL` policy intentionally rejects redundant leading zeros.

The methods return `Optional.empty()` on parse failure for ease of demonstration; they **do not distinguish error reasons**. For a real UI or API, return a result carrying error categories such as `REQUIRED`, `BAD_FORMAT`, `OUT_OF_RANGE`, and `INVALID_DATE` so appropriate messages can be shown.

## 5. APIs with Easily Misunderstood Behavior

### Integers: parsing checks the entire value and range

`Integer.parseInt("123")` returns `123`. `Integer.parseInt("12abc")` throws `NumberFormatException`; `Integer.parseInt("2147483648")` also throws an exception due to range overflow. `Long.parseLong` follows the same rules with a different `long` range.

You do not always need regex before parsing: if you only need **the exact syntax supported by the parse API** and accept reporting errors via exceptions, you can call parse directly inside `try/catch`. Adding a full-string check is helpful when **the input policy is stricter** than the parser's default behavior or when detailed error messages are needed. For example, Java's integer parser can accept certain Unicode digits that ASCII `[0-9]` intentionally rejects.

### Booleans: `parseBoolean` does not distinguish bad format from `false`

`Boolean.parseBoolean("true")` returns `true`; `Boolean.parseBoolean("FALSE")`, `Boolean.parseBoolean("yes")`, and `Boolean.parseBoolean(null)` all return `false`. This is a convenient API when you want everything other than `true` treated as `false`, but **unsuitable if `"yes"` must be flagged as invalid data**. When strictly the two values `true`/`false` are required, check each value explicitly as in the `booleanValue` method.

### Floating-point: `Double.parseDouble` can accept special forms

`Double.parseDouble` supports exponent notation and special values like `NaN` or `Infinity`. Therefore, **a successful parse does not mean the value is a finite number under the application's policy**. If using `double` and requiring finite values, also check `Double.isFinite(value)`. For monetary amounts needing decimal precision, `BigDecimal` is usually more suitable than `double`; however, formatting, range, decimal point, and fractional digit policies still need to be defined separately.

### Dates: right format is not enough for a valid date

The regex `[0-9]{4}-[0-9]{2}-[0-9]{2}` accepts the shape `"2023-02-29"`, yet that does not guarantee the date exists. Use `java.time.LocalDate` and a formatter with strict checking, such as `DateTimeFormatter.ISO_LOCAL_DATE`. With custom patterns, understand symbols like `uuuu` vs. `yyyy` and `ResolverStyle.STRICT`: a custom format can resolve differently from expectations if you simply assemble a pattern without checking calendar style. A validly parsed date can still violate business rules, such as a birth date in the future.

## 6. Data with Separators and Locale

Some data requires **locale** rules, such as `1.234,56` in many regions using a comma as the decimal mark, versus `1,234.56` in other regions. `new BigDecimal(String)` accepts canonical number representations according to its own syntax; it does not guess locale or strip units like `"USD"`.

If the application genuinely allows locale-formatted numbers, you can use `NumberFormat`/`DecimalFormat` with a specified `Locale` and `ParsePosition` to confirm the parser consumed **to the end of the input**. Principle example:

```java
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

NumberFormat format = NumberFormat.getNumberInstance(Locale.GERMANY);
String input = "1.234,56";
ParsePosition position = new ParsePosition(0);
Number number = format.parse(input, position);

boolean fullyConsumed =
        number != null && position.getIndex() == input.length();
```

The snippet above is **illustrative inside a block**, not a standalone runnable program. `fullyConsumed` checks whether the parser left a trailing suffix; **it does not guarantee strict formatting policy by itself**, because `NumberFormat` can be lenient about digit grouping, signs, and other details. Depending on the application, configure the parser appropriately or combine explicit syntax checks with value conversion. Do not blindly delete all `.` and `,` characters without knowing which is the grouping separator and which is the decimal separator.

If the format is an identifier or postal code, do not convert to a number and re-serialize, because that can drop leading zeros or alter representation. Storing it as a `String` and validating the full string against the contract is the better choice.

## 7. Error Handling: Report the Right Reason, Preserve the Right Data

Real-world applications can distinguish:

| Case | Example input | Appropriate handling |
| --- | --- | --- |
| Not provided | `null` | `REQUIRED` error if mandatory; "no value" state if optional. |
| Whitespace only | `"   "` | Empty error after normalization if policy permits `strip()`. |
| Syntax error | `"12x"` | Report the supported format, do not extract `12`. |
| Type range overflow | `"2147483648"` for `int` | Report out-of-range, do not force into `int` by truncation or unchecked casting. |
| Business rule violation | `"-5"` when quantity must be positive | Parse may succeed, but business validation must reject it. |
| Non-existent date | `"2023-02-29"` | Report invalid date; do not auto-correct to another date unless the contract allows it. |
| Outside boolean set | `"yes"` when only `true/false` allowed | Report invalid choice, do not treat `yes` as `false`. |
| Trailing content | `"19.95 USD"` when field requires pure amount | Reject or route to a unit parser with explicit rules. |

**Do not handle errors with silent defaults:** If `Integer.parseInt` fails, returning `0` without an error state can cause the application to confuse corrupted data with a valid `0`. Avoid wrapping an entire pipeline in a broad `catch (Exception ex)`; catch expected exceptions such as `NumberFormatException` or `DateTimeParseException`, then map them to appropriate input errors at the system boundary.

**Do not overwrite invalid data:** When displaying errors to users, keep the original input so they can understand and fix it, while optionally storing the normalized value separately when conversion succeeds. When logging, avoid writing full sensitive data or untrusted values directly into logs without consideration.

**Do not rely solely on client-side checks:** If input enters a backend system, validate against the contract at the trusted processing boundary, even if the UI already performs validation. Regex used for format validation does not replace SQL parameterization, authorization checks, input size limits, or business error handling.

## 8. Notes on Unicode, Whitespace, and Long Data

- **Digit policy:** `[0-9]` allows only ASCII digits. If you want to accept digits from multiple writing systems, define Unicode rules and check the downstream parser's behavior; do not assume regex and parse APIs always accept the exact same character set.
- **Whitespace:** `strip()` handles characters per `Character.isWhitespace`, yet does not remove every whitespace character, such as non-breaking spaces. If input must follow a protocol with specific ASCII whitespace, define the corresponding policy.
- **Very long numbers:** A syntactically valid regex does not check `int`/`long` bounds. Check maximum length beforehand, catch parse exceptions, and do not use unbounded `BigInteger`/`BigDecimal` on untrusted data if the system has resource constraints.
- **Error messages:** Phrase them as concrete requirements ("Enter an integer from 1 to 100 only"), rather than exposing stack traces or internal `NumberFormatException` messages.
- **Repeatedly used regex:** Reuse a compiled `Pattern`, as in the example, rather than recompiling on every record. Avoid regexes with expensive backtracking when processing large or untrusted data.
- **Boundary testing:** Test `null`, empty strings, whitespace, negative numbers, plus signs, Unicode digits, separators, leading zeros, overflow numbers, leap dates, trailing suffixes, and maximum length.

## 9. Practice Questions

1. Why does `Pattern.compile("[0-9]+").matcher("id=42x").find()` return `true`, yet cannot be used to confirm the entire input is an integer?
2. If `"2147483648"` matches `[0-9]+`, why does `Integer.parseInt` still throw `NumberFormatException`?
3. Why can using `Boolean.parseBoolean("yes")` corrupt data if the system requires strictly `true` or `false`?
4. For the date `"2023-02-29"`, what does the regex validate, and what does `LocalDate.parse` check further?
5. If a user enters `"00123"` as a member code, should it be converted to `int` before storing? Why or why not?
6. When parsing numbers by locale, why is parsing only a leading prefix of the input not considered valid data?

**Key takeaway:** Safe `String` conversion requires **policy-based whole-string validation**, **parsing to the right type and range**, **business-rule validation**, and **clear error reporting** if any step fails. Never equate "found a matching segment" with "the entire input is valid".