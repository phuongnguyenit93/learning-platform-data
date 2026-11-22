
# Date-Time Formats, Decimals, and Character Encodings in Data Exchange

During a Java upgrade, compatibility is not limited to methods, bytecode, or dependencies. An application may run normally yet exchange **wrong timestamps**, **wrong monetary amounts**, or **corrupted characters** with other systems because date-time formats, decimal rules, and charsets implicitly depend on the JDK, locale, or deployment environment.

For example, one service produces the string `"01/02/2026 08:30"` without declaring the timezone, day-month order, or offset. Another service parses `"1.234,50"` as 1.23450 instead of 1234.50. A Vietnamese CSV file written with a Windows machine's default charset and then read as UTF-8 on Linux will show garbled characters. All of these cases can happen even when Java source compiles cleanly.

This lesson belongs to the **Java Advance Compatibility Migration** topic, **Data and Protocols** section, presenting how to design and verify data exchange contracts that remain stable across JDK upgrades, environment moves, library replacements, or simultaneous deployments of multiple producer and consumer versions.

## 1. How Specific Must a Data Exchange Contract Be?

A data protocol must answer questions that Java code often leaves implicit:

- Is the date-time an **absolute instant** or **local time**?
- If it is an absolute instant, how is the offset or timezone transmitted?
- Is the format ISO 8601/RFC 3339 or an application-defined custom pattern?
- Is the timestamp accurate to seconds, milliseconds, microseconds, or nanoseconds?
- Do decimals use a dot or a comma; are exponents, plus signs, and leading zeros permitted?
- Are monetary amounts stored as decimals, integer minor units, or floating-point?
- Must scale such as `1.20` versus `1.2` be preserved, or only the numeric value?
- Are strings encoded in UTF-8, UTF-16, or another charset?
- How are Byte Order Marks (BOM), newlines, Unicode normalization, and malformed characters handled?
- Which schema and version govern parsing, validation, and serialization?
- How will old consumers handle data emitted by new producers?

A good contract does not vaguely say "date in ISO," "numbers in the default locale," or "text in server encoding," but explicitly defines the **wire** representation, validation, and migration policy.

### 1.1. Distinguishing Value, Representation, and Encoding

For example, a transaction occurring at a specific instant, with a total of 1234.50 USD and a Vietnamese note:

| Layer | Example | Responsibility |
|---|---|---|
| Time value | An `Instant` on the UTC timeline | Business point in time |
| Time representation | `2026-11-12T09:30:00Z` | Contract-compliant text |
| Numeric value | `BigDecimal("1234.50")` | Exact decimal number |
| Numeric representation | `"1234.50"` | Digits/decimal point per contract |
| Currency unit | `USD` | Separate currency identifier |
| Characters | `"Đã thanh toán"` | Unicode character sequence |
| Byte encoding | UTF-8 | Turns string into bytes |
| Protocol | JSON/CSV/XML/message | Field structure, escaping, and schema |

Do not take a UI display string as the protocol representation merely because it "looks right" on the developer's machine.

~~~mermaid
flowchart TD
    A["Typed business data"] --> B["Explicit serialization rules"]
    B --> C["Text/schema representation"]
    C --> D["Charset and byte encoding"]
    D --> E["Bytes on the wire or in a file"]
    E --> F["Decode using the agreed charset"]
    F --> G["Parse and validate against schema"]
    G --> H["Typed data at the consumer"]
~~~

## 2. The Date-Time Model in java.time

The `java.time` API has multiple types, each describing different information. They cannot be swapped arbitrarily.

| Type | Meaning | When Appropriate |
|---|---|---|
| `LocalDate` | Calendar date without time/zone | Birthdays, accounting dates per local rules |
| `LocalTime` | Time of day without date/zone | Opening hours when paired with zone rules |
| `LocalDateTime` | Local date + time, **without** offset/zone | Appointments interpreted in a specific region |
| `OffsetDateTime` | Date-time + offset such as `+07:00` | Payloads needing an explicit offset |
| `ZonedDateTime` | Date-time + region `ZoneId` and zone rules | Region-dependent schedules such as `Asia/Ho_Chi_Minh` |
| `Instant` | Absolute point on the UTC timeline | Event timestamps, audit logs, created_at |
| `Duration` | Time span in seconds/nanoseconds | Timeouts, task durations |
| `Period` | Calendar span in years/months/days | Calendar-based recurring rules |
| `ZoneId` | Timezone ID or offset | Selecting calendar interpretation rules |
| `ZoneOffset` | Fixed offset from UTC | Timestamp UTC offset information |

A `LocalDateTime` such as `2026-11-12T09:30:00` **does not identify a unique instant**. That same local time corresponds to different instants in Hanoi and Tokyo. In regions observing Daylight Saving Time (DST), some local times may not even exist or may repeat.

### 2.1. Instant for Past Events

~~~java
import java.time.Instant;

public final class EventTimestamp {
    public static void main(String[] args) {
        Instant eventTime = Instant.now();
        String wire = eventTime.toString();

        Instant recovered = Instant.parse(wire);
        System.out.println(wire);
        System.out.println(recovered.equals(eventTime));
    }
}
~~~

`Instant` is well suited for recording a past event that systems across multiple timezones must compare on the same timeline.

However, producer and consumer must still agree on precision. If a datastore retains only milliseconds while the producer emits nanoseconds, round-trips can lose sub-millisecond precision.

### 2.2. OffsetDateTime for Timestamps with an Offset

~~~java
import java.time.OffsetDateTime;

OffsetDateTime created =
        OffsetDateTime.parse("2026-11-12T16:30:00+07:00");

System.out.println(created.toInstant());
~~~

A string carrying offset `+07:00` is sufficient to derive an instant. An offset is **not** a region ID. It does not contain complete historical and future DST rules like `Asia/Ho_Chi_Minh` or `Europe/Berlin`.

Two payloads with different offsets can still represent the same instant. If the contract only cares about the timeline, compare `toInstant()` rather than assuming strings or local fields must match.

### 2.3. ZonedDateTime for Region-Based Schedules

~~~java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

LocalDateTime meeting =
        LocalDateTime.of(2026, 11, 12, 9, 30);

ZonedDateTime scheduled =
        meeting.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));

System.out.println(scheduled);
~~~

If an event must happen at 9:30 AM **in a region's local time**, pay attention to the region ID and timezone rules. Storing only an `Instant` may not suffice to reproduce recurring schedules on other days; conversely, storing only `LocalDateTime` is insufficient to determine when a past event happened.

### 2.4. Storing UTC Does Not Mean Dropping Zone Information in Every Problem

A common rule is storing event timestamps in UTC. That fits audits, logs, and past events. However, appointments, workday recurrences, or opening hours may require **both local time and region zone ID**.

For example, a product requires running a task at 08:00 Paris time every day. Do not compute a single UTC offset at configuration time and keep it fixed for all subsequent days if the region observes DST.

## 3. Wire Format Standards: ISO 8601 and RFC 3339

ISO 8601 is a family of date-time representation rules; RFC 3339 specifies a timestamp profile widely used in Internet exchange. In Java, several built-in formatters belong to `DateTimeFormatter`, yet they are not fully interchangeable across all temporal types.

### 3.1. Clear Timestamp Examples

~~~text
2026-11-12T09:30:00Z
2026-11-12T16:30:00+07:00
2026-11-12T16:30:00.123+07:00
~~~

These strings can describe the same instant when the offset and seconds align; the third string includes an extra 123 milliseconds and thus describes a different instant from the first two.

A contract may require:

- Timestamps must carry an offset or `Z` marker.
- Omitting the offset is disallowed.
- Output normalized to UTC `Z` or preserving the input offset.
- Fractional seconds with maximum precision and zero-padding rules.
- Accepting only valid calendar dates.
- Documented leap-second handling rules if the system has special requirements.

Do not just write "ISO 8601" and allow arbitrary variants accepted by some parser without a schema.

### 3.2. Formatting and Parsing Timestamps

~~~java
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.format.DateTimeFormatter;

public class WireTime {
    public static void main(String[] args) {
        Instant time =
                Instant.parse("2026-11-12T09:30:00.123Z");

        String output =
                DateTimeFormatter.ISO_INSTANT.format(time);

        Instant decoded =
                Instant.parse(output);

        OffsetDateTime offsetTime =
                OffsetDateTime.parse(
                        "2026-11-12T16:30:00+07:00",
                        DateTimeFormatter.ISO_OFFSET_DATE_TIME);

        System.out.println(output);
        System.out.println(decoded.equals(time));
        System.out.println(offsetTime.toInstant());
    }
}
~~~

Use the parse type matching the wire schema:

- If the payload is a UTC instant, use `Instant.parse` or a compatible formatter.
- If the payload contains an offset, `OffsetDateTime.parse` may be appropriate.
- If the payload is date-only, use `LocalDate.parse`.
- If the wire contains a region zone ID, use a format and parser that preserve that zone.

### 3.3. Do Not Use Human-Readable Formats as API Formats

Error-prone example:

~~~java
// Unsuitable as a machine-readable contract without defining locale/zone.
String output = java.text.DateFormat.getDateTimeInstance().format(date);
~~~

The output depends on locale and configuration, not a stable representation for consumers on different platforms.

When displaying in a user interface, locale-aware formatters can be used. However, APIs and event buses require time strings following a fixed contract.

## 4. Date-Time Patterns: Similar Letters with Different Meanings

`DateTimeFormatter` has many pattern letters. Two mistakes are especially common:

- `yyyy`: year-of-era.
- `YYYY`: week-based-year under week rules; **not** synonymous with calendar year.
- `MM`: month-of-year.
- `mm`: minute-of-hour.
- `dd`: day-of-month.
- `DD`: day-of-year.

Example:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

LocalDate date = LocalDate.of(2020, 12, 31);

DateTimeFormatter calendar =
        DateTimeFormatter.ofPattern(
                "uuuu-MM-dd", Locale.ROOT);

DateTimeFormatter weekBased =
        DateTimeFormatter.ofPattern(
                "YYYY-MM-dd", Locale.US);

System.out.println(calendar.format(date));
System.out.println(weekBased.format(date));
~~~

Around year transitions, `YYYY` can differ from the calendar year depending on the locale's week rules. If the protocol intends a calendar date, never use `YYYY` instead of `uuuu` or an ISO formatter merely because "capital Y looks nicer."

### 4.1. uuuu and yyyy in Strict Parsing

`uuuu` describes proleptic year; `yyyy` is year-of-era, which can interact differently with a strict resolver and eras. For standard protocol date formats, prefer built-in formatters like `DateTimeFormatter.ISO_LOCAL_DATE` or tested custom rules.

### 4.2. Locale and Month/Day Symbols

Patterns containing month/weekday names such as `MMM` or `EEEE` produce locale-dependent text. They suit UI display, yet should not be emitted as machine-readable data unless consumers are configured with the exact same locale and provider.

Example:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

LocalDate date = LocalDate.of(2026, 11, 12);
DateTimeFormatter view =
        DateTimeFormatter.ofPattern(
                "dd MMMM uuuu", Locale.forLanguageTag("vi-VN"));

System.out.println(view.format(date));
~~~

The output can depend on the JDK's locale data version. For data exchange, `2026-11-12` is more stable than a language-specific month-name string.

### 4.3. Resolver Style When Parsing

An overly lenient parser can silently turn invalid date inputs into different dates, causing quiet data corruption. For inputs under strict contracts, use `ResolverStyle.STRICT` when building custom formatters:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.Locale;

DateTimeFormatter strict = DateTimeFormatter
        .ofPattern("uuuu-MM-dd", Locale.ROOT)
        .withResolverStyle(ResolverStyle.STRICT);

LocalDate parsed =
        LocalDate.parse("2026-11-12", strict);
~~~

A string such as `2026-02-30` should be rejected as requiring a valid date, rather than automatically rolling over into March.

## 5. DST, Gaps, Overlaps, and Historical Data

In timezones with DST transitions, the same local datetime can:

- Have exactly one valid offset.
- Have no valid offset because clocks jump over an interval (gap).
- Have two valid offsets because clocks fall back (overlap).

Check using `ZoneRules`:

~~~java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.List;

ZoneId zone = ZoneId.of("Europe/Berlin");

LocalDateTime localTime =
        LocalDateTime.of(2026, 10, 25, 2, 30);

List<ZoneOffset> offsets =
        zone.getRules().getValidOffsets(localTime);

System.out.println("Valid offsets: " + offsets);
~~~

If there are two offsets, a local datetime is insufficient to pick a unique instant. If there is no offset, that local time does not exist under the zone rules on that date.

Business policies must define how to handle this:

- Reject ambiguous times and require the user to choose.
- Select the earlier or later offset according to business rules.
- Shift times across a gap according to a published rule.
- Store both the resolved instant and the zone ID if auditing is needed.

Do not simply call `atZone(...)` and assume Java's default resolution is right for every business domain.

### 5.1. TZDB Can Change Across JDK Updates

Timezone rules are maintained in the time zone database (tzdb). When laws in a country/region change, a JDK update may introduce different rules.

Therefore:

- A future scheduled event may convert to a different UTC instant after a tzdb update.
- A test hardcoding an offset for a future date may be unstable.
- When verifying schedules, record the JDK/tzdb version and the zone used in the test.
- Distributed services should follow a consistent tzdb update policy when calculating schedules jointly.

Do not treat a region's current offset as permanent.

## 6. Unix Epoch and Time Units

A common data bug is confusing **seconds**, **milliseconds**, **microseconds**, and **nanoseconds** since the Unix epoch.

| Representation | Unit | Example of Typical Digit Length in Modern Dates |
|---|---|---|
| Epoch seconds | Seconds | Around 10 digits |
| Epoch millis | Milliseconds | Around 13 digits |
| Epoch micros | Microseconds | Around 16 digits |
| Epoch nanos | Nanoseconds | May require 64-bit integers with explicit range limits |

Digit length is only a heuristic indicator, **not a reliable parsing rule**. Contracts must name fields and units explicitly, such as `createdAtEpochMillis`.

~~~java
import java.time.Instant;

long millis = 1_800_000_000_000L;
Instant time = Instant.ofEpochMilli(millis);

long roundTrip = time.toEpochMilli();
System.out.println(roundTrip == millis);
~~~

If a consumer reads milliseconds as seconds, timestamp data will be severely wrong or exceed supported ranges.

### 6.1. Timestamp Precision Must Have a Policy

Different systems store timestamps at different precisions:

- Java `Instant` can represent nanoseconds.
- Database columns may keep microseconds or milliseconds depending on type and configuration.
- JSON clients may round or truncate fractional digits.
- A serialization library may write three, six, or nine fractional digits.

When comparing round-trips, establish the actual precision first. You can normalize to milliseconds if the contract only requires that level:

~~~java
import java.time.Instant;
import java.time.temporal.ChronoUnit;

Instant source = Instant.now();
Instant normalized = source.truncatedTo(ChronoUnit.MILLIS);
~~~

Precision truncation must be intentional and documented, not accidentally introduced by a mapper.

### 6.2. Do Not Use Local Datetime as an Event Timestamp Without a Zone

The following JSON example does not itself determine an instant:

~~~json
{
  "createdAt": "2026-11-12T16:30:00"
}
~~~

If the contract is an event timestamp, prefer:

~~~json
{
  "createdAt": "2026-11-12T09:30:00Z"
}
~~~

If storing the local datetime of an appointment is genuinely needed, model it explicitly:

~~~json
{
  "appointmentLocalTime": "2026-11-12T16:30:00",
  "timeZone": "Asia/Ho_Chi_Minh"
}
~~~

The two designs serve different problems. Do not implicitly apply the server default zone to every local datetime from a request.

## 7. Be Careful with java.util.Date, Calendar, and JDBC

Long-lived Java systems may use `java.util.Date`, `Calendar`, `java.sql.Date`, `java.sql.Timestamp`, and legacy formatting APIs. They have different conversion rules and are easily confused with `java.time`.

### 7.1. Date Does Not Store a Timezone

`java.util.Date` represents an instant, yet `Date.toString()` formats output based on the JVM's default timezone. Therefore, `Date.toString()` cannot serve as a stable timestamp protocol.

When converting to `Instant`:

~~~java
import java.time.Instant;
import java.util.Date;

Date legacy = new Date();
Instant instant = legacy.toInstant();
Date restored = Date.from(instant);
~~~

This conversion interprets the instant; it does not preserve a user's display zone.

### 7.2. SimpleDateFormat Has Mutable State

`java.text.SimpleDateFormat` is not thread-safe when shared across threads. When migrating, prefer `java.time.format.DateTimeFormatter`, which is immutable and safely reusable under the appropriate formatter contract.

Avoid changing patterns without verifying equivalence, because pattern letters between legacy and modern APIs may be interpreted differently in edge cases.

### 7.3. JDBC and Database Timezones

A SQL `TIMESTAMP` or `TIMESTAMP WITH TIME ZONE` field has database/vendor-dependent semantics. Do not assume every DBMS stores the original zone ID or retains offsets in the same way.

Define:

- Column types and semantics.
- JDBC driver conversions.
- Database session timezone.
- Precision (milli/micro/nano).
- How the ORM maps `Instant`, `OffsetDateTime`, and `LocalDateTime`.
- Migration and behavior when upgrading the driver/JDK.

Test against a **real database and real driver**, not only H2 or a mock differing from production.

## 8. Decimals: Value and String Representation

The number `1234.50` can be represented as:

~~~text
1234.50
1,234.50
1.234,50
1 234,50
1.2345E3
~~~

These strings are not equivalent to every parser. In the protocol, specify the syntax: decimal separator, whether grouping is permitted, exponents, minus signs, precision limits, and scale.

**Machine-readable protocols should not directly take output from a user-locale `NumberFormat`.**

### 8.1. BigDecimal for Exact Decimal Values

~~~java
import java.math.BigDecimal;

BigDecimal amount = new BigDecimal("1234.50");

System.out.println(amount.toPlainString());
System.out.println(amount.scale());
~~~

`BigDecimal` preserves exact decimals according to decimal representation. Avoid constructing from `double` literals if exact numbers supplied by users or protocols must be preserved:

~~~java
BigDecimal problematic = new BigDecimal(0.1);
BigDecimal exact = new BigDecimal("0.1");
~~~

`new BigDecimal(0.1)` receives the exact binary value of the double, not the exact decimal literal "0.1".

### 8.2. BigDecimal: compareTo and equals

~~~java
import java.math.BigDecimal;

BigDecimal a = new BigDecimal("1.20");
BigDecimal b = new BigDecimal("1.2");

System.out.println(a.compareTo(b) == 0); // true
System.out.println(a.equals(b));          // false
~~~

`compareTo` treats them as having the same numeric value; `equals` also checks scale. Therefore, if a payload must preserve scale (for example, decimal digits declared on an invoice), do not accidentally normalize away trailing zeros. Conversely, if the contract requires only numeric equality, tests should not equate a scale difference with a calculation bug.

### 8.3. toString and toPlainString

`BigDecimal.toString()` may emit exponent notation in some cases. `toPlainString()` always outputs plain decimal text without exponents, though it can produce very long strings when scale is huge.

~~~java
BigDecimal value = new BigDecimal("1E+6");

System.out.println(value.toString());      // 1E+6
System.out.println(value.toPlainString()); // 1000000
~~~

When choosing a decimal string contract, specify whether exponents are allowed, maximum scale/precision, and input size limits to prevent abnormal payloads.

### 8.4. Monetary Amounts Need a Separate Currency

A monetary amount is at least an `amount + currency code` pair:

~~~json
{
  "amount": "1234.50",
  "currency": "USD"
}
~~~

Do not send:

~~~json
{
  "amount": "$1,234.50"
}
~~~

as a machine-readable value without a dedicated schema; the `$` symbol does not uniquely identify a currency and the format is locale-dependent. Currency codes and rounding/scale rules must be specified in the business contract.

## 9. Rounding, Precision, and Data Limits

Exact decimals do not mean every arithmetic operation yields a finite result at the required scale.

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal amount = new BigDecimal("12.345");
BigDecimal rounded =
        amount.setScale(2, RoundingMode.HALF_UP);

System.out.println(rounded.toPlainString());
~~~

The output `12.35` in the example reflects a rounding decision. `HALF_UP` is only illustrative; finance, accounting, and tax domains may use different policies.

### 9.1. Division Must Specify Rules

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal one = BigDecimal.ONE;
BigDecimal three = new BigDecimal("3");

BigDecimal quotient =
        one.divide(three, 6, RoundingMode.HALF_EVEN);
~~~

If calling a division without a finite decimal representation without specifying how to handle it, `BigDecimal.divide(...)` may throw `ArithmeticException`.

### 9.2. Numeric Contract Constraints

Specify explicitly:

- Maximum precision.
- Allowed scale, and whether negative scale is permitted.
- Min/max range and overflow handling.
- Negative signs, zero, and negative zero if consumers use floating-point.
- Whether exponents are accepted.
- Whether leading `+` or leading zeros are accepted.
- Rounding mode and when rounding occurs.
- Policy for `NaN`/`Infinity` when the data source is double/float; `BigDecimal` does not represent these values.

Do not merely say "decimal" and let each library pick its own parse/serialize rules.

### 9.3. Minor Units Must Accompany Scale/Currency

Some systems store amounts as integer minor units:

~~~json
{
  "minorUnits": 123450,
  "currency": "USD"
}
~~~

This may correspond to 1234.50 USD if the contract specifies scale 2. However, not every currency defaults to two fractional digits; domain-specific policies also exist. Consumers need to know the exact scale associated with the value. Do not extrapolate a single rule across all tokens or currencies.

## 10. NumberFormat and Locale: Suitable for UI, Not Default for Wire

`NumberFormat` and `DecimalFormat` can format strings by locale:

~~~java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.Locale;

BigDecimal amount = new BigDecimal("1234.50");

NumberFormat en =
        NumberFormat.getNumberInstance(Locale.US);

NumberFormat de =
        NumberFormat.getNumberInstance(Locale.GERMANY);

System.out.println(en.format(amount));
System.out.println(de.format(amount));
~~~

Differences in dots, commas, grouping, and digits are **expected behavior when formatting by locale**, yet should not be placed directly into JSON fields or machine-readable CSV exchanges.

### 10.1. Default Locale Can Change After Upgrading the JDK or Container

~~~java
NumberFormat format = NumberFormat.getNumberInstance();
~~~

The code above depends on the default formatting locale. If the server changes locale, the output changes without modifying source code.

In Java, locale data can also be updated across JDK releases, including CLDR rules. Some locales use special Unicode spaces for grouping. For protocols, avoid relying on a specific separator remaining invariant across all JDK updates.

### 10.2. Do Not Parse Numbers with Arbitrary String.replace

Code like:

~~~java
String normalized =
        input.replace(".", "").replace(",", ".");
~~~

works only if the input format has been strictly verified, and easily breaks when input contains unexpected separators.

For UI input, select the user's locale, use the matching parser, and verify the entire string was parsed. For machine-readable protocols, define a canonical syntax and strict parser.

### 10.3. ParsePosition Helps Detect Trailing Characters

~~~java
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

NumberFormat parser =
        NumberFormat.getNumberInstance(Locale.GERMANY);

String input = "1.234,50";
ParsePosition pos = new ParsePosition(0);

Number number = parser.parse(input, pos);

if (number == null || pos.getIndex() != input.length()) {
    throw new IllegalArgumentException("Invalid numeric input");
}

System.out.println(number);
~~~

The returned `Number` may not be a `BigDecimal`. If decimal precision must be preserved, consider `DecimalFormat.setParseBigDecimal(true)` when supported by the implementation and still validate input schemas.

## 11. JSON and Numeric Precision

JSON has its own number syntax; it does not use locale grouping. However, a JSON number is not required to be parsed into the same numeric type by every language.

Example:

~~~json
{
  "amount": 1234.50,
  "currency": "USD"
}
~~~

In Java, JSON libraries can parse into `BigDecimal` if configured; in JavaScript, JSON numbers are typically IEEE 754 doubles. That can lose precision on large values or numbers with many decimal digits.

If the contract needs to preserve exact decimals across all clients, one option is a decimal string:

~~~json
{
  "amount": "1234.50",
  "currency": "USD"
}
~~~

This is a **schema decision**: consumers must parse the string field according to the specified decimal grammar rather than automatically treating it as a number. Another option is integer minor units with explicit limits.

### 11.1. Do Not Equate JSON Number with Java double

Some Java libraries support deserializing JSON numbers to `BigDecimal`; others default to `Double` or `Long` depending on configuration. The result depends on the field type and mapper configuration.

Test:

- Values exceeding JavaScript clients' safe integer range, if applicable.
- Decimals with many fractional digits.
- Negative numbers and zero.
- Exponent notation if allowed by the contract.
- Scale/trailing zeros if preservation is required.
- Round-trips across producers/consumers in different languages.

### 11.2. Schemas Must Define Structure and Validation

A schema might specify:

- `timestamp` is an RFC 3339 date-time string with offset.
- `amount` is a decimal string with a pattern or constraint.
- `currency` is the currency code.
- `note` is a Unicode string encoded as UTF-8 on the wire.

If a producer changes from `"amount": "12.30"` to `"amount": 12.30`, that is a **JSON data type change**, not merely a format optimization. Evaluate backward compatibility for all consumers.

## 12. Character Encodings and Unicode Are Not the Same Concept

A Java `String` holds text under the Unicode model, whereas files and network transports store **bytes**. A charset determines the conversion.

A Vietnamese string:

~~~text
Đơn hàng đã xác nhận
~~~

can be encoded into UTF-8, UTF-16, or another charset's bytes. If the receiver decodes with the wrong charset, accented characters can become corrupted (mojibake) or turn into replacement characters.

### 12.1. Encoding and Decoding Explicitly with UTF-8

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public class TextEncoding {
    public static void main(String[] args) {
        String text = "Đơn hàng đã xác nhận";

        byte[] bytes =
                text.getBytes(StandardCharsets.UTF_8);

        String recovered =
                new String(bytes, StandardCharsets.UTF_8);

        System.out.println(Arrays.toString(bytes));
        System.out.println(text.equals(recovered));
    }
}
~~~

If both producer and consumer use UTF-8 per contract, strings can round-trip accurately for valid inputs.

### 12.2. Avoid Default Charsets in Protocols

The following calls depend on the default charset or implicit API conventions:

~~~java
byte[] data = text.getBytes();
String decoded = new String(data);
~~~

For data exchange, write:

~~~java
byte[] data =
        text.getBytes(java.nio.charset.StandardCharsets.UTF_8);

String decoded =
        new String(data, java.nio.charset.StandardCharsets.UTF_8);
~~~

The same charset must be applied at both ends, even if the system initially has only a single Java service.

### 12.3. JDK 18 and the Default Charset Change

Starting in JDK 18, JEP 400 made UTF-8 the default charset in most standard configurations, instead of commonly depending on the operating system's default charset as before. However, **there is no reason to rely on the default charset** when designing protocols.

A legacy application that previously wrote files using a legacy charset on Windows and moves to a newer JDK may encounter differences when:

- Writing new files in UTF-8.
- Reading old files with the new default charset.
- Using libraries that read files based on the OS.
- Moving files across Windows, Linux, and container images.

Evaluate migrating stored data, not only swapping the JDK. For legacy files, determine each file's true charset via metadata/contract rather than assuming old files are UTF-8 and decoding them erroneously.

### 12.4. Using the Files API with an Explicit Charset

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of("orders.csv");

Files.writeString(
        path,
        "id,description\n1,Đã thanh toán\n",
        StandardCharsets.UTF_8);

String content =
        Files.readString(path, StandardCharsets.UTF_8);
~~~

Even when a modern overload defaults to UTF-8, passing an explicit charset lets maintainers see the contract right at the call site and makes cross-checking with consumers easier.

## 13. CharsetDecoder and Invalid Byte Data

Not every byte sequence is valid UTF-8. How malformed input is handled is part of the data contract:

- **REPORT**: reject invalid data.
- **REPLACE**: insert a replacement character.
- **IGNORE**: skip invalid bytes.

For financial data or critical identifiers, silently replacing/dropping bytes can corrupt data unnoticed. Consider rejecting and logging controlled errors instead.

~~~java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class StrictUtf8 {
    public static String decode(byte[] bytes)
            throws CharacterCodingException {

        var decoder = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);

        CharBuffer result =
                decoder.decode(ByteBuffer.wrap(bytes));

        return result.toString();
    }
}
~~~

When encoding Java strings to UTF-8, also understand how the encoder handles strings with unpaired surrogates. For data requiring integrity, validate inputs rather than letting conversion silently produce replacements.

### 13.1. Do Not Measure Wire Length Using String.length()

`String.length()` returns the count of UTF-16 code units, not Unicode code points and not UTF-8 bytes.

~~~java
import java.nio.charset.StandardCharsets;

String value = "Tiếng Việt 😊";

int utf16Units = value.length();
int codePoints = value.codePointCount(0, value.length());
int utf8Bytes =
        value.getBytes(StandardCharsets.UTF_8).length;

System.out.println(utf16Units);
System.out.println(codePoints);
System.out.println(utf8Bytes);
~~~

If a protocol has a length field or payload size limit, specify whether length is measured in bytes, code points, grapheme clusters, or user-perceived characters. Do not mix units.

### 13.2. Truncating Strings by Bytes Can Corrupt UTF-8

If truncating a `byte[]` in the middle of a multibyte UTF-8 sequence, consumers may receive malformed data. If the limit is in bytes, truncate at code point boundaries or use a controlled encoding/streaming mechanism; if the limit is display characters, account for Unicode grapheme clusters.

## 14. BOM, Newlines, and Unicode Normalization

### 14.1. UTF-8 BOM

UTF-8 can appear with the BOM byte prefix `EF BB BF` in some files, even though a BOM is unnecessary to determine UTF-8 endianness.

Some spreadsheet software accepts or expects a BOM in CSV files; many other parsers treat it as a `U+FEFF` character at the start of content and corrupt the first header name.

For each file format, specify:

- Is a BOM permitted?
- If so, where does the parser strip the BOM?
- Is a BOM written when exporting files?
- Test both permitted and prohibited cases.

Do not blindly remove every `U+FEFF` character anywhere without knowing the semantics; handling a leading BOM is an encoding/file-format-layer decision.

### 14.2. Newlines

Environments use different conventions:

- LF: `\n`.
- CRLF: `\r\n`.
- CR: `\r`, less common in modern files.

For CSV or text protocols, specify output newlines explicitly; when parsing, decide whether multiple newline styles are accepted. Avoid concatenating `System.lineSeparator()` into protocols requiring fixed LF, because it depends on the operating system.

### 14.3. Unicode Normalization

Two visually identical strings can use different code point sequences. For example, accented characters can appear in composed or decomposed form.

~~~java
import java.text.Normalizer;

String input = "Tiếng Việt";

String normalized =
        Normalizer.normalize(input, Normalizer.Form.NFC);

System.out.println(normalized);
~~~

Determine whether and at which boundary to normalize. Normalization can suit search, comparison, or IDs by design, yet should not be applied indiscriminately to:

- Text whose exact bytes must be preserved for digital signature verification.
- Signed or hashed payloads.
- Data where byte-level equality is required.
- Certain identifiers with dedicated rules.

In particular, when signing JSON/XML/text, two strings with the same visible content yet differing whitespace or normalization can yield different signatures. Specify canonicalization at the protocol layer or sign the exact bytes transmitted.

## 15. HTTP, JSON, CSV, and XML Have Different Encoding Rules

### 15.1. HTTP and Content-Type

For HTTP transmitting text, how bytes are interpreted depends on the media type and that format's rules. Some formats have a charset parameter, while others have their own rules.

For interoperable JSON across open systems, UTF-8 is the standard choice under modern JSON rules. Do not assume a Java character string sent over HTTP will automatically be encoded properly if the HTTP client or framework sets a different charset.

Check:

- Actual media type.
- What encoding produces the body bytes.
- What encoding the consumer uses to decode.
- Whether double-encoding or mistaken URL/form encoding occurs.
- Content-Length, if present, is calculated in bytes, not characters.

### 15.2. JSON Escaping Is Not Charset Encoding

A JSON string can emit:

~~~json
{
  "message": "Đã xử lý"
}
~~~

or use Unicode escapes for certain characters. After JSON serialization, the entire body still must be encoded into bytes using the transport charset. Backslash escapes in JSON and UTF-8 operate at two different layers.

Do not "fix Vietnamese diacritics" by manually replacing characters with escape strings outside proper JSON context.

### 15.3. CSV Needs a Schema Beyond Delimiters

CSV does not by itself carry enough information about:

- Column data types.
- Date-time formats.
- Number locale.
- Currency.
- Charset.
- Headers.
- Newlines and quoting behavior.

Canonical CSV example:

~~~csv
order_id,created_at,amount,currency,note
A-100,2026-11-12T09:30:00Z,1234.50,USD,Da thanh toan
~~~

If Vietnamese text is needed, encode the entire file in UTF-8 and explicitly specify the BOM policy. When columns contain commas, quotes, or newlines, use a CSV writer/parser adhering to escape/quote rules rather than concatenating strings manually.

### 15.4. Be Careful When Users Open CSVs in Spreadsheets

Spreadsheets may auto-guess date types, decimals, or strip leading zeros based on machine locale. A customer ID `"00123"` may be interpreted as the number 123. This does not mean the backend CSV lost bytes, rather that the spreadsheet consumer applied type inference.

For format-sensitive data, use a fixed import schema or a file format with explicit data types. If exporting CSV for users, provide import instructions and consider spreadsheet formula injection risks from cells starting with special characters per your data export security policy.

### 15.5. XML Encoding Declaration Must Match Bytes

XML example:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<order>
  <createdAt>2026-11-12T09:30:00Z</createdAt>
  <amount currency="USD">1234.50</amount>
</order>
~~~

The `encoding="UTF-8"` declaration is accurate only if bytes are actually written in UTF-8. A serializer using a different default charset while writing a UTF-8 declaration produces an inconsistent file.

XML also involves namespaces, schemas, entities, and canonicalization rules; when signing XML, whitespace and canonicalization must be controlled according to the applicable signature standard.

## 16. Serializers and Frameworks Are Part of the Contract

An application might not call `DateTimeFormatter` or `BigDecimal.toPlainString()` directly because JSON/XML/JDBC frameworks handle them.

When upgrading dependencies or the JDK, check:

- Does the serializer use `java.util.Date`, `Instant`, or `LocalDateTime`?
- Are timestamps written as text or numeric epochs?
- Are numeric epochs in seconds or millis?
- Does the formatter use UTC offset, local zone, or the default JVM timezone?
- Is BigDecimal serialized as a JSON number, string, or exponent notation?
- Does the parser read numbers into `Double` or `BigDecimal`?
- Is HTTP body/file encoding explicitly specified?
- Is there a `java.time` module/plugin, and does it have new default settings?
- Are there changes in Unicode escaping, null fields, property names, or schemas?

In particular, swapping a serializer can alter representation even when the DTO keeps the exact same field types.

### 16.1. DTOs Should Have Clear Semantics

~~~java
import java.math.BigDecimal;
import java.time.Instant;

public record PaymentEvent(
        String id,
        Instant occurredAt,
        BigDecimal amount,
        String currency,
        String note) {
}
~~~

A DTO expresses data types in Java; it **does not by itself prove** that JSON output produces the expected timestamp string, decimal format, and encoding. Configure the mapper and test the actual wire representation.

### 16.2. Do Not Treat Annotations as Sufficient Verification

An annotation on a DTO may control one framework's serializer, yet not apply if another producer uses a different framework or if a dependency version changes how the annotation is interpreted.

Contracts must be described in schemas and **tested at real boundaries**, not only by inspecting source code.

## 17. Testing Bidirectional Producer and Consumer Compatibility

When upgrading Java, many systems cannot deploy simultaneously. For a period there will be:

- Old producer → Old consumer.
- New producer → Old consumer.
- Old producer → New consumer.
- New producer → New consumer.

Test matrix:

| Producer | Consumer | Key Verification |
|---|---|---|
| Old | Old | Baseline of data already in production |
| New | New | New contract and new functionality work |
| New | Old | Does the old consumer understand new dates/decimals/charsets? |
| Old | New | Can the new consumer read old data/files/events? |

For example, a new producer starts emitting timestamps with nanoseconds, while an old consumer parses strictly three millisecond digits. Even though each side works fine independently, they can be incompatible.

Version the contract and choose one of the following approaches:

- Keep output within the range supported by both sides.
- Upgrade consumers before producers emit the new format.
- Accept multiple controlled input forms while emitting a single canonical form.
- Version endpoints, event schemas, or file formats for breaking changes.
- Provide adapters during the transition period.

Do not "fix" this by letting parsers guess every format if guessing can corrupt timestamps or money.

## 18. Building a Regression Dataset

### 18.1. Date-Time Case Suite

Select representative cases:

- UTC timestamps with `Z`.
- Timestamps with positive and negative offsets.
- Timestamps with and without fractional seconds.
- Values right around year transitions.
- Valid and invalid February 29 dates.
- DST gaps and overlaps in supported regions.
- Calendar dates without timezones.
- Epoch seconds/millis with explicit units.
- DB timestamp conversions with lower precision.
- Future schedule data when tzdb updates.

Do not test only "now" or a fixed non-DST date.

### 18.2. Decimal Case Suite

- `0` and `0.00`.
- Negative numbers, including `-0.0` if sources involve floating-point.
- Values smaller than 1 and very large numbers.
- Numbers with many decimal digits.
- `1.20` and `1.2` to check scale.
- Numbers in exponent notation if allowed by contract.
- Numbers near rounding boundaries.
- Strings containing grouping separators to verify parser rejection under canonical format.
- Data exceeding published precision/scale limits.
- Currencies with differing fractional-digit rules.

### 18.3. Text/Encoding Case Suite

- ASCII.
- Accented Vietnamese text.
- Emojis and characters outside the Basic Multilingual Plane.
- Combining marks and Unicode NFC/NFD.
- Malformed UTF-8 byte sequences.
- Leading file BOM.
- LF and CRLF.
- Strings containing quotes, commas, and newlines in CSV.
- JSON escapes.
- Significant leading/trailing whitespace.

### 18.4. Golden Tests and Normalized Values

For contracts requiring exact wire bytes, use **golden bytes** and checksums. For contracts requiring only timestamp instants, compare parsed `Instant` values. For decimals, compare by numeric value or scale depending on the schema. For Unicode, compare exact code points if that is the contract; normalize only when governed by a rule.

Do not force every test into exact string comparison or conversely ignore every difference. The comparison method must align with **business semantics**.

## 19. Step-by-Step Migration Procedure

~~~mermaid
flowchart TD
    A["Catalog date/number/text fields"] --> B["Define wire schema"]
    B --> C["Capture real data from the old version"]
    C --> D["Run producer and consumer on target JDK"]
    D --> E{"Do representation and semantics change?"}
    E -->|No| F["Save compatibility evidence"]
    E -->|Yes| G["Identify source: JDK, tzdb, locale, charset, mapper"]
    G --> H["Fix code or version the contract"]
    H --> I["Test old/new data bidirectionally"]
    F --> I
    I --> J["Roll out in order, monitor, rollback"]
~~~

### Step 1: Locate Data Conversion Points

Some search patterns in the project:

~~~bash
rg -n "DateTimeFormatter|SimpleDateFormat|Instant|OffsetDateTime|ZonedDateTime" src
rg -n "LocalDateTime|ZoneId|ZoneOffset|toEpochMilli|ofEpochSecond" src
rg -n "NumberFormat|DecimalFormat|BigDecimal|RoundingMode" src
rg -n "getBytes\\(|new String\\(|InputStreamReader|OutputStreamWriter" src
rg -n "Charset.defaultCharset|file.encoding|StandardCharsets" src
~~~

The examples use `rg` to aid searching. Also inspect serializers, schemas, database migrations, integration code, CSV export jobs, shell scripts, and framework configuration.

### Step 2: Build a Data Field Contract Ledger

| Field | Java type | Wire type | Format/encoding | Precision | Scope |
|---|---|---|---|---|---|
| `occurredAt` | `Instant` | JSON string | RFC 3339 UTC/offset | Millisecond | Event API |
| `businessDate` | `LocalDate` | JSON string | `uuuu-MM-dd` | Day | Accounting |
| `amount` | `BigDecimal` | Decimal string | Dot separator, no grouping | Scale per schema | Payment |
| `currency` | `String` | JSON string | Currency code | N/A | Payment |
| `description` | `String` | UTF-8 JSON text | Unicode | N/A | Event API |

The table is an example contract; actual values must be determined by your system.

### Step 3: Lock Down the Actual Baseline

Record:

- Artifact and checksum.
- Source JDK version/vendor.
- Target JDK version/vendor.
- OS/container image.
- Default locale, timezone, and charset.
- tzdb/rules where relevant.
- Serializer/library/driver versions.
- Actual byte payloads exchanged.

If upgrading both the JDK and dependencies simultaneously, isolate tests to see whether changes come from the runtime or from the framework.

### Step 4: Test Data from the Old Version

Keep old payloads and files as fixtures:

- Published JSON events.
- CSV/Excel import files from partners.
- DB records from different time periods.
- Messages potentially still lingering in queues.
- Digitally signed documents or files if signatures depend on bytes.

New consumers must be tested on **historical data**, not only on data produced by the new version.

### Step 5: Run Multi-JDK and Multi-Environment Tests

A practical matrix:

| Runtime | Producer | Consumer | Goal |
|---|---|---|---|
| Old JDK | Old | Old | Baseline |
| New JDK | New | New | Functionality |
| Mixed new/old JDK | New | Old | Backward compatibility |
| Mixed new/old JDK | Old | New | Forward reading |
| Target production container | New | Partner | Network/file integration |

Test both **byte representation** and **parsed values**, especially for monetary amount and timezone fields.

### Step 6: Roll Out Migration with Rollback Capability

For example, if an old consumer cannot read six-digit fractional seconds:

1. Upgrade consumers or introduce a parser accepting the specified format.
2. Verify new consumers can read old payloads.
3. Verify producers still emit the old format during the mixed phase.
4. Once consumers support it, expand precision if needed.
5. Monitor parse errors and enable rollback matching the contract version.

For legacy file charsets, a data conversion job with checksums and an audit trail may be needed. Do not alter digitally signed historical bytes without a dedicated procedure.

## 20. Diagnosing Common Errors

| Symptom | Possible Cause | What to Check |
|---|---|---|
| `DateTimeParseException` | Pattern/offset/locale/precision mismatch | Raw payload, formatter, and schema |
| Timestamp shifted by several hours | Confusing zone/offset or using default timezone | `Instant`, `ZoneId`, and conversion sites |
| Timestamp off by thousands of years | Confusing epoch seconds with millis | Field units, parser conversion |
| Schedule shifted by one hour | DST/tzdb or ambiguous local time | Valid offsets, JDK rules |
| `ArithmeticException` on decimal division | Rounding undefined for non-terminating division | `BigDecimal.divide` and policy |
| Monetary amount changes through JSON | Double/float losing precision | Mapper config and client numeric type |
| Number `1,234` parsed unexpectedly | Wrong locale/grouping | Canonical contract vs. UI parser |
| Garbled Vietnamese characters | Encoding/decoding charset mismatch | Raw bytes, `Content-Type`, UTF-8 |
| Strange character at start of CSV header | UTF-8 BOM treated as text | First three bytes of the file |
| Invalid JSON digital signature | Differing whitespace/encoding/canonicalization | Bytes before/after serialization |
| CSV splits columns incorrectly | Unquoted/unescaped commas/newlines | CSV writer/parser |
| Text exceeds length limit | Confusing `String.length()` with UTF-8 byte count | Measure code points and encoded bytes |
| Snapshot differs after JDK upgrade | Locale/CLDR/tzdb/formatter changed | Runtime version, locale, and code points |

An error message alone cannot confirm the root cause; collect **raw payloads/bytes**, artifact versions, and actual configuration. When logging business data, mask personal information, secrets, and sensitive content per regulations.

## 21. Design and Verification Checklist

### Date-Time

- [ ] Each field is defined as an instant, local date, local time, or zone-based schedule.
- [ ] Wire timestamps include an offset/UTC when the contract requires an instant.
- [ ] Pattern and precision are explicitly documented.
- [ ] Do not use `LocalDateTime` without a zone to represent event timestamps.
- [ ] Verified epoch units.
- [ ] Checked DST gaps/overlaps and zone rules.
- [ ] Checked JDBC/ORM/database conversions.
- [ ] Handled invalid date inputs using an appropriate parse policy.

### Decimals and Currency

- [ ] Machine-readable data does not rely on default `NumberFormat`.
- [ ] Decimal grammar, scale, and precision are specified.
- [ ] Used `BigDecimal` or an approved representation when precision is required.
- [ ] An explicit rounding policy exists.
- [ ] Currency is passed via a separate identifier.
- [ ] Checked whether clients use IEEE 754 double.
- [ ] Tested exponents, trailing zeros, and large values.
- [ ] Do not use display currency symbols as transaction identifiers.

### Character Encodings and Unicode

- [ ] Charset is specified explicitly at boundaries.
- [ ] Checked default charset when upgrading across JDK versions.
- [ ] Defined how legacy files are read.
- [ ] Tested BOM, newlines, and malformed UTF-8 input.
- [ ] Tested Vietnamese Unicode strings, combining marks, and emojis.
- [ ] Distinguished character count from byte length.
- [ ] Determined whether and at which step Unicode normalization is applied.
- [ ] Checked JSON/CSV/XML escaping and raw transport bytes.

### Migration

- [ ] Documented the contract for each critical field.
- [ ] Saved the baseline from old JDK/producer/consumer.
- [ ] Ran tests on the target JDK and container.
- [ ] Tested old consumer with new producer and vice versa.
- [ ] Tested historical data and new payloads.
- [ ] Identified breaking changes and versioning strategy.
- [ ] Set up monitoring for parse errors, rounding discrepancies, time shifts, and encoding issues.
- [ ] Prepared rollback when format changes affect transactions.

## Conclusion

In data exchange, **date-time, decimals, and character encodings** are parts of the contract between systems. Java provides `java.time` to model time, `BigDecimal` for exact decimals, and `Charset`/`StandardCharsets` to control text-to-bytes conversion. Yet those APIs achieve compatibility only when applications **explicitly specify representation, precision, offset/zone, rounding, and charset**.

When upgrading the JDK or dependencies, avoid default locales/timezones/charsets at communication boundaries, do not use presentation strings as machine data, and do not let parsers guess ambiguous fields. Collect old data, inspect raw bytes and parsed values across both producer–consumer directions, and deploy changes under versioned contracts. That is how to preserve **data accuracy and compatibility** even as the Java platform continues to evolve.
