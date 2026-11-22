# Building a Strict Date Input Parser with Clear Error Messages

## 1. A Date Input Parser Needs a Contract Before a Parser

Accepting a string and producing an object is not enough. The input parser must clearly state which format is accepted, whether the date must actually exist in the calendar, and what the user needs to fix when it fails.

In this exercise, choose a specific contract:

- Enter `dd/MM/uuuu` exactly: two digits for day, two digits for month, four digits for year, separated by `/`.
- Accept only ASCII digits `0–9`, with no leading/trailing whitespace or extra characters.
- The date must be valid in the ISO calendar; do not automatically adjust 31/4 to 30/4 or 29/2 in a common year to 28/2.
- The application's year range is 0001–9999.
- Success returns a `LocalDate`; failure returns an error code and an understandable message.

This is the contract for this exercise, not a general limitation of `LocalDate`: this type also supports year 0, negative years, and a larger range. Choosing a separate year range prevents the example from silently imposing business constraints onto the library.

## 2. Separating Three Validation Layers

```text
Input string
  → has data and matches the shape?
  → is an existing calendar date?
  → satisfies application rules?
  → LocalDate or clear error
```

| Layer | Error example | Appropriate response |
| --- | --- | --- |
| Required | `null`, empty string | Ask user to enter a date |
| Shape | `1/2/2024`, `2024-02-01` | Specify the accepted format |
| Calendar date | `31/04/2024`, `29/02/2023` | Report that the date does not exist |
| Application range | `01/01/0000` | Report the year limit |

Regex can validate the shape, but it should not take on all month, day, and leap-year rules by itself. `LocalDate` together with a strict-resolving formatter handles calendar validation. [LocalDate.parse](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDate.html#parse(java.lang.CharSequence,java.time.format.DateTimeFormatter))

## 3. Choosing uuuu and ResolverStyle.STRICT

`DateTimeFormatter.ofPattern` uses `SMART` resolution by default. For day-of-month, that mode can adjust certain values exceeding the last day of the month to the last valid day. Because the input parser requires not altering the date, you must choose `withResolverStyle(ResolverStyle.STRICT)`.

`STRICT` checks the compatibility of year, month, and day; `LENIENT` allows overflow interpretation according to rules, while `SMART` applies certain reasonable adjustments. They are not interchangeable within an input contract. [ResolverStyle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/ResolverStyle.html)

In this ISO date pattern, use `uuuu` for the year. `yyyy` is year-of-era; under strict resolution without era information, it may not be sufficient to construct the date as the author expects. Also do not use `YYYY`: that is week-based-year.

`Locale.ROOT` makes it clear that this parser does not follow the machine's default locale conventions. The digit and width contract is checked separately on the input. The formatter is an immutable and thread-safe object, so a single shared constant can be kept. [DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html)

## 4. Do Not Return Fake Dates or Raw Technical Messages

If the input is invalid, do not return `LocalDate.now()`, the epoch, or an adjusted end-of-month date. Those values could continue to be stored as real data.

Nor should you expose raw stack traces or `DateTimeParseException.getMessage()` to the user. You can keep stable error codes for calling code and Vietnamese messages for the UI:

| Code | Message |
| --- | --- |
| `REQUIRED` | Vui lòng nhập ngày. |
| `FORMAT` | Nhập đúng dd/MM/uuuu, ví dụ 29/02/2024. |
| `INVALID_DATE` | Ngày không tồn tại; hãy kiểm tra ngày, tháng và năm nhuận. |
| `YEAR_RANGE` | Năm phải nằm trong khoảng 0001–9999. |

Error codes and display messages are two separate components. The UI can translate the message without changing the processing logic or parsing the message string.

## 5. Complete Java Program

Save as `StrictDateInputDemo.java`. Two separate result types prevent an object from simultaneously holding a success value and an error.

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;
import java.util.regex.Pattern;

public class StrictDateInputDemo {
    private static final Pattern SHAPE =
            Pattern.compile("[0-9]{2}/[0-9]{2}/[0-9]{4}");
    private static final DateTimeFormatter FORMATTER =
            DateTimeFormatter.ofPattern("dd/MM/uuuu", Locale.ROOT)
                    .withResolverStyle(ResolverStyle.STRICT);

    enum ErrorCode { REQUIRED, FORMAT, INVALID_DATE, YEAR_RANGE }
    sealed interface Result permits Parsed, Rejected {}
    record Parsed(LocalDate date) implements Result {}
    record Rejected(ErrorCode code, String message) implements Result {}

    static Result parseDate(String raw) {
        if (raw == null || raw.isBlank()) {
            return new Rejected(ErrorCode.REQUIRED, "Vui lòng nhập ngày.");
        }
        if (!SHAPE.matcher(raw).matches()) {
            return new Rejected(ErrorCode.FORMAT,
                    "Nhập đúng dd/MM/uuuu, ví dụ 29/02/2024.");
        }

        final LocalDate date;
        try {
            date = LocalDate.parse(raw, FORMATTER);
        } catch (DateTimeParseException ex) {
            return new Rejected(ErrorCode.INVALID_DATE,
                    "Ngày không tồn tại; hãy kiểm tra ngày, tháng và năm nhuận.");
        }

        if (date.getYear() < 1 || date.getYear() > 9999) {
            return new Rejected(ErrorCode.YEAR_RANGE,
                    "Năm phải nằm trong khoảng 0001–9999.");
        }
        return new Parsed(date);
    }

    static void show(String raw) {
        String label = raw == null ? "<null>" : "\"" + raw + "\"";
        Result result = parseDate(raw);
        if (result instanceof Parsed parsed) {
            System.out.println(label + " -> OK: " + parsed.date());
        } else if (result instanceof Rejected rejected) {
            System.out.println(label + " -> " + rejected.code() + ": "
                    + rejected.message());
        }
    }

    public static void main(String[] args) {
        String[] inputs = {
                null, "", "29/02/2024", "29/02/2023", "31/04/2024",
                "1/2/2024", "2024-02-29", "29/02/2024 ",
                "01/01/0000", "29/02/2000", "29/02/2100", "01/13/2024"
        };
        for (String input : inputs) {
            show(input);
        }
    }
}
```

Compile and run with JDK 17 or later, saving the file as UTF-8:

```shell
javac -encoding UTF-8 --release 17 StrictDateInputDemo.java
java "-Dfile.encoding=UTF-8" StrictDateInputDemo
```

Exact stdout:

```text
<null> -> REQUIRED: Vui lòng nhập ngày.
"" -> REQUIRED: Vui lòng nhập ngày.
"29/02/2024" -> OK: 2024-02-29
"29/02/2023" -> INVALID_DATE: Ngày không tồn tại; hãy kiểm tra ngày, tháng và năm nhuận.
"31/04/2024" -> INVALID_DATE: Ngày không tồn tại; hãy kiểm tra ngày, tháng và năm nhuận.
"1/2/2024" -> FORMAT: Nhập đúng dd/MM/uuuu, ví dụ 29/02/2024.
"2024-02-29" -> FORMAT: Nhập đúng dd/MM/uuuu, ví dụ 29/02/2024.
"29/02/2024 " -> FORMAT: Nhập đúng dd/MM/uuuu, ví dụ 29/02/2024.
"01/01/0000" -> YEAR_RANGE: Năm phải nằm trong khoảng 0001–9999.
"29/02/2000" -> OK: 2000-02-29
"29/02/2100" -> INVALID_DATE: Ngày không tồn tại; hãy kiểm tra ngày, tháng và năm nhuận.
"01/13/2024" -> INVALID_DATE: Ngày không tồn tại; hãy kiểm tra ngày, tháng và năm nhuận.
```

`matches()` requires the entire string to match the shape; `LocalDate.parse` constructs a date from the entire input. Month 13 has the valid two-digit shape but is outside the calendar range, so it falls into `INVALID_DATE`, not `FORMAT`.

A whitespace-only string is treated as missing data; a string containing a date with whitespace is a shape error under the chosen contract. If the product wants to allow surrounding whitespace, add a documented and explicitly tested normalization step instead of changing it silently.

## 6. Classify Errors Clearly Without Over-Guessing

A date resolution error can be caused by the relationship between multiple fields. For example, 29/2 is only invalid in certain years. The message “the date does not exist; check day, month, and leap year” is more accurate than always concluding a specific character is wrong.

`DateTimeParseException` provides the parsed string and error index, which is useful for diagnostics. However, that index does not always correspond to a single day/month/year field that needs fixing, especially for errors during the field-resolving phase. Do not promise “the character at this position is definitely the cause” for all calendar errors. [DateTimeParseException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeParseException.html)

The parser catches the exact parsing exception at the input boundary. Do not catch all `Exception` types and label them all as “invalid date”, because formatter configuration errors or programming bugs need to be detected separately.

Validation order is also part of the feedback: for example, `31/02/0000` fails during calendar date validation before checking the year range. If the application needs to report multiple errors at once, you must design a separate error-aggregation policy; do not infer backward from a single message.

## 7. Place Business Rules After Obtaining LocalDate

A generic parser should not forbid all future dates on its own: an appointment date may be in the future, whereas a birth date usually cannot be in the future. After receiving `Parsed`, the business layer validates according to context.

Illustrative snippet inside a method:

```java
LocalDate birthDate = parsedDate; // Successfully parsed value.
LocalDate today = LocalDate.of(2025, 6, 15);
if (birthDate.isAfter(today)) {
    // Return a dedicated business code: birth date cannot be after today.
}
```

In a real application, determine today using an explicit clock and business time zone; in tests, use a fixed date or an injected `Clock`. Do not introduce a clock dependency into the parser if the parser is only responsible for reading a date.

There is no need to convert the newly parsed date to an `Instant`: the input has no time or time zone. Keep `LocalDate` across layers where the meaning remains a calendar date.

## 8. Checks Before Putting into a Real Input Flow

- Valid regular dates, end-of-month dates, and 29/2 in leap years.
- Non-existent dates, month 00/13, day 00, and century year exceptions such as 2000/2100.
- Missing leading zeros, different separators, extra characters, whitespace, and out-of-contract digits.
- Year 0000, year 0001, and 9999 to verify application boundaries.
- Running under a different default locale to ensure the contract remains unchanged.

The same parser can be used for multiple rows of an input file and return errors attached to row/field positions. That part belongs to the input orchestration layer; the date parser still only takes a string and returns a single result.

If you want to accept multiple formats, document the list and how ambiguity is handled. Do not try both `dd/MM/uuuu` and `MM/dd/uuuu` and take the first result for `01/02/2024`: both interpretations can be valid dates.

## 9. Further Exercises

1. Allow surrounding whitespace while still forbidding whitespace inside the date; keep the calendar parser strict.
2. Add a validation layer for an allowed date range, with an error code distinct from format errors.
3. Verify that `31/12/9999` and `01/01/0001` succeed, and `01/01/0000` fails according to the contract.
4. Replace `STRICT` with `SMART` in a separate experiment to observe why the input parser must not auto-correct dates.

The result to preserve is a valid date or a meaningful error; no invalid input case should ever be silently turned into another date.