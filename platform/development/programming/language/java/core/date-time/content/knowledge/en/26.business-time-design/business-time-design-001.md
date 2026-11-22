# Birth dates, expiration dates, and appointments need different time types

## 1. Choosing a type from the business question

All three pieces of data may look “date-and-time related”, but they answer three different questions: on what calendar day was the person born, when does entitlement end, and at what time and by which clock does the appointment take place. Using the same type for all three often forces the system to guess the missing information.

A time type is part of the data contract. Choosing the right type makes invalid operations harder to write, while clarifying when a time zone, duration, or calendar rule is needed.

| Requirement | Usually suitable model |
| --- | --- |
| Full birth date | `LocalDate` |
| Anniversary needing only month/day | `MonthDay` |
| Expires after a duration, at the same global instant | `Instant` for the point in time, `Duration` for the amount |
| Valid through the end of a day in a business zone | `LocalDate` and `ZoneId`, plus a boundary rule |
| Expiration recording only month/year | `YearMonth`, plus an interpretation rule |
| Appointment at 09:00 on a specific date at a location | `LocalDateTime` and `ZoneId`, resolved to an instant |

The table is a starting point; the same phrase “expiration date” may still require different models depending on the agreed meaning.

## 2. Birth date: a calendar date, not UTC midnight

`LocalDate` keeps year, month, and day without a time of day or time zone. That is usually the source data to store for a birth date. There is no need to fabricate `2000-04-10T00:00Z`: when displayed in a zone with a negative offset, that fabricated instant can become April 9, corrupting the birth date data.

To calculate age by calendar date, first determine “today” in the business zone, verify that the birth date is not in the future, and then count full calendar years. Do not divide a millisecond difference by 365 days: years have different lengths.

`MonthDay` is only enough to match an anniversary; dropping the birth year loses the information needed to calculate age. For a February 29 birth date, how the anniversary is determined in a given year usually requires a dedicated policy; do not treat a default date adjustment as the entire business rule. [LocalDate](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDate.html)

## 3. Expiration: ending at an instant or after a day?

### Expires after 15 minutes

For a code valid for 15 minutes from issuance, the natural model is `issuedAt: Instant`, `ttl: Duration`, `expiresAt: Instant`. Every place compares the same expiration instant; a time zone is only needed for display.

Lock down the boundary first: for example, validity in the interval `[issuedAt, expiresAt)`, meaning at exactly `expiresAt` it has already expired. In that case, the condition is `!now.isBefore(expiresAt)`, rather than just `now.isAfter(expiresAt)`, which misses the exact equality point. [Instant](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Instant.html)

### Valid through the end of April 9 in a zone

If the product says “valid through the end of April 9 in Vietnam time”, the source data is a date and a specified zone. The expiration point can be represented as the **start of the next day** in that zone, and then compared as an `Instant`.

Do not hardcode the end of the day as `23:59:59`: data with fractional seconds will introduce gaps or precision errors. Do not assume a local day is always 24 hours long. `atStartOfDay(zone)` selects the earliest valid instant of the day according to the zone rules, making it more appropriate than adding a fixed number of seconds.

### Recording only month and year

If the input genuinely has only month/year, use `YearMonth` instead of arbitrarily assigning day 1 or a dummy day. Then explicitly specify whether entitlement ends at the start of the next month or at some other boundary, and in which zone. The data type does not decide the missing rule on its own.

## 4. Appointments: local time and location

`LocalDateTime.of(2025, 4, 10, 9, 0)` means “09:00 on April 10”, but does not yet identify a global instant. 09:00 in Ho Chi Minh City differs from 09:00 in Berlin. Add a `ZoneId` to apply the zone rules. [LocalDateTime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDateTime.html)

In places with daylight saving time, a local time may not exist or may occur twice. Therefore, when accepting an appointment, you must define how to handle it:

- No valid offset: reject that time or suggest another time according to policy.
- One valid offset: resolve normally.
- Two valid offsets: ask the user to choose the earlier or later occurrence, or apply a published policy.

`atZone` has default behavior for these cases; you should not let an accidental default stand in for the scheduler's intent. A fixed `ZoneOffset` such as `+01:00` also cannot replace the rules of a zone like `Europe/Berlin`. [ZonedDateTime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZonedDateTime.html)

## 5. Program demonstrating the three contracts

The example below chooses a strict appointment policy: it only resolves automatically when the local time has exactly one offset. Missing or ambiguous times are rejected for the caller to handle.

Save as `BusinessTimeDemo.java`:

```java
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.Period;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.util.List;

public class BusinessTimeDemo {
    static int calendarAge(LocalDate birthDate, LocalDate today) {
        if (birthDate.isAfter(today)) {
            throw new IllegalArgumentException("Birth date is in the future");
        }
        return Period.between(birthDate, today).getYears();
    }

    static boolean expired(Instant now, Instant expiresAt) {
        return !now.isBefore(expiresAt);
    }

    static Instant endExclusive(LocalDate validThrough, ZoneId zone) {
        return validThrough.plusDays(1).atStartOfDay(zone).toInstant();
    }

    static Instant appointment(LocalDateTime local, ZoneId zone) {
        List<ZoneOffset> offsets = zone.getRules().getValidOffsets(local);
        if (offsets.size() != 1) {
            throw new IllegalArgumentException("Local time requires an explicit policy");
        }
        return ZonedDateTime.ofStrict(local, offsets.get(0), zone).toInstant();
    }

    public static void main(String[] args) {
        LocalDate birthDate = LocalDate.of(2000, 4, 10);
        System.out.println("ageBeforeBirthday="
                + calendarAge(birthDate, LocalDate.of(2025, 4, 9)));
        System.out.println("ageOnBirthday="
                + calendarAge(birthDate, LocalDate.of(2025, 4, 10)));

        Instant issuedAt = Instant.parse("2025-04-09T10:00:00Z");
        Instant expiresAt = issuedAt.plus(Duration.ofMinutes(15));
        System.out.println("expiresAt=" + expiresAt);
        System.out.println("expiredBefore="
                + expired(expiresAt.minusNanos(1), expiresAt));
        System.out.println("expiredExactly=" + expired(expiresAt, expiresAt));

        ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
        System.out.println("dayCutoff="
                + endExclusive(LocalDate.of(2025, 4, 9), vietnam));
        System.out.println("appointmentInstant="
                + appointment(LocalDateTime.of(2025, 4, 10, 9, 0), vietnam));

        ZoneId berlin = ZoneId.of("Europe/Berlin");
        try {
            appointment(LocalDateTime.of(2025, 3, 30, 2, 30), berlin);
        } catch (IllegalArgumentException ex) {
            System.out.println("gapRejected");
        }
        try {
            appointment(LocalDateTime.of(2025, 10, 26, 2, 30), berlin);
        } catch (IllegalArgumentException ex) {
            System.out.println("overlapRejected");
        }
    }
}
```

Compile and run with JDK 17 or later:

```shell
javac --release 17 BusinessTimeDemo.java
java BusinessTimeDemo
```

Stdout with IANA time zone data corresponding to the 2025 rules in the example:

```text
ageBeforeBirthday=24
ageOnBirthday=25
expiresAt=2025-04-09T10:15:00Z
expiredBefore=false
expiredExactly=true
dayCutoff=2025-04-09T17:00:00Z
appointmentInstant=2025-04-10T02:00:00Z
gapRejected
overlapRejected
```

The `dayCutoff` point is 00:00 on April 10 in Vietnam, corresponding to 17:00 UTC on April 9. It does not change the meaning of “end of April 9”; it is the same boundary represented on the timeline.

`calendarAge` demonstrates full calendar years for a typical birth date. Special age rules, especially for February 29, must be defined separately if the application has specific requirements. `endExclusive` also assumes the next day can be represented; at the `LocalDate.MAX` boundary, it must be rejected or handled with another rule.

## 6. Which data is the source of truth when time zone rules change?

For an event that has already happened, `Instant` is usually the source of truth to know the exact chronological order; the zone/offset can be stored for display or auditing.

For a future appointment “09:00 in Berlin”, the original intent may be the local time and zone. If time zone rules are updated, you must decide whether to keep 09:00 local time or keep the previously resolved instant. The two choices can produce different results.

A model may store `localDateTime`, `zoneId`, `resolvedInstant`, and the disambiguation choice for overlaps, but it must clearly document which field is authoritative and when to recompute. Storing multiple fields without a synchronization rule only creates contradictions.

Weekly recurring schedules also should not generate all future occurrences by adding `Duration.ofDays(7)` if the requirement is the same local time. Keep the recurrence rule and resolve each occurrence against the zone.

## 7. Encoding the contract in field names and system boundaries

Generic names like `date`, `time`, and `timestamp` easily obscure meaning. Names such as `birthDate`, `validThroughDate`, `expiresAt`, `appointmentLocal`, and `appointmentZone` indicate which rules apply.

For APIs and databases, choose appropriate formats/storage types:

- Birth date: keep an ISO date `uuuu-MM-dd` or a date column; do not implicitly convert to an instant.
- Global expiration instant: exchange instants with explicit UTC/offset; check precision when persisting.
- Location-based appointment: keep the named zone ID and the local information that must be preserved.
- Month/year or month/day: do not silently fill in missing components.

Obtain “now” via an injected `Clock` or a parameter so that expiration boundaries, birthdays, and year-end dates can be tested. Do not call multiple different clocks within the same decision if doing so could cause checks to use different points in time.

## 8. Questions to finalize the design

1. Is the data a calendar date, a local time, an instant, or a recurrence rule?
2. Which components are provided by the user; which are business rules?
3. In which zone is the date/time interpreted?
4. Is the end boundary considered still valid?
5. When a time is missing/ambiguous, on February 29, or when zone rules change, what is the policy?

You do not need to store every type at once. Keep only the information that needs to be preserved and perform conversions where all required rules are available.

## 9. Self-practice

1. Design fields for a membership card that has a birth date and is valid through the end of a day in Vietnam.
2. Change the verification code lifetime from 15 minutes to 24 hours and explain why `Duration` is still used.
3. Accepting an appointment for `2025-10-26T02:30` in Berlin: what additional choice is needed before locking in an `Instant`?
4. For an entitlement that expires at exactly 10:15:00Z, check 10:14:59.999999999Z, exactly 10:15:00Z, and afterward.

Check your answers: (1) `LocalDate` for the two dates, with the zone and validity boundary kept explicit; (2) the requirement is elapsed physical duration; (3) choose the occurrence by the appropriate offset; (4) valid, expired, and expired respectively under the chosen half-open end-exclusive interval.