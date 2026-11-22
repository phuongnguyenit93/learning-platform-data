# ISO-8601 Conventions and Explicit Offsets on Exchange Interfaces

## 1. Why Can a Well-Formatted Date-Time String Still Be Ambiguous?

Two services both receive the string `2024-08-20T09:15:30`. Service A interprets it as Vietnam time, while Service B interprets it as UTC. Both can read the year, month, day, and time, yet they produce two instants seven hours apart.

The problem does not lie in the hyphens or the letter `T`. The string lacks information linking the local time to UTC. When a data field means **the instant an event occurred**, the exchange interface must transmit enough information for the receiver to determine the exact same instant.

The following three examples have different meanings:

| String | Information Present | Does It Identify an Instant? |
| --- | --- | --- |
| `2024-08-20` | A calendar date | No; it could be a birth date or a business date |
| `2024-08-20T09:15:30` | Local date and time | Not yet, without an accompanying time zone rule |
| `2024-08-20T09:15:30+07:00` | Date, time, and offset from UTC | Yes |

This lesson focuses on instant strings on exchange interfaces between systems: JSON fields, messages, import/export data, or communication parameters. Not all date-time data needs an offset; this requirement depends on the meaning of the field.

The goal is to know how to read offsets, choose the appropriate Java type, and build a testable contract, rather than merely writing "ISO format".

## 2. ISO-8601 Is the Foundation; an API Contract Needs to Be More Specific

ISO-8601 covers many ways of representing dates and times. In the Java ecosystem, you encounter extended date formats, basic formats, ordinal dates, week dates, and various time/offset combinations. Therefore, the label "ISO-8601" does not answer all implementation questions.

An exchange contract needs to lock down at least:

- Does the field represent a date, a local date-time, or an instant?
- Is an offset required? Does it accept `Z`, `+00:00`, `+07:00`, or other forms?
- Are seconds required? How many digits are allowed for fractional seconds?
- Is a zone name such as `Asia/Ho_Chi_Minh` accepted in the same string?
- Are lowercase letters, spaces, expanded years, leap seconds, or 24:00 accepted?
- Does the output normalize to UTC or preserve the input offset?
- How are missing values, invalid values, and out-of-range values handled?

RFC 3339 is a convention for Internet timestamps, built as a profile of ISO-8601. You should not assume every string that Java can parse with a formatter named ISO is a contract-compliant RFC 3339 string. See [RFC 3339](https://www.rfc-editor.org/rfc/rfc3339.html).

In this lesson, we will choose **one example contract with clear boundaries** and implement it. That contract is not a validator for all of ISO-8601 or all of RFC 3339.

## 3. Reading Offsets in the Right Direction

An offset is the difference of local time relative to UTC:

```text
local time = UTC + offset
UTC = local time - offset
```

Example:

```text
2024-08-20T09:15:30+07:00
              ↓ same instant
2024-08-20T02:15:30Z
```

`+07:00` means the written time is seven hours ahead of UTC. Converting to UTC requires subtracting seven hours. With a negative offset, subtracting a negative offset increases the UTC hour and may change the date.

`Z` represents an instant with a zero offset for calculation purposes. `+00:00` also has an arithmetic offset of zero. Do not conclude that two strings represent different instants just because one uses `Z` and the other uses `+00:00`.

### 3.1 An Offset Is Not a Zone Name

`+07:00` refers to an offset. `Asia/Ho_Chi_Minh` is a zone name with rules over time. Multiple zones can share the same offset at a given point in time, so you cannot uniquely reverse-infer a zone name from `+07:00`.

A timestamp with an offset is suitable for identifying an instant that has already occurred. A meeting schedule of "09:00 every Monday in New York" also needs the zone and local calendar rules; keeping only the offset of the first meeting is not enough for subsequent occurrences when time rules change.

If both the instant and the business zone are needed, you can design two separate fields or use an extended format agreed upon by both parties:

```json
{
  "occurredAt": "2024-08-20T02:15:30.000Z",
  "displayZone": "Asia/Ho_Chi_Minh"
}
```

The name `displayZone` in the example is a zone for presentation purposes. For a future appointment, the meaning of the zone may belong to the appointment rule itself; more appropriate naming and contract design are needed.

### 3.2 Do Not Infer Additional Meaning from Z

In a Java program, `Z` and `+00:00` both resolve to an offset of 0. However, a protocol may further distinguish whether the local offset information is known or unknown.

RFC 9557 updates RFC 3339's interpretation of `Z` while also defining an extended syntax containing information such as zone names. Therefore, do not automatically infer that a string ending in `Z` proves the sender lives in the UTC time zone. See [RFC 9557: updates to RFC 3339](https://www.rfc-editor.org/rfc/rfc9557.html#section-2).

If you need to preserve differences in representation or source information status, store that metadata separately. `OffsetDateTime` does not preserve every character-level difference or additional protocol meaning after parsing.

## 4. Choosing a Java Type Based on Exchanged Content

| Requirement | Usually Suitable Type | Notes |
| --- | --- | --- |
| A date only | `LocalDate` | E.g., `2024-08-20`; do not add an offset on your own |
| Local date-time under a private contract | `LocalDateTime` | Does not identify an instant on its own |
| Date-time with input offset | `OffsetDateTime` | Preserves the arithmetic offset |
| Normalized instant for comparison/storage | `Instant` | Does not preserve the sender's offset |
| Date-time bound to zone rules | `ZonedDateTime` | Requires a zone name convention when exchanging |

`OffsetDateTime` stores a date-time and an offset; `Instant` represents an instant; `ZonedDateTime` adds zone rules. This distinction is described in [Java SE 21 OffsetDateTime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/OffsetDateTime.html).

Example of reading a timestamp field with an offset:

```java
OffsetDateTime received = OffsetDateTime.parse(
        "2024-08-20T09:15:30+07:00",
        DateTimeFormatter.ISO_OFFSET_DATE_TIME);
Instant eventTime = received.toInstant();
```

This is an object conversion step; do not manually add or subtract seven hours after `toInstant()`. The offset in the string has already been used to determine the instant.

## 5. A Standard Formatter Does Not Replace the Entire Contract

`DateTimeFormatter.ISO_OFFSET_DATE_TIME` is a good choice for handling date-times with offsets, but what it accepts is broader than many specific API contracts. For example, the formatter can accept an offset with a seconds component; the minutes part of the offset can be omitted during parsing.

`ISO_DATE_TIME` also allows optional parts such as an offset or zone name. Choosing it and assuming "an offset is always required" easily leaves gaps in input validation.

When formatting, `ISO_INSTANT` produces a UTC representation with `Z`, but the number of fractional second digits can vary depending on the value. The formatter name does not inherently guarantee "always exactly three millisecond digits". These differences are noted in [DateTimeFormatter: Predefined Formatters](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html#predefined).

A readable implementation consists of two layers:

```text
Check shape belonging to the contract
                 ↓
Parse and validate date/time/offset validity
                 ↓
Convert to business type
                 ↓
Format in normalized output form
```

Shape checking cannot on its own prove that February 29 is valid. Successfully parsing with a broad formatter also does not prove that the string belongs to the exact set of forms published by the API. The two layers complement each other.

## 6. A Concrete Exchange Contract

Suppose the `occurredAt` field is an event instant, and the target system supports milliseconds. We choose the following convention for the example:

| Component | Chosen Convention |
| --- | --- |
| Date | `uuuu-MM-dd`, years 0001–9999 |
| Date/time separator | Uppercase letter `T` |
| Time | `HH:mm:ss`, seconds required |
| Fractional seconds | None or 1–3 digits after the dot |
| Offset | Required uppercase `Z` or `±HH:mm` |
| Offset range | Java-supported range, from -18:00 to +18:00; both ends have minutes equal to 00 |
| Excluded forms | Reject `-00:00`, zone names in brackets, seconds in offset, leap seconds, 24:00, extra whitespace |
| Output format | UTC, `Z`, always exactly three fractional second digits |
| Output range | After converting to UTC, must still fall within years 0001–9999 |

These are choices for this example, not a statement that the ISO standard forbids all excluded forms. Rejecting `-00:00` is a decision of this contract to avoid accepting a representation that might carry additional meaning the model cannot preserve.

Input `.1` corresponds to 100 milliseconds; `.12` corresponds to 120 milliseconds; `.123` corresponds to 123 milliseconds. Forms like `.1234` are rejected, even if a general-purpose parsing library can read them.

When normalizing, the original offset is no longer present in the output string. If audit requirements need to preserve the original string verbatim, store it separately alongside the validated value with a clear purpose.

## 7. Program to Verify the Contract

Save as `IsoExchangeContractDemo.java`. The program uses standard Java without needing a JSON library because the focus is on the rules of a single text field.

```text
javac --release 17 IsoExchangeContractDemo.java
java IsoExchangeContractDemo
```

```java
import java.time.DateTimeException;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.util.regex.Pattern;

public class IsoExchangeContractDemo {
    private static final Pattern WIRE = Pattern.compile(
            "[0-9]{4}-[0-9]{2}-[0-9]{2}T"
            + "[0-9]{2}:[0-9]{2}:[0-9]{2}"
            + "(?:[.][0-9]{1,3})?"
            + "(?:Z|[+-][0-9]{2}:[0-9]{2})");

    private static final DateTimeFormatter OUTPUT =
            new DateTimeFormatterBuilder().appendInstant(3).toFormatter();

    private static OffsetDateTime parseWire(String text) {
        if (text == null || !WIRE.matcher(text).matches()
                || text.endsWith("-00:00")) {
            throw new IllegalArgumentException("Invalid timestamp shape");
        }
        try {
            OffsetDateTime parsed = OffsetDateTime.parse(
                    text, DateTimeFormatter.ISO_OFFSET_DATE_TIME);
            if (parsed.getYear() < 1 || parsed.getYear() > 9999) {
                throw new IllegalArgumentException("Local year out of range");
            }
            canonical(parsed.toInstant());
            return parsed;
        } catch (DateTimeException ex) {
            throw new IllegalArgumentException("Invalid timestamp value", ex);
        }
    }

    private static String canonical(Instant instant) {
        if (instant == null || instant.getNano() % 1_000_000 != 0) {
            throw new IllegalArgumentException("Millisecond precision required");
        }
        int year = instant.atOffset(ZoneOffset.UTC).getYear();
        if (year < 1 || year > 9999) {
            throw new IllegalArgumentException("UTC year out of range");
        }
        return OUTPUT.format(instant);
    }

    private static void check(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    private static boolean rejected(String input) {
        try {
            parseWire(input);
            return false;
        } catch (IllegalArgumentException expected) {
            return true;
        }
    }

    public static void main(String[] args) {
        OffsetDateTime localOffset = parseWire(
                "2024-08-20T09:15:30+07:00");
        OffsetDateTime utc = parseWire("2024-08-20T02:15:30Z");
        check(localOffset.isEqual(utc), "same instant");
        check(!localOffset.equals(utc), "different local fields and offsets");
        System.out.println("same-instant=" + localOffset.isEqual(utc));
        System.out.println("same-offset-date-time=" + localOffset.equals(utc));
        System.out.println("canonical=" + canonical(localOffset.toInstant()));

        OffsetDateTime fractional = parseWire(
                "2024-08-20T09:15:30.12+07:00");
        check(fractional.getNano() == 120_000_000, "fraction scale");
        String normalized = canonical(fractional.toInstant());
        check(normalized.equals("2024-08-20T02:15:30.120Z"),
                "fixed millisecond output");
        check(parseWire(normalized).toInstant().equals(fractional.toInstant()),
                "canonical round trip");
        check(canonical(parseWire(normalized).toInstant()).equals(normalized),
                "canonical idempotence");
        check(parseWire("2024-08-20T02:15:30+00:00")
                .toInstant().equals(utc.toInstant()), "zero offset");
        System.out.println("fractional-canonical=" + normalized);

        String[] bad = {
            "2024-08-20T09:15:30",
            "2024-08-20T09:15+07:00",
            "2024-08-20 09:15:30+07:00",
            "2024-08-20t09:15:30z",
            "2024-08-20T09:15:30+0700",
            "2024-08-20T09:15:30+07",
            "2024-08-20T09:15:30+07:00:30",
            "2024-08-20T09:15:30+07:00[Asia/Ho_Chi_Minh]",
            "2024-02-30T09:15:30Z",
            "2024-08-20T24:00:00Z",
            "2016-12-31T23:59:60Z",
            "2024-08-20T09:15:30.1234Z",
            "2024-08-20T09:15:30-00:00",
            "2024-08-20T09:15:30+18:01",
            "0000-01-01T00:00:00Z",
            "0001-01-01T00:00:00+01:00",
            "2024-08-20T09:15:30Z ",
            null
        };
        int rejectedCount = 0;
        for (String input : bad) {
            check(rejected(input), "must reject: " + input);
            rejectedCount++;
        }
        System.out.println("rejected=" + rejectedCount + "/" + bad.length);

        boolean preciseRejected = false;
        try {
            canonical(Instant.parse("2024-08-20T02:15:30.000000001Z"));
        } catch (IllegalArgumentException expected) {
            preciseRejected = true;
        }
        check(preciseRejected, "do not silently discard nanos");
        System.out.println("excess-precision-rejected=" + preciseRejected);

        String a = "2024-01-01T00:30:00+01:00";
        String b = "2023-12-31T23:45:00Z";
        check(a.compareTo(b) > 0, "textual order");
        check(parseWire(a).toInstant().isBefore(parseWire(b).toInstant()),
                "chronological order");
        System.out.println("text-a-after-b=" + (a.compareTo(b) > 0));
        System.out.println("instant-a-before-b="
                + parseWire(a).toInstant().isBefore(parseWire(b).toInstant()));
        System.out.println("PASS");
    }
}
```

Output:

```text
same-instant=true
same-offset-date-time=false
canonical=2024-08-20T02:15:30.000Z
fractional-canonical=2024-08-20T02:15:30.120Z
rejected=18/18
excess-precision-rejected=true
text-a-after-b=true
instant-a-before-b=true
PASS
```

### 7.1 Why Check the Shape Before Parsing?

The regular expression restricts the exact character set and chosen format. `matches()` requires matching the entire string, so it does not accept trailing characters. It also does not automatically `trim()`; whitespace outside the contract is rejected.

The `OffsetDateTime.parse(...)` step checks calendar date validity and time/offset ranges. The string `2024-02-30T09:15:30Z` has a valid shape, yet it is still rejected at this step.

The `canonical(...)` step checks precision and the UTC year. Data near the start of year 0001 with a positive offset can shift into year 0000 in UTC; the example proactively rejects that case because the output must stay within the published range.

### 7.2 Why Not Let the Formatter Truncate Nanoseconds?

`appendInstant(3)` ensures exactly three fractional digits when formatting. However, if the internal value has sub-millisecond parts, you need to decide upfront whether to reject, truncate, or round.

The example chooses to reject excess precision, so `canonical` checks divisibility by one million nanoseconds before formatting. Inputs from `parseWire` already have at most three digits; this check also protects against calling `canonical` directly with an `Instant` created elsewhere.

### 7.3 Why Does equals Return false for the Same Instant?

The first two `OffsetDateTime` objects in the program hold different local fields and offsets. `equals` checks that representation as well. `isEqual` or comparing `toInstant()` checks for the same instant.

When deduplicating events, do not use the raw string as the representative for the instant if the protocol allows multiple offsets. Conversely, if you need to keep the sender's offset for auditing, storing only `Instant` will not meet all requirements.

## 8. Input with Offset, Normalized Output: What Is Preserved?

Normalizing the two strings:

```text
2024-08-20T09:15:30+07:00
2024-08-20T02:15:30Z
```

into the same form:

```text
2024-08-20T02:15:30.000Z
```

preserves the instant and precision of the example. It changes the spelling, local hour, displayed offset, and number of fractional digits.

A good contract distinguishes two types of round-trips:

| Requirement | What Can Be Tested |
| --- | --- |
| Semantic round-trip | Parse, format, then parse again still yields the same `Instant` |
| Verbatim round-trip | The final string matches the initial string character-for-character |

The example only guarantees a semantic round-trip and stability of the normalized form. If verbatim preservation is needed, the source string must be stored separately; do not expect `toString()` to remember it.

Do not append `Z` to the end of a `LocalDateTime` via simple string concatenation. That action declares offset 0 without having determined the instant from the source. You must know the true time zone/offset and convert the meaning properly before formatting.

## 9. Sorting and Comparing Exchanged Data

Two input strings with different offsets are not guaranteed to have lexicographical order match chronological order. The end of the program provides a counterexample:

- `2024-01-01T00:30:00+01:00` is 23:30 UTC on 2023-12-31.
- `2023-12-31T23:45:00Z` occurs 15 minutes later.

The year in the first string is larger, yet the instant is earlier. Parse and compare `Instant` when data is not normalized.

Only when all strings share UTC, the same year width, and the same fixed precision—like the example's output—does lexicographical order have the conditions to match chronological order. Do not apply this conclusion to sets of strings with different widths, offsets, or fractional parts.

Event ordering may also require a secondary key when multiple events share the same millisecond. A time format does not on its own provide uniqueness or a total order for simultaneous events.

## 10. Bringing the Convention into a Real Exchange Interface

For a JSON field like `occurredAt`, documentation must state the meaning and validation rules, not just a nice example. You can publish:

```text
occurredAt:
- The instant when the event occurred.
- Accepts years 0001–9999, seconds required, and up to 3 fractional digits.
- Offset required: Z or ±HH:mm within the published range.
- Returns UTC with exactly 3 millisecond digits.
- Does not fall back to the server's time zone when offset is missing.
- Missing, null, blank, or invalid values are reported according to the error contract.
```

This is a condensed description; the excluded cases in the contract table still need to be documented in the full specification.

If using a JSON serializer/deserializer, verify that it actually reads and writes according to this contract. Declaring `Instant` or `OffsetDateTime` in Java does not automatically prove that the library configuration satisfies the fractional digit count, offset set, or error policy.

Do not use human-readable formats like `20/08/2024 09:15` as a machine protocol when the contract requires a timestamp with an offset. The user interface can display according to locale; exchanged data should still follow the agreed convention.

If the instant is in a query string or form, it must be encoded at the protocol layer. The `+` sign of an offset can be decoded as a space by the form layer if parameters are concatenated raw. Use an appropriate URI/form builder and check the decoded value, rather than patching it with arbitrary string replacements in the date-time parser.

## 11. Common Pitfalls

| Pitfall | Consequence | Fix |
| --- | --- | --- |
| Accepting a string missing an offset and using the server's time zone | Different results across environments | Reject per contract or require the zone in an explicit field |
| Appending `Z` to local time | Wrongly assigns offset 0, shifting the instant | Interpret using the right zone/offset, then normalize |
| Using a formatter broader than the spec without extra checks | Accepts forms that partners do not support | Restrict the shape and validate values |
| Calling `toString()` expecting seconds and three fractional digits always | Output format may be inconsistent | Use a specific output formatter and write tests |
| Treating `+07:00` as a unique zone name | Loses local rules for future schedules | Pass `ZoneId` when business logic requires it |
| Silently truncating fractional parts | Loss of precision | Explicitly decide reject/truncate/round and test it |
| Sorting strings with different offsets directly | Wrong chronological order | Compare `Instant` |
| Assuming the `[Asia/Ho_Chi_Minh]` suffix is accepted by all APIs | Compatibility errors | Use only when both sides publish support for the same format |

A zone name suffix in a Java string is not a reason to assume a parser supports every Internet extended format. If choosing RFC 9557 or another extended contract, define the syntax, metadata, and behavior when the offset does not match the zone according to that protocol.

## 12. Practice and Self-Check

### Exercise 1 — Identifying Missing Information

The `paidAt` field receives `2024-08-20T09:15:30`. Can it be assumed to be UTC because the server runs in UTC?

**Solution hint:** only if the contract explicitly defines it that way; under the contract in this lesson, it must be rejected for missing an offset. The server's time zone is not a fact about the sender.

### Exercise 2 — Converting in the Right Direction

What UTC time does `2024-08-20T09:15:30-04:00` correspond to?

**Solution hint:** 13:15:30 UTC on the same day. Subtracting a negative offset means adding four hours. Use `OffsetDateTime.parse(...).toInstant()` to verify.

### Exercise 3 — Preserve the Instant or Preserve the Representation?

A partner sends `2024-08-20T09:15:30+07:00`, and the system returns `2024-08-20T02:15:30.000Z`. Was the original instant lost?

**Solution hint:** the instant is preserved. The offset and spelling were normalized. If sender context needs to be stored, add separate data per the contract.

### Exercise 4 — Expanding Precision

A new partner needs microseconds. Should you simply remove the three-digit check on input?

**Solution hint:** not enough. You must update the storage model, output formatter, conversion policy for legacy systems, and round-trip tests. If the output remains three digits, the extra received data may be lost.

### Exercise 5 — Building a Contract Test Suite

Add cases for a valid leap day, invalid leap day, negative offset, date change when converting to UTC, fractional parts `.0`, `.001`, strings with trailing characters, and unsupported zone names.

**Solution hint:** each case must explicitly assert acceptance or rejection. For accepted values, check `Instant`, normalized output, and re-parsing. Do not just check "no exception thrown".

### Exercise 6 — Designing a Date-Only Field

A `birthDate` field only records a birth date. Should you force sending `2000-01-01T00:00:00Z` so that every field has an offset?

**Solution hint:** no, if the meaning is only a date. Choose `2000-01-01` and `LocalDate`. The explicit offset requirement should be applied properly to fields representing instants, avoiding assumptions that do not belong to the data.
