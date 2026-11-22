# Reading Error Positions from DateTimeParseException

## 1. From "Invalid Date" to Useful Diagnostic Information

When parsing a date-time string fails, simply reporting "invalid format" is often not enough for users or developers to know what needs to be fixed. In `java.time`, `DateTimeParseException` carries **the string being parsed** and **the index where the parser detected the error**.

For example, with the pattern `uuuu-MM-dd`, the string `2026/10/25` has a `/` where the pattern expects `-`. The reported position is index 4:

```text
index:  0123456789
string: 2026/10/25
            ^
```

This index is 0-based. It is a clue for locating the error, though it does not always uniquely identify the character that needs to be changed. For a nonexistent date such as `2023-02-29`, the fields were already parsed successfully; the error only occurs when resolving them into a date. Such a case may be reported at the start of the string, even though the year digits are not wrong.

This lesson focuses on how to read the exception information and present the position meaningfully, rather than guessing the cause from the number alone.

## 2. Information to Retrieve When Catching the Exception

| Method | Data Returned | How to Use It |
|---|---|---|
| `getParsedString()` | The string the parser was reading | Match the exact source associated with the error index |
| `getErrorIndex()` | The index where the error was detected | Highlight the position or include it in a diagnostic report |
| `getMessage()` | Detailed description of the exception | Read to understand the cause during debugging |
| `getCause()` | The underlying cause, if any | Find additional context, especially for errors when resolving fields |

Illustrative example inside a Java method:

```java
try {
    LocalDate.parse(text, formatter);
} catch (DateTimeParseException e) {
    String parsed = e.getParsedString();
    int index = e.getErrorIndex();
    String detail = e.getMessage();
    Throwable cause = e.getCause();
    // Use this data to build a message or assist with debugging.
}
```

The snippet above only illustrates how to retrieve the data: `text` and `formatter` must be passed in or declared in the calling context. A standalone program is provided in Section 5.

There is no need to parse `getMessage()` back to find the index: `getErrorIndex()` is already provided. Nor should the full English JDK message be treated as a stable protocol for classifying errors via string matching. When localized user-facing messages are needed, keep the technical message for diagnostics and write guidance that matches the application's input contract.

## 3. Reading the Index Correctly

### The index is 0-based, not a 1-based column number

For the single-line ASCII string `2026/10/25`, `getErrorIndex() == 4` points to the first `/`. If the UI displays 1-based position numbers, it can be described as the 5th position, but the convention should be stated clearly.

Do not report "position 4" and then place the cursor on the fourth character according to human counting. Be consistent with terminology such as "index 4, 0-based" or convert it consistently for the UI.

### The index can fall immediately after the last character

For the input `2026-10-`, the day part has not appeared yet. The parser can report index 8, which equals the string length:

```text
2026-10-
        ^
```

This is the end-of-input position, not an existing character on which `charAt(8)` can be called. An empty string can also report index 0, which likewise equals length 0.

When you need to access the character at the error position, you must check `0 <= index && index < parsed.length()`. If you only want to place a marker at the boundary after the string, then `index == parsed.length()` is still meaningful. Checking bounds before using the index prevents the error-reporting code itself from throwing another exception.

### The index belongs to a Java string, not a general display column

String indices in Java are counted in UTF-16 code units. For ASCII digit and punctuation examples, one code unit corresponds to one visible character, so a caret line can be built using `" ".repeat(index)`.

For emojis, combining characters, tabs, or multi-line strings, one index does not necessarily correspond to one display-width cell on screen. To highlight in a UI, use the selection mechanism of the input component and the index convention it expects. If line/column numbers are needed, convert from the index on the exact string rather than treating it directly as a column number.

## 4. Detection Position Differs from Business Cause

Consider the strict formatter `uuuu-MM-dd` used in the program in the next section:

| Input | Observed Index | Correct Interpretation |
|---|---|---|
| `2026/10/25` | `4` | Separator mismatch at this position |
| `2026-XX-25` | `5` | Parser failed to read the month field starting here |
| `2026-10-` | `8` | Input ended before the day field was complete |
| `2026-10-25extra` | `10` | Date finished parsing, but trailing unparsed text remains |
| `2023-02-29` | `0` | Error when resolving fields into a date; do not conclude the year is syntactically wrong |
| Empty string | `0` | No data to parse right from the start |

The indices above are tied to **the specific formatter, target type, and parsing method in the example**. Changing the pattern, optional sections, or call style can change the detection position. A multi-character field can also be reported at the start of the field rather than at the exact final character that caused the issue.

There are two categories of failures to distinguish:

- **Syntactic parsing errors:** mismatched characters, digit counts, month names, or separators.
- **Field resolution errors:** the numbers were parsed, but they do not form a valid date/time, or there is not enough information to construct the requested target type.

You cannot infer these two categories solely by a rule like "index 0 means wrong year, index 5 means wrong month." You also need to inspect the message, any cause, and the formatter configuration.

For example, missing an era when using `yyyy` with `ResolverStyle.STRICT` can cause `LocalDate` creation to fail even when the numbers look like a familiar date. In standard ISO date patterns, use `uuuu` to represent the year field directly; do not automatically alter the user's input date just because the error is reported at index 0.

## 5. Program to Read and Mark the Error Position

Save the following code to `ParseErrorPositionDemo.java`. The code requires Java 17 or later and needs no external libraries. The `^` marker is designed for the single-line ASCII strings in the example.

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;

public class ParseErrorPositionDemo {
    private static final DateTimeFormatter FORMAT = DateTimeFormatter
            .ofPattern("uuuu-MM-dd", Locale.ROOT)
            .withResolverStyle(ResolverStyle.STRICT);

    public static void main(String[] args) {
        for (String text : new String[]{
                "2026-10-25", "2026/10/25", "2026-XX-25",
                "2026-10-", "2026-10-25extra", "2023-02-29", ""
        }) {
            inspect(text);
        }
    }

    private static void inspect(String text) {
        try {
            LocalDate date = LocalDate.parse(text, FORMAT);
            System.out.println("OK " + date);
        } catch (DateTimeParseException e) {
            String parsed = e.getParsedString();
            int index = e.getErrorIndex();
            System.out.println("ERROR index=" + index
                    + " length=" + parsed.length());
            System.out.println(parsed);

            if (index >= 0 && index <= parsed.length()) {
                System.out.println(" ".repeat(index) + "^");
                System.out.println(index == parsed.length()
                        ? "position=end-of-input"
                        : "position=UTF-16 index " + index);
            } else {
                System.out.println("position=outside-input");
            }
        }
    }
}
```

Compile and run:

```shell
javac ParseErrorPositionDemo.java
java ParseErrorPositionDemo
```

Expected output; the leading spaces before `^` and the blank line near the end are intentional:

```text
OK 2026-10-25
ERROR index=4 length=10
2026/10/25
    ^
position=UTF-16 index 4
ERROR index=5 length=10
2026-XX-25
     ^
position=UTF-16 index 5
ERROR index=8 length=8
2026-10-
        ^
position=end-of-input
ERROR index=10 length=15
2026-10-25extra
          ^
position=UTF-16 index 10
ERROR index=0 length=10
2023-02-29
^
position=UTF-16 index 0
ERROR index=0 length=0

^
position=end-of-input
```

The program uses `ResolverStyle.STRICT` so that February 29, 2023 actually triggers an error. If the default `SMART` mode of `ofPattern` were kept, that case could be adjusted to February 28 and would not enter the `catch` block. When testing error reporting, always verify the active resolver policy.

`LocalDate.parse(text, FORMAT)` requires the entire string to be consumed. As a result, the `extra` suffix is not silently ignored. Lower-level parsing APIs that take `ParsePosition` have a different contract; do not assume they always throw the same exception or report trailing text in the same way.

The `outside-input` branch is a defensive guard in the display helper against an unusable index. This program does not produce that case; you should not replace any unexpected index with 0 and claim the first character is wrong.

## 6. Associating the Position with the Right Version of the Input

Suppose an ingestion layer calls `strip()` to trim leading and trailing whitespace before parsing the date. The exception will store the string passed into the parser—that is, the trimmed string. Its index no longer points directly to the same position in the original string.

For example:

```text
Original string: "  2026/10/25  "
Parsed string:   "2026/10/25"
Error index:     4 in the parsed string
```

To highlight the original input field, you need to map the position back through the transformation, or display the exact `getParsedString()` alongside the error. With more complex transformations such as Unicode normalization or removing characters in the middle of the string, you cannot always just add a fixed offset.

If multiple formatters are tried, each exception also belongs to a specific attempt. When reporting the error, retain both the pattern attempted and the string actually parsed, rather than keeping only the last exception and claiming it is the sole cause. A larger error index does not by itself prove that one formatter is the right choice for the input.

## 7. Turning Technical Information into User-Friendly Messages

For a form that specifies a `uuuu-MM-dd` date, a useful general message could be: "Could not parse the date. Please enter it in the format 2026-10-25 and use a valid calendar date." When you have reliable information about a separator error, you can add the position so the user can check it.

Keep details such as the field name, expected pattern, error index, and technical description separate to support debugging. There is no need to expose a full stack trace in the input UI. If the input string contains personal data, only store what is necessary according to your application's policy; the error position can still be reported without logging the entire input value in every log record.

Catching `DateTimeParseException` specifically around the parsing call avoids turning other programming bugs into "invalid date" messages. For instance, `null` should be checked as missing input; do not assume it always produces the same exception with an error index to highlight.

After parsing succeeds, perform business validations such as ensuring the start date is not after the end date. A business rule failure like that does not necessarily belong to a single character in the string, so do not arbitrarily assign index 0 and make it look like a syntax error.

## 8. Practice on Your Own

Add the following three inputs to the program and predict the output before running it:

1. `2026-10-25 `: the string has a trailing space, so full-string parsing reports trailing unparsed text starting at index 10.
2. `2026-10`: missing the separator and the following day field; the detected position is where the string ends, index 7.
3. `2024-02-29`: a valid leap day, so no exception is thrown.

For each error, answer separately: which string does the reported position belong to, is there a character at that position or has the string ended, and is the available data enough to conclude the cause? These three questions help you use `getErrorIndex()` as accurate diagnostic information rather than guesswork.

Reference: [DateTimeParseException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeParseException.html) and [DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html) in Java SE 21.
