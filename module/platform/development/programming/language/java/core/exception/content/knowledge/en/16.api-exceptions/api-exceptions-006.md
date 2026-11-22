# ParseException, DateTimeParseException, and Data Parsing Context in Java

Data entering a Java program is often **unvalidated text**: birth dates from forms, delivery dates in CSVs, timestamps in URLs, locale-grouped numbers, or data from legacy systems. Converting text into a typed object is called **parsing**. When a string does not match the format or cannot produce a valid value, the parser API reports an error. Two exception names that are very easy to confuse are **java.text.ParseException** and **java.time.format.DateTimeParseException**.

Key points:

- **ParseException** belongs to **java.text** and is a **checked exception** (inherits directly from Exception). Many legacy APIs such as **SimpleDateFormat.parse(String)** and **NumberFormat.parse(String)** declare it in their signature with **throws ParseException**.
- **DateTimeParseException** belongs to **java.time.format** and is an **unchecked exception** (inherits from DateTimeException → RuntimeException). Modern APIs such as **LocalDate.parse** and **DateTimeFormatter.parse** can throw it when they cannot read or resolve temporal data.
- Both can attach information about the **error position**, but **ParseException.getErrorOffset()** and **DateTimeParseException.getErrorIndex()** are not the same "business error codes". DateTimeParseException also retains the parsed string via **getParsedString()**.
- **Matching the character pattern alone is not enough** to guarantee that a date exists, that the entire string was consumed, that the value has the right time zone, or that it satisfies the requirements of an input field.
- When conversion APIs have different checked/unchecked policies, the handling layer must catch the right exception, add **input field context**, preserve the **cause** if wrapping the error, and avoid exposing sensitive text in user-facing messages.

This article targets **Java 17+**, covering mechanisms, API choices, strict/smart/lenient modes, error positions, ParsePosition, time and locale, along with standalone examples including compile commands and stdout results.

## 1. Hierarchy and Checked/Unchecked Differences

Diagram:

~~~text
java.lang.Throwable
  └── java.lang.Exception
       ├── java.text.ParseException                  [checked]
       └── java.lang.RuntimeException
            └── java.time.DateTimeException
                 └── java.time.format.DateTimeParseException [unchecked]
~~~

The two exceptions do not have a direct parent–child relationship and cannot be replaced by a single specific catch branch.

| Criterion | ParseException | DateTimeParseException |
| --- | --- | --- |
| Package | java.text | java.time.format |
| Checked or unchecked? | Checked | Unchecked |
| Direct superclass | Exception | DateTimeException |
| Typical APIs | SimpleDateFormat.parse(String), NumberFormat.parse(String) | LocalDate.parse, LocalDateTime.parse, DateTimeFormatter.parse |
| Position information | getErrorOffset() | getErrorIndex() |
| Retains raw input text? | No dedicated getter to retrieve the full string | getParsedString() |
| Handling at call site | Catch or declare throws ParseException | Not enforced by compiler, but should be handled at the input boundary |
| Common result types | java.util.Date, Number | LocalDate, LocalDateTime, OffsetDateTime, ZonedDateTime, TemporalAccessor |

**Do not assume all parsers throw the same exception.** Integer.parseInt("bad") throws **NumberFormatException**, which is also unchecked, rather than ParseException. JSON, XML, or CSV libraries may have their own exceptions. You must inspect the **actual method signature** instead of guessing based on the fact that an API is "parsing a string".

### Why does this distinction matter?

With a method using the java.text API:

~~~java
static java.util.Date readLegacy(String text)
        throws java.text.ParseException {
    java.text.SimpleDateFormat format =
            new java.text.SimpleDateFormat("dd/MM/yyyy");
    return format.parse(text);
}
~~~

This is an illustrative method, not a program with main. Because ParseException is checked, the caller must catch or declare it appropriately.

With java.time:

~~~java
static java.time.LocalDate readModern(String text) {
    return java.time.LocalDate.parse(text);
}
~~~

This method does not need to declare throws DateTimeParseException. However, if reading text from a user, the application still must decide how to return an input error instead of letting an unchecked exception crash an unhandled request.

## 2. What Does ParseException in java.text Represent?

The constructor signature of java.text.ParseException:

~~~java
public ParseException(String message, int errorOffset)
~~~

Useful information:

- **getMessage()**: a descriptive string provided by the parser or the code creating the exception; there is no unified error-code structure across all parsers.
- **getErrorOffset()**: the error position determined by the detector. You should not assume every parser always provides an exact index for the underlying root cause.
- **getCause()**: the standard Throwable mechanism if a cause is linked; the ParseException constructor does not have a dedicated (String, Throwable) overload, but **initCause** can be used when linking a cause is genuinely needed and the cause has not been initialized yet.

Example of an internal parser creating a ParseException itself:

~~~java
throw new java.text.ParseException("Invalid token", 4);
~~~

This is a snippet that can live inside a method declaring throws ParseException. When caught, **getErrorOffset()** returns 4 because the program itself set this offset.

Do not assume **getErrorOffset()** is a line number in a file or a column number in a UI. It is a position provided by the parser within its own text context. When the data is a multi-line CSV, the application needs to track the **line number**, **column name**, **original value**, and the rule for translating from a character position to a user-understandable position.

## 3. Java 17+ Program: Catching Checked ParseException

Save as **LegacyParseDemo.java**:

~~~java
import java.text.ParseException;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

public class LegacyParseDemo {
    static Date parseLegacy(String text) throws ParseException {
        SimpleDateFormat format =
                new SimpleDateFormat("dd/MM/yyyy", Locale.ROOT);
        format.setLenient(false);
        return format.parse(text);
    }

    public static void main(String[] args) {
        try {
            Date date = parseLegacy("19/10/2026");
            SimpleDateFormat output =
                    new SimpleDateFormat("dd/MM/yyyy", Locale.ROOT);
            output.setLenient(false);
            System.out.println("valid=" + output.format(date));
        } catch (ParseException ex) {
            System.out.println("unexpected parse failure");
        }

        try {
            parseLegacy("31/02/2026");
        } catch (ParseException ex) {
            System.out.println("invalid="
                    + ex.getClass().getSimpleName());
            System.out.println("offsetNonNegative="
                    + (ex.getErrorOffset() >= 0));
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 LegacyParseDemo.java
java LegacyParseDemo
~~~

Output in a typical Java 17+ environment:

~~~text
valid=19/10/2026
invalid=ParseException
offsetNonNegative=true
~~~

Key takeaways:

1. **setLenient(false)** makes SimpleDateFormat reject nonexistent dates such as February 31. Merely matching the digit count to the pattern cannot turn that date into a valid calendar value.
2. **parseLegacy** declares **throws ParseException**. The main program catches this checked exception.
3. When an error occurs, the code only prints whether the offset is non-negative, avoiding reliance on a specific parser index value for different invalid inputs.
4. To make the date output easy to verify, the program formats the Date back into the same pattern rather than printing Date.toString(), which is affected by the display time zone.

**Major limitation:** setLenient(false) controls how date fields are interpreted, but it **does not automatically guarantee** that every character of the input was consumed.

## 4. Prefix Parsing Trap in Legacy APIs

Parsers in java.text often allow parsing a **valid leading portion** of a string. For example, **SimpleDateFormat.parse(String)** can accept a date string at the beginning and leave behind a suffix that does not belong to the pattern. Similarly, NumberFormat.parse(String) can produce a Number from a valid prefix.

To control input consumption, use **java.text.ParsePosition**:

~~~java
ParsePosition position = new ParsePosition(0);
Date date = format.parse(raw, position);

boolean full = date != null
        && position.getIndex() == raw.length();
~~~

The snippet above sits inside a method with a valid **format** and **raw**. Unlike **parse(String)** which throws a checked ParseException, the **parse(String, ParsePosition)** overload of SimpleDateFormat signals failure by returning **null** and updating position information.

### Java 17+ Program: Detecting Trailing Suffixes

Save as **LegacyPositionDemo.java**:

~~~java
import java.text.ParsePosition;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

public class LegacyPositionDemo {
    static SimpleDateFormat formatter() {
        SimpleDateFormat result =
                new SimpleDateFormat("dd/MM/yyyy", Locale.ROOT);
        result.setLenient(false);
        return result;
    }

    public static void main(String[] args) {
        SimpleDateFormat format = formatter();
        String raw = "19/10/2026tail";

        ParsePosition position = new ParsePosition(0);
        Date parsed = format.parse(raw, position);

        System.out.println("parsed=" + (parsed != null));
        System.out.println("consumed=" + position.getIndex());
        System.out.println("whole="
                + (parsed != null
                   && position.getIndex() == raw.length()));

        ParsePosition invalidPosition = new ParsePosition(0);
        Date invalid = format.parse("31/02/2026", invalidPosition);
        System.out.println("invalid=" + (invalid == null));
        System.out.println("hasErrorIndex="
                + (invalidPosition.getErrorIndex() >= 0));
    }
}
~~~

~~~bash
javac -encoding UTF-8 LegacyPositionDemo.java
java LegacyPositionDemo
~~~

Output:

~~~text
parsed=true
consumed=10
whole=false
invalid=true
hasErrorIndex=true
~~~

The string **19/10/2026tail** has ten characters forming a date at the start. The parser obtains a Date, but **position.getIndex() == 10**, which is less than the length of the entire string. Therefore, an input field whose contract **requires a full-string match** must be rejected.

ParsePosition has two state fields to distinguish:

- **getIndex()**: the position after the last successfully parsed character.
- **getErrorIndex()**: the position where the parser reports an error on failure, typically -1 if no error has been recorded.

Do not use **parsed != null** as proof that the entire input is valid. Do not treat the ParsePosition index as a line or column number; if the source file has multiple lines, the application must attach data coordinates itself.

## 5. DateTimeParseException in java.time

The modern JDK provides the **java.time** library, with clearly separated data types:

- **LocalDate**: an ISO calendar date, without time of day or time zone.
- **LocalTime**: a time of day, without date or time zone.
- **LocalDateTime**: a local date + time, without an offset or time zone.
- **OffsetDateTime**: a date-time with a specific offset.
- **ZonedDateTime**: a date-time associated with a time-zone region via ZoneId.
- **Instant**: a point on the timeline.

**DateTimeParseException** is thrown when a date-time parse operation cannot process the input string according to the formatter and requested target type. This exception inherits from DateTimeException and is therefore unchecked.

API for reading diagnostic information:

~~~java
String originalText = ex.getParsedString();
int errorAt = ex.getErrorIndex();
String description = ex.getMessage();
~~~

These are illustrative expressions when **ex** has type DateTimeParseException. **getParsedString()** may contain the raw input data verbatim; when the string holds sensitive values, do not write the entire string to public logs. **getErrorIndex()** helps identify the position, but it is not a business error code or a guarantee of the exact root-cause character across all parsing stages.

### Java 17+ Program: DateTimeParseException Output

Save as **ModernDateParseDemo.java**:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeParseException;

public class ModernDateParseDemo {
    static void inspect(String raw) {
        try {
            LocalDate date = LocalDate.parse(raw);
            System.out.println("ok=" + date);
        } catch (DateTimeParseException ex) {
            System.out.println("bad=" + ex.getParsedString());
            System.out.println("type="
                    + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        inspect("2026-10-19");
        inspect("2026-02-30");
    }
}
~~~

~~~bash
javac -encoding UTF-8 ModernDateParseDemo.java
java ModernDateParseDemo
~~~

Output:

~~~text
ok=2026-10-19
bad=2026-02-30
type=DateTimeParseException
~~~

**2026-02-30** has character components matching the ISO yyyy-MM-dd format, but February 30 does not exist. **DateTimeFormatter.ISO_LOCAL_DATE** uses strict resolution; failing to construct a valid LocalDate results in a DateTimeParseException.

Do not hardcode an assumed value of **getErrorIndex()** for invalid calendar date errors: the index during the date-field resolution stage can differ from the index of a pure character syntax error. Here we print parsedString to verify the link to the input; in production, only log this value when data policy permits.

## 6. Syntax Errors and Date Resolution Errors Are Two Different Stages

DateTimeFormatter describes the parsing process in two major steps:

1. **Text parsing**: reading characters according to the pattern/formatter to extract field values such as YEAR, MONTH_OF_YEAR, and DAY_OF_MONTH.
2. **Resolving**: combining those field values into a meaningful date/time, checking consistency and calendar rules.

Therefore:

| String / Error | Issue |
| --- | --- |
| "2026/10/19" with ISO_LOCAL_DATE | Wrong separator character during the text-reading stage |
| "2026-13-19" | Month is outside the allowed range |
| "2026-02-30" | Syntax looks valid, but the date does not exist |
| "2026-10-19extra" | Valid prefix but trailing suffix; full-string parse methods reject it |
| "2026-10-19" | Valid ISO date |
| "2024-02-29" | Valid leap-year date |

The error message of DateTimeParseException often distinguishes "could not be parsed at index..." from "could not be parsed: ...", but **applications should not reverse-parse the message string** to decide which error occurred. Determine the validation policy using the formatter, target type, and dedicated validation logic.

### Java 17+ Program: Checking the Position of Trailing Characters

Save as **TrailingTextDemo.java**:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeParseException;

public class TrailingTextDemo {
    public static void main(String[] args) {
        String raw = "2026-10-19extra";

        try {
            LocalDate.parse(raw);
        } catch (DateTimeParseException ex) {
            System.out.println("sameText="
                    + raw.equals(ex.getParsedString()));
            System.out.println("errorAt="
                    + ex.getErrorIndex());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 TrailingTextDemo.java
java TrailingTextDemo
~~~

Output:

~~~text
sameText=true
errorAt=10
~~~

With ten characters forming the ISO date at the start, the first unconsumed character is at index 10 in Java's 0-based string indexing. This is a specific syntax error case with a deterministic result; do not generalize that non-leap-day errors or resolver errors will always have the same index.

Default parsers like **LocalDate.parse(text)** expect the **entire text** to match the format. If you intentionally want to parse a segment of a larger text, java.time provides an overload with ParsePosition for advanced processing, but you must manage positions and boundaries yourself.

## 7. ResolverStyle: STRICT, SMART, LENIENT

**java.time.format.ResolverStyle** determines how parsed date/time fields are resolved:

| Style | Meaning | On nonexistent dates |
| --- | --- | --- |
| STRICT | Requires fields to be valid according to the calendar/type | Rejects |
| SMART | Adjusts certain values that can be reasonably inferred | May clamp to the end of the month |
| LENIENT | Allows flexible resolution, potentially rolling across months/days | May roll over into another month/day |

**DateTimeFormatter.ofPattern(...)** defaults to **ResolverStyle.SMART**, whereas predefined ISO formatters such as **ISO_LOCAL_DATE** use appropriate strict rules. If the data must adhere strictly to the calendar, **explicitly choose STRICT**.

One common point of confusion is the year symbol:

- **u / uuuu**: proleptic year; suitable when strictly parsing LocalDate in the ISO calendar.
- **y / yyyy**: year-of-era. In strict parsing, having only year-of-era without an era may be insufficient to construct a LocalDate.

Therefore, when defining a strict custom formatter for **dd/MM/yyyy** with the usual ISO calendar year meaning, using **dd/MM/uuuu** is generally clearer.

### Java 17+ Program: SMART Can Adjust Dates, STRICT Rejects Them

Save as **ResolverStyleDemo.java**:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;

public class ResolverStyleDemo {
    public static void main(String[] args) {
        DateTimeFormatter smart =
                DateTimeFormatter.ofPattern("dd/MM/uuuu", Locale.ROOT);
        DateTimeFormatter strict =
                smart.withResolverStyle(ResolverStyle.STRICT);

        System.out.println("smart="
                + LocalDate.parse("29/02/2023", smart));
        System.out.println("leap="
                + LocalDate.parse("29/02/2024", strict));

        try {
            LocalDate.parse("29/02/2023", strict);
        } catch (DateTimeParseException ex) {
            System.out.println("strict=invalid-date");
        }

        DateTimeFormatter strictYearOfEra =
                DateTimeFormatter.ofPattern("dd/MM/yyyy", Locale.ROOT)
                        .withResolverStyle(ResolverStyle.STRICT);
        try {
            LocalDate.parse("19/10/2026", strictYearOfEra);
        } catch (DateTimeParseException ex) {
            System.out.println("year-of-era=unresolved");
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ResolverStyleDemo.java
java ResolverStyleDemo
~~~

Output:

~~~text
smart=2023-02-28
leap=2024-02-29
strict=invalid-date
year-of-era=unresolved
~~~

Crucial point: with a SMART formatter, **29/02/2023** can be resolved to **2023-02-28**. If an application accepts birth dates, payment due dates, or audit timestamps, such silent adjustment may be inappropriate. Choose **ResolverStyle.STRICT** and test end-of-month and leap-year dates.

Do not mistakenly assume that switching from SimpleDateFormat to DateTimeFormatter means **every java.time formatter is always strict**. You must check the actual resolver style of the formatter.

## 8. Comparing Legacy API Lenient Mode and Modern API ResolverStyle

**SimpleDateFormat** has **setLenient(boolean)**, which controls the Calendar used to resolve date fields. By default, the legacy mechanism is typically lenient: a nonexistent value can be normalized into another date. When a valid calendar date is required, call **setLenient(false)**.

**DateTimeFormatter** is immutable and configured with **withResolverStyle(ResolverStyle.STRICT)** to create a new formatter without modifying the old one. For the ISO calendar, STRICT ensures that fields do not produce nonexistent dates; SMART may adjust end-of-month dates.

However, the two concepts are **not completely identical**. Pattern syntax, number parsing, locale support, and time handling differ between the two APIs. Do not mechanically port a pattern from SimpleDateFormat to DateTimeFormatter expecting every pattern letter to have the exact same meaning.

Particularly important differences:

| Aspect | java.text.SimpleDateFormat | java.time.DateTimeFormatter |
| --- | --- | --- |
| Strict configuration | setLenient(false) | withResolverStyle(STRICT) |
| Mutability | Mutable | Immutable |
| Sharing across threads | Do not share a mutable instance without synchronization | Formatter is designed to be immutable and thread-safe |
| Result type | java.util.Date | Typically LocalDate/LocalDateTime/TemporalAccessor |
| Typical parse(String) error | Checked ParseException | Unchecked DateTimeParseException |
| Full string | parse(String) may accept a prefix | Standard LocalDate.parse/DateTimeFormatter.parse requires a full-string match |
| Advanced parse position | ParsePosition, typically returns null on error | ParsePosition API has overload-specific error behavior |

When maintaining legacy systems, you can keep SimpleDateFormat at the compatibility boundary; for new APIs, java.time generally models date/time better and avoids sharing unsafe mutable objects across threads.

## 9. Locale and Textual Month Symbols

Date formats using month abbreviations depend on Locale. With DateTimeFormatter, specifying Locale explicitly avoids depending on the default language of the host machine.

Save as **LocaleDateDemo.java**:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;

public class LocaleDateDemo {
    public static void main(String[] args) {
        DateTimeFormatter english =
                DateTimeFormatter.ofPattern("dd MMM uuuu", Locale.ENGLISH)
                        .withResolverStyle(ResolverStyle.STRICT);

        LocalDate date = LocalDate.parse("19 Oct 2026", english);
        System.out.println("date=" + date);

        try {
            LocalDate.parse("19 Foo 2026", english);
        } catch (DateTimeParseException ex) {
            System.out.println("unknown-month=invalid");
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 LocaleDateDemo.java
java LocaleDateDemo
~~~

Output:

~~~text
date=2026-10-19
unknown-month=invalid
~~~

For standard data exchange between systems, an ISO format like **2026-10-19** is usually more convenient than locale-dependent textual month strings. If the UI requires the user's language, use an explicit Locale and test with actual localized representations.

Also distinguish **Locale** from **ZoneId**. Locale primarily affects language/formatting conventions; it **does not automatically attach a time zone** to LocalDate or LocalDateTime. If the string contains an offset or time zone, use the appropriate target type.

## 10. Choosing the Right Target Type: Date, Local Date-Time, or Instant

A string **2026-10-19** describes only a date, giving no time of day or time zone. Thus **LocalDate.parse** is appropriate.

Conversely:

- **2026-10-19T14:30:00** has a date and time without an offset: typically **LocalDateTime**.
- **2026-10-19T14:30:00+07:00** has an offset: typically **OffsetDateTime**.
- **2026-10-19T07:30:00Z** represents a UTC instant and can be parsed with **Instant.parse**.
- A string with a time-zone region such as **[Asia/Ho_Chi_Minh]** needs a formatter and type that support zones if the format includes that part.

Do not take a LocalDateTime and treat it as an **Instant** without business-valid offset/zone information. Missing temporal context can lead to **syntactically valid date-times that represent the wrong actual point in time**, even though no DateTimeParseException occurs.

### Java 17+ Program: Same Instant, Two Representations

Save as **TemporalTypeDemo.java**:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;

public class TemporalTypeDemo {
    public static void main(String[] args) {
        System.out.println("date="
                + LocalDate.parse("2026-10-19"));
        System.out.println("local="
                + LocalDateTime.parse("2026-10-19T14:30:00"));
        System.out.println("offset="
                + OffsetDateTime.parse(
                        "2026-10-19T14:30:00+07:00").toInstant());
        System.out.println("instant="
                + Instant.parse("2026-10-19T07:30:00Z"));
    }
}
~~~

~~~bash
javac -encoding UTF-8 TemporalTypeDemo.java
java TemporalTypeDemo
~~~

Output:

~~~text
date=2026-10-19
local=2026-10-19T14:30
offset=2026-10-19T07:30:00Z
instant=2026-10-19T07:30:00Z
~~~

LocalDateTime.toString() omits seconds when they are 0 in this example, so **local=2026-10-19T14:30**. The last two lines express the same Instant: offset +07:00 at 14:30 corresponds to 07:30 UTC. Do not turn **LocalDateTime** into a global point in time without zone information.

## 11. NumberFormat.parse(String) Also Uses Checked ParseException

ParseException does not appear only when reading dates. Locale-aware number parsers such as **NumberFormat.parse(String)** also declare checked ParseException. This is a notable difference from **Integer.parseInt(String)**, which throws unchecked NumberFormatException.

Example using Locale.GERMANY to parse **1.234,5** according to grouping and decimal separator conventions:

Save as **LegacyNumberParseDemo.java**:

~~~java
import java.text.NumberFormat;
import java.text.ParseException;
import java.text.ParsePosition;
import java.util.Locale;

public class LegacyNumberParseDemo {
    public static void main(String[] args) {
        NumberFormat formatter =
                NumberFormat.getNumberInstance(Locale.GERMANY);

        try {
            Number value = formatter.parse("1.234,5");
            System.out.println("number=" + value.doubleValue());
        } catch (ParseException ex) {
            System.out.println("unexpected-invalid");
        }

        try {
            formatter.parse("not-a-number");
        } catch (ParseException ex) {
            System.out.println("invalid=ParseException");
        }

        String partial = "1.234,5tail";
        ParsePosition position = new ParsePosition(0);
        Number parsed = formatter.parse(partial, position);
        System.out.println("hasNumber=" + (parsed != null));
        System.out.println("consumed=" + position.getIndex());
        System.out.println("whole="
                + (parsed != null
                   && position.getIndex() == partial.length()));
    }
}
~~~

~~~bash
javac -encoding UTF-8 LegacyNumberParseDemo.java
java LegacyNumberParseDemo
~~~

Output with standard locale data:

~~~text
number=1234.5
invalid=ParseException
hasNumber=true
consumed=7
whole=false
~~~

**NumberFormat.parse(String)** can accept a valid prefix, so to check the entire string, use ParsePosition or a stricter validation layer. For monetary data requiring exact decimal precision, consider DecimalFormat configured with **setParseBigDecimal(true)** and an appropriate scale policy instead of converting to double by default.

**The difference is not that a checked exception is "stricter" in a business sense.** Checked/unchecked is a language-level policy at the call site; a parser can still be permissive with prefixes or values even when it declares a checked exception.

## 12. ParsePosition Differs Between java.text and java.time

**java.text.Format** has several parse overloads with ParsePosition. For instance, **SimpleDateFormat.parse(String, ParsePosition)** typically returns **null** when the parser cannot read the input and updates **getErrorIndex()**. The caller must check for null and inspect the consumed index.

In **DateTimeFormatter.parse(CharSequence, ParsePosition)**, the JDK documentation states that **DateTimeParseException** can be thrown on a parse error, rather than encoding every error as null like some java.text formatters. There is also **parseUnresolved(...)** for handling the unresolved-field parsing stage, with its own usage and error-checking rules.

Therefore, do not generalize:

~~~java
// DO NOT APPLY BLINDLY TO EVERY PARSER:
Object result = parser.parse(text, position);
if (result == null) {
    // assume all parsing errors arrive here
}
~~~

This is only **illustrative pseudocode**. Read the contract of the specific overload: return type, checked/unchecked exceptions, ParsePosition updates, and whether full-string checking is needed.

For most applications that need a complete LocalDate, use **LocalDate.parse(text, formatter)** and validate the input before/after parsing instead of manually calling parseUnresolved.

## 13. Translating Exceptions into Contextual Errors at the API Boundary

An API layer should not expose raw parser messages to users if the input may contain tokens, personal data, very long content, or unsuitable representations. The application layer knows the **field name**, **required format**, and **error code**. It can translate library exceptions into domain-specific exceptions or error objects.

For example, an invoice entry flow expects an **invoiceDate** field in ISO format. Use a custom unchecked error type to report validation failure, while **preserving the cause** so technical loggers can still trace the DateTimeParseException.

Save as **InputContextDemo.java**:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeParseException;

public class InputContextDemo {
    static class InvalidFieldException extends IllegalArgumentException {
        private final String field;

        InvalidFieldException(
                String field, String message, Throwable cause) {
            super(message, cause);
            this.field = field;
        }

        String field() {
            return field;
        }
    }

    static LocalDate invoiceDate(String raw) {
        if (raw == null || raw.isBlank()) {
            throw new InvalidFieldException(
                    "invoiceDate", "date is required", null);
        }

        try {
            return LocalDate.parse(raw);
        } catch (DateTimeParseException ex) {
            throw new InvalidFieldException(
                    "invoiceDate", "date must be yyyy-MM-dd", ex);
        }
    }

    public static void main(String[] args) {
        System.out.println("valid="
                + invoiceDate("2026-10-19"));

        try {
            invoiceDate("19/10/2026");
        } catch (InvalidFieldException ex) {
            System.out.println("field=" + ex.field());
            System.out.println("message=" + ex.getMessage());
            System.out.println("causeType="
                    + ex.getCause().getClass().getSimpleName());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 InputContextDemo.java
java InputContextDemo
~~~

Output:

~~~text
valid=2026-10-19
field=invoiceDate
message=date must be yyyy-MM-dd
causeType=DateTimeParseException
~~~

In the example, **LocalDate.parse** is kept inside a small try block: an unrelated DateTimeParseException from outside logic will not be misattributed as an invoiceDate field error. The wrapper can carry a strongly typed **field** property; the frontend does not need to parse the message to identify which field failed.

If using checked ParseException in a legacy layer, you can wrap it in a custom checked domain exception that **extends Exception**, or translate it at the API boundary when that matches the module's contract. Do not wrap every checked exception into a RuntimeException without considering recoverability.

## 14. Checked ParseException and Preserving Cause When Wrapping into a Domain Exception

A business exception class can be checked:

~~~java
class ImportDateException extends Exception {
    ImportDateException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

This is a valid class declaration without main. If a legacy import step throws ParseException:

~~~java
try {
    return legacyFormatter.parse(raw);
} catch (java.text.ParseException ex) {
    throw new ImportDateException(
            "Invalid import date in column invoiceDate", ex);
}
~~~

This is an illustrative snippet inside a method returning **java.util.Date** and declaring **throws ImportDateException**, with **legacyFormatter** and **raw** already defined.

Information retained after translation:

- **ImportDateException.getMessage()** expresses the context of the import step.
- **getCause()** preserves the original ParseException object; you can inspect **getErrorOffset()** after appropriately casting the cause.
- The cause's stack trace still helps locate where the legacy parser detected the error.
- The wrapper has its own stack trace at the translation point; there is no need to call **setStackTrace()** to "stitch" frames together.

**Do not merely create** a new exception with the original error's message. Doing so severs the causal chain and makes diagnostics harder. At the same time, do not assume **getCause()** is always non-null in all situations; check before accessing it if the wrapper can be constructed without a cause.

## 15. Batch Record Import: Recording Error State Per Row

A CSV file containing many dates may require reporting every invalid row instead of stopping at the first error. When each row is independent, a parse exception can be converted into a result object containing a code and context.

Save as **DateBatchDemo.java**:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeParseException;
import java.util.List;

public class DateBatchDemo {
    record RowResult(int row, LocalDate value, String error) {
        boolean valid() {
            return error == null;
        }
    }

    static RowResult parseRow(int row, String raw) {
        try {
            return new RowResult(row, LocalDate.parse(raw), null);
        } catch (DateTimeParseException ex) {
            return new RowResult(row, null, "INVALID_DATE");
        }
    }

    public static void main(String[] args) {
        List<String> inputs = List.of(
                "2026-10-19", "2026-02-30", "2024-02-29");

        for (int i = 0; i < inputs.size(); i++) {
            RowResult result = parseRow(i + 1, inputs.get(i));
            if (result.valid()) {
                System.out.println("ok=" + result.row()
                        + ":" + result.value());
            } else {
                System.out.println("error=" + result.row()
                        + ":" + result.error());
            }
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 DateBatchDemo.java
java DateBatchDemo
~~~

Output:

~~~text
ok=1:2026-10-19
error=2:INVALID_DATE
ok=3:2024-02-29
~~~

Record is a standard Java 17 feature. The example stores only an error code because the goal is per-row reporting. A production design can store the **error index** (when meaningful), column name, and cause object in an internal result if tracing is needed, while avoiding writing the full raw string to public logs.

Do not automatically choose a "continue" policy for a transaction that must be atomic: if all rows must succeed or roll back together, stopping or aggregating errors must follow that contract.

## 16. Errors That Are Neither ParseException Nor DateTimeParseException

Text-processing APIs may throw other types:

| Scenario | Typical exception or error reporting |
| --- | --- |
| Integer.parseInt("bad") | NumberFormatException (unchecked) |
| LocalDate.parse("not-date") | DateTimeParseException (unchecked) |
| SimpleDateFormat.parse("bad") | ParseException (checked) |
| NumberFormat.parse("bad") | ParseException (checked) |
| DateTimeFormatter.ofPattern("pattern invalid") | IllegalArgumentException when the pattern is invalid |
| Calling some parse APIs with a null argument | Possibly NullPointerException, depending on the API |
| Reading a file before parsing | IOException or corresponding I/O exception |
| Valid date that violates business bounds | Application-defined validation error |
| Narrowing a large number inaccurately | ArithmeticException if using toIntExact/intValueExact |
| Parsing JSON/XML data with another library | Library-specific exceptions, not necessarily the two in this article |

There is no **single ParseException for all Java parsers**. Do not write **catch(ParseException)** expecting it to also catch DateTimeParseException or NumberFormatException. If a unified error convention is needed at the application layer, build an **error code / field / message / cause** model and map each parser type at its respective boundary.

## 17. Data and Security Pitfalls

1. **Raw value in the exception:** DateTimeParseException.getParsedString can contain the entire rejected text. Do not log it verbatim when it contains tokens, user information, or very long strings.
2. **Parser message:** getMessage may include input values and implementation details. Do not send the entire message to clients as an API contract.
3. **Error position:** the error index is a diagnostic index, not necessarily a UI column number. Java uses string indices; special Unicode characters can cause "visible character" counts to differ from offset counts.
4. **Whitespace:** ISO-based LocalDate.parse does not allow extra characters by default; if the UI permits leading/trailing whitespace, only use strip/trim when that is a documented policy.
5. **Input length:** limit character count and record count before performing complex parsing, especially when receiving data from untrusted sources.
6. **Time zone:** successfully parsing a LocalDateTime does not determine an Instant if zone/offset is missing. Do not treat error-free parsing as proof of accurate point-in-time data.
7. **System defaults:** SimpleDateFormat has timezone/locale state, and DateTimeFormatter.ofPattern without an explicit locale can depend on environment settings. Set configuration explicitly at the data boundary.
8. **Thread safety:** do not share the same mutable SimpleDateFormat across multiple threads without synchronization. DateTimeFormatter is immutable and much safer to reuse.
9. **Calendar-invalid data:** strict resolver prevents silent date adjustment; test leap years and end-of-month dates.
10. **Do not parse the exception's text message:** to decide the error code/type, use the exception type, position, and application data structures, not getMessage content as a contract.

## 18. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Thinking ParseException and DateTimeParseException are both checked | Incorrect error-handling signature | Remember java.text is checked, java.time is unchecked |
| Catching ParseException to handle LocalDate.parse errors | Fails to catch DateTimeParseException | Catch DateTimeParseException when appropriate |
| Catching DateTimeParseException to handle SimpleDateFormat.parse | Does not satisfy checked ParseException | Catch or declare ParseException |
| Calling setLenient(false) and assuming the parser reads the whole string | May ignore invalid trailing suffixes | Use ParsePosition and check getIndex == text.length |
| Using ofPattern("dd/MM/yyyy") + STRICT and thinking it matches uuuu | Year-of-era may fail to resolve without an era | Use uuuu for ISO proleptic year |
| Assuming ofPattern is always STRICT | ofPattern defaults to SMART | Set withResolverStyle(STRICT) when needed |
| Accepting 29/02/2023 because the pattern matches | Nonexistent date | Strict resolver and calendar validation |
| Printing java.util.Date.toString and comparing with a date string | Display depends on time zone | Format with explicit timezone/locale or use LocalDate |
| Logging ex.getParsedString for every field | May leak sensitive data | Log only permitted data, preferring field/code |
| Trusting error index to always point to the business error character | Parser has two stages; index is contextual | Use index for diagnostics, not as sole source of truth |
| Parsing LocalDateTime and assuming UTC | Missing zone/offset | Use OffsetDateTime, ZonedDateTime, or Instant matching the data |
| Sharing mutable SimpleDateFormat across threads | Risk of wrong results / data race | Create per-thread instances or use DateTimeFormatter |
| Parsing date strings with month names without specifying Locale | Machine-dependent, may fail | Specify Locale explicitly |
| Catching broad Exception and returning null | Hides unrelated errors and loses the cause | Catch the specific type and preserve the cause |
| Converting parser error to just a string | Loses stack trace and original error | Use a wrapper (message, cause) or Result with clear code |
| Not checking for null/blank | May trigger technical errors instead of validation | Check upfront and report a field error |

## 19. Checklist for Implementing a Reliable Parser

Before writing or reviewing data-parsing code:

1. **Identify the target data type:** Date, LocalDate, LocalDateTime, OffsetDateTime, or Instant? Is a timezone required?
2. **Identify the format:** standard ISO, dd/MM/uuuu, textual month, or locale-specific format?
3. **Set the resolver style:** STRICT if the date must exist exactly without silent adjustment.
4. **Decide whitespace policy:** strip leading/trailing spaces or not; allow suffixes or not?
5. **Read the exception contract:** checked ParseException, unchecked DateTimeParseException, NumberFormatException, or another type?
6. **Check the full string:** especially with java.text.ParsePosition.
7. **Handle missing values:** should null/blank have a dedicated message?
8. **Preserve context:** field name, CSV row, required format, error code.
9. **Preserve the cause:** if translating to a domain exception, use a constructor that accepts a cause.
10. **Protect sensitive information:** avoid logging raw parsedString/message if sensitive.
11. **Check thread-safety:** is the formatter mutable or immutable; is it shared across multiple threads?
12. **Write tests:** leap year, end of month, wrong separator, trailing text, locale, offset/zone, null, overly long input.
13. **Handling layer:** if fixable at the input boundary, return validation feedback; otherwise, log and propagate the exception per contract.
14. **Do not equate exception with validation:** a successful parse can still violate business rules.

## 20. Self-Check Questions

**1.** Do ParseException and DateTimeParseException have the same checked/unchecked status?  
**No.** ParseException is checked; DateTimeParseException is unchecked.

**2.** What error type does SimpleDateFormat.parse(String) typically declare for invalid input?  
**ParseException**, so the caller must catch or declare throws according to the checked contract.

**3.** Can LocalDate.parse("2026-02-30") construct a date?  
**No.** Strict ISO rejects nonexistent dates with DateTimeParseException.

**4.** Does SimpleDateFormat.setLenient(false) guarantee the parser reads the entire string?  
**No.** You need to check ParsePosition or an equivalent mechanism.

**5.** What useful dedicated getters does DateTimeParseException have?  
**getParsedString()** and **getErrorIndex()**.

**6.** Does ParseException have a dedicated getter to retrieve the entire input string?  
**No.** It has **getErrorOffset()**; the application must retain the input context itself if needed.

**7.** What resolver style does DateTimeFormatter.ofPattern("dd/MM/uuuu") use by default?  
**SMART**. Use **withResolverStyle(STRICT)** if strictly valid dates are required.

**8.** Why might dd/MM/yyyy + STRICT fail to resolve into a LocalDate?  
Because yyyy is **year-of-era**; without an era, it may be insufficient to determine the proleptic year. Use **uuuu** when targeting the ISO calendar.

**9.** Does NumberFormat.parse(String) throw ParseException or NumberFormatException in the standard API?  
**Checked ParseException**; unlike Integer.parseInt.

**10.** Are Locale and ZoneId equivalent?  
**No.** Locale is for language/formatting conventions; ZoneId defines a time-zone region.

**11.** What does wrapping an error with new InvalidFieldException("date", message, cause) achieve?  
It preserves a **contextual message**, **field name**, and the **cause** of the original parse error.

**12.** Can DateTimeParseException.getErrorIndex() be used directly as a CSV column number?  
**No.** It is the position reported by the parser within the parsed string; it must be mapped to record/field coordinates.

**13.** Does DateTimeFormatter.parse with ParsePosition always behave like java.text's return-null-on-error behavior?  
**No.** Read the overload contract; DateTimeFormatter may throw DateTimeParseException.

**14.** Is parsing a date that matches a pattern enough to construct an accurate Instant?  
**Not yet.** Without an offset or zone, the global point in time is not determined.

## Standard References

- [Java SE 21 — java.text.ParseException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/ParseException.html).
- [Java SE 21 — java.text.ParsePosition](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/ParsePosition.html).
- [Java SE 21 — java.text.SimpleDateFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/SimpleDateFormat.html).
- [Java SE 21 — java.text.NumberFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/NumberFormat.html).
- [Java SE 21 — java.time.format.DateTimeParseException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeParseException.html).
- [Java SE 21 — java.time.format.DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html).
- [Java SE 21 — java.time.format.ResolverStyle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/ResolverStyle.html).
- [Java SE 21 — java.time.LocalDate](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDate.html).
- [JLS 21 — §11.1.1 Checked and unchecked exceptions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-11.html#jls-11.1.1).

**Remember:** ParseException is the classic checked exception of **java.text**, while DateTimeParseException is the unchecked exception of **java.time**. To parse reliably, choose the right target type, formatter, locale, and resolver style, check the **full string** when needed, preserve the error cause, and always attach input data context instead of letting the parser's message or offset act as a business contract.
