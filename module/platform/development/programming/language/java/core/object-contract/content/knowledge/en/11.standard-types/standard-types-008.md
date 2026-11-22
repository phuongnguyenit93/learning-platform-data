# Value objects in java.time and the requirement to read each type's contract carefully

## 1. Why can't all "equality" operations in java.time be treated the same?

Familiar types in **java.time** such as **LocalDate**, **LocalTime**, **LocalDateTime**, **Instant**, **OffsetDateTime**, **ZonedDateTime**, **Duration**, **Period**, and **YearMonth** are designed to describe **temporal values**. Many of these types are **value-based classes**: two instances that are equal under the type's contract can be used interchangeably. Do not rely on object identity with the **==** operator, **System.identityHashCode**, or using an instance as a **synchronized** lock. Use **equals** and **hashCode** strictly according to the type's documentation.

The hardest part is not calling equals, but determining **what "same value" means**:

- **Same calendar date**: does 2026-10-23 equal 2026-10-23? **LocalDate.equals** answers this.
- **Same absolute point in time**: is 09:00 at UTC+07 the same as 02:00 UTC? **Instant.equals** or the timeline comparison **isEqual** on offset/zoned types answers this.
- **Same date-time and offset representation**: does 09:00+07 equal 02:00Z? **OffsetDateTime.equals** returns false, even though both values refer to the same instant.
- **Same named time zone region**: **Europe/Paris** and **UTC** are not the same **ZoneId**, even when a specific point in time may share the same offset.
- **Same time-based amount** or **same calendar unit counts**: **Duration** measures seconds/nanoseconds, while **Period** measures years/months/days; they are two different models.

**General rules from Object** still apply:

1. **Reflexive:** a.equals(a) is true.
2. **Symmetric:** a.equals(b) yields the same result as b.equals(a).
3. **Transitive:** if a equals b and b equals c, then a equals c.
4. **Consistent:** given the same value state, the result does not change.
5. **Non-null:** a.equals(null) is false.
6. **Hash relation:** if a.equals(b) is true then a.hashCode() must equal b.hashCode(); equal hashes alone are not sufficient to conclude equals.

A comparison such as **isEqual**, **isBefore**, or **isAfter** may return a different result from **equals** without violating any contract whatsoever. They answer **different questions**.

## 2. Contract lookup table by value type

| java.time type | Values examined by equals | What should not be inferred |
| --- | --- | --- |
| **LocalDate** | ISO date: year, month, day | Carries no time zone and does not uniquely identify an Instant |
| **LocalTime** | Hour, minute, second, nano of day | Not a global point in time |
| **LocalDateTime** | Local date and time, down to nano | Has no offset/zone, so insufficient to identify an instant |
| **Instant** | Position on the UTC timeline (epoch seconds and nanos) | Does not store local time zone or user formatting |
| **OffsetDateTime** | Local date-time **and UTC offset** | Same Instant does not guarantee equals |
| **OffsetTime** | Local time **and UTC offset** | Carries no date; **isEqual** is based on corresponding UTC time on a standard day |
| **ZonedDateTime** | Local date-time, offset, and **ZoneId** | Same Instant does not guarantee equals; same offset does not guarantee same zone |
| **ZoneId** | Time zone ID (e.g., Europe/Paris) | Two IDs with identical current rules/offsets can still be different values |
| **ZoneOffset** | Fixed offset from UTC, measured in seconds | Does not describe a region's full daylight saving rules |
| **Duration** | Length in seconds and nanoseconds | Not a count of calendar days/months |
| **Period** | Number of years, months, and days in ISO | Does not represent a fixed number of seconds |
| **Year**, **YearMonth**, **MonthDay** | Calendar components as named | Do not by themselves represent a complete date-time |

**Read each type accurately before choosing it as a key.** With **LocalDateTime**, turning a local clock back during a time change can produce identical representations at two different Instants. With **OffsetDateTime**, the offset is part of equals. With **ZonedDateTime**, ZoneId is also part of equals. With **Instant**, time-zone representation has been stripped away, leaving only the absolute point.

The **equals** comparison of these types does not automatically convert one type into another: **Instant** and **OffsetDateTime** can refer to the same point in time, yet they are not two values of the same type under Object.equals. To compare whether two values represent the same instant, convert them to **Instant** before comparing.

## 3. Value-based: use value, do not rely on identity

Java may create multiple instances carrying the same value. For value-based classes, there is **no object identity guarantee** that a program should rely on. Therefore:

~~~java
LocalDate a = LocalDate.of(2026, 10, 23);
LocalDate b = LocalDate.parse("2026-10-23");

// Correct: compare date values.
boolean sameDate = a.equals(b);

// Semantically wrong: == asks about reference identity;
// not the value comparison criterion for java.time.
// boolean sameDate = (a == b);
~~~

This is only an **illustrative code snippet** placed in a method with **java.time.LocalDate** imported, not a standalone file. Even if **==** happens to be true in some case, the program must never rely on it.

### Full example: objects with equal values in a hash collection

Create the file **BasicTimeValueDemo.java**:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.util.HashSet;
import java.util.Set;

public class BasicTimeValueDemo {
    public static void main(String[] args) {
        LocalDate first = LocalDate.of(2026, 10, 23);
        LocalDate second = LocalDate.parse("2026-10-23");

        System.out.println("date equals: " + first.equals(second));
        System.out.println("date hash equals: " +
            (first.hashCode() == second.hashCode()));

        Set<LocalDate> dates = new HashSet<>();
        dates.add(first);
        dates.add(second);
        System.out.println("unique dates: " + dates.size());

        LocalDateTime midnight =
            LocalDateTime.of(2026, 10, 23, 0, 0);
        System.out.println("date equals date-time: " +
            first.equals(midnight));

        Instant absolute = Instant.parse("2026-10-23T02:30:00Z");
        OffsetDateTime fromOffset =
            OffsetDateTime.parse("2026-10-23T09:30:00+07:00");
        System.out.println("same instant: " +
            absolute.equals(fromOffset.toInstant()));
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac BasicTimeValueDemo.java
java BasicTimeValueDemo
~~~

Exact output:

~~~text
date equals: true
date hash equals: true
unique dates: 1
date equals date-time: false
same instant: true
~~~

**Explanation:** LocalDate.of and LocalDate.parse construct the same ISO date; equals is true, hashCode matches, and HashSet stores only one logical value. However, **LocalDate** cannot equal **LocalDateTime** via Object.equals, even though LocalDateTime represents midnight on that exact date. **OffsetDateTime.toInstant()** converts an offset date-time to an absolute point on the timeline, so comparing with Instant.parse returns true.

Standard java.time classes already implement appropriate equals/hashCode. When using them directly as HashMap keys or HashSet elements, you usually **do not need to reimplement equals/hashCode for them**.

## 4. Same Instant yet not equals: OffsetDateTime

**OffsetDateTime** carries both a **local date-time** and a **ZoneOffset**. The following two representations refer to the same point in time:

~~~text
2026-10-23T09:00:00+07:00
2026-10-23T02:00:00Z
~~~

Under **equals**, they differ: the local time differs and the offset differs. However, **isEqual** returns true when two values represent the same point on the timeline. **toInstant()** also yields two equal Instants.

Create the file **OffsetEqualityDemo.java**:

~~~java
import java.time.OffsetDateTime;
import java.time.Instant;
import java.util.HashSet;
import java.util.Set;

public class OffsetEqualityDemo {
    public static void main(String[] args) {
        OffsetDateTime vietnam =
            OffsetDateTime.parse("2026-10-23T09:00:00+07:00");
        OffsetDateTime utc =
            OffsetDateTime.parse("2026-10-23T02:00:00Z");

        System.out.println("equals: " + vietnam.equals(utc));
        System.out.println("isEqual: " + vietnam.isEqual(utc));
        System.out.println("instant equals: " +
            vietnam.toInstant().equals(utc.toInstant()));
        System.out.println("compareTo zero: " +
            (vietnam.compareTo(utc) == 0));

        Set<OffsetDateTime> offsets = new HashSet<>();
        offsets.add(vietnam);
        offsets.add(utc);

        Set<Instant> instants = new HashSet<>();
        instants.add(vietnam.toInstant());
        instants.add(utc.toInstant());

        System.out.println("offset keys: " + offsets.size());
        System.out.println("instant keys: " + instants.size());
    }
}
~~~

Commands:

~~~bash
javac OffsetEqualityDemo.java
java OffsetEqualityDemo
~~~

Output:

~~~text
equals: false
isEqual: true
instant equals: true
compareTo zero: false
offset keys: 2
instant keys: 1
~~~

**Important point about compareTo:** **OffsetDateTime.compareTo** first compares the position on the timeline; if the instants match, it additionally examines the local date-time to keep the ordering **consistent with equals**. Therefore, **compareTo == 0** is not synonymous with **isEqual** when two offsets differ. If you only want to ask "same absolute point in time?", use **isEqual** or compare **toInstant()**.

If using **HashSet<OffsetDateTime>**, both representations are retained because equals is false. If business logic wants to deduplicate by absolute event time, use **HashSet<Instant>** or keys converted to Instant.

## 5. ZonedDateTime: same instant can still have a different ZoneId

**ZonedDateTime** holds the full **LocalDateTime + ZoneOffset + ZoneId**. ZoneId is typically a region name with historical and transition rules, such as **Europe/Paris**. Two ZonedDateTime values with the same Instant but different ZoneIds are not considered equal under equals.

Full example **ZonedEqualityDemo.java**:

~~~java
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class ZonedEqualityDemo {
    public static void main(String[] args) {
        ZonedDateTime paris = ZonedDateTime.of(
            2026, 1, 15, 9, 0, 0, 0, ZoneId.of("Europe/Paris")
        );

        ZonedDateTime sameInstantUtc =
            paris.withZoneSameInstant(ZoneId.of("UTC"));

        ZonedDateTime sameLocalUtc =
            paris.withZoneSameLocal(ZoneId.of("UTC"));

        System.out.println("instant version equals: " +
            paris.equals(sameInstantUtc));
        System.out.println("instant version isEqual: " +
            paris.isEqual(sameInstantUtc));
        System.out.println("instant version compares zero: " +
            (paris.compareTo(sameInstantUtc) == 0));

        System.out.println("local version same wall time: " +
            paris.toLocalDateTime()
                 .equals(sameLocalUtc.toLocalDateTime()));
        System.out.println("local version same instant: " +
            paris.toInstant().equals(sameLocalUtc.toInstant()));
    }
}
~~~

Run:

~~~bash
javac ZonedEqualityDemo.java
java ZonedEqualityDemo
~~~

Output:

~~~text
instant version equals: false
instant version isEqual: true
instant version compares zero: false
local version same wall time: true
local version same instant: false
~~~

**withZoneSameInstant(zone)** changes the time zone while **preserving the absolute instant**, adjusting the local clock. **withZoneSameLocal(zone)** keeps the **wall-clock date-time** as far as possible, then recomputes the offset/absolute instant for the new zone. In a case with no DST transition like UTC in this example, the local date-time is preserved exactly. The two methods serve **two different requirements**.

**ZonedDateTime.compareTo** also includes additional criteria in its ordering so that a 0 result stays consistent with equals; having the same Instant does not guarantee compareTo returns 0. Never use compareTo == 0 in place of **isEqual** when the business criterion is solely the same point in time.

### ZoneId and ZoneOffset are two kinds of information

- **ZoneOffset** is a fixed offset, such as +07:00, +01:00, or Z.
- **ZoneId** can be a region like Europe/Paris with offset rules that change over time, or an ID representing a fixed offset.
- Two ZoneIds may have the same offset at one Instant yet **have different IDs** and different time policies at other instants.

Example:

~~~java
ZoneId named = ZoneId.of("UTC");
ZoneId numeric = ZoneOffset.UTC;

// named.equals(numeric) is false: "UTC" differs from ID "Z".
// named.getRules().getOffset(Instant.EPOCH)
//     .equals(ZoneOffset.UTC) is true.
~~~

This is an **illustrative snippet**, requiring imports for **java.time.ZoneId**, **java.time.ZoneOffset**, and **java.time.Instant** if placed in a separate Java file.

If business logic needs to store the **user-selected time zone** for display or future meeting schedules, keep **ZoneId**. If you only need to compare ordering or whether historical events occurred at the same moment, **Instant** is usually the better key.

## 6. LocalDate, LocalTime, and LocalDateTime do not carry an absolute instant

**LocalDate** represents a date on the ISO calendar; **LocalTime** represents a time of day; **LocalDateTime** combines both. Neither type inherently contains a ZoneId or an offset.

For example, **2026-10-23T09:00** can be interpreted as 09:00 in Hanoi, Tokyo, or London, corresponding to different Instants. Therefore:

~~~java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;

public class LocalTimeMeaningDemo {
    public static void main(String[] args) {
        LocalDateTime wall =
            LocalDateTime.parse("2026-10-23T09:00:00");

        Instant vietnam = wall
            .atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
            .toInstant();

        Instant tokyo = wall
            .atZone(ZoneId.of("Asia/Tokyo"))
            .toInstant();

        System.out.println("same local datetime: " +
            wall.equals(LocalDateTime.parse("2026-10-23T09:00:00")));
        System.out.println("same instant: " + vietnam.equals(tokyo));
    }
}
~~~

Save to **LocalTimeMeaningDemo.java** and run:

~~~bash
javac LocalTimeMeaningDemo.java
java LocalTimeMeaningDemo
~~~

Output:

~~~text
same local datetime: true
same instant: false
~~~

**Be cautious around DST transitions:** A LocalDateTime may **not exist** in a zone (when the clock skips forward) or **occur twice** (when the clock repeats an hour). **LocalDateTime.atZone(zone)** has default rules to resolve gaps/overlaps; those default rules may not match business requirements. If you need to distinguish two occurrences of the same wall-clock time, store the resolved offset or Instant explicitly.

**Do not use LocalDateTime.equals to uniquely identify a global event** unless the data domain intentionally standardizes local date-time and zone under one consistent policy.

## 7. isEqual on calendar types and across calendar systems

Beyond offset/zone differences, java.time also includes calendar systems (chronologies) other than ISO. **LocalDate** is an ISO date, whereas **JapaneseDate**, **HijrahDate**, and **ThaiBuddhistDate** belong to different chronologies.

On the **ChronoLocalDate** interface, the **isEqual(ChronoLocalDate)** method asks whether two values represent the same day on the epoch-day line. Meanwhile, equals still includes the **calendar system semantics** of the concrete type.

Example **ChronologyEqualityDemo.java**:

~~~java
import java.time.LocalDate;
import java.time.chrono.JapaneseDate;

public class ChronologyEqualityDemo {
    public static void main(String[] args) {
        LocalDate iso = LocalDate.of(2026, 10, 23);
        JapaneseDate japanese = JapaneseDate.from(iso);

        System.out.println("equals: " + iso.equals(japanese));
        System.out.println("isEqual: " + iso.isEqual(japanese));
        System.out.println("same epoch day: " +
            (iso.toEpochDay() == japanese.toEpochDay()));
    }
}
~~~

Run:

~~~bash
javac ChronologyEqualityDemo.java
java ChronologyEqualityDemo
~~~

Output:

~~~text
equals: false
isEqual: true
same epoch day: true
~~~

**Meaning:** Both values represent the same physical day, yet in **two different calendar systems**. To find the same day regardless of chronology, compare **toEpochDay()**, or use **ChronoLocalDate.isEqual**. To preserve values under their specific chronology, do not arbitrarily change equals to "same epoch day."

If building Map or Set keys across multiple chronologies, decide upfront whether to group by **same chronology + date** or **same epoch day**. For the second goal, using a canonical key of type **long epochDay** is clearer and more consistent.

## 8. Duration and Period: two contracts for two different concepts

**Duration** represents a quantity of time in seconds/nanoseconds; **Period** represents ISO calendar components of years, months, and days. Their equals implementations reflect the **value structure** of each type:

- **Duration.ofMinutes(60)** equals **Duration.ofHours(1)** because both represent the same 3600 seconds.
- **Period.ofMonths(12)** **does not equal** **Period.ofYears(1)**: one value has 0 years/12 months, and the other has 1 year/0 months. **normalized()** can normalize months into years.
- **Period.ofDays(1)** cannot be assumed equivalent to **Duration.ofDays(1)** because a calendar day crossing a DST transition can be 23 or 25 hours long; a Duration of one day is always 86400 seconds.

Create the file **DurationPeriodDemo.java**:

~~~java
import java.time.Duration;
import java.time.Period;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class DurationPeriodDemo {
    public static void main(String[] args) {
        System.out.println("duration equal: " +
            Duration.ofMinutes(60).equals(Duration.ofHours(1)));

        Period months = Period.ofMonths(12);
        Period year = Period.ofYears(1);
        System.out.println("period equal: " + months.equals(year));
        System.out.println("normalized equal: " +
            months.normalized().equals(year));

        ZonedDateTime start = ZonedDateTime.of(
            2026, 3, 28, 12, 0, 0, 0, ZoneId.of("Europe/Paris")
        );

        ZonedDateTime calendarDay = start.plus(Period.ofDays(1));
        ZonedDateTime fixedDay = start.plus(Duration.ofDays(1));

        System.out.println("calendar day hour: " + calendarDay.getHour());
        System.out.println("fixed day hour: " + fixedDay.getHour());
        System.out.println("calendar elapsed hours: " +
            Duration.between(start.toInstant(),
                             calendarDay.toInstant()).toHours());
        System.out.println("fixed elapsed hours: " +
            Duration.between(start.toInstant(),
                             fixedDay.toInstant()).toHours());
    }
}
~~~

Run:

~~~bash
javac DurationPeriodDemo.java
java DurationPeriodDemo
~~~

Output under Europe/Paris time zone rules for the 2026 daylight saving transition date:

~~~text
duration equal: true
period equal: false
normalized equal: true
calendar day hour: 12
fixed day hour: 13
calendar elapsed hours: 23
fixed elapsed hours: 24
~~~

In Paris, March 29, 2026 switches to daylight saving time. Adding **Period.ofDays(1)** lands at 12:00 noon on the next calendar day, with 23 hours of actual elapsed time. Adding **Duration.ofDays(1)** preserves 24 absolute hours, resulting in 13:00 local time on the next day. The results are not contradictory: the two objects represent **two different kinds of quantities**.

**Do not use Period to represent timeouts, session lifetimes, or processing durations.** Use Duration for machine-measured elapsed time. Use Period for calendar year/month/day policies, such as "renew for one month" or "next local day." **Do not convert Duration to Period or vice versa** without providing a complete starting point, zone, and business rules.

## 9. Precision, normalization, and text representation

Temporal values often have a nanosecond component. **Instant.equals** and **LocalDateTime.equals** examine exact nanoseconds; two timestamps 1 nanosecond apart are not equal.

~~~java
import java.time.Instant;
import java.time.temporal.ChronoUnit;

public class PrecisionDemo {
    public static void main(String[] args) {
        Instant base = Instant.parse("2026-10-23T00:00:00Z");
        Instant later = base.plusNanos(1);

        System.out.println("raw equals: " + base.equals(later));
        System.out.println("same whole second: " +
            base.truncatedTo(ChronoUnit.SECONDS)
                .equals(later.truncatedTo(ChronoUnit.SECONDS)));
    }
}
~~~

Save the file **PrecisionDemo.java** and run:

~~~bash
javac PrecisionDemo.java
java PrecisionDemo
~~~

Output:

~~~text
raw equals: false
same whole second: true
~~~

**Design constraint:** If database storage only keeps millisecond precision while another source provides nanoseconds, you must define a **canonical precision** beforehand. Normalize values **before storing and before using as keys**, with an appropriate truncation or rounding rule. Never write custom equals treating two timestamps as equal within an error threshold, such as less than 1 second apart: such a relation can be **non-transitive**.

### String formatting is not the value

**toString()**, **DateTimeFormatter**, and **parse** deal with textual representation. Two different strings can represent the same Instant, for instance with different offsets. To compare **Instants**, parse into the proper type and then normalize. Do not compare formatted strings as a substitute for equals, especially when formatting may omit offset, zone, or fractional seconds.

Do not infer **equals** from **format(...)** output unless business rules intentionally choose a single canonical text representation without losing required data.

## 10. Choosing keys for HashMap, HashSet, and records

Immutable java.time types generally make **good keys** because their equals/hashCode are stable by value. However, choosing **the right key type** defines what counts as a duplicate element.

| Problem | Suitable key | Why |
| --- | --- | --- |
| Global events at the same moment | **Instant** | Ignores display offset and zone |
| Local holiday without time of day | **LocalDate** with calendar/zone convention | The value is a date, not an Instant |
| Record preserving the original offset | **OffsetDateTime** | Offset is a component of the value |
| Meeting schedule that must remember the chosen zone | **ZonedDateTime** or a structure with **LocalDateTime + ZoneId + DST policy** | Must distinguish zone rules and local time interpretation |
| Machine-measured time span | **Duration** | Based on seconds and nanos |
| Cycle defined by calendar days/months/years | **Period** | Based on calendar units |
| Monthly statistics | **YearMonth** | Needs only year and month |

### Full example: event key using normalized Instant

Create the file **EventKeyDemo.java**:

~~~java
import java.time.Instant;
import java.time.OffsetDateTime;
import java.util.HashMap;
import java.util.Map;

public class EventKeyDemo {
    record EventKey(String resourceId, Instant startedAt) {}

    public static void main(String[] args) {
        OffsetDateTime local =
            OffsetDateTime.parse("2026-10-23T09:00:00+07:00");
        OffsetDateTime utc =
            OffsetDateTime.parse("2026-10-23T02:00:00Z");

        EventKey first = new EventKey("room-7", local.toInstant());
        EventKey second = new EventKey("room-7", utc.toInstant());

        Map<EventKey, String> events = new HashMap<>();
        events.put(first, "confirmed");

        System.out.println("same key: " + first.equals(second));
        System.out.println("lookup: " + events.get(second));
        System.out.println("size: " + events.size());
    }
}
~~~

Run:

~~~bash
javac EventKeyDemo.java
java EventKeyDemo
~~~

Output:

~~~text
same key: true
lookup: confirmed
size: 1
~~~

The **EventKey** record auto-generates equals/hashCode from its components, where both **String** and **Instant** have stable value contracts. Two OffsetDateTimes with different representations are normalized to the same Instant, so the two keys are equal.

**However, if business logic needs to distinguish the original offset**, a key containing only Instant has intentionally **discarded that information**. In that case, store the offset, zone, or original representation separately. Normalization must match the problem's exact criteria; converting everything to UTC is not always enough.

### Records containing java.time components

A record with **LocalDate**, **Instant**, **ZoneId**, or **Duration** components can usually rely on its auto-generated equals/hashCode. Yet you must ask whether the record describes **the same data record** or **the same point in time**. For example, a record containing **Instant** and **ZoneId** will treat two records with the same Instant but different zones as **different values**, because all components participate in comparison.

## 11. Common pitfalls

### 11.1. Using == instead of equals

Do not rely on identity with value-based classes. Even when two variables happen to point to the same object, **==** does not express the equivalence criterion of the temporal contract.

### 11.2. Treating isEqual and equals as synonymous

**OffsetDateTime** and **ZonedDateTime** can have **isEqual true** while **equals is false**. One checks for the same Instant, while the other checks the full value including offset/zone. When picking data structures, HashMap/HashSet use **equals/hashCode**, not silently isEqual.

### 11.3. Assuming every compareTo == 0 is based solely on Instant

**OffsetDateTime.compareTo** and **ZonedDateTime.compareTo** maintain an ordering consistent with equals; if two values represent the same Instant yet have different offsets/zones, compareTo may be non-zero. Do not use a naturally ordered TreeSet and assume it deduplicates strictly by Instant.

### 11.4. Treating LocalDateTime as an Instant

LocalDateTime does not store a zone, so its UTC instant cannot be known without specifying a zone/offset and handling gaps/overlaps. A local date-time is insufficient to uniquely identify an absolute event across time zones.

### 11.5. Using ZoneOffset instead of ZoneId when future rules are needed

An offset like +07:00 is only a fixed displacement. A region may change offsets seasonally or by legal decree. For future appointments in a region's local time, store ZoneId and a DST resolution policy; when an absolute moment is needed, compute the Instant using the corresponding time-zone rules.

### 11.6. Assuming a one-day Period always equals a 24-hour Duration

Across DST, a calendar day can be 23 or 25 hours long. Depending on requirements, choose whether to add by Period or Duration.

### 11.7. Ignoring nanoseconds when aggregating data

Some sources store timestamps to seconds, milliseconds, or microseconds, while others go down to nanoseconds. Equals still distinguishes the nanosecond part; if you want to group by second, **normalize explicitly** beforehand.

### 11.8. Writing custom equals with the wrong criterion

For domain types containing Instant, OffsetDateTime, or ZoneId, **automatic record equals** may already be right if every component belongs to the value. If the domain wants to compare differently, such as by eventId alone, model a separate domain key. Avoid modifying equals based on non-transitive "approximate time" checks.

## 12. Checklist when working with java.time

1. **Identify the exact kind of quantity:** date, local time, absolute instant, offset, zone, duration, or calendar period.
2. **Read the exact type's contract:** which fields participate in equals/hashCode? Does another API like isEqual or toInstant satisfy the real criterion?
3. **Check type distinctions:** LocalDate differs from LocalDateTime; Instant differs from OffsetDateTime; Duration differs from Period; data with the same abstract meaning is not necessarily the same Java type value.
4. **Define the key before inserting into HashMap/HashSet:** does the same record need to preserve offset, ZoneId, chronology, nanosecond precision, and user-chosen zone?
5. **Handle zones and DST:** if a local date-time does not exist or occurs twice, what is the rule for choosing an Instant? Do you need to store the resolved offset?
6. **Standardize precision and chronology:** when integrating multiple sources/calendar systems, convert intentionally to a canonical key.
7. **Test with adversarial cases:** two OffsetDateTimes with the same Instant and different offsets; two ZonedDateTimes with the same Instant and different zones; two LocalDateTimes with the same wall time in two zones; Duration and Period across a DST day; two Instants differing by 1 nanosecond.
8. **Verify the hash contract:** keys where equals is true must have equal hashes, yet equal hashes do not prove equals is true.

**Core takeaway:** **java.time types are values with distinct contracts**. **equals/hashCode** answers whether two objects have the same **value of that exact type**. **isEqual** on appropriate types or **toInstant()** answers whether they share the same **position on the timeline**. **LocalDateTime** has no absolute instant; **Period** is not **Duration**; **ZoneId** is not **ZoneOffset**. Match the type and comparison operation to the business meaning before grouping, looking up, or deduplicating.
