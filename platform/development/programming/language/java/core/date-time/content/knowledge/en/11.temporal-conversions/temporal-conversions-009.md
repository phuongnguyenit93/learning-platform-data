# Identifying Conversions That Lose Date, Time Zone, or Precision in `java.time`

When converting between Java date-time types, the danger is not only whether "the program compiles," but also **which meaning has been discarded**. A very short statement like `zoned.toLocalDate()` can be right when you want a calendar date, but wrong if the target value is used as an event timestamp.

There are three groups of information to check separately:

1. **Local date and time** — do you still know the year, month, day, and hour/minute/second?
2. **Time zone/offset and absolute point in time** — can you still determine a unique `Instant`? Do you still know the geographical region `ZoneId`?
3. **Precision** — are seconds, milliseconds, microseconds, and nanoseconds preserved, or are they truncated/rounded?

**Key principle:** "Information loss" depends on the intended use. Converting a `ZonedDateTime` to a `LocalDate` is reasonable if you only need *the date in the chosen zone*. However, that is **not** a conversion that preserves an event in UTC.

## 1. Information Map of Common Date-Time Types

| Java Type | Has calendar date? | Has local time? | Has offset/ZoneId? | Has unique UTC instant? |
| --- | --- | --- | --- | --- |
| `LocalDate` | Yes | No | No | No |
| `LocalTime` | No | Yes | No | No |
| `LocalDateTime` | Yes | Yes | No | No |
| `OffsetTime` | No | Yes | Offset, but **missing date** | Does not identify an event on the timeline without a date |
| `OffsetDateTime` | Yes | Yes | Offset; **no region ID** | Yes |
| `ZonedDateTime` | Yes | Yes | `ZoneId` and resolved offset | Yes |
| `Instant` | Does not store local date/time | Does not store local time | Does not store display zone/offset | Yes |

An `Instant` can still **be represented** as a UTC date-time (for example, `2026-01-15T00:30:45Z`); saying it "does not store a local date" means it does not inherently carry a date in `Asia/Ho_Chi_Minh`, `Europe/Paris`, or any specific region.

An `OffsetDateTime` has an offset like `+07:00`, but it does not know whether that is `Asia/Ho_Chi_Minh` or another region also using `+07:00`. A region `ZoneId` has offset rules that change over time; a `ZoneOffset` is an offset at a point in time or a fixed offset.

### Three Questions Before Every Conversion

- **What fields does the source value have?** For example, a `ZonedDateTime` contains a local date-time, a zone ID, and an offset.
- **What fields does the target value retain?** For example, `LocalDateTime` has no zone/offset.
- **To reverse it, do you need to ask for or store additional data?** For example, from a `LocalDateTime` you cannot necessarily determine a single instant, especially during a DST overlap.

If a conversion needs to automatically "add 00:00", "pick a default zone", or "drop fractional seconds", that is a sign to review the data contract.

## 2. Conversions Prone to Losing Date, Time, or Time Zone

### 2.1. `LocalDateTime → LocalDate`: Keeps the Date, Loses All Time

~~~java
LocalDateTime appointment =
        LocalDateTime.of(2026, 1, 15, 7, 30, 45, 123_456_789);

LocalDate dateOnly = appointment.toLocalDate();
// 2026-01-15
~~~

In the snippet above (placed inside a method with `java.time` types imported), the fields `07:30:45.123456789` **are not in `dateOnly`**. From `LocalDate`, it is impossible to tell whether the appointment originally took place at 07:30 or 18:30.

If you call `dateOnly.atStartOfDay()`, you get a **`LocalDateTime` with time 00:00**; that is a **newly assumed time**, not a recovery of the original time. This is especially important when handling appointments, payment events, and audit data.

`LocalDate` is still the **right** type for birth dates, invoice dates, or regulation effective dates when the business domain only asks **which date on the calendar**.

### 2.2. `LocalDateTime → LocalTime`: Keeps the Time, Loses the Date

~~~java
LocalDateTime recorded =
        LocalDateTime.of(2026, 1, 15, 23, 45);

LocalTime timeOnly = recorded.toLocalTime();
// 23:45
~~~

You cannot recover the **date 2026-01-15** from `timeOnly`. If a record the next day also shows `23:45`, the two records have the same `LocalTime` but are not necessarily the same event.

Only use `LocalTime` when the data truly represents a time of day, such as "the store opens at 09:00 every day." When an event must have an exact date, use a type that carries the full date or store the date as a separate field.

### 2.3. `ZonedDateTime → LocalDateTime`: Drops Zone and Offset

~~~java
Instant event = Instant.parse("2026-01-15T00:30:45.123456789Z");
ZonedDateTime inVietnam =
        event.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));

LocalDateTime local = inVietnam.toLocalDateTime();
// 2026-01-15T07:30:45.123456789
~~~

`local` still keeps **all date, time, and nanosecond fields** of the Vietnam representation, but **no longer has `Asia/Ho_Chi_Minh` and `+07:00`**. If you only store `local`, later readers will not know which offset to use to convert back to UTC.

Specifically on a DST overlap day, **two different instants can share the same `LocalDateTime`**. Therefore, converting `ZonedDateTime → LocalDateTime` can lose the uniqueness of the point in time, even though the wall-clock date/time does not change.

### 2.4. `ZonedDateTime → OffsetDateTime`: Drops Region Name, Keeps Offset

~~~java
OffsetDateTime withOffset = inVietnam.toOffsetDateTime();
// 2026-01-15T07:30:45.123456789+07:00
~~~

This `OffsetDateTime` **still uniquely identifies the instant**, because date-time + offset is enough to derive UTC. However, it **no longer has the region ID `Asia/Ho_Chi_Minh`**. If you use the result as a template for next month's recurring schedule, the offset `+07:00` does not contain the historical and future time zone rules of a locality.

**Do not equate "losing zone" with "losing instant":** `ZonedDateTime → OffsetDateTime` preserves the instant, but loses the *region ID*. If the application only needs the event timestamp, losing the region name may be acceptable; if you need wall-clock appointments in a specific location, do not drop the zone.

### 2.5. `ZonedDateTime → Instant`: Keeps the Event, Drops the Regional Representation

~~~java
Instant timestamp = inVietnam.toInstant();
// 2026-01-15T00:30:45.123456789Z
~~~

This conversion **does not lose the absolute point in time** and preserves nanoseconds. However, the `Instant` value no longer records that the user viewed the event in Vietnam. If you later convert the timestamp to `America/Los_Angeles`, you will see **January 14**, not January 15.

To restore *the same representation in the original zone*, you must **still know the original `ZoneId`** and use the appropriate time zone rules:

~~~java
ZonedDateTime restored =
        timestamp.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
~~~

This recovery relies on **external zone information**, not because `Instant` itself contains a zone. If the time zone rules database is updated, reconstructing historical displays in special cases may also need to account for audit requirements.

### 2.6. `Instant → LocalDate`: Must Choose a Zone First, Then Extract the Date

`Instant` does not have a direct `toLocalDate()` method; you must convert through a zone:

~~~java
Instant event = Instant.parse("2026-01-15T00:30:45.123456789Z");

LocalDate vietnamDate =
        event.atZone(ZoneId.of("Asia/Ho_Chi_Minh")).toLocalDate();
// 2026-01-15

LocalDate losAngelesDate =
        event.atZone(ZoneId.of("America/Los_Angeles")).toLocalDate();
// 2026-01-14
~~~

**Two different dates from the same instant is completely valid.** The mistake is taking `LocalDate` using the server's zone without explicitly specifying which zone the business logic requires.

Once you pick a `LocalDate`, you also lose **hours, minutes, seconds, and nanoseconds**. For example, `vietnamDate.atStartOfDay(zone).toInstant()` produces **`2026-01-14T17:00:00Z`**, which does not equal the original event `2026-01-15T00:30:45.123456789Z`. Do not treat `atStartOfDay` as the inverse of `toLocalDate`.

## 3. Classification Table: Which Conversion Loses What, and Which Still Keeps the Instant?

| Conversion | Retained data | Dropped / assumed data | Can automatically return to original value? |
| --- | --- | --- | --- |
| `localDateTime.toLocalDate()` | Year/month/day | All hours/minutes/seconds/nanoseconds | **No** |
| `localDateTime.toLocalTime()` | Hours/minutes/seconds/nanoseconds | Year/month/day | **No** |
| `zoned.toLocalDateTime()` | Local date-time, nanoseconds | Zone ID, offset, so instant can be lost | **Not guaranteed** |
| `zoned.toOffsetDateTime()` | Local date-time, offset, instant | Region `ZoneId` | Only if the region is known again |
| `zoned.toInstant()` | Instant, nanoseconds | Zone ID and local display representation | Restores zoned view if zone is known |
| `instant.atZone(zone)` | Instant and precision | Does not lose instant; **adds** zone representation | `toInstant()` returns the exact instant |
| `offsetDateTime.toInstant()` | Instant, nanoseconds | Original local date-time and offset | Cannot know original offset unless stored |
| `instant.truncatedTo(SECONDS)` | Time down to seconds | Sub-second fraction | **No** |
| `Instant.ofEpochMilli(instant.toEpochMilli())` | Timestamp down to milliseconds | Remaining micro/nanosecond fraction | **No** if source has sub-millisecond fraction |
| `Date.from(instant).toInstant()` | Timestamp down to milliseconds | Sub-millisecond fraction | **No** if source has sub-millisecond fraction |
| `format("uuuu-MM-dd HH:mm")` | Displayed date, hour, and minute | Seconds, nanoseconds, offset, and zone if not written into string | **No** |

"Loss" in this table means **the target value does not carry enough information on its own to automatically reconstruct the source value**, not that the JVM erases the contents of the source variable. `java.time` types are immutable; the original object still exists if a reference to it is kept.

## 4. Two Different Issues: Losing the Time Zone vs. Changing the UTC Instant

A method can **change the display representation** while preserving the point in time:

~~~java
Instant event = Instant.parse("2026-01-15T00:30:45.123456789Z");

ZonedDateTime hcm =
        event.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
ZonedDateTime la =
        hcm.withZoneSameInstant(ZoneId.of("America/Los_Angeles"));

System.out.println(hcm.toInstant().equals(la.toInstant()));
// true
~~~

The wall-clock date and time change, even the calendar date changes, but **the instant does not change**. This is not an event information-loss bug.

Conversely, attaching a zone/offset to a `LocalDateTime` can create or change the instant meaning:

~~~java
LocalDateTime local =
        LocalDateTime.of(2026, 1, 15, 7, 30);

OffsetDateTime withPlusSeven =
        local.atOffset(ZoneOffset.ofHours(7));
// 2026-01-15T07:30+07:00

OffsetDateTime withMinusFive =
        local.atOffset(ZoneOffset.ofHours(-5));
// 2026-01-15T07:30-05:00
~~~

Here, **the same local date-time** with two offsets creates **two different instants** 12 hours apart. `atOffset` **does not guess** a geographical region; the offset supplied by the caller must come from a trustworthy data contract.

Further distinction:

- `OffsetDateTime.withOffsetSameInstant(newOffset)` keeps the instant and changes the wall-clock time.
- `OffsetDateTime.withOffsetSameLocal(newOffset)` keeps the wall-clock time and **changes the instant**.
- `ZonedDateTime.withZoneSameInstant(zone)` keeps the instant and changes the zoned representation.
- `ZonedDateTime.withZoneSameLocal(zone)` tries to keep the local date-time and **can change the instant**.

**Does a conversion change the instant?** Check directly with `source.toInstant().equals(result.toInstant())` when both types support `toInstant()`, rather than just looking at the hour numbers in the UI.

## 5. DST Proves Why Losing the Offset Can Lose Reversibility

Consider `Europe/Paris` on **2024-10-27**, at the end of daylight saving time. Local time **02:30 occurs twice**:

~~~java
ZoneId paris = ZoneId.of("Europe/Paris");
LocalDateTime overlap = LocalDateTime.of(2024, 10, 27, 2, 30);

System.out.println(paris.getRules().getValidOffsets(overlap));
// [+02:00, +01:00]

ZonedDateTime first = overlap.atZone(paris);
ZonedDateTime second = first.withLaterOffsetAtOverlap();

// first : 2024-10-27T02:30+02:00[Europe/Paris]
// second: 2024-10-27T02:30+01:00[Europe/Paris]
~~~

Both `first.toLocalDateTime()` and `second.toLocalDateTime()` are **`2024-10-27T02:30`**, yet:

- `first.toInstant()` = **`2024-10-27T00:30:00Z`**.
- `second.toInstant()` = **`2024-10-27T01:30:00Z`**.

If you only store `LocalDateTime` together with the zone while dropping the chosen offset, there is not enough information later to know whether 02:30 was **the first or the second occurrence**.

In the opposite direction, there is a **DST gap**: on **2024-03-31**, 02:30 in Paris **does not exist**. Calling `LocalDateTime.of(2024, 3, 31, 2, 30).atZone(paris)` by default **adjusts to 03:30+02:00**, rather than keeping the time the user entered. If business rules prohibit automatic adjustment, proactively check `ZoneRules.getValidOffsets(local)` (empty for a gap, two values for an overlap), apply your business rules, and consider using `ZonedDateTime.ofStrict(local, offset, zone)` when you need to reject invalid combinations.

**Converting from `Instant` to `ZonedDateTime` for a zone is deterministic**: once the instant is known, the zone yields a single valid offset at that instant. Ambiguity only arises when starting from local time fields that lack sufficient context.

## 6. Precision Loss: Nanoseconds, Milliseconds, and String Formatting

`Instant`, `LocalDateTime`, `OffsetDateTime`, and `ZonedDateTime` can store **sub-second fractions down to nanoseconds**. However, not every conversion preserves all 9 decimal digits of seconds.

Take this example:

`2026-01-15T00:30:45.123456789Z`

| Result | Remaining sub-second fraction | Dropped information |
| --- | --- | --- |
| Original `instant` | `.123456789` | None |
| `instant.truncatedTo(ChronoUnit.SECONDS)` | None | 123,456,789 nanoseconds |
| `Instant.ofEpochSecond(instant.getEpochSecond())` | None | 123,456,789 nanoseconds |
| `Instant.ofEpochMilli(instant.toEpochMilli())` | `.123` | 456,789 nanoseconds |
| `Date.from(instant).toInstant()` | `.123` | 456,789 nanoseconds |

### Whole Seconds Are Not Equivalent to Whole Milliseconds

~~~java
Instant event = Instant.parse(
        "2026-01-15T00:30:45.123456789Z");

Instant secondsOnly =
        Instant.ofEpochSecond(event.getEpochSecond());
// 2026-01-15T00:30:45Z

Instant millisOnly =
        Instant.ofEpochMilli(event.toEpochMilli());
// 2026-01-15T00:30:45.123Z
~~~

`getEpochSecond()` only retrieves the seconds part; to carry full precision when storing parts separately, you must also record `getNano()`, or use the full ISO representation.

`toEpochMilli()` only has **millisecond** precision; smaller fractions are discarded. For pre-epoch (1970) timestamps, be especially careful with negative division and rounding — do not replace standard APIs with untested hand-written arithmetic.

### Does `java.util.Date` Preserve Nanoseconds?

No. Traditional `java.util.Date` stores time with **millisecond precision**. Converting `Instant → Date → Instant` cannot recover the remaining micro/nanosecond fraction:

~~~java
Instant precise = Instant.parse(
        "2026-01-15T00:30:45.123456789Z");

Instant recovered = java.util.Date.from(precise).toInstant();
// 2026-01-15T00:30:45.123Z

System.out.println(precise.equals(recovered));
// false
~~~

On the other hand, `java.util.Date` does not "contain the machine's timezone." It stores the millisecond count of a point in time; `Date.toString()` may display using the JVM's default timezone. Distinguish between **precision loss** and **display zone changes**.

### Rounding or Truncation?

`truncatedTo(unit)` **truncates the fraction smaller than the unit**, rather than rounding to the nearest unit. For example, `45.999999999` seconds truncated to seconds becomes **45 seconds**, not 46 seconds. For systems that require rounding, design custom rounding rules and test boundary cases.

## 7. Data Loss During `format()` / `parse()`

Even without directly changing date-time types, **formatting to a string** can discard information that the program cannot recover on its own:

~~~java
Instant event = Instant.parse(
        "2026-01-15T00:30:45.123456789Z");

ZonedDateTime zoned =
        event.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));

DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm");

String label = zoned.format(formatter);
// 2026-01-15 07:30

LocalDateTime reparsed =
        LocalDateTime.parse(label, formatter);
// 2026-01-15T07:30
~~~

This snippet is an example inside a method with `java.time` and `java.time.format.DateTimeFormatter` imported.

The string `label` **dropped seconds, nanoseconds, offset, and zone**. Parsing it back only yields hour and minute `07:30`, with seconds/nanoseconds defaulting to 0 as determined by the formatter. Therefore, `reparsed.equals(zoned.toLocalDateTime())` is **`false`**.

Do not use a **display-only** string as the timestamp storage source if the system needs to recover the exact point in time. Separate:

- **Canonical source value:** `Instant`, or `OffsetDateTime`/zoned model when truly needed.
- **Display string:** formatted according to the desired locale, zone, and level of detail.
- **Input data:** parsed according to a contract that explicitly specifies the required zone/offset and precision.

`DateTimeFormatter.ISO_INSTANT` and `Instant.toString()` can preserve the nanosecond fraction of an `Instant` when UTC serialization is needed. Even so, a downstream API/database might still reduce precision, so you cannot conclude **the entire pipeline is lossless** just because an initial formatter has enough digits.

## 8. Standalone Java 17+ Program and Verified Stdout

Create the file **`DateTimeConversionLossDemo.java`**:

~~~java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoUnit;
import java.util.Date;

public class DateTimeConversionLossDemo {
    public static void main(String[] args) {
        Instant event =
                Instant.parse("2026-01-15T00:30:45.123456789Z");
        ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
        ZonedDateTime zoned = event.atZone(vietnam);

        System.out.println("event = " + event);
        System.out.println("zoned = " + zoned);
        System.out.println("dateOnly = " + zoned.toLocalDate());
        System.out.println("timeOnly = " + zoned.toLocalTime());
        System.out.println("localNoZone = "
                + zoned.toLocalDateTime());
        System.out.println("offsetNoRegion = "
                + zoned.toOffsetDateTime());
        System.out.println("originalInstant = " + zoned.toInstant());

        Instant midnight = zoned.toLocalDate()
                .atStartOfDay(vietnam).toInstant();
        System.out.println("midnightInstant = " + midnight);
        System.out.println("midnightIsEvent = "
                + midnight.equals(event));

        System.out.println("wholeSeconds = "
                + Instant.ofEpochSecond(event.getEpochSecond()));
        System.out.println("wholeMillis = "
                + Instant.ofEpochMilli(event.toEpochMilli()));
        System.out.println("javaUtilDate = "
                + Date.from(event).toInstant());
        System.out.println("truncatedSeconds = "
                + event.truncatedTo(ChronoUnit.SECONDS));
        System.out.println("roundTripInstant = "
                + zoned.toInstant().equals(event));

        DateTimeFormatter formatter =
                DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm");
        String display = formatter.format(zoned);
        LocalDateTime reparsed =
                LocalDateTime.parse(display, formatter);
        System.out.println("display = " + display);
        System.out.println("reparsed = " + reparsed);
        System.out.println("reparsedEqualsOriginalLocal = "
                + reparsed.equals(zoned.toLocalDateTime()));

        ZoneId paris = ZoneId.of("Europe/Paris");
        LocalDateTime overlap =
                LocalDateTime.of(2024, 10, 27, 2, 30);
        System.out.println("overlapOffsets = "
                + paris.getRules().getValidOffsets(overlap));

        ZonedDateTime first = overlap.atZone(paris);
        ZonedDateTime second = first.withLaterOffsetAtOverlap();
        System.out.println("overlapFirst = " + first);
        System.out.println("overlapSecond = " + second);
        System.out.println("localSame = "
                + first.toLocalDateTime()
                    .equals(second.toLocalDateTime()));
        System.out.println("instantSame = "
                + first.toInstant().equals(second.toInstant()));

        LocalDateTime gap =
                LocalDateTime.of(2024, 3, 31, 2, 30);
        System.out.println("gapOffsets = "
                + paris.getRules().getValidOffsets(gap));
        System.out.println("gapResolved = " + gap.atZone(paris));

        System.out.println("laRepresentation = "
                + event.atZone(
                        ZoneId.of("America/Los_Angeles")));
    }
}
~~~

Compile and run:

~~~bash
javac DateTimeConversionLossDemo.java
java DateTimeConversionLossDemo
~~~

Output:

~~~text
event = 2026-01-15T00:30:45.123456789Z
zoned = 2026-01-15T07:30:45.123456789+07:00[Asia/Ho_Chi_Minh]
dateOnly = 2026-01-15
timeOnly = 07:30:45.123456789
localNoZone = 2026-01-15T07:30:45.123456789
offsetNoRegion = 2026-01-15T07:30:45.123456789+07:00
originalInstant = 2026-01-15T00:30:45.123456789Z
midnightInstant = 2026-01-14T17:00:00Z
midnightIsEvent = false
wholeSeconds = 2026-01-15T00:30:45Z
wholeMillis = 2026-01-15T00:30:45.123Z
javaUtilDate = 2026-01-15T00:30:45.123Z
truncatedSeconds = 2026-01-15T00:30:45Z
roundTripInstant = true
display = 2026-01-15 07:30
reparsed = 2026-01-15T07:30
reparsedEqualsOriginalLocal = false
overlapOffsets = [+02:00, +01:00]
overlapFirst = 2024-10-27T02:30+02:00[Europe/Paris]
overlapSecond = 2024-10-27T02:30+01:00[Europe/Paris]
localSame = true
instantSame = false
gapOffsets = []
gapResolved = 2024-03-31T03:30+02:00[Europe/Paris]
laRepresentation = 2026-01-14T16:30:45.123456789-08:00[America/Los_Angeles]
~~~

The calculations and output formatting have been verified with Java. The program uses fixed instants and IANA timezones; therefore, the zoned results depend on the Java runtime's tzdb rules. Under the historical rules of the zones in the example, the output is as shown above.

From the program, we can see two **independent** groups of data loss:

1. `zoned.toLocalDate()`, `toLocalDateTime()`, `toOffsetDateTime()`: lose time, time zone/offset, or region ID respectively depending on the target type.
2. `getEpochSecond()`, `toEpochMilli()`, `Date.from()`, and formatters missing fields: reduce data granularity without changing the zone.

`zoned.toInstant()` still preserves the point in time and nanoseconds, so `roundTripInstant = true`. However, `zoned.toLocalDate().atStartOfDay(vietnam).toInstant()` replaces the event with the **start of the day** in that zone, so `midnightIsEvent = false`.

## 9. Data Storage and APIs: Watch Out for Hidden Conversions

### SQL/JDBC/ORM

Mapping temporal data to a database is another type conversion. Check the **configured column type and precision**:

| Purpose | Typically suitable Java value | Notes |
| --- | --- | --- |
| Birth date, invoice date | `LocalDate` | `DATE` column; do not implicitly attach `00:00 UTC` |
| Wall-clock date-time without zone | `LocalDateTime` | Do not treat it as an instant without offset/zone |
| Timestamp of a past event | `Instant` | Store timestamp with a clear UTC contract; check column precision |
| Date-time with offset | `OffsetDateTime` | Some DBs normalize to UTC and **do not retain the original offset** |
| Appointment at a specific location | Local date-time + `ZoneId`, DST policy | To recover original local time, retain zone and necessary choices |

For example, a timestamp column supporting only **milliseconds** will not retain `.123456789`; a `DATE` column does not retain hours/minutes; a `TIMESTAMP WITHOUT TIME ZONE` column does not tell you an instant on its own. **SQL type names do not guarantee identical behavior across all DBs/drivers**, so inspect the schema, JDBC/ORM mapping, UTC storage behavior, and precision in the actual system.

If you need to know *both the UTC event* and *the user-selected zone*, store them as **two separate business fields**. Do not try to guess `ZoneId` back from an offset unreliably.

### JSON, Formatting, and Data Transfer Contracts

Example requiring full nanosecond precision of the event and the display zone:

~~~json
{
  "occurredAt": "2026-01-15T00:30:45.123456789Z",
  "displayZone": "Asia/Ho_Chi_Minh"
}
~~~

The receiver parses `occurredAt` into `Instant`, parses `displayZone` into `ZoneId`, and then calls `occurredAt.atZone(displayZone)` when displaying.

If an API only sends `"2026-01-15"`, you cannot tell whether the event occurred at 00:30 UTC or 23:59 UTC. If an API only sends `"2026-01-15T07:30"`, there is not enough offset/zone information to determine the instant. If an API only sends epoch **seconds**, the nanosecond fraction was not stored and may have been lost. **Do not infer true precision from the number of displayed digits if upstream already truncated the data.**

### Converting UTC to a Business Date

The question "does the transaction belong to January 15 in Vietnam or in Los Angeles?" must start from **a preserved instant and a chosen zone**:

~~~java
LocalDate vietnamDay = event
        .atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
        .toLocalDate();

LocalDate laDay = event
        .atZone(ZoneId.of("America/Los_Angeles"))
        .toLocalDate();
~~~

The same `event` can belong to two **different calendar dates**. This is not a lost-date bug; it is the correct result of **choosing different zone-based day boundaries**. Conversely, if the business domain only needs a declared **birth date**, use `LocalDate` directly rather than forcing a birth date into a fake UTC instant and converting it to the viewer's zone.

## 10. How to Verify a Conversion Is Safe

A reliable verification workflow consists of four steps.

**Step 1 — Explicitly state "what must be preserved."** For payment logs, that is usually `Instant` to the required precision. For birth dates, that is `LocalDate`. For location-based appointments, that is local date-time, zone ID, and DST policy.

**Step 2 — Compare data immediately before and after conversion.** When `toInstant()` is available, check:

~~~java
boolean sameEvent = before.toInstant()
        .equals(after.toInstant());
~~~

*This is an illustrative expression inside a method, applicable only when both `before` and `after` have a `toInstant()` method.*

When wall-clock time matters, use `toLocalDateTime()` to compare **the same local value**. When zone ID matters, compare `getZone()` of two `ZonedDateTime` values; compare `getOffset()` separately. These are **different invariants** and cannot substitute for one another via a single `equals` call.

**Step 3 — Check precision on both input and output.** For example, `instant.getNano()` must be preserved if the contract promises full nanoseconds. Test with `.123456789`, not just `.000`, because testing with whole seconds will not catch precision loss.

**Step 4 — Test boundaries.** Use times around midnight, month/year transitions, DST gaps and overlaps, pre-1970 timestamps, and numbers near DB/API precision limits.

### Mini Quiz

1. From `2026-01-15T07:30+07:00`, does calling `toLocalDateTime()` then `atOffset(+07:00)` recover the instant? **Yes**, if you **keep and re-supply the exact offset**; `LocalDateTime` by itself does not carry an offset.
2. From a `ZonedDateTime`, does calling `toOffsetDateTime()` lose the instant? **No**; it still has the offset and date-time. However, it **loses the geographical `ZoneId`**.
3. From `ZonedDateTime`, does calling `toInstant()` lose nanoseconds? **No**; `Instant` supports nanoseconds. However, it does not retain the original display zone.
4. Does `Instant → LocalDate` have a unique inverse? **No**; it lacks the time of day and requires a zone to know the day boundaries.
5. Can two `2024-10-27T02:30` values in Paris refer to two different instants? **Yes**, due to DST overlap; the chosen offset is needed.
6. Does `Instant.ofEpochMilli(event.toEpochMilli())` preserve `.123456789`? **No**, only `.123` remains.
7. Is a string `2026-01-15 07:30` sufficient as a transaction timestamp? **No**; it lacks offset/zone, seconds, and sub-second fractions if needed by the business domain.
8. Does `Date.from(instant).toInstant()` keep all nanoseconds? **No**, only up to millisecond precision.

## 11. Checklist to Avoid Information Loss When Writing Java

- [ ] Identify whether the data is a **calendar date**, **local time**, **zoned appointment**, or **event instant**.
- [ ] Explicitly note the source fields and which fields **no longer exist in the target type**.
- [ ] If dropping `ZoneId` or `ZoneOffset`, decide whether they must be kept in a separate field.
- [ ] If attaching a zone to a local date-time, define how to handle **DST gap/overlap** and the chosen offset.
- [ ] If converting to `LocalDate` or `LocalTime`, do not expect the dropped parts to be automatically recoverable.
- [ ] If converting `Instant` to a local date, use an **explicit business zone**, not the server's implicit default timezone.
- [ ] If going through epoch seconds/millis, `java.util.Date`, a DB, or a formatter, confirm the **maximum precision of the target**.
- [ ] Separate **user display** strings from the canonical data to be stored.
- [ ] Write unit tests comparing instant, local date/time, zone, offset, and nanoseconds **according to the exact business properties**.
- [ ] Verify behavior across cross-zone date differences, DST overlap/gap, and pre-epoch date-times.
- [ ] Remember `java.time` is immutable: calling a conversion or transformation while ignoring the return value **does not modify the source object**.

**Key takeaway:** Date-time conversion is not merely changing a class name. Always ask **"which date, local time, time zone, instant, or precision am I keeping?"**. `ZonedDateTime → LocalDateTime` drops offset/zone; `LocalDateTime → LocalDate` drops time; `ZonedDateTime → Instant` keeps the event but drops the regional representation; and epoch millis/`Date` or incomplete formatters can lose nanoseconds. Keep all necessary context separately so that data remains accurate when stored, transmitted, and read back.
