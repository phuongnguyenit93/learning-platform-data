# Calendar Dates, Local Times, Instants, and Time Zones

## Lesson objectives

After this lesson, you will be able to distinguish calendar dates, times of day, local date-times, and absolute instants; explain the role of time zones and UTC offsets; choose appropriate storage representations for birthdays, appointments, transactions, and recurring schedules; and handle cases where local times do not exist or occur twice during clock changes.

You will also know how to design API contracts and database schemas to avoid date-shift bugs, wrong timestamps, lost time zone information, and inconsistent interpretations across systems.

## 1. Why is time easy to model incorrectly?

A value like `21-11-2026` or `09:30` looks simple, yet can carry very different meanings:

- A person's date of birth is a calendar date, not an instant that occurred in a specific time zone.
- A meeting at 09:30 in Hanoi is a local time tied to the location's time zone.
- A payment transaction accepted at 02:30 UTC is an instant on the timeline.
- A revenue report for November 21 may use the calendar date in the store's time zone.
- Daily opening hours 09:00–17:00 are a recurring local-time rule, not a fixed pair of UTC instants.

Storing all of these with a single timestamp type can cause the system to misinterpret them. For example, storing a birthday as a UTC instant and converting it to another time zone can display the date shifted backward or forward by one day. Conversely, storing a payment timestamp as a local time string without a time zone prevents the system from knowing whether the transaction occurred before or after an event elsewhere.

The first step when designing a temporal attribute is to ask: **does this value describe a calendar date, a local wall-clock time, or a specific instant on the timeline?**

## 2. Four concepts to distinguish

### 2.1. Calendar date

A calendar date represents a date on the calendar, typically consisting of year, month, and day. It has no hour, minute, or time zone.

Examples:

- date of birth: `2001-04-12`;
- contract start date: `2026-11-21`;
- branch holiday date: `2027-01-01`;
- accounting period posting date: `2026-11-30`.

A calendar date does not by itself identify an absolute instant. November 21, 2026 in Vietnam and November 21, 2026 in California share the same calendar label, yet the actual time spans each place calls that day do not match.

Use DATE or an equivalent date type when the business only cares about the date. Do not attach `00:00 UTC` to a calendar date unless the business specifies that rule.

### 2.2. Local time of day (local time / wall-clock time)

Local time of day represents a time on a clock, such as `09:30` or `17:45:20`. It has no date and does not carry enough information to identify an absolute instant.

Examples:

- store opens at `09:00`;
- support call starts at `08:30`;
- alarm rings at `06:15`.

The time `09:30` happens every day and in every time zone. Store only time of day when the date does not matter or as part of a recurring rule.

### 2.3. Local date-time (local date-time / wall-clock date-time)

A local date-time combines a calendar date and a wall-clock time, such as `2026-11-21 09:30`. This value describes what a user sees on a calendar or clock at a location, yet does not uniquely identify an instant without a time zone or UTC offset.

Example: “The meeting starts at 09:30 on November 21 in Ho Chi Minh City.” To convert this into an instant on the timeline, you need the time zone rules effective at that location on that date.

### 2.4. Absolute instant (instant)

An **instant** is a specific point on the timeline, independent of time zone display formatting. The same instant can be rendered as different local times.

For example, the instant `2026-11-21T02:30:00Z` can be displayed as `09:30` at a location using `UTC+07:00`. The instant value does not change when the viewer changes time zones; only its display formatting changes.

Events such as an accepted payment, a published message, an uploaded file, or a server-recorded request typically require an instant.

### 2.5. Comparison table

| Concept | Example | Has time zone? | Identifies an instant? |
|---|---|---|---|
| Calendar date | 2026-11-21 | No | No |
| Time of day | 09:30:00 | No | No |
| Local date-time | 2026-11-21 09:30 | Not yet | No, unless zone/offset and rules are added |
| Date-time with offset | 2026-11-21T09:30:00+07:00 | Has UTC offset | Yes |
| Instant | 2026-11-21T02:30:00Z | Represented in UTC | Yes |

A UTC offset allows determining the instant for that moment. However, it does not convey the full time zone rules of a location in the past or future.

## 3. Time zones, UTC, and UTC offsets

### 3.1. UTC

**UTC (Coordinated Universal Time)** is the reference time standard widely used for exchanging and storing instants. When representing a timestamp in UTC, the suffix symbol is typically `Z`.

Example:

~~~text
2026-11-21T02:30:00Z
~~~

The letter `Z` means a UTC offset of `00:00`. This is a representation of an instant.

UTC allows systems across regions to compare event ordering without guessing local time zones.

### 3.2. UTC offset

A UTC offset is the difference between local time and UTC at a specific moment, for example:

- `+07:00`: local time is seven hours ahead of UTC;
- `-05:00`: local time is five hours behind UTC;
- `+05:30`: local time is five hours and thirty minutes ahead of UTC.

For example, the following two representations refer to the exact same instant:

~~~text
2026-11-21T02:30:00Z
2026-11-21T09:30:00+07:00
~~~

An offset suffices to convert a specific date-time into an instant. However, an offset is just a number at that moment. It contains neither seasonal clock-change rules, historical policy changes, nor a location name.

### 3.3. Regional time zones (time zone)

A regional time zone is a set of rules determining the applicable offset by location and time. Systems commonly use identifiers from the IANA time zone database, such as:

- `Asia/Ho_Chi_Minh`;
- `Asia/Tokyo`;
- `Europe/Paris`;
- `America/New_York`.

A region name determines historical rules and future effective rules according to installed time zone data.

Do not replace a region name with a fixed offset if the business needs to preserve local wall-clock time across daylight saving changes or local policy changes.

### 3.4. How does an offset differ from a zone ID?

| Information | Example | What it tells us |
|---|---|---|
| Offset | +07:00 | Difference from UTC at a specific moment |
| Zone ID | Asia/Ho_Chi_Minh | Time rules of a geographical region |
| Local date-time | 2026-11-21 09:30 | Calendar/clock time the user intends to see |
| Instant | 2026-11-21T02:30:00Z | Specific point on the timeline |

An offset like `+01:00` may be used by multiple regions with different rules. One zone ID may have different offsets at different times.

For events that already happened, storing the instant is usually the most important foundation. If you need to retain location context or how the user entered the time, additionally store the zone ID and/or original offset per audit requirements.

## 4. Choosing data types by business meaning

No single temporal type fits every attribute. Choose based on the question the data must answer.

| Business need | Suitable conceptual type | Example |
|---|---|---|
| Date of birth, holiday, effective date | Date | 2001-04-12 |
| Daily opening hours | Local time | 09:00 |
| User-entered time for an appointment | Local date-time + zone ID | 2026-11-21 09:30, Asia/Ho_Chi_Minh |
| Event that occurred | Instant | 2026-11-21T02:30:00Z |
| Actual elapsed time | Duration | 90 minutes |
| Calendar-based span | Period | 1 month, 1 year |
| Local recurring schedule | Recurrence rule + local time + zone ID | Every Monday at 09:00 in a region |

### 4.1. A calendar date is not a midnight timestamp

For example, a birth date `2001-04-12` should be stored as a date value. If stored as `2001-04-12T00:00:00Z` and displayed in `UTC-07:00`, the user may see `2001-04-11`.

Attaching an instant to a birth date invents information that does not exist in the business domain and can cause bugs across time zone conversions.

### 4.2. A local time is not an instant

An opening hour of `09:00` is a local wall-clock rule. Storing it as `02:00 UTC` breaks when applied in another region or when offsets change.

Store the time of day and the zone ID at the branch level if location identification is needed. If a store has day-by-day opening schedules, store both the day-of-week rule and the time intervals.

### 4.3. Local date-times need context to convert into instants

A booking form might receive:

~~~json
{
  "localDateTime": "2026-11-21T09:30:00",
  "timeZone": "Asia/Ho_Chi_Minh"
}
~~~

The backend uses the zone ID and time rules on that date to resolve the instant. If the local time is invalid or ambiguous due to a clock transition, the system must have an explicit handling policy.

### 4.4. Occurred events should store instants

For example, the system receives a payment confirmation. The event needs a timestamp for ordering, reconciliation, and investigation.

~~~json
{
  "eventType": "PaymentAccepted",
  "occurredAt": "2026-11-21T02:30:00Z"
}
~~~

You may additionally store the system receipt time and sender source to distinguish when the event occurred from when the system learned about it.

## 5. Storing dates and times in databases

DBMSs have slightly different data type names and semantics. Read your DBMS documentation rather than relying solely on type names.

### 5.1. DATE

`DATE` stores a calendar date, typically year, month, and day. It fits birth dates, contract signing dates, holidays, or accounting posting dates.

~~~sql
CREATE TABLE employees (
    employee_id BIGINT PRIMARY KEY,
    birth_date DATE
);
~~~

Do not add a time zone to a calendar-date attribute unless the business requires it.

### 5.2. TIME

`TIME` stores a time of day. In many DBMSs, `TIME` is not bound to a specific date or time zone.

~~~sql
CREATE TABLE store_opening_hours (
    store_id BIGINT NOT NULL,
    day_of_week SMALLINT NOT NULL,
    opens_at TIME NOT NULL,
    closes_at TIME NOT NULL
);
~~~

For opening schedules, define the store's time zone elsewhere in the model. Also handle shifts crossing midnight, holidays, and multiple open intervals within the same day.

### 5.3. TIMESTAMP without time zone

A timestamp without time zone usually stores calendar date and clock time without defining an instant on its own. It fits when preserving the exact local time entered by a user, provided you store a separate zone ID if conversion to an instant is needed.

Type names can be misleading: a timestamp without a zone does not inherently know whether the value is UTC or local time. Never assume a value lacking an offset means UTC.

### 5.4. TIMESTAMP with time zone or equivalent

Some DBMSs provide timestamp types with instant semantics or offset storage. Storage and display behaviors vary across products:

- Some DBMSs normalize instants to UTC and display them in the session's time zone.
- Some types retain the original offset without storing the full IANA region rules.
- Some DBMSs share identical type names yet have different conversion behaviors.

For example, in PostgreSQL, `TIMESTAMP WITH TIME ZONE` (`timestamptz`) represents an instant; PostgreSQL converts zoned input internally to UTC and renders it according to the session time zone. It does not retain the original zone name such as `Asia/Ho_Chi_Minh`. If the zone ID must be kept, store an additional column.

### 5.5. Storing instant and zone ID separately when needed

An appointments table may need both the resolved instant and the user's scheduling context:

~~~sql
CREATE TABLE appointments (
    appointment_id BIGINT PRIMARY KEY,
    starts_at_utc TIMESTAMP WITH TIME ZONE NOT NULL,
    time_zone_id VARCHAR(100) NOT NULL,
    local_start TIMESTAMP NOT NULL
);
~~~

In this example:

- `starts_at_utc` is the instant used for comparisons, reminders, and integrations;
- `time_zone_id` provides the regional rules for location-based display and interpretation;
- `local_start` preserves the confirmed local time if auditing or preserving the scheduler's original intent is required.

Not every application needs all three fields. Avoid storing redundant copies without a concrete need; if stored, designate the canonical source and verify consistency among them.

## 6. Local times may not exist or may occur twice

In regions observing Daylight Saving Time (DST), local clocks can jump forward or fall back. Consequently, mapping from a local date-time to an instant is not always one-to-one.

### 6.1. Non-existent time intervals (gap)

When clocks spring forward, a span of local time is skipped. As an illustrative example, clocks jump from `01:59` to `03:00`, so `02:30` does not exist on that day in that region.

If a user schedules an appointment at `02:30` inside a gap, the system cannot infer a valid instant on its own. Decide whether to:

- return an error and ask the user to choose another time;
- shift automatically to the next valid time;
- or apply a published business rule.

For important appointments, asking the user to confirm is usually clearer and avoids silently shifting schedules.

### 6.2. Repeated time intervals (overlap)

When clocks fall back, a span of local time occurs twice. For example, `01:30` can occur twice with two different offsets.

Local date-time and zone ID alone are insufficient to pick a single instant. The system must:

- ask the user to select the first or second occurrence;
- accept an explicit offset from the client after validation;
- or apply a business-approved default rule.

Do not arbitrarily pick an instant without a policy, especially for payments, financial transactions, or high-impact appointments.

### 6.3. Why does zone ID matter?

A fixed offset cannot tell whether a gap or overlap exists on a given date. Only a zone ID combined with time zone rule data can determine:

- whether a local date-time is valid;
- whether there is one or two corresponding instants;
- which offset applies;
- historical and future rules according to time zone data.

Time zone rule data can be updated when governments change policies. Applications should keep their time zone database updated and define how future appointments are handled when rules change.

## 7. Appointments, events, and recurring schedules

### 7.1. One-time appointments

A user-chosen appointment in local time typically requires:

- the local date-time chosen by the user;
- the zone ID of the location or organizer;
- the resolved instant;
- a policy for resolving gaps/overlaps;
- creator info and creation timestamp if auditing is needed.

Once confirmed, the instant drives timely reminders. The zone ID enables rendering in the desired region and preserving calendar context.

If an appointment shifts due to a time zone rule change, decide whether the business goal is to keep the instant fixed or keep the local wall-clock time fixed. Those two choices produce different displayed times.

### 7.2. Occurred events

For occurred events such as payments, logins, deliveries, or message receipts, the instant is primary for timeline ordering.

Fields that may be needed:

- `occurred_at`: business timestamp when the event occurred per source;
- `received_at`: timestamp when the system received the data;
- `recorded_at`: timestamp when written to the data store;
- `source_time_zone` or `source_offset`: source context if needed.

Do not collapse these timestamps into a single `created_at` column when they carry distinct meanings.

### 7.3. Recurring schedules in local time

Examples: “The store opens at 09:00 every day” or “The team meeting runs at 09:00 Mondays in Paris.”

These are local-time rules. Store:

- day/week pattern or recurrence rule;
- local time;
- zone ID;
- start date and end date if any;
- exceptions, holidays, or cancelled occurrences;
- gap/overlap policy.

Do not generate recurring schedules by taking the previous instant and adding 24 hours if the goal is to keep local wall-clock time. When offsets change, local time will shift by an hour.

For example, a 09:00 meeting in a DST region must continue occurring at 09:00 local clock time after seasonal transition, even though its UTC instant changes.

### 7.4. All-day events

An event “Holiday Nov 21” can be a calendar date, not an instant interval from `00:00` to `23:59 UTC`.

It is commonly represented with start and end dates under an explicit convention. In many calendars, date ranges use inclusive start and exclusive end:

~~~text
start_date = 2026-11-21
end_date_exclusive = 2026-11-22
~~~

This representation simplifies counting days and joining adjacent events without assuming every day is exactly 24 hours long. If an all-day event is tied to a location, the zone ID may be needed to convert it into an instant range when syncing with other systems.

## 8. Duration and Period: spans that are not date-times

Two concepts are frequently confused:

- **Duration:** an amount of elapsed time measured in physical time units, typically seconds or nanoseconds.
- **Period:** a calendar-based span, such as 1 day, 1 month, or 1 year.

Examples:

- A 30-second timeout is a duration.
- A payment deadline after 3 calendar days is a period or business-day rule depending on domain.
- A contract valid for 1 year from signing date may require calendar addition.
- A request taking 500 milliseconds is a duration measured by a monotonic clock, rather than relying on a wall clock that can be adjusted.

A calendar day is not always 24 hours in regions with offset transitions. A month does not have a fixed number of days either. Choose operations matching the intended semantics.

### 8.1. Calendar-date deadlines vs. duration deadlines

Compare:

- “Due at end of day Nov 21 local time”: requires date, zone ID, and end-of-day cutoff rule.
- “Due exactly 48 hours after payment”: requires starting instant plus a 48-hour duration.

The two rules can yield different instants across a time zone transition.

### 8.2. Monotonic clocks for measuring duration

When measuring elapsed runtime within a process or device, the system clock may be resynchronized or adjusted. To measure duration accurately, use a monotonic clock, which guarantees non-decreasing progression during measurement.

UTC timestamps fit recording start/end instants for auditing; monotonic clocks fit measuring elapsed intervals. The two tools serve different purposes.

## 9. Exchange formats and API contracts

### 9.1. Use unambiguous ISO 8601 formats

Common representations:

~~~text
2026-11-21
09:30:00
2026-11-21T09:30:00
2026-11-21T09:30:00+07:00
2026-11-21T02:30:00Z
~~~

Their meanings are respectively: date, time, local date-time without zone, date-time with offset, and instant represented in UTC.

Do not send a date-time without an offset and expect all parties to interpret it as UTC. The contract must state explicitly whether a value is a local date-time requiring a zone ID or a UTC value by convention.

### 9.2. APIs for instants

For occurred events, payloads can use UTC:

~~~json
{
  "paymentId": "PAY-9001",
  "acceptedAt": "2026-11-21T02:30:00Z"
}
~~~

Field names should convey semantics. If a field is an instant, require an offset or `Z` in the format. Clients can convert to the user's time zone for display.

### 9.3. APIs for local times

For appointments, payloads need local date-time and zone ID:

~~~json
{
  "localStart": "2026-11-21T09:30:00",
  "timeZone": "Asia/Ho_Chi_Minh"
}
~~~

The backend must validate the time in that zone before resolving the instant. If the time falls in an overlap, the contract may require an additional offset or occurrence selection.

### 9.4. Do not use abbreviated time zone names as identifiers

Strings like `CST`, `IST`, or `PST` can have multiple meanings depending on region and date. They do not always uniquely identify a zone ID.

Prefer IANA region names like `America/Chicago` or `Asia/Kolkata` when geographical rules are needed. If only an instant is needed, a specific offset or UTC suffices.

### 9.5. Precision and rounding

Systems may support different precisions: seconds, milliseconds, microseconds, or nanoseconds. Agree on:

- field precision;
- rounding or truncation behavior;
- how two timestamps are compared;
- serialization format;
- handling source data with higher precision than the target database.

Do not use timestamps as unique keys when precision or clock sources cannot guarantee uniqueness. Multiple events can occur within the same millisecond.

## 10. Example with the Java Time API

In Java, the `java.time` package provides dedicated types for each semantic concept:

| Java type | Meaning |
|---|---|
| LocalDate | Calendar date |
| LocalTime | Time of day |
| LocalDateTime | Local date-time, without zone |
| Instant | Absolute instant |
| ZoneId | Regional time zone rules |
| ZonedDateTime | Date-time bound to a zone |
| OffsetDateTime | Date-time bound to a specific offset |
| Duration | Elapsed time span |
| Period | Calendar-based time span |

Example:

~~~java
import java.time.*;

LocalDate birthday = LocalDate.of(2001, 4, 12);
LocalTime openingTime = LocalTime.of(9, 0);

LocalDateTime localMeeting =
    LocalDateTime.of(2026, 11, 21, 9, 30);

ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
ZonedDateTime meetingInZone = localMeeting.atZone(zone);

Instant meetingInstant = meetingInZone.toInstant();
OffsetDateTime utcRepresentation =
    meetingInstant.atOffset(ZoneOffset.UTC);
~~~

Here:

- `birthday` has no time zone;
- `openingTime` is only a wall-clock time;
- `localMeeting` does not yet identify an instant;
- `zone` adds regional rules;
- `meetingInZone` represents the date-time in that zone;
- `meetingInstant` is the instant suitable for exchange across systems.

### 10.1. Checking ambiguous local times

When resolving local time in a zone, you can query how many valid offsets exist for the local date-time:

~~~java
ZoneId zone = ZoneId.of("Europe/Paris");
LocalDateTime local = LocalDateTime.of(2026, 10, 25, 2, 30);

var validOffsets = zone.getRules().getValidOffsets(local);

if (validOffsets.isEmpty()) {
    // Local time is in a gap: no corresponding instant.
} else if (validOffsets.size() == 1) {
    // Exactly one valid offset.
} else {
    // Overlap: two valid offsets; ask for or apply a policy.
}
~~~

This snippet illustrates the principle. Exact results depend on date, zone ID, and time zone data version. Do not hardcode assumptions that a specific hour is always a gap or overlap in every year.

### 10.2. Choosing types by purpose

Do not use `LocalDateTime` for every temporal field simply because it is convenient to construct. If you need an instant, use `Instant` or an offset/zoned type as appropriate. If you need to store a birth date, use `LocalDate`. If you need a local recurring schedule, keep both the recurrence rule and `ZoneId`.

## 11. Verifying temporal models

Use the following scenarios to test schemas and APIs:

1. A birth date viewed in `UTC-08:00` and `UTC+09:00` stays the same calendar date.
2. A transaction occurring at `02:30 UTC` renders with the correct local times in two countries.
3. An appointment at a normal time converts to the right instant per its zone ID.
4. An appointment falling into a non-existent gap time is handled according to policy.
5. An appointment falling into an overlap time prompts for selection or applies an explicit rule.
6. Weekly recurring meetings keep the same local wall-clock time after a region's DST transition.
7. Late-arriving events retain both `occurred_at` and `received_at`.
8. An all-day event does not shift backward or forward by a day when viewed in another region.
9. Adding 1 calendar day vs. 24 hours duration yields results matching business requirements.
10. Timestamps with different precisions between source and target do not cause unintended comparison mismatches.

### 11.1. Checklist before finalizing schemas

- [ ] Identified whether each field is date, local time, local date-time, or instant.
- [ ] Where a zone is needed, selected a zone ID with clear rules.
- [ ] Distinguished offset from zone ID.
- [ ] Agreed on how instants are stored and exchanged.
- [ ] Defined gap and overlap policies.
- [ ] Determined the goal for future schedules: keep instant fixed or keep local time fixed.
- [ ] Distinguished duration from period.
- [ ] Agreed on precision and rounding behavior.
- [ ] Checked how the target DBMS stores and renders timestamp types.
- [ ] Added tests covering multiple time zones, boundary dates, and DST rules.

## 12. Common mistakes

- **Storing birth dates as UTC timestamps:** across time zone conversions, the date can shift. Use a calendar date type.
- **Treating local time as an instant:** `09:30` is incomplete without a date and zone.
- **Storing only offsets for recurring schedules:** offsets can change with regional rules. Store zone ID when local wall-clock time must be preserved.
- **Storing local date-time without a zone:** cannot reliably resolve an instant or interpret location context.
- **Using abbreviated time zone names:** abbreviations can be ambiguous. Use a UTC offset or explicit zone ID depending on purpose.
- **Assuming every day is 24 hours long:** local days can be shorter or longer during clock transitions.
- **Adding 24 hours to build weekly schedules:** local time can drift after DST. Compute each occurrence from the recurrence rule and zone.
- **Ignoring gaps and overlaps:** a local time may not exist or may occur twice.
- **Using a single `created_at` column for all timestamps:** event time, received time, and recorded time carry different meanings.
- **Using timestamps as unique IDs:** multiple events can share the same timestamp at the available precision.
- **Failing to update the time zone database:** local rules can change by government decree.

## 13. Conclusion

Calendar dates, times of day, local date-times, and instants are distinct concepts. UTC and offsets represent or convert instants; zone IDs provide location- and time-specific rules. Duration measures elapsed time, whereas Period describes calendar spans.

When modeling, identify business meaning before choosing data types. Use date for calendar dates, local time for wall-clock hours, local date-time plus zone for local schedules, and instant for occurred events. For future or recurring schedules, specify clearly whether to preserve absolute instants or local times, and how clock transitions are handled.

## Self-check

1. Why should a birth date use `DATE` instead of a UTC timestamp?
2. Distinguish a UTC offset from an IANA Zone ID.
3. Is a local date-time sufficient to identify an instant? What must be added?
4. Why can a local wall-clock time not exist or occur twice?
5. For a meeting recurring every Monday at `09:00` in a region with DST, which components should be stored?
6. Distinguish Duration and Period using a payment-deadline example.
7. A system receives events late from a partner. Which timestamps should be stored to preserve both occurrence time and receipt time?
8. Pick three temporal fields in a system you know and specify their semantics, data types, required zones, and test scenarios.
