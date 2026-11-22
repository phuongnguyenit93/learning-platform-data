# Calculating Work Session Duration Across Midnight

## 1. Crossing midnight is a date change, not a special time subtraction

A session starting at 22:30 on April 10 and ending at 06:15 on April 11 lasts 7 hours 45 minutes if that zone has no offset change during this interval. If you only keep two `LocalTime` values, the date part is lost and subtraction will treat 06:15 as being before 22:30 on the same day.

To calculate correctly, first determine both full endpoints. For an actual session, you should have the start/end instants, for example two `Instant` values. If the user enters local clock times, you need the date and zone to convert them into instants.

| Input data | What can be calculated |
| --- | --- |
| Only start time and end time | Not enough to know the end date or the number of days of the session |
| Two `LocalDateTime` values | Difference in local date and time |
| Two `Instant` values, or two resolved zoned timestamps | Actual elapsed duration |

`LocalTime` does not store a date or time zone; calling `Duration.between` on two times does not automatically infer that "the end time is the next morning". [LocalTime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalTime.html)

## 2. Choose the duration type before calculating

Distinguish between two questions:

- **How much do the local clocks differ?** You can calculate on `LocalDateTime` when that is the required criterion.
- **How much time has actually elapsed?** Convert both resolved timestamps to `Instant` and then use `Duration.between`.

Across a daylight saving time transition night, the two results may differ. A 22:00–06:00 session on the wall clock still looks like 8 hours, but the actual elapsed time may be 7 or 9 hours. Which calculation is used for timekeeping or business conversion must be determined separately; do not automatically assume every policy equals actual elapsed duration.

`Duration` holds an amount of seconds and nanoseconds, suitable for adding/subtracting durations. Do not use `Period` for total session hours; `Period` describes calendar years/months/days. [Duration](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Duration.html)

## 3. If the input only has times

Only add the next day when the input contract explicitly states so. For example, a form with a start date and an "ends next day" option can construct the end date from that choice.

Illustrative snippet inside a method:

```java
LocalDate startDate = LocalDate.of(2025, 4, 10);
LocalTime startTime = LocalTime.of(22, 30);
LocalTime endTime = LocalTime.of(6, 15);
boolean endsNextDay = true;

LocalDate endDate = endsNextDay ? startDate.plusDays(1) : startDate;
LocalDateTime localStart = LocalDateTime.of(startDate, startTime);
LocalDateTime localEnd = LocalDateTime.of(endDate, endTime);
```

Do not use the rule "if the result is negative, add 24 hours" for all data. It can hide an error where the two endpoints were entered in reverse order, fails to handle multi-day sessions, and ignores longer/shorter days during time changes.

You also need to decide the case where both times are equal: it could be a 0-hour session, a 24-hour session, or multiple days. Two `LocalTime` values cannot distinguish these possibilities.

## 4. Invariants to validate

For a closed session with positive duration:

1. Neither endpoint may be missing.
2. The end timestamp must be after the start timestamp.
3. Breaks to subtract must lie within the session.
4. Breaks must not overlap if you sum them directly to subtract.

Representing intervals as `[start, end)` ensures two adjacent breaks do not overlap at their boundary point. If you want to accept a 0-hour session, you must change the check and define its meaning clearly; the example below intentionally rejects it.

## 5. Program to calculate duration and subtract breaks

Save as `OvernightSessionDemo.java`. The normal example uses the Vietnam zone; the two Berlin examples choose start/end times that do not fall into a gap or overlap.

```java
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;

public class OvernightSessionDemo {
    record Span(Instant start, Instant end) {
        Span {
            Objects.requireNonNull(start, "start");
            Objects.requireNonNull(end, "end");
            if (!start.isBefore(end)) {
                throw new IllegalArgumentException("End must be after start");
            }
        }

        Duration elapsed() {
            return Duration.between(start, end);
        }
    }

    static Span localSpan(LocalDateTime start, LocalDateTime end, ZoneId zone) {
        return new Span(start.atZone(zone).toInstant(), end.atZone(zone).toInstant());
    }

    static Duration netDuration(Span session, List<Span> breaks) {
        List<Span> ordered = breaks.stream()
                .sorted(Comparator.comparing(Span::start)).toList();
        Duration rest = Duration.ZERO;
        Instant previousEnd = session.start();

        for (Span item : ordered) {
            if (item.start().isBefore(session.start())
                    || item.end().isAfter(session.end())) {
                throw new IllegalArgumentException("Break must be inside session");
            }
            if (item.start().isBefore(previousEnd)) {
                throw new IllegalArgumentException("Breaks must not overlap");
            }
            rest = rest.plus(item.elapsed());
            previousEnd = item.end();
        }
        return session.elapsed().minus(rest);
    }

    static String hoursAndMinutes(Duration value) {
        return value.toHours() + "h " + value.toMinutesPart() + "m";
    }

    public static void main(String[] args) {
        ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
        Span session = localSpan(
                LocalDateTime.of(2025, 4, 10, 22, 30),
                LocalDateTime.of(2025, 4, 11, 6, 15), vietnam);
        Span rest = localSpan(
                LocalDateTime.of(2025, 4, 11, 2, 0),
                LocalDateTime.of(2025, 4, 11, 2, 30), vietnam);

        System.out.println("grossMinutes=" + session.elapsed().toMinutes());
        System.out.println("gross=" + hoursAndMinutes(session.elapsed()));
        Duration net = netDuration(session, List.of(rest));
        System.out.println("netMinutes=" + net.toMinutes());
        System.out.println("net=" + hoursAndMinutes(net));

        ZoneId berlin = ZoneId.of("Europe/Berlin");
        LocalDateTime springStart = LocalDateTime.of(2025, 3, 29, 22, 0);
        LocalDateTime springEnd = LocalDateTime.of(2025, 3, 30, 6, 0);
        Span spring = localSpan(springStart, springEnd, berlin);
        Span autumn = localSpan(
                LocalDateTime.of(2025, 10, 25, 22, 0),
                LocalDateTime.of(2025, 10, 26, 6, 0), berlin);

        System.out.println("springWallHours="
                + Duration.between(springStart, springEnd).toHours());
        System.out.println("springElapsedHours=" + spring.elapsed().toHours());
        System.out.println("autumnElapsedHours=" + autumn.elapsed().toHours());
        System.out.println("longSession=" + hoursAndMinutes(Duration.ofHours(30)));
    }
}
```

Compile and run with JDK 17 or later:

```shell
javac --release 17 OvernightSessionDemo.java
java OvernightSessionDemo
```

Stdout with IANA data matching the 2025 zone rules:

```text
grossMinutes=465
gross=7h 45m
netMinutes=435
net=7h 15m
springWallHours=8
springElapsedHours=7
autumnElapsedHours=9
longSession=30h 0m
```

The end date in the Vietnam example is April 11; the break at 02:00 also belongs to April 11, not the start date. Keeping the date for each endpoint makes subtraction natural, with no "across midnight" patch branch needed.

The break-subtraction function sorts the intervals and rejects overlaps to avoid subtracting the same span of time twice. It only subtracts the intervals passed to it; which intervals count as breaks is a rule outside the function.

## 6. DST and resolving entered times

`Duration.between(springStart, springEnd)` on two `LocalDateTime` values in the program gives 8 hours according to the local components. After attaching the Berlin zone and converting to `Instant`, the actual elapsed result is 7 hours because there is a forward time jump during the night.

On the autumn fall-back night, the actual elapsed time is 9 hours. Do not hardcode adding or subtracting one hour by month; use the zone rules for the exact date.

If the input actually falls in a gap/overlap, `atZone` has a default policy that adjusts or picks an offset. The `localSpan` function in this article should only be used with endpoints known to be valid and unambiguous, like the sample data. When building a general form, check `zone.getRules().getValidOffsets(local)` and require explicit handling of missing/ambiguous times before calling it.

When you already have timestamps from a timekeeping device as `Instant`, use those two timestamps directly to calculate actual elapsed time; do not convert them to local time and strip the zone to recalculate. [ZonedDateTime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZonedDateTime.html)

## 7. Displaying and rounding durations

`Duration.toHours()` returns the total whole hours; `toHoursPart()` is the hours part after extracting 24-hour days. For a 30-hour session, using `toHoursPart()` to display the total would show only 6 hours. Similarly, do not use `LocalTime` as a container for total duration because it wraps around within a day.

The `hoursAndMinutes` function uses total hours and the minutes part to produce `30h 0m`. If the data has seconds or fractional parts, this function only **displays** down to minutes and does not apply business rounding rules.

If you must convert to minutes or decimal hours, you need to decide how and at which step to truncate/round. Rounding each segment before summing can differ from summing exact durations and rounding once. Keep `Duration` or a sufficiently precise unit in intermediate calculations.

## 8. Multi-day sessions, open sessions, and daily reporting

For sessions longer than one night, keep the actual end date; do not use a single "overnight" flag to represent all multi-day intervals. Check length limits if the business rules have them, rather than silently wrapping modulo 24 hours.

An unfinished session needs its own status. You can calculate a provisional duration up to a `now` obtained from the chosen clock, but do not record that provisional timestamp as the actual end time if the session is still open.

If a report needs to split an overnight session into individual local days, construct the start-of-day boundaries according to the zone, slice the session interval at those boundaries, and then calculate each segment using `Instant`. Splitting by day and summing the total are two separate tasks; do not let segmenting alter the total actual elapsed time.

When the two endpoints have different zones, you can still calculate between two `Instant` values; as for assigning the session to a business date, you must choose a reporting zone explicitly. [LocalDateTime: data without a zone](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDateTime.html)

## 9. Self-check

1. Calculate the session from 23:50 on 31/12/2025 to 00:20 on 1/1/2026 in Vietnam.
2. Add two adjacent breaks and then test two overlapping breaks.
3. Compare the 22:00–06:00 session across the two Berlin time-change nights in the program.
4. Create a 30-hour session and verify that the display does not wrap back to 06:00.

Check: (1) 30 minutes; (2) adjacent breaks are accepted, overlapping breaks are rejected; (3) actual elapsed time is 7 and 9 hours even though the local clock differs by 8 hours; (4) the total is 30 hours.
