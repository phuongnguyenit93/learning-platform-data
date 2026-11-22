# Time Zones, tzdb Data, and Date-Time Processing Results

When upgrading the JDK, changing container images, or moving an application to a new deployment environment, date-time handling code can begin producing **different results** even though the source code has not changed. A meeting converting to a different local time than before, a scheduled job shifting by an hour, an expiration timestamp miscalculated around daylight saving time transitions, or transaction history displaying a different offset are situations you may encounter.

The cause is not necessarily a bug in the Java API. Date-time processing results depend simultaneously on the **time data type**, the **selected time zone**, the **tzdb time zone rule set**, the **system clock**, **input/output data**, and the **policy for handling nonexistent or overlapping times**. A newer JDK may include a newer tzdb update reflecting regulatory decisions across many countries. Consequently, the same `LocalDateTime` and the same `ZoneId` may map to a different `Instant` for future points in time.

This lesson explains the relationship between `java.time`, tzdb data (Time Zone Database/IANA), the default timezone, and calendar calculations; guides inventorying and verifying changes during Java Advance Compatibility Migration; and recommends appropriate time representations for transactions, appointments, schedules, and data exchange.

## 1. Distinguishing Fundamental Concepts

Using a single phrase "date-time" for every value easily leads to bugs. Distinguish:

| Concept | Example | Meaning |
|---|---|---|
| **Instant** | `2024-03-10T07:30:00Z` | A specific point on the UTC timeline |
| **Local date** | `2024-03-10` | A date in a calendar system, without a time zone |
| **Local time** | `09:00` | A wall-clock time, without a date or time zone |
| **Local date-time** | `2024-03-10T02:30` | Date and time "on the wall", without an instant determined yet |
| **UTC offset** | `+07:00`, `-05:00` | Numeric offset at a point in time |
| **Time zone ID** | `Asia/Ho_Chi_Minh`, `America/New_York` | Region identifier carrying offset rules over time |
| **Zone rules / tzdb** | Transitions and offsets per region | Historical and future rules used to map local time ↔ instant |
| **Duration** | 24 hours | Length of time on the timeline |
| **Period** | One calendar day | Amount of time in calendar fields, not always equal to 24 actual hours |

### 1.1. An Offset Is Not a Time Zone

An offset such as `+07:00` states that local time is seven hours ahead of UTC. However, this offset **contains no historical rules, DST, or future changes**.

A Zone ID such as `America/New_York` tells the JVM to look up transition rules by date. At different times, this region may use `-05:00` or `-04:00` by regulation. Storing only the current offset is insufficient to compute the local time of a meeting taking place months later.

`Asia/Ho_Chi_Minh` is an appropriate IANA Zone ID when the system needs to represent Vietnam time and historical rules. If you only need to represent a known offset, `ZoneOffset.ofHours(7)` has a different meaning: a fixed offset not tied to a region's history/policy.

### 1.2. LocalDateTime Is Not a Point on the Timeline

Two systems given the same `LocalDateTime.parse("2024-04-01T09:00")` but applying `Asia/Ho_Chi_Minh` and `Europe/London` will yield different `Instant`s. Only after combining local time with a zone and deciding how to handle ambiguous times do we determine an actual point in time.

This matters when API or database data contains only the string `2024-04-01 09:00:00`. You cannot infer on your own whether it is UTC, user time, server time, or headquarters time if the data contract does not specify it.

### 1.3. UTC Is an Exchange Baseline, Not a Replacement for Business Time Zones

For audit logs, event generation timestamps, and transaction ordering, storing `Instant`/UTC is usually appropriate. For "the store opens at 09:00 local time," a fixed UTC timestamp is insufficient to describe the recurring rule in the future.

You should separate:
- **When did it happen?** → instant/UTC.
- **Which local time in which zone does the user want?** → local date/time + ZoneId.
- **Is the schedule calculated by calendar days or actual elapsed time?** → `Period` or `Duration` accordingly.

## 2. What Is tzdb and Why Does It Change Results?

The **Time Zone Database (tzdb)**, also commonly known as the IANA Time Zone Database, stores the history and time-transition rules of regions. The data includes offsets, daylight saving time (DST) transitions, transition instants, and information needed to interpret civil calendars.

Countries/territories may change daylight saving policies or offsets through new regulations. When tzdb is updated, rules for future dates can change; historical data is also occasionally revised based on new information.

Java provides the `java.time` API to query rules. In many common JDKs, tzdb data is bundled in the runtime image and updated alongside JDK/vendor updates. Some environments have a custom `ZoneRulesProvider`; therefore, do not assume every runtime uses the same source or the same data version.

### 2.1. JDK Versions and tzdb Versions Are Not Uniform

Two JVMs both reporting "Java 21" from different update builds or vendors may contain different tzdb versions. Conversely, two different JDK releases may share the exact same set of tzdb rules for a given region.

Therefore, writing only:
 
~~~text
JDK 21
~~~

is **insufficient** for a date-time handling bug report. You should also record:
- JDK vendor, release, build, and runtime image digest.
- Zone ID used.
- tzdb version reported by the JVM if inspectable.
- Input local date-time or instant.
- How gaps/overlaps are handled.
- Locale, formatter, database driver, and related configuration if applicable.

### 2.2. Reading Versions Known to ZoneRulesProvider

Java example:

~~~java
import java.time.ZoneId;
import java.time.zone.ZoneRules;
import java.time.zone.ZoneRulesProvider;
import java.util.NavigableMap;

public class TzdbInfo {
    public static void main(String[] args) {
        String zoneName = "America/New_York";
        ZoneId zone = ZoneId.of(zoneName);

        NavigableMap<String, ZoneRules> versions =
                ZoneRulesProvider.getVersions(zone.getId());

        System.out.println("Zone: " + zone);
        System.out.println("Known rules versions: " + versions.keySet());
        System.out.println("Current rules: " + zone.getRules());
    }
}
~~~

With the default TZDB provider in many JDKs, keys look like `2024a` or `2025b`. Exact values depend on the JDK build and data source; **do not hardcode a single expected version for every system**.

`ZoneRulesProvider.getVersions` returns the versions that the provider can supply for that zone; it is not an API promise that all historical tzdb versions are always retained. A custom provider may use a different version format or not supply multiple versions. Record what the actual runtime reports.

### 2.3. JVM Timezone and the Operating System

A container may hold the operating system's timezone library (for example, zoneinfo) and a Java runtime with its own tzdb. Updating the OS timezone package **does not guarantee** the Java runtime has the same rule version; likewise, updating the JDK does not necessarily update every tool or database outside the JVM.

Inventory separately:
- Java runtime and JVM tzdb.
- OS timezone configuration, and the `TZ` environment variable if used.
- Database/server timezone data.
- Other services written in different languages.
- Browser/mobile clients or third-party timezone libraries.
- Standalone schedulers or message queue systems that process local time.

With the same Zone ID, components using different tzdb versions may compute different results for points in time affected by new rules.

## 3. java.time: Choosing the Right Data Type

The core classes in `java.time` help avoid using a single type to represent every concept.

| Java type | Has date? | Has time? | Has offset/zone? | When to use |
|---|---:|---:|---|---|
| `Instant` | On timeline | On timeline | UTC timeline | Past events, absolute timestamps |
| `LocalDate` | Yes | No | No | Birthdays, invoice dates, calendar holidays |
| `LocalTime` | No | Yes | No | Daily opening hours |
| `LocalDateTime` | Yes | Yes | No | User-selected local time, unresolved |
| `OffsetDateTime` | Yes | Yes | Fixed offset | Passing an instant and offset across APIs |
| `ZonedDateTime` | Yes | Yes | ZoneId + resolved offset | Displaying/calculating schedules tied to a zone |
| `ZoneId` | No | No | Region identifier | Timezone rules to apply |
| `ZoneOffset` | No | No | Offset | Representing an offset at a point in time |
| `Duration` | Time span |  | No | Timeouts, SLAs, actual seconds/minutes |
| `Period` | Calendar span |  | No | Adding calendar days/months/years |

Note: an `OffsetDateTime` has an offset and thus identifies an instant, yet does not carry an IANA region name to compute future daylight saving policies. A `ZonedDateTime` stores a ZoneId and the offset applied to a local date-time; when reconstructed from local time after tzdb changes, the resolved instant may differ.

### 3.1. Example Converting from Instant to Local Time

~~~java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class TimeConversion {
    public static void main(String[] args) {
        Instant event = Instant.parse("2024-01-01T00:00:00Z");

        ZonedDateTime vietnam =
                event.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));

        ZonedDateTime newYork =
                event.atZone(ZoneId.of("America/New_York"));

        System.out.println(vietnam);
        System.out.println(newYork);
    }
}
~~~

From the **same instant**, different time zones may display different dates and times. Switching zones for display should not alter the instant of an event that has already occurred.

### 3.2. Example Resolving Local Time to an Instant

~~~java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class AppointmentTime {
    public static void main(String[] args) {
        LocalDateTime requested =
                LocalDateTime.parse("2024-01-01T09:00:00");
        ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

        ZonedDateTime scheduled = requested.atZone(zone);
        Instant when = scheduled.toInstant();

        System.out.println(scheduled);
        System.out.println(when);
    }
}
~~~

For the timestamp in this example, there is no DST ambiguity. However, for regions with offset changes, `atZone` applies the API's default rules when encountering a gap/overlap. For legally or financially significant appointments, actively define a policy to avoid unexpected "automatic selection."

## 4. DST Gap: Nonexistent Local Times

A region observing daylight saving time may move clocks forward by one hour. When that happens, the local time span between the two clock marks may **not exist**.

For example, under `America/New_York` rules on 2024-03-10: clocks jump from 02:00 to 03:00. Therefore, the local time `2024-03-10T02:30` has no valid instant in that zone.

~~~text
Before transition:
2024-03-10 01:59:59  -05:00

After transition:
2024-03-10 03:00:00  -04:00

2024-03-10 02:30:00  (does not exist in this zone)
~~~

### 4.1. How LocalDateTime.atZone Handles Gaps by Default

~~~java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class GapExample {
    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("America/New_York");
        LocalDateTime local =
                LocalDateTime.of(2024, 3, 10, 2, 30);

        ZonedDateTime resolved = local.atZone(zone);
        System.out.println(resolved);
    }
}
~~~

With the zone rules for that point in time, the standard API will **shift the local time forward by the gap length**: `02:30` becomes `03:30` with offset `-04:00`.

This is intentional default behavior of the API, but it does not necessarily suit business requirements. For example, for a trading session that may only open strictly at 02:30, automatically moving it to 03:30 could violate the contract.

### 4.2. Detecting Gaps Before Accepting a Schedule

~~~java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.zone.ZoneRules;
import java.util.List;
import java.time.ZoneOffset;

public class GapValidation {
    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("America/New_York");
        LocalDateTime local =
                LocalDateTime.of(2024, 3, 10, 2, 30);

        ZoneRules rules = zone.getRules();
        List<ZoneOffset> offsets = rules.getValidOffsets(local);

        if (offsets.isEmpty()) {
            System.out.println("Gap: local time does not exist");
            System.out.println(rules.getTransition(local));
        } else {
            System.out.println("Valid offsets: " + offsets);
        }
    }
}
~~~

For a gap, `getValidOffsets` returns an empty list. `getTransition` can provide the corresponding transition. The application can choose a policy:
- **Reject:** require the user to enter another valid time.
- **Shift forward:** advance by the gap length like `atZone`.
- **Move to next valid local time:** move to the first valid local time (for example, 03:00), unlike shifting 02:30 to 03:30.
- **Follow domain rule:** custom rules for booking, payroll, settlement, or schedulers.

Which policy is right depends on the business contract; there is no single choice valid for every kind of data.

## 5. DST Overlap: A Local Time Occurring Twice

When clocks fall back, a local hour span can repeat. In `America/New_York` on 2024-11-03, `01:30` occurs **twice**:
- `2024-11-03T01:30-04:00`, corresponding to instant `2024-11-03T05:30:00Z`.
- `2024-11-03T01:30-05:00`, corresponding to instant `2024-11-03T06:30:00Z`.

The same displayed date and time, yet two different events on the timeline.

### 5.1. Inspecting Both Valid Offsets

~~~java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.util.List;

public class OverlapExample {
    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("America/New_York");
        LocalDateTime local =
                LocalDateTime.of(2024, 11, 3, 1, 30);

        List<ZoneOffset> offsets =
                zone.getRules().getValidOffsets(local);

        System.out.println(offsets);

        ZonedDateTime first = ZonedDateTime.ofLocal(
                local, zone, offsets.get(0)
        );
        ZonedDateTime second = ZonedDateTime.ofLocal(
                local, zone, offsets.get(1)
        );

        System.out.println(first.toInstant());
        System.out.println(second.toInstant());
    }
}
~~~

Under the rules for that time, the list contains two offsets; the instants differ by one hour. `ZonedDateTime.ofLocal` uses the preferred offset if that offset is valid. For an overlap, `LocalDateTime.atZone` normally selects the offset occurring earlier in the transition, typically the daylight saving offset; do not let default behavior decide in place of your scheduling policy.

### 5.2. Overlap Handling Policies

A booking system can:
- Require the user to select the first or second occurrence.
- Use the offset submitted by the user alongside the local time.
- Prohibit schedules falling inside an overlap if they cannot be disambiguated clearly.
- Choose the earlier or later instant according to a published business rule.

A log/audit must never store only `2024-11-03 01:30` in the New York zone: that lacks enough information to identify which event occurred. Use instant/UTC, and additionally store ZoneId if display in the original zone is needed.

## 6. Strict Time Conversion

If the application needs to guarantee that a local time has **exactly one valid offset**, do not call `atZone` directly; instead check `ZoneRules`.

~~~java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.util.List;

public final class StrictLocalTimeResolver {
    public static ZonedDateTime resolve(
            LocalDateTime local,
            ZoneId zone
    ) {
        List<ZoneOffset> validOffsets =
                zone.getRules().getValidOffsets(local);

        if (validOffsets.isEmpty()) {
            throw new IllegalArgumentException(
                    "Non-existent local time: " + local + " in " + zone
            );
        }

        if (validOffsets.size() > 1) {
            throw new IllegalArgumentException(
                    "Ambiguous local time: " + local + " in " + zone
            );
        }

        return ZonedDateTime.ofStrict(
                local,
                validOffsets.get(0),
                zone
        );
    }
}
~~~

Key differences:
- `getValidOffsets(...).size() == 0`: gap, no valid instant.
- `size() == 1`: one valid offset.
- `size() == 2`: typical overlap, two valid instants.

The function above **rejects gaps and overlaps**, which fits when you want users to resolve ambiguities. In another business domain, you can define a resolver taking a policy parameter. What matters is that function names, API contracts, and tests clearly express the choice, avoiding an implicit conversion step.

### 6.1. Do Not Assume Every Transition Is Exactly One Hour

Some regions may adjust offsets by a number of minutes other than one hour or have larger historical changes. Do not write code that automatically adds/subtracts exactly 60 minutes if the goal is to handle transitions according to tzdb rules.

The `ZoneOffsetTransition` and `ZoneRules` APIs provide the transition and actual duration of the gap/overlap at the examined date-time. Depending on policy, use `transition.getDuration()` and the before/after transition bounds rather than hardcoding.

## 7. Duration vs. Period: 24 Hours Is Not Always One Calendar Day

A common source of bugs is treating adding one day as always equivalent to adding 24 hours. This is false when a local date-time crosses a DST transition.

Example:
- Start at `2024-03-09 12:00` in New York (before switching to DST).
- `plusDays(1)` moves the schedule to **12:00 the next day** in local time.
- `plusHours(24)` advances the point on the timeline by **24 actual hours**; after the DST jump, the local time may be **13:00**.

~~~java
import java.time.Duration;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class CalendarVsDuration {
    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("America/New_York");
        ZonedDateTime start =
                ZonedDateTime.of(2024, 3, 9, 12, 0, 0, 0, zone);

        ZonedDateTime oneCalendarDayLater = start.plusDays(1);
        ZonedDateTime twentyFourHoursLater = start.plusHours(24);

        System.out.println(oneCalendarDayLater);
        System.out.println(twentyFourHoursLater);

        System.out.println(
            Duration.between(
                start.toInstant(),
                oneCalendarDayLater.toInstant()
            ).toHours()
        );
    }
}
~~~

Under the example's DST rules, the instant interval from 12:00 on March 9 to 12:00 on March 10 is **23 hours**, not 24 hours.

### 7.1. Choosing According to Need

| Need | Appropriate Expression |
|---|---|
| 30-second request timeout | `Duration.ofSeconds(30)` |
| Token expiring after 24 actual hours | `Instant.plus(Duration.ofHours(24))` |
| An event occurring at 09:00 local time every day | `LocalTime` + `ZoneId` and calendar rules |
| Extending a contract by one calendar month | `LocalDate.plusMonths(1)` or `Period`, per policy |
| Calculating processing latency | Difference between two `Instant`s or a monotonic clock for in-process duration measurement |
| Scheduling at 02:30 on a DST transition day | Explicit gap/overlap policy |

For measuring elapsed time inside a process, `System.nanoTime()` is a more suitable duration source than subtracting two `LocalDateTime.now()` values, because the wall clock can be adjusted by the OS or time synchronization. `nanoTime` is not a UTC timestamp and must not be used as an absolute calendar point in time.

## 8. JVM Default Timezone: A Hidden Source of Discrepancies

Not all code passes `ZoneId` explicitly. The following calls depend on the default timezone or environment configuration:

~~~java
ZoneId.systemDefault();
ZonedDateTime.now();
java.util.TimeZone.getDefault();
new java.text.SimpleDateFormat("yyyy-MM-dd HH:mm:ss");
~~~

Meanwhile:
- `Instant.now()` reads the current instant, without attaching a ZoneId to the value itself.
- `LocalDate.now()` uses the default time zone to determine "today," unless a zone/clock is explicitly passed.
- `LocalDateTime.now()` obtains the local date-time in the default timezone.

If the image/runtime/OS changes the default zone, the same instant may be converted into a different local time and day boundaries may shift.

### 8.1. Inspecting Runtime Configuration

~~~bash
java -version
java -XshowSettings:properties -version
~~~

Look for information such as:
- `java.version`, `java.vendor`, `java.home`.
- `user.timezone` if set.
- `user.language` and `user.country` when parsing/formatting depends on locale.

You can use the following small program:

~~~java
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.util.TimeZone;

public class DefaultTimeZoneReport {
    public static void main(String[] args) {
        System.out.println("user.timezone=" +
                System.getProperty("user.timezone"));
        System.out.println("ZoneId.systemDefault=" +
                ZoneId.systemDefault());
        System.out.println("TimeZone.getDefault=" +
                TimeZone.getDefault().getID());
        System.out.println("Local now=" + ZonedDateTime.now());
    }
}
~~~

`user.timezone` may be unset before the runtime derives the zone from the system. Observe `ZoneId.systemDefault()` and actual process configuration rather than checking only the property.

### 8.2. Controlling Timezone Deliberately

For an application-operated JVM, you can specify the timezone at launch:

~~~bash
java -Duser.timezone=UTC -jar app.jar
~~~

Note that `-Duser.timezone=UTC` comes **before** `-jar`, not as a trailing application argument. Some OSes/containers also have a `TZ` environment variable, yet how the JVM derives the timezone from the OS and environment depends on the platform, vendor, and JDK build.

Setting the JVM timezone to UTC can be a good choice to reduce ambiguity in logging/backends. However, it **does not replace storing the business ZoneId**. For example, a reminder at 09:00 Hanoi time should not be reinterpreted as 09:00 UTC simply because the server runs in UTC.

### 8.3. Caching and Changing the Default Timezone In-Process

Legacy APIs such as `TimeZone.getDefault()` may cache the default information. Changing an environment variable or host timezone after the JVM is already running does not guarantee that every library, formatter, or scheduler immediately picks up the new rules.

`TimeZone.setDefault(...)` can change the default timezone inside the JVM, but calling it at runtime has process-wide effects and can cause inconsistent behavior in other components. Lock down configuration at startup, pass `ZoneId`/`Clock` explicitly in business code, and use an appropriate deploy/restart procedure when updating the runtime.

## 9. Legacy Java Date, Calendar, and SimpleDateFormat

Long-lived code often uses:
- `java.util.Date`.
- `java.util.Calendar`.
- `java.text.SimpleDateFormat`.
- `java.sql.Date`, `java.sql.Time`, `java.sql.Timestamp`.

These APIs are not inherently "wrong" in every case, yet their mutable design and reliance on the default timezone easily cause discrepancies during migration. For instance, `Date` represents a point in time to millisecond precision in most ordinary usage; when calling `Date.toString()`, the output is rendered in the default timezone. Thus a string looking different does not necessarily prove the instant changed.

### 9.1. Converting Date to Instant and Formatting Explicitly

~~~java
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Date;

public class LegacyDateAdapter {
    private static final DateTimeFormatter FORMAT =
            DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm:ss VV");

    public static String format(Date legacyDate, ZoneId zone) {
        Instant instant = legacyDate.toInstant();
        return FORMAT.format(instant.atZone(zone));
    }

    public static Date fromInstant(Instant instant) {
        return Date.from(instant);
    }
}
~~~

Here the formatter has an explicit pattern, the zone is passed in, and the input is an explicit instant. Do not use `Date.toString()` as an exchange format between services because it depends on the default timezone and is not a stable format for machine parsing.

### 9.2. Note That SimpleDateFormat Is Not Thread-Safe

`SimpleDateFormat` is mutable and unsafe to share as a single instance across multiple threads without synchronization. In new code, prefer immutable/thread-safe `DateTimeFormatter` with explicit pattern, locale, and zone when formatting data.

However, verify patterns when migrating: `yyyy` vs. `uuuu`, `YYYY` (week-based-year), offset/zone symbols, and lenient/strict parsing are not always equivalent. A formatter change can corrupt data near year-end boundaries or when parsing inputs lacking an offset.

## 10. Storing and Exchanging Date-Time Data

### 10.1. Past Events: Store Instant

For order created time, payment captured time, audit events, or token issue time, typically store an absolute instant:

~~~text
2024-11-03T06:30:00Z
~~~

Instead of only:
 
~~~text
2024-11-03 01:30:00
~~~

The first can be compared on the timeline; the second lacks a zone/offset and can therefore be ambiguous across regions.

JSON APIs should clearly specify the type and format, such as an ISO-8601 timestamp with an offset or UTC `Z`, rather than letting the client infer from the device's timezone. Field names like `createdAtUtc` can make the contract clearer if consistent with system conventions.

### 10.2. Future Events by Civil Time: Store Local + Zone

For example, a user schedules a meeting in New York:
 
~~~json
{
  "localDateTime": "2025-11-03T09:00:00",
  "timeZone": "America/New_York"
}
~~~

At scheduling time, the system may also compute and store the resolved instant to send notifications. However, if authorities change tzdb rules for that future time, a policy is needed: **keep 09:00 local time** or **keep the instant locked in at booking time**?

There is no universal answer. For airport/store appointments, there is usually reason to keep the local time; for a financial transaction with a fixed actual point in time, keeping the instant may be required. For a system requiring auditing, store the local input, ZoneId, resolved offset/instant, rules version used, and recalculation timestamp when changes occur.

### 10.3. Databases: Do Not Infer from SQL Type Names

Databases and JDBC drivers have differing semantics for:
- `TIMESTAMP WITHOUT TIME ZONE`.
- `TIMESTAMP WITH TIME ZONE`.
- `DATETIME`.
- `DATE`, `TIME`.
- Mappings for `Instant`, `OffsetDateTime`, and `LocalDateTime`.

The name `TIMESTAMP WITH TIME ZONE` **does not guarantee the database preserves the user's IANA ZoneId**. Some DBMSs normalize or store offsets/instants in their own way; drivers may apply a session timezone or conversion on read/write.

When migrating:
1. Check the column types and semantics of the exact database in use.
2. Check JDBC/ORM mappings, driver versions, and session timezone.
3. Create fixtures at UTC day boundaries, DST gaps/overlaps, and year-end dates.
4. Read/write using the exact target JDK and driver.
5. Compare both instants and local displays against the contract, not only text formats.

### 10.4. Serialization and External Partners

If an API returns:
 
~~~json
{"timestamp":"2024-11-03T01:30:00"}
~~~

without an offset/ZoneId, consumers may apply their own timezone, leading to different outcomes when clients are in different regions or when a new server changes its default. Define an explicit contract:
- Event timestamps: ISO-8601 UTC or an offset convertible to an instant.
- Local-time schedules: local date-time plus IANA ZoneId.
- Durations: explicit units and calendar/elapsed semantics.
- Ambiguous/gap inputs: validation errors or a documented policy.

## 11. Recurring Schedules and Schedulers

A cron expression such as "02:30 every day" is **insufficient** to define a schedule under DST:
- On spring-forward days, 02:30 may not exist.
- On fall-back days, 01:30 may occur twice.
- If tzdb changes, future schedules may shift their expected instants.

Each scheduler/framework has its own policy for misfires, gaps, overlaps, timezones, and missed executions; do not assume all cron engines behave like `ZonedDateTime.atZone`.

### 11.1. Three Policy Types to Distinguish

| Requirement | Design Choice | Consequence |
|---|---|---|
| Run once every 24 actual hours | 24h Duration on the timeline | Local time may shift across DST |
| Every local day at 09:00 | LocalTime + ZoneId + calendar scheduling | Interval between runs may be 23 or 25 hours |
| Run exactly once at 01:30 on an overlap day | Must specify offset/occurrence | Cannot be inferred from local time alone |
| Do not skip batch when time does not exist | Explicit skip/shift/retry rule | Requires dedicated handling for gap days |

For business applications, determine whether the requirement follows **civil time** or **elapsed time**, and choose the corresponding scheduler policy. A daily invoice calculation task may need accounting periods by local date; a 24-hour TTL job should not rely on adding one calendar day.

### 11.2. Recomputing Schedules After a tzdb Update

If a scheduler stores many future triggers as precomputed instants, upgrading tzdb may require recomputing instants from the ZoneId and local recurrence rule when the new policy takes effect.

The plan should state:
- Which triggers undergo recalculation.
- Which locked schedules must not change automatically.
- How schedules already sent to consumers/partners are handled.
- Audit trail of the tzdb version and reason for change.
- Testing on service restarts and with multi-instance schedulers.

Do not silently alter user schedules due to a JDK upgrade unless the product contract specifies it.

## 12. Regression Testing When JDK/tzdb Changes

To prove date-time results are controlled, tests must use **deterministic inputs**, **explicit zones**, **documented expected behavior**, and run on the **target JDK/tzdb**.

### 12.1. Do Not Use the Default Zone or Real Clock in Critical Unit Tests

A test like:

~~~java
assertEquals(LocalDate.now(), businessService.currentDate());
~~~

may depend on CI run time, the build agent's timezone, and day boundaries. Inject `Clock` and `ZoneId` instead:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

public final class BusinessDates {
    private final Clock clock;
    private final ZoneId businessZone;

    public BusinessDates(Clock clock, ZoneId businessZone) {
        this.clock = clock;
        this.businessZone = businessZone;
    }

    public LocalDate today() {
        return LocalDate.now(clock.withZone(businessZone));
    }

    public static void main(String[] args) {
        Clock fixed = Clock.fixed(
                Instant.parse("2024-01-01T23:30:00Z"),
                ZoneId.of("UTC")
        );

        BusinessDates dates = new BusinessDates(
                fixed,
                ZoneId.of("Asia/Ho_Chi_Minh")
        );

        System.out.println(dates.today());
    }
}
~~~

The same instant at `23:30Z` is already the next day in Vietnam. A test with a fixed clock stabilizes the current point in time, yet **does not freeze tzdb**; if the test uses a zone whose rules changed, expected results may still change when the JDK updates its data.

### 12.2. Testing Gaps/Overlaps with ZoneRules

JUnit 5 example:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

import java.time.LocalDateTime;
import java.time.ZoneId;

class DstRulesTest {
    private final ZoneId newYork =
            ZoneId.of("America/New_York");

    @Test
    void springForwardTimeDoesNotExist() {
        LocalDateTime gap =
                LocalDateTime.of(2024, 3, 10, 2, 30);

        assertTrue(
                newYork.getRules().getValidOffsets(gap).isEmpty()
        );
    }

    @Test
    void fallBackTimeIsAmbiguous() {
        LocalDateTime overlap =
                LocalDateTime.of(2024, 11, 3, 1, 30);

        assertEquals(
                2,
                newYork.getRules().getValidOffsets(overlap).size()
        );
    }
}
~~~

This is an illustrative test using rules that have already occurred. When writing tests involving future schedules in regions at risk of policy changes, distinguish:
- **Business policy** tests: "reject all gaps" or "choose the later offset," independent of specific dates.
- **tzdb behavior** tests: use specific region dates, explicitly tied to an accepted rules/version baseline.
- **Deployment** tests: run on the actual JDK image to detect version drift.

### 12.3. Regression Matrix to Cover

| Group | Scenarios |
|---|---|
| Default timezone | JVM UTC vs. a specific region; with/without `user.timezone` |
| Instant conversion | UTC ↔ Asia/Ho_Chi_Minh, America/New_York, or customer regions |
| Gap | Nonexistent local times and handling policies |
| Overlap | Two valid offsets, selecting offset and instant |
| Calendar-day arithmetic | plusDays/plusMonths across DST and month-end |
| Elapsed duration | plusHours/Duration, timeouts, and TTLs |
| Format/parse | Locale, ISO-8601, offsets, ZoneId, boundary years |
| Database | Round-trip Instant, LocalDateTime, OffsetDateTime |
| Scheduler | Recurring runs by local time across transitions |
| Data exchange | Clients in different zones reading the same payload |
| tzdb drift | Old/new JDKs using different region rules |

### 12.4. Characterization Before Upgrading the JDK

For a legacy system lacking an explicit contract, run fixtures on the current JDK and record:
- Inputs, time types, and ZoneId.
- Tzdb version/runtime identity.
- Offsets, instants, formatted outputs, and side effects.
- Schedules/expirations computed by the system.
- Known or accepted discrepancies.

Then run the same fixtures on the target JDK and categorize differences:
1. Intentional tzdb changes per region regulations.
2. Differences in default timezone/locale/container.
3. Parse/format/mapping/driver errors.
4. Business logic bugs mixing local time with elapsed time.
5. Drift caused by non-deterministic clocks and test data.

Do not alter every expected value just to make tests pass; decide which results are right according to the business contract and new timezone policy.

## 13. A Program for Comparing Rules Across Environments

You can write a small program printing the runtime, tzdb version, and conversion results to run on two different JDKs. No framework dependencies are needed.

~~~java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.zone.ZoneRulesProvider;

public class TimeZoneDiagnostic {
    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("America/New_York");
        LocalDateTime requested =
                LocalDateTime.parse("2024-11-03T01:30:00");

        System.out.println("Java: " +
                System.getProperty("java.runtime.version"));
        System.out.println("Vendor: " +
                System.getProperty("java.vendor"));
        System.out.println("Default zone: " +
                ZoneId.systemDefault());
        System.out.println("TZDB versions: " +
                ZoneRulesProvider.getVersions(zone.getId()).keySet());
        System.out.println("Valid offsets: " +
                zone.getRules().getValidOffsets(requested));

        ZonedDateTime defaultResolution = requested.atZone(zone);
        Instant instant = defaultResolution.toInstant();

        System.out.println("Resolved value: " + defaultResolution);
        System.out.println("Resolved instant: " + instant);
    }
}
~~~

Execute with different JDKs:

~~~bash
/path/to/jdk-old/bin/javac TimeZoneDiagnostic.java
/path/to/jdk-old/bin/java TimeZoneDiagnostic

/path/to/jdk-new/bin/javac TimeZoneDiagnostic.java
/path/to/jdk-new/bin/java TimeZoneDiagnostic
~~~

If building classes with a newer JDK to run on an older JDK, use the appropriate target release (for example, `--release` with a compiler-supported release) or compile separately per JDK. Do not let an `UnsupportedClassVersionError` from the class-file target obscure the timezone issue under investigation.

### 13.1. Which Zones Should Be Compared?

There is no need to scan every ZoneId when the product serves only certain regions. Prioritize:
- ZoneIds actually stored in user/partner data.
- Regions with DST or past policy changes.
- Regions serving critical scheduling/settlement.
- Zones with prior bugs or incidents.
- Aliases/legacy timezone IDs still appearing in the database.

Check the number of zones in the system via an actual inventory rather than assuming customers only use the server's timezone.

## 14. Safe JDK/tzdb Rollout Procedure

### Step 1: Lock In the Time Contract

Explicitly document each data field as an instant, local time, local date, or recurrence schedule. For future events, determine whether a tzdb change shifts the instant alongside local time.

### Step 2: Inventory All Rule Sources

Record the JDK/vendor/build, tzdb version, default timezone, and container configuration. Check DBs, schedulers, clients, and other services that perform independent conversions. If JVM tzdb is updated via a JDK patch, verify the actual runtime binary inside the final image.

### Step 3: Establish Baseline and Fixtures

Collect historical production cases, DST gap/overlap cases, future events, and regions actively used by customers. Avoid tests relying only on `LocalDateTime.now()` or the real clock.

### Step 4: Test on the New JDK/tzdb

Run unit, integration, database round-trip, scheduler, and API contract tests. Compare instants, local displays, offsets, dates, and trigger conditions. For discrepancies, determine whether they were pre-existing bugs or valid changes in region data.

### Step 5: Confirm Policy for Future Events

For schedules far in the future, decide the re-resolution procedure after a tzdb update. Record audits and send notifications when instants change, if required by contracts. Be especially careful with payment times, opening hours, tickets, meetings, and legal deadlines.

### Step 6: Roll Out in Batches

Deploy the new JDK image to staging and canary. Ensure interacting replicas/services do not suffer rules drift causing inconsistent results, especially when jointly processing a local schedule. Watch for scheduler failures, increased parse errors, shifted notification times, and incorrect displayed dates.

### Step 7: Operate and Maintain

Periodically monitor JDK/tzdb updates from your vendor. Maintain region-specific test fixtures and add cases when time policies change in served regions. Do not try to hold onto an old tzdb permanently just to "avoid changing results"; that can cause the system to compute the new legal time incorrectly.

## 15. Common Mistakes

- **Treating a ZoneId as a fixed offset:** breaks when a region changes DST or historical/future policies.
- **Storing LocalDateTime and calling it UTC:** loses timezone information and can turn an ambiguous time into the wrong instant.
- **Using OffsetDateTime for all future schedules:** an offset does not describe future region rules.
- **Using server time as business time:** switching containers to UTC changes results if code relies on the default zone.
- **Adding 24 hours for "tomorrow at the same local time":** breaks across DST.
- **Adding one calendar day for a 24-hour TTL:** in reality it may be only 23 or up to 25 hours.
- **Letting atZone silently resolve gaps/overlaps without a policy:** user schedules may be shifted or pick the wrong occurrence.
- **Storing only date-time strings without offset/ZoneId:** insufficient data for cross-service exchange.
- **Believing OS timezone updates mean JVM tzdb was updated:** components may use different data sources.
- **Recording only the Java major version:** lacks vendor, patch build, and rules version for investigation.
- **Believing Clock.fixed freezes timezone rules:** a fixed clock freezes the reference instant, not tzdb data.
- **Testing only normal hours:** gaps/overlaps and day boundaries remain uncovered.
- **Comparing Date.toString() and concluding a timestamp changed:** output depends on the default timezone.
- **Failing to review database drivers/ORMs:** JDBC and SQL types have different semantics.
- **Immediately editing expected values when upgrading tzdb:** can mask bugs or alter unapproved future contracts.
- **Not checking across multiple services:** schedulers or clients using another tzdb version may compute differently from the backend.

## 16. Checklist Before Accepting Date-Time Behavior Changes

- [ ] Recorded JDK vendor/version/build and deployed runtime image.
- [ ] Recorded IANA ZoneIds used in business data, not just offsets.
- [ ] Identified where the JVM default timezone comes from and where code depends on it.
- [ ] Queried runtime tzdb/rules version where tooling supports it.
- [ ] Distinguished instant, local date-time, offset date-time, and recurrence schedule data types.
- [ ] Gap/overlap inputs have explicit policies, not relying on implicit choices.
- [ ] Verified Duration/Period arithmetic across DST.
- [ ] Tested day/year boundaries and locale/formatting where relevant.
- [ ] Checked database mapping, session timezone, JDBC/ORM, and API payloads.
- [ ] Explicit fixtures and Clock/ZoneId exist for critical tests.
- [ ] Compared the same fixtures on baseline JDK/tzdb and target JDK/tzdb.
- [ ] Decided whether future schedule instants should be recomputed when rules change.
- [ ] Replicas, schedulers, databases, and clients have consistent rules policies.
- [ ] Monitoring is in place for scheduling/notification/settlement errors after rollout.
- [ ] Accepted differences have business sign-off and evidence.

## 17. Conclusion

**Time zones are not merely offsets, and tzdb is not immutable data.** A Java migration can change the rules the JVM uses to convert a local time into an instant; changing the default timezone, swapping the JDK image, updating the database driver, or upgrading the scheduler can also make date-time processing results differ from before.

To keep contracts accurate, choose Java time types according to the nature of the data, use explicit `ZoneId` and `Clock`, distinguish civil calendars from Duration, actively handle DST gaps/overlaps, and test against the actual runtimes/tzdb that will be deployed. For past events, store instants; for future schedules in local time, store local time + ZoneId along with an adjustment policy. Recording region data versions, comparing fixtures, and managing schedule changes after tzdb updates will help the system reflect new legal rules without accidentally breaking time commitments to users.
