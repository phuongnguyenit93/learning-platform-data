# Designing Unambiguous Input and Full-String Validation

## A successful parse does not guarantee the data was read correctly

The string `03/06/2024` can be interpreted as June 3 or March 6. Both are valid dates. If an application tries `dd/MM/uuuu` and then `MM/dd/uuuu`, the result depends on the order of attempts rather than the sender's intent.

Another common bug is accepting `2024-02-29junk` because the parser managed to read the date prefix at the beginning. Reading a prefix does not prove that the entire input value conforms.

Good design must answer three questions simultaneously:

1. What structure and meaning is the string allowed to carry?
2. Which characters of the input must be read and validated?
3. Is the parsed value valid according to both the calendar and business rules?

This lesson uses a course date to build a clear contract, then illustrates the difference between parsing the whole string, partial parsing, and parsing only unresolved fields.

## 1. An input contract must be clearer than a sample string

A data contract is a specification that ensures both sender and receiver interpret a value the same way. For a course date, we can agree on:

| Property | Example specification |
| --- | --- |
| Meaning | An ISO calendar date, with no time or time zone |
| Structure | Year–month–day, e.g. `2024-06-03` |
| Width | Year exactly 4 digits, month and day exactly 2 digits |
| Digits | ASCII `0..9` |
| Separator | ASCII hyphen `-` |
| Whitespace | Not accepted at the start, end, or inside |
| Trailing characters | No extra characters accepted |
| Calendar validity | Must be an existing date, no automatic adjustment |
| Business range | Year from 2000 to 2099, inclusive |
| Missing values | Both `null` and empty strings are rejected |

The year range here is an illustrative application rule, not a general Java limitation.

A message like "please enter the date in the right format" still leaves the user guessing. Guidance such as "enter the date as year-month-day, e.g. 2024-06-03" lets both users and integrators know exactly what is expected.

For a field with a different meaning, the contract must change as well. A global submission deadline might require a date-time with an offset; a birth date usually needs only a date. Do not add a default time or server time zone just to force every input into the same type.

## 2. Eliminate ambiguity at the source instead of guessing by pattern order

Common ambiguous inputs:

| Input | Unclear information |
| --- | --- |
| `03/06/2024` | Month first or day first? |
| `03/06/24` | Which century? |
| `08:30` | Time of which day, where, and under which system? |
| `2024-06-03T08:30` | Local time or an instant that needs an offset/zone? |
| Textual month name | In which language/locale? |
| An integer timestamp | Seconds or milliseconds, and from which epoch? |

The solution is to choose an agreed-upon representation, provide type/format labels when needed, and preserve sufficient meaningful data. For example, two legacy sources using different component orders should be distinguished via source configuration or interface version; you should not let each individual value "choose" a pattern by trial and error.

If you are migrating a system and must accept multiple patterns, explicitly define the pattern set and the policy when multiple patterns parse successfully but yield different results. A semantically safe choice is to reject ambiguous values and require the source to send the canonical form. `parseBest` or a chain of `try/catch` blocks cannot discover the sender's intent on its own.

Display formatting can still be locale-friendly. A UI can provide a calendar picker and then submit a canonical representation; the display format and the data-transfer contract do not have to be identical.

## 3. Distinguish the four validation layers

```text
Raw string
   ↓ null / empty / whitespace policy
Allowed shape
   ↓ digits, separators, width, entire input
Valid calendar date
   ↓ year–month–day combination must exist
Business rules
   ↓ year range, registration date, deadline...
Typed value used by the application
```

The four layers do not replace one another:

- The regular expression `[0-9]{4}-[0-9]{2}-[0-9]{2}` matches both `2023-02-29` and `2024-99-99`; it does not check calendar validity.
- `STRICT` resolver mode checks that the date exists, but it does not know on its own that the product only allows years `2000..2099`.
- Reading a valid date at the beginning of a string does not rule out trailing characters.
- Truncating a string to 10 characters can destroy evidence of invalid input.

For standard ISO format where the contract has no additional textual restrictions, `LocalDate.parse(text)` is usually simple enough. A separate shape-validation layer is only needed when the contract also specifies exact digits, widths, or character sets as in this lesson's example.

## 4. Complete program: clear contract and thorough validation

Save as `UnambiguousDateInputDemo.java`. This program requires Java 17 or later:

```java
import java.text.ParsePosition;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.time.temporal.TemporalAccessor;
import java.util.Locale;
import java.util.regex.Pattern;

public class UnambiguousDateInputDemo {
    private static final Pattern DATE_SHAPE =
            Pattern.compile("[0-9]{4}-[0-9]{2}-[0-9]{2}");

    private static final DateTimeFormatter DATE =
            DateTimeFormatter.ofPattern("uuuu-MM-dd", Locale.ROOT)
                    .withResolverStyle(ResolverStyle.STRICT);

    static LocalDate parseCourseDate(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException("Ngay hoc khong duoc null");
        }
        if (!DATE_SHAPE.matcher(raw).matches()) {
            throw new IllegalArgumentException(
                    "Ngay hoc phai dung dang nam-thang-ngay, vi du 2024-06-03");
        }

        LocalDate date = LocalDate.parse(raw, DATE);
        if (date.getYear() < 2000 || date.getYear() > 2099) {
            throw new IllegalArgumentException("Nam hoc phai trong 2000..2099");
        }
        return date;
    }

    private static void show(String label, String raw) {
        try {
            System.out.println(label + "=" + parseCourseDate(raw));
        } catch (DateTimeParseException | IllegalArgumentException ex) {
            System.out.println(label + "=REJECTED");
        }
    }

    public static void main(String[] args) {
        show("valid", "2024-02-29");
        show("invalidCalendarDate", "2023-02-29");
        show("wrongWidth", "2024-2-9");
        show("leadingSpace", " 2024-02-29");
        show("trailingText", "2024-02-29junk");
        show("slashDate", "03/06/2024");
        show("outsideBusinessRange", "2100-01-01");
        show("empty", "");
        show("missing", null);

        DateTimeFormatter dayFirst =
                DateTimeFormatter.ofPattern("dd/MM/uuuu", Locale.ROOT)
                        .withResolverStyle(ResolverStyle.STRICT);
        DateTimeFormatter monthFirst =
                DateTimeFormatter.ofPattern("MM/dd/uuuu", Locale.ROOT)
                        .withResolverStyle(ResolverStyle.STRICT);

        String ambiguous = "03/06/2024";
        System.out.println("dayFirst=" + LocalDate.parse(ambiguous, dayFirst));
        System.out.println("monthFirst=" + LocalDate.parse(ambiguous, monthFirst));

        String extra = "2024-02-29junk";
        ParsePosition position = new ParsePosition(0);
        TemporalAccessor prefix = DATE.parse(extra, position);

        System.out.println("prefixDate=" + LocalDate.from(prefix));
        System.out.println("consumed=" + position.getIndex());
        System.out.println("remaining=" + extra.substring(position.getIndex()));
        System.out.println("consumedWholeInput="
                + (position.getIndex() == extra.length()));

        try {
            LocalDate.parse(extra, DATE);
            System.out.println("fullParseAccepted");
        } catch (DateTimeParseException ex) {
            System.out.println("fullParseRejected");
        }

        ParsePosition syntaxPosition = new ParsePosition(0);
        TemporalAccessor syntaxOnly =
                DATE.parseUnresolved("2023-02-29", syntaxPosition);

        System.out.println("syntaxOnlyReadInvalid=" + (syntaxOnly != null));
        System.out.println("syntaxOnlyConsumed=" + syntaxPosition.getIndex());
    }
}
```

Compile and run:

```shell
javac --release 17 UnambiguousDateInputDemo.java
java UnambiguousDateInputDemo
```

Stdout:

```text
valid=2024-02-29
invalidCalendarDate=REJECTED
wrongWidth=REJECTED
leadingSpace=REJECTED
trailingText=REJECTED
slashDate=REJECTED
outsideBusinessRange=REJECTED
empty=REJECTED
missing=REJECTED
dayFirst=2024-06-03
monthFirst=2024-03-06
prefixDate=2024-02-29
consumed=10
remaining=junk
consumedWholeInput=false
fullParseRejected
syntaxOnlyReadInvalid=true
syntaxOnlyConsumed=10
```

The program prints `REJECTED` itself so that stdout focuses on behavior rather than depending on the exact exception message wording of a particular JDK release.

## 5. Why does the example's input function validate sufficiently?

### Validating the exact full shape

`DATE_SHAPE.matcher(raw).matches()` requires matching the entire input of the newly created matcher. It differs from `find()`, which searches for a matching subsequence. No extra anchors are needed to perform full-string matching in this call. [`Matcher` documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/regex/Matcher.html)

As a result, inputs with whitespace, extra characters, slashes, or wrong widths are rejected before calendar parsing.

### Validating that the date actually exists

`LocalDate.parse(raw, DATE)` produces the exact date type the application needs. The pattern uses `uuuu` to have a direct year field, and `ResolverStyle.STRICT` so that February 29, 2023 is not silently adjusted to another date.

Full-parse methods require the entire string to be consumed; in the program, `LocalDate.parse(extra, DATE)` rejects the trailing `junk`. [`LocalDate.parse` documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDate.html#parse(java.lang.CharSequence,java.time.format.DateTimeFormatter)), [full-parse documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html#parse(java.lang.CharSequence))

### Validating the allowed product range

Once the date is obtained, the function checks the year. The date `2100-01-01` exists on the calendar but falls outside the example's range, so it is still rejected.

In a real application, you can add conditions such as not before the registration opening date. Those rules should operate on the typed value after the input has been validated, rather than comparing date strings arbitrarily.

## 6. When using `ParsePosition`, checking for remaining text is your responsibility

The `formatter.parse(text, position)` overload is designed to support parsing from a specified index and may stop before the end of the string. In the program, the parser reads the first date, updates the position to `10`, and leaves `junk` behind. [`DateTimeFormatter.parse` with position documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html#parse(java.lang.CharSequence,java.text.ParsePosition))

`ParsePosition.getIndex()` is the position immediately after the last character read; `getErrorIndex()` provides the error position if one was set. [`ParsePosition` documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/ParsePosition.html)

If you are reading a standalone field and intentionally use this style of API, you must ensure:

- The starting position is at the exact start of the field, usually `0`.
- The parse operation does not fail and the result can produce the target type.
- No error index is reported.
- The ending position equals the field length if the contract requires reading the entire input.

An illustrative skeleton for the resolving overload:

```java
ParsePosition position = new ParsePosition(0);
TemporalAccessor parsed = formatter.parse(text, position);

if (position.getErrorIndex() >= 0 || position.getIndex() != text.length()) {
    throw new IllegalArgumentException("Truong ngay con ky tu du hoac bi loi");
}
LocalDate date = LocalDate.from(parsed);
```

This is an illustrative snippet assuming `formatter` is already configured and `text` is non-null; the `parse` method can still throw an exception before reaching the condition. If you only need to parse a standalone date, using `LocalDate.parse` directly is usually easier to verify.

Partial parsing is not always wrong. It is useful when reading a larger structure containing multiple fields and delimiters. In that case, the enclosing parser must continue reading and validating the remaining parts. The mistake is treating success on a single segment as proof for the entire field or the entire record.

## 7. `parseUnresolved` is not date-validity verification

In the program:

```text
syntaxOnlyReadInvalid=true
syntaxOnlyConsumed=10
```

appears for `2023-02-29`. `parseUnresolved` reads the fields syntactically without resolving them into a date. Therefore, receiving a non-null object and consuming all 10 characters does not prove the year–month–day combination exists. [`parseUnresolved` documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html#parseUnresolved(java.lang.CharSequence,java.text.ParsePosition))

This is the difference between:

```text
Parsed YEAR=2023, MONTH=2, DAY=29
                       ≠
Valid LocalDate created
```

This low-level API is appropriate when you have a reason to process fields individually. Do not merely check that the result is non-null and then admit the data into the system as a validated date.

Nor should you call `LocalDate.from` on an unresolved set of fields assuming it will run the formatter's full resolution pipeline on its own. For ordinary date input, let the full-parse API return a valid `LocalDate` right at the input boundary.

## 8. Input normalization must be an explicit public rule

There are two valid but distinct policies:

- Strict protocol: `2024-06-03` is accepted; ` 2024-06-03 ` is rejected.
- User form allowing outer whitespace: the application normalizes according to the chosen rule and then validates the rest.

What matters is deciding upfront and applying it consistently. Do not silently `trim()`, strip separators, reorder components, or truncate strings just to make an existing pattern succeed.

If normalization is allowed, distinguish:

```text
rawInput        = string sent by the source
normalizedInput = string after allowed normalization rules
parsedValue     = parsed date/time
```

You do not need to store all three in every system. When traceability is needed, decide which information must be retained and protect it according to data sensitivity. However, do not call an arbitrary transformation "normalization" if it alters the meaning of the input.

When multiple representations are allowed, the canonical output may differ from the original text. Checking whether "reformatting produces the exact source string" is only appropriate when the contract truly requires a single textual form; it does not replace date validation and business-rule checks.

## 9. Designing error messages and testing against the contract

A production function should distinguish errors so users can fix the right thing, for example:

| Error type | Helpful feedback |
| --- | --- |
| Missing value | Prompt to enter the course date |
| Invalid structure | State the year-month-day format and an example |
| Non-existent date | Explain that the day/month/year combination is invalid |
| Out of range | State the allowed year range |
| Ambiguous across conventions | Request the canonical representation or confirm the source format |
| Extra characters | Indicate that the field must contain only a single date value |

Avoid returning the current date, a default date, or `null` to mask errors. Those values can flow into business processing and create hard-to-detect bad data.

When testing, use the contract as the baseline rather than only testing happy-path strings:

- A normal date and a valid leap-day date.
- A non-existent date and an out-of-range month.
- Extra leading and trailing characters, including spaces or newlines if forbidden.
- Wrong width, different separators, different structures.
- Empty and null values.
- Both boundaries of the allowed range and values immediately outside the boundaries.
- Strings easily misinterpreted across conventions.

These cases should assert the accepted value or the rejection category, not just that "the function ran".

## 10. Practice exercises

1. Why does trying `dd/MM/uuuu` before `MM/dd/uuuu` fail to resolve the meaning of `03/06/2024`?
2. Is a string that matches a date-shaped regex guaranteed to exist on the calendar?
3. Is a parse using `ParsePosition` that stops at index 10 in a 14-character string sufficient for a standalone date field?
4. What does `parseUnresolved` consuming all of `2023-02-29` prove?
5. Why must the year range be checked after obtaining a `LocalDate`?

Suggested answers:

1. Both patterns can be valid and produce two different dates; you need an explicit contract or source metadata.
2. No; textual shape is different from calendar validity.
3. No; four characters remain unvalidated under the field contract.
4. That the fields were read syntactically, not that they form a valid date.
5. The library knows the calendar; only the application knows the year range allowed by business rules.

Make input meaning clear by design, use the right API to parse the entire value, and keep shape, calendar, and business-rule checks distinct.
