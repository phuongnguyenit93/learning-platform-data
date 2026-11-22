# `ParsePosition`: Ending Position and Error Position When Parsing Input in Java

## 1. Why Does a Successful Parse Not Guarantee Valid Input?

In localized applications, users enter numbers, dates, and strings with separators that vary by `Locale`. Java provides APIs such as `NumberFormat`, `DecimalFormat`, and `DateFormat` to read such data. However, many parsing methods in `java.text` **are allowed to read a valid prefix and stop**, even if unprocessed characters remain afterward.

For example, with German symbols:

```text
Input:    1.234,56abc
          └──────┘└─┘
           parsed  unread
Value: 1234.56
Ending index: 8 (0-based)
```

If a program only checks that `parse(...)` returns a non-`null` `Number`, it could treat `1.234,56abc` as a valid number, even when business requirements state that **the entire input field must be a number**.

`java.text.ParsePosition` lets you inspect the **starting position**, the **position where the parser stopped after reading**, and the **error position when the parser fails to read the input**. It is an essential tool for distinguishing:

- **Partial success:** a value was read, but an unconsumed suffix remains.
- **Full success:** a value was read and the stopping position equals the input length.
- **Unparseable:** no value could be read at the requested position; the method typically returns `null` and updates the error index.
- **Business rule failure:** the parser may read the entire string, yet the value still violates the data type, precision, range, or format rules required by the product.

**Principle:** `ParsePosition` reports parser progress; it **does not automatically turn a parser into a strict data validator**. The application must still enforce its own acceptance criteria.

## 2. What Is `ParsePosition`?

The `java.text.ParsePosition` class is a **mutable** object holding two integers:

| Component | Methods | Meaning |
| --- | --- | --- |
| Current reading position (`index`) | `getIndex()`, `setIndex(int)` | Starting position when passed to the parser; after a successful read, typically the position **immediately after the last consumed character** |
| Error position (`errorIndex`) | `getErrorIndex()`, `setErrorIndex(int)` | Position of the error recorded by the parser if parsing failed |
| Construction | `new ParsePosition(startIndex)` | Specifies the starting index, usually `0`; default error index is `-1` |

Typical usage:

```java
ParsePosition position = new ParsePosition(0);
Number value = numberFormat.parse(input, position);

if (value == null) {
    // No value could be read at the requested position.
} else if (position.getIndex() != input.length()) {
    // Only a prefix of the string was read.
} else {
    // The entire string was read at the parser level.
}
```

This is an **illustrative code snippet** using existing `numberFormat` and `input` variables; standalone runnable examples with full imports and classes appear later.

### Two Different Positions

- `getIndex()` returns **how far the parser progressed**, which is not always the length of the string.
- `getErrorIndex()` returns **the position where the parser reported an error**, not the “number of remaining characters” and not the “stopping position” in every case.
- `-1` in `errorIndex` means **no error position was recorded**. This **does not guarantee the entire string is valid**.
- When a non-`null` `Number` is returned but `index < input.length()`, you must detect **trailing data** using `index` — even when `errorIndex == -1`.

`ParsePosition` indices are positions in a Java string, i.e., indices of **UTF-16 code units**, just like `String.length()` and `substring()`. Do not confuse them with UTF-8 byte counts or user-perceived characters. For emojis and characters outside the BMP, a single code point can occupy two UTF-16 code units.

## 3. Which APIs Accept `ParsePosition`?

Key APIs in `java.text` include:

```java
NumberFormat.parse(String source, ParsePosition pos)
DateFormat.parse(String source, ParsePosition pos)
Format.parseObject(String source, ParsePosition pos)
```

Specialized formatters such as `DecimalFormat` and `SimpleDateFormat` inherit/implement these capabilities.

| Call | Return Value | Failure Behavior | Input Consumption Scope |
| --- | --- | --- | --- |
| `NumberFormat.parse(text, pos)` | `Number` or `null` | Usually returns `null`, records error index | May read only a valid prefix |
| `DateFormat.parse(text, pos)` | `Date` or `null` | Usually returns `null`, records error index | May read only a valid prefix |
| `Format.parseObject(text, pos)` | `Object` or `null` | Depends on specific formatter | May read only a valid prefix |
| `NumberFormat.parse(text)` | `Number` | May throw `ParseException` if unparseable from start | **Does not guarantee full text consumption** |

Key takeaway: overloads **without** `ParsePosition` look convenient, but they usually do not expose the stopping position so you can check for a trailing suffix. `ParseException` is not the only indicator of bad data; if the parser reads a valid prefix, it may **throw no exception** even when letters follow at the end.

## 4. Complete Example: Parsing German Numbers and Observing All Three States

Create the file **`ParsePositionNumberDemo.java`**:

```java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParsePosition;
import java.util.Locale;

public class ParsePositionNumberDemo {
    private static DecimalFormat createFormatter() {
        DecimalFormat formatter = new DecimalFormat(
                "#,##0.00",
                DecimalFormatSymbols.getInstance(Locale.GERMANY));
        formatter.setParseBigDecimal(true);
        return formatter;
    }

    private static void check(String input, DecimalFormat formatter) {
        ParsePosition pos = new ParsePosition(0);
        Number value = formatter.parse(input, pos);
        boolean whole = value != null && pos.getIndex() == input.length();

        System.out.printf(
                "input=%s, value=%s, index=%d, error=%d, whole=%s%n",
                input, value, pos.getIndex(), pos.getErrorIndex(), whole);
    }

    public static void main(String[] args) {
        DecimalFormat formatter = createFormatter();

        check("1.234,56", formatter);
        check("1.234,56abc", formatter);
        check("abc", formatter);
        check("12,3", formatter);
    }
}
```

Compile and run with Java 17+:

```bash
javac -encoding UTF-8 ParsePositionNumberDemo.java
java -cp . ParsePositionNumberDemo
```

Output with German symbols on a JDK supporting that locale:

```text
input=1.234,56, value=1234.56, index=8, error=-1, whole=true
input=1.234,56abc, value=1234.56, index=8, error=-1, whole=false
input=abc, value=null, index=0, error=0, whole=false
input=12,3, value=12.3, index=4, error=-1, whole=true
```

**Reading line by line:**

1. `1.234,56` has eight UTF-16 code units; `DecimalFormat` reads all of it and returns `1234.56`.
2. `1.234,56abc` returns the **same value**, but stops at `index=8`, while `input.length()=11`. This is **partial success**.
3. `abc` does not start with a valid number, so `value=null`, `index=0`, and `errorIndex=0` in this example.
4. `12,3` is read completely, even though the pattern specifies two fractional digits. **A two-decimal-digit formatting pattern is not a rule forcing input to have exactly two decimal digits.** If business rules require exact two decimal places, add an extra check.

Calling `formatter.setParseBigDecimal(true)` yields a `BigDecimal` for finite decimal numbers, helping reduce binary floating-point rounding issues in monetary and decimal calculations. That alone does not guarantee the input satisfies all business constraints.

## 5. `index` Is Both the Starting Position and the Ending Position

Parsing does not have to start at index 0. When data has an **allowed prefix** or is embedded inside a larger format, you can start at a non-zero offset.

Example string:

```text
x:1.234,56!
01234567890
  ^       ^
  start=2 end=10
```

File **`ParseFromOffsetDemo.java`**:

```java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParsePosition;
import java.util.Locale;

public class ParseFromOffsetDemo {
    public static void main(String[] args) {
        String source = "x:1.234,56!";
        DecimalFormat formatter = new DecimalFormat(
                "#,##0.00",
                DecimalFormatSymbols.getInstance(Locale.GERMANY));
        formatter.setParseBigDecimal(true);

        ParsePosition position = new ParsePosition(2);
        Number number = formatter.parse(source, position);

        System.out.println("number=" + number);
        System.out.println("start=2");
        System.out.println("end=" + position.getIndex());
        System.out.println("error=" + position.getErrorIndex());
        System.out.println("remaining=" +
                source.substring(position.getIndex()));
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 ParseFromOffsetDemo.java
java -cp . ParseFromOffsetDemo
```

Output:

```text
number=1234.56
start=2
end=10
error=-1
remaining=!
```

Note: `index=10` is an **absolute index in the source string**, not the “number of characters read” starting from index 2. The number of UTF-16 code units consumed is `end - start = 8`. For a whole-string single-value parser starting at 0, the condition is `pos.getIndex() == source.length()`. For parsing a substring segment, the ending condition must compare against the **boundary of the allowed segment**, not necessarily the end of the entire source string.

If the start index is out of bounds for readable content or the character at the start is invalid, inspect the return value and error index; do not assume the parser automatically skips any prefix or whitespace.

## 6. `getErrorIndex()`: Error Position Is Not the Ending Position

When parsing fails, the error index indicates where the parser recorded the failure (according to the formatter's implementation). For example:

```text
input = "abc"
NumberFormat at index 0
→ value = null
→ index = 0
→ errorIndex = 0
```

However, in `input="1.234,56abc"`, Java successfully read a numeric value and stopped at `'a'`. **This is not automatically treated as a formatter error**; it may return `errorIndex=-1` because it recognized a valid numeric prefix. **Only the application knows whether the `abc` suffix is forbidden.**

To display a UI error such as “Invalid character at position X”, a practical rule is:

```java
if (value == null) {
    int errorAt = pos.getErrorIndex();
    // report parse error at errorAt if this value >= 0
} else if (pos.getIndex() < input.length()) {
    int unexpectedAt = pos.getIndex();
    // report trailing data at unexpectedAt
}
```

This snippet assumes `value`, `pos`, and `input` are already declared; it is not a standalone program.

Some parsers report the error index where **they detect** the failure, which may be at the end of the string or after several matched characters, rather than the character position a human perceives as “wrong.” Treat `errorIndex` as **diagnostic information provided by the parser**, not a UI guarantee for highlighting a single grapheme.

## 7. Writing a Function That Accepts a Number Only When the Full String Is Read

If an input field requires a **single number**, check both the return value and the number of characters consumed. The standalone example below returns `Optional<BigDecimal>`.

Create **`StrictNumberInputDemo.java`**:

```java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParsePosition;
import java.util.Locale;
import java.util.Optional;

public class StrictNumberInputDemo {
    private static Optional<BigDecimal> parseWholeGermanNumber(
            String input) {
        if (input == null || input.isEmpty()) {
            return Optional.empty();
        }

        DecimalFormat formatter = new DecimalFormat(
                "#,##0.00",
                DecimalFormatSymbols.getInstance(Locale.GERMANY));
        formatter.setParseBigDecimal(true);

        ParsePosition position = new ParsePosition(0);
        Number parsed = formatter.parse(input, position);

        if (!(parsed instanceof BigDecimal amount)
                || position.getIndex() != input.length()) {
            return Optional.empty();
        }

        return Optional.of(amount);
    }

    public static void main(String[] args) {
        for (String input : new String[] {
                "1.234,56", "1.234,56xyz", "abc", "12,3"
        }) {
            System.out.println(input + " -> " +
                    parseWholeGermanNumber(input)
                            .map(BigDecimal::toPlainString)
                            .orElse("INVALID"));
        }
    }
}
```

Compile and run with JDK 17+:

```bash
javac -encoding UTF-8 StrictNumberInputDemo.java
java -cp . StrictNumberInputDemo
```

Output:

```text
1.234,56 -> 1234.56
1.234,56xyz -> INVALID
abc -> INVALID
12,3 -> 12.3
```

This function accepts `12,3` because the parser read the whole string. If the form requires **exactly two fractional digits**, forbids arbitrary grouping separators, accepts only positive values, or caps the digit count, **add appropriate validation**. `ParsePosition` only tells you **how much the parser read**; it does not enforce the full data standard of your application.

### Should Whitespace Be Allowed?

Decide the policy upfront during design:

- If leading/trailing whitespace is allowed, you can normalize the input **before** parsing. Note that error positions will then refer to the **normalized** string rather than directly mapping to indices in the original string.
- If only an exact format with no leading/trailing whitespace is allowed, do not automatically `trim()` or `strip()` before checking.
- In many locales, the grouping separator can be a **special space** (such as a no-break space or narrow no-break space), not an ASCII space. Avoid replacing all whitespace with plain spaces without understanding the data and requirements.

## 8. Dates: `DateFormat` Can Also Perform Partial Reads

`java.text.DateFormat` and `SimpleDateFormat` also accept `ParsePosition`. There is an additional concern: `31.02.2025` is a **nonexistent date** even though it looks like the pattern `dd.MM.yyyy`. With `SimpleDateFormat`, call `setLenient(false)` to prevent silently rolling invalid dates into another month.

Create **`DateParsePositionDemo.java`**:

```java
import java.text.ParsePosition;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;

public class DateParsePositionDemo {
    private static void check(SimpleDateFormat formatter, String input) {
        ParsePosition position = new ParsePosition(0);
        Date value = formatter.parse(input, position);
        boolean whole = value != null &&
                position.getIndex() == input.length();

        System.out.printf(
                "input=%s, parsed=%s, index=%d, error=%d, whole=%s%n",
                input, value != null, position.getIndex(),
                position.getErrorIndex(), whole);
    }

    public static void main(String[] args) {
        SimpleDateFormat formatter =
                new SimpleDateFormat("dd.MM.yyyy", Locale.GERMANY);
        formatter.setLenient(false);
        formatter.setTimeZone(TimeZone.getTimeZone("UTC"));

        check(formatter, "28.02.2025");
        check(formatter, "28.02.2025tail");
        check(formatter, "31.02.2025");
    }
}
```

Run:

```bash
javac -encoding UTF-8 DateParsePositionDemo.java
java -cp . DateParsePositionDemo
```

Output with the pattern and data in the example:

```text
input=28.02.2025, parsed=true, index=10, error=-1, whole=true
input=28.02.2025tail, parsed=true, index=10, error=-1, whole=false
input=31.02.2025, parsed=false, index=0, error=10, whole=false
```

Look at `28.02.2025tail`: `setLenient(false)` controls the validity of the **date value**, but it **does not mean** the parser must consume the entire string. To verify the whole input, you still need to compare `position.getIndex()` against `input.length()`.

`31.02.2025` is rejected because the date does not exist; in this example, `errorIndex=10` marks where the parser recorded the failure after parsing the date shape. Do not rely on the specific number 10 as a universal rule across all date errors or JDK versions.

The example sets UTC as the time zone to avoid environment dependence when converting the date to `Date`, even though it only prints pass/fail status. For new projects, consider the `java.time` API such as `LocalDate` and `DateTimeFormatter` when working with calendar dates.

## 9. Differences Between `java.text` and `java.time` APIs

In Java 8+, `DateTimeFormatter` in `java.time.format` also has an overload:

```java
TemporalAccessor parse(CharSequence text, ParsePosition position)
```

However, **do not assume** `DateTimeFormatter`'s error reporting works identically to `NumberFormat.parse(text, position)`. `java.time` separates parsing into temporal fields from **resolving** those fields into a valid date/time; an error during resolution can throw `DateTimeParseException` even when `ParsePosition` has advanced to the end of the string.

Example:

```java
DateTimeFormatter formatter = DateTimeFormatter
        .ofPattern("uuuu-MM-dd")
        .withResolverStyle(ResolverStyle.STRICT);

ParsePosition position = new ParsePosition(0);
TemporalAccessor parsed =
        formatter.parse("2025-02-28tail", position);
LocalDate date = LocalDate.from(parsed);
```

This is a **snippet** requiring imports for `java.text.ParsePosition`, `java.time.LocalDate`, `java.time.format.DateTimeFormatter`, `java.time.format.ResolverStyle`, and `java.time.temporal.TemporalAccessor`. It illustrates partial reading and converting `TemporalAccessor` to `LocalDate`.

If the input is `2025-02-31`, the `STRICT` resolver cannot produce a valid date and may throw `DateTimeParseException`. Therefore:

- With `java.text.NumberFormat` or `DateFormat`, check `null`, `index`, and `errorIndex` according to each API's contract.
- With `java.time.DateTimeFormatter`, handle **exceptions** thrown during parsing/resolving, and treat `ParsePosition` as positional metadata for the parse operation.
- For an input string expected to be **one complete date**, `LocalDate.parse(text, formatter)` is usually simpler and more direct than the `ParsePosition` overload; it requires matching the full string within its parse contract and signals errors via exceptions.

**Do not mix `DateTimeFormatter` and `SimpleDateFormat` as if both classes shared the same pattern rules and error handling.** They belong to two different API families, especially regarding resolvers and date/time types.

## 10. Subtle Pitfalls When Using `ParsePosition`

### 10.1. Reusing `ParsePosition` Without Resetting

`ParsePosition` is stateful. If after one parse `index` is 8 and you pass the same object to parse another string, the parser will **start at position 8** instead of automatically resetting to 0.

Similarly, `errorIndex` can retain stale information if you reuse the object and the formatter does not reset it the way you expect. A successful parse carries no universal contract that every method resets `errorIndex` to `-1`.

The safest approach for independent input fields:

```java
ParsePosition pos = new ParsePosition(0);
Number value = formatter.parse(input, pos);
```

Create a **new instance for each check**. If reuse is truly necessary, reset both `setIndex(start)` and `setErrorIndex(-1)`, and understand exactly how the parser interacts with the object.

### 10.2. Mistaking `errorIndex == -1` for Full Parsing

`input="1.234,56abc"` demonstrated this clearly: `value != null`, `errorIndex == -1`, yet `index == 8` in a length-11 string. If business rules require the entire string to be a number, that is a **trailing data** error that Java does not necessarily treat as a syntax error in the parsed portion.

### 10.3. Checking Only `index > 0`

If you started at index 5, `index > 0` does not tell you whether the parser read any additional characters. Check `value != null` and compare start/end indices against the expected bounds.

### 10.4. Ignoring Unicode

`ParsePosition` counts indices in UTF-16 code units. For example, a string with a leading emoji has a larger `String.length()` than its code point count. When displaying an error position to users—especially when highlighting a selection in the UI—map the index to the UI's representation and avoid splitting inside a surrogate pair.

### 10.5. Assuming `DecimalFormat` Patterns Validate Input Shape

A pattern like `#,##0.00` is primarily for formatting; the fact that the parser accepts `12,3` proves it does not enforce two fractional digits. Grouping rules can also be lenient depending on the formatter. Never take parser success as proof that input satisfies all requirements for grouping separators, digit counts, signs, value limits, or accounting data standards.

### 10.6. Treating Locale Parsing Like Protocol Data Parsing

Machine-to-machine data (JSON APIs, IDs, ISO codes, interchange files) typically uses a **dedicated canonical format** independent of UI language. Never implicitly use `Locale.getDefault()` to parse machine-to-machine fields. Distinguish:

- **User input:** may require `NumberFormat` / `DateFormat` / `DateTimeFormatter` per locale and product policy.
- **Protocol input:** use a protocol-compliant parser without letting grouping or decimal separators vary with UI preferences.
- **Critical business data:** beyond valid syntax, validate value range, precision, rounding, currency/timezone, unit, and safety limits.

### 10.7. Sharing Mutable Formatters Across Threads

`DecimalFormat` and `SimpleDateFormat` are mutable objects and are not thread-safe for concurrent sharing by default. `ParsePosition` is also mutable; do not share one instance across concurrent parse operations. Use separate instances or proper synchronization. With `java.time.DateTimeFormatter`, the formatter itself is immutable and designed to be safely shared.

## 11. Designing an Input Validator That Reports Error Positions

A practical validator should distinguish at least three outcome types:

| Status | Example | Information to Report |
| --- | --- | --- |
| `VALID` | `1.234,56` | Parsed value; domain range policies still apply |
| `PARSE_ERROR` | `abc` | Error position from `getErrorIndex()` if available |
| `TRAILING_INPUT` | `1.234,56abc` | Start of trailing data from `getIndex()` |

For a form accepting a single numeric value, the core logic can be:

```text
parse(input, new ParsePosition(0))
         |
         +-- value == null --------> PARSE_ERROR
         |                           position = errorIndex (if available)
         |
         +-- index != input.length()
         |                       ---> TRAILING_INPUT
         |                           position = index
         |
         +-- full value read ------> Business validation
                                     (min/max, scale, sign, ...)
                                     then VALID
```

Do not expose raw parser errors wholesale to end users; UI errors should provide locale-appropriate guidance, such as “Enter a number with a decimal comma” when the language/region uses a comma. When `errorIndex < 0` on a failed parse, use a general message or highlight the entire field; do not fabricate an error position.

Before highlighting a substring, always check bounds `0 <= position <= input.length()` prior to calling `substring`, especially when indices come from different parsers or are adjusted in code.

## 12. Minimum Tests You Should Have

To ensure a validator is both locale-accurate and catches trailing suffixes:

1. **Fully valid string:** for German number `1.234,56`, expect `value != null` and `index == length`.
2. **String with suffix:** `1.234,56abc` may parse a number, but must be rejected if the field requires a whole number.
3. **Failure at start:** `abc` → `null`, with an error index reported by the parser.
4. **Non-zero start position:** verify that the final `index` is an absolute index.
5. **Empty/null strings:** required/optional input policies must be explicit; do not pass `null` to parsers that reject it.
6. **Whitespace and Unicode separators:** test actual grouping separators and whitespace policies.
7. **Valid date with suffix:** `28.02.2025tail` must be rejected by a whole-string validator.
8. **Nonexistent date:** `31.02.2025` must be rejected under strict parsing.
9. **Distinguishing parser success from business contract:** `12,3` can parse completely yet fail a field requiring exactly two fractional digits.
10. **Huge or high-precision values:** verify returned `Number` type, `BigDecimal`, scale, and business limits.
11. **Object reuse:** verify no stale `index` or `errorIndex` leaks from prior parses.
12. **Multi-locale and multi-runtime:** compare US, Germany, Vietnam, and actual target deployment locales; locale data in JDK/CLDR can change between versions.

## 13. Distinguishing `ParsePosition`, `FieldPosition`, and `ParseException`

Three similar names that are easily confused:

- **`ParsePosition`**: used in **parsing** to track starting position, ending position, and error position; does not throw an exception merely because trailing characters exist.
- **`FieldPosition`**: typically used in **formatting** to locate a specific field within the output string, such as the integer part; does not replace `ParsePosition`.
- **`ParseException`**: some parse overloads report errors via exception with `getErrorOffset()`, though you still must check whether that API enforces full input consumption.

Do not pick among the three just because they contain “Position” or “Parse.” If your application needs to report **where trailing data begins in a number** and retain control over whole-string acceptance, `ParsePosition` is the direct tool.

## 14. Key Takeaways

- **`ParsePosition.getIndex()`** is the position immediately after the input portion successfully consumed by the parser, not necessarily the end of the string.
- **`getErrorIndex()`** indicates the error position recorded by the parser; `-1` **does not mean** no trailing data remains.
- When requiring **a single value spanning the entire input**, verify **a non-`null` return value and `getIndex() == input.length()`**; then still run business validation.
- When parsing from an offset, `index` is an **absolute index in the source string**; Java string indices count **UTF-16** code units, not bytes.
- **Create a fresh `ParsePosition`** for each independent parse to avoid stale `index`/`errorIndex` state.
- For dates, you must also enforce **calendar validity** (`setLenient(false)` or a strict resolver), not just the ending position.
- In `java.time`, resolution steps can throw `DateTimeParseException`; do not assume every parse API shares the same error contract as `java.text.NumberFormat`.
