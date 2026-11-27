# CONVERT_TZ, Timezone Tables, and Daylight Saving Time Transitions

Working with time-zone-aware dates and times requires distinguishing an **absolute instant** from **local wall-clock time**. The same UTC instant can display as different clock times across regions; conversely, a local clock time on a Daylight Saving Time transition date may not exist or may occur twice. MySQL provides `CONVERT_TZ()` to convert between time zones, though conversions using named regions such as `Asia/Ho_Chi_Minh` or `America/New_York` only work properly when the server has the corresponding time zone data loaded.

This lesson focuses on three areas: using `CONVERT_TZ()`, installing and updating timezone tables, and handling Daylight Saving Time (DST). This is essential in the `DATABASE_MYSQL` module because time zone discrepancies can corrupt order creation timestamps, appointments, daily reports, payment deadlines, and cross-system data synchronization.

## 1. A Time Zone Is a Set of Rules, Not Just a UTC Offset

A named time zone such as `America/New_York` is a collection of rules determining the UTC offset at any point in time. Those rules can change over history, legislation, and regional policy. Consequently, the current offset `-04:00` is insufficient to represent the entire New York time zone.

Distinguish two forms:

- **Named time zone:** a region name from the IANA database, e.g. `Asia/Ho_Chi_Minh`, `Europe/Paris`, `America/New_York`. It contains history and date-dependent transition rules.
- **Fixed UTC offset:** e.g. `+07:00`, `-05:00`, `+00:00`. It represents only a static shift at the point of use, containing no DST rules or regional history.

Vietnam currently uses `Asia/Ho_Chi_Minh` at UTC+07:00 and does not currently observe DST. Even so, using the named zone remains meaningful when representing geographic time zones, historical periods, or synchronizing with external systems. For systems that only need to store absolute instants, storing UTC is usually simpler.

Avoid using abbreviations such as `EST`, `PST`, or `CST` as time zone identifiers. They can be ambiguous, fail to capture full DST rules, or be interpreted differently across systems. Prefer full IANA names.

## 2. How Does `CONVERT_TZ()` Work?

Syntax:

```sql
CONVERT_TZ(datetime_value, from_tz, to_tz)
```

- `datetime_value`: the date/time value to convert.
- `from_tz`: source time zone, either a loaded zone name or a UTC offset.
- `to_tz`: target time zone, either a loaded zone name or a UTC offset.
- Return value: a `DATETIME` value converted to the target time zone; returns `NULL` if an argument is invalid or a time zone name is unrecognized.

Example converting a UTC instant to Vietnam time:

```sql
SELECT CONVERT_TZ(
    '2026-01-15 12:00:00',
    '+00:00',
    'Asia/Ho_Chi_Minh'
) AS vietnam_time;
```

The result is `2026-01-15 19:00:00`, as Vietnam is seven hours ahead of UTC at that time.

Converting Vietnam time to UTC:

```sql
SELECT CONVERT_TZ(
    '2026-01-15 19:00:00',
    'Asia/Ho_Chi_Minh',
    '+00:00'
) AS utc_time;
```

The result is `2026-01-15 12:00:00`.

### Converting Between Two Named Time Zones

```sql
SELECT CONVERT_TZ(
    '2026-07-01 12:00:00',
    'America/New_York',
    'Europe/Paris'
) AS paris_time;
```

MySQL looks up the source region's rules at the input time, determines the corresponding instant, and applies the target region's rules at that exact instant. Because of DST, the difference between two regions is not necessarily constant year-round.

### Using Fixed UTC Offsets

```sql
SELECT CONVERT_TZ(
    '2026-01-15 12:00:00',
    '+00:00',
    '+07:00'
) AS fixed_offset_time;
```

This example does not require zone names in timezone tables because both arguments are fixed offsets. Offsets are suitable for calculations with a known static shift, yet do not replace named time zones when DST or historical rules are needed.

## 3. Why Can `CONVERT_TZ()` Return `NULL`?

Common causes:

1. Misspelled or invalid time zone name, e.g. typo in `Asia/Ho_Chi_Minh`.
2. Server has not loaded timezone tables or is missing the requested region name.
3. Invalid date/time value or offset.
4. Invalid date/time or time zone argument. Cases where a date/time falls outside the convertible range supported by your MySQL version must be tested separately; MySQL may return the value unconverted rather than returning `NULL`.

Quick check:

```sql
SELECT
    CONVERT_TZ('2026-01-15 12:00:00', '+00:00', '+07:00') AS fixed_offset_result,
    CONVERT_TZ('2026-01-15 12:00:00', '+00:00', 'Asia/Ho_Chi_Minh') AS named_zone_result;
```

If the fixed-offset call succeeds while the named-zone call returns `NULL`, check the timezone tables and region name. If both return `NULL`, check the date/time value and offset syntax. If the input falls outside your MySQL version's conversion range, do not rely solely on checking for `NULL`: verify whether the value is returned unchanged without conversion and consult documentation for your running version.

Check whether region names exist in the system table:

```sql
SELECT Name
FROM mysql.time_zone_name
WHERE Name IN (
    'UTC',
    'Asia/Ho_Chi_Minh',
    'America/New_York',
    'Europe/Paris'
)
ORDER BY Name;
```

The `mysql.time_zone*` tables belong to the `mysql` system schema. Application accounts normally should not have read or write privileges on them; loading and updating time zone data should be performed by a DBA or administrative workflow.

## 4. MySQL Time Zone Tables

MySQL uses system tables to store named time zone data. The main tables are:

| Table | General Role |
|---|---|
| `mysql.time_zone_name` | Maps time zone names to internal IDs. |
| `mysql.time_zone` | Time zone structural metadata. |
| `mysql.time_zone_transition` | Rule/offset transition instants. |
| `mysql.time_zone_transition_type` | Offset types and statuses active within a region. |
| `mysql.time_zone_leap_second` | Leap second data if loaded and supported. |

These tables are populated from operating system time zone data or an appropriate timezone package. When empty or missing a required region, functions requiring named time zones such as `CONVERT_TZ()` cannot perform conversions using that region's rules.

### Checking Whether Tables Are Loaded

```sql
SELECT COUNT(*) AS named_zone_count
FROM mysql.time_zone_name;

SELECT Name
FROM mysql.time_zone_name
WHERE Name = 'America/New_York';
```

If the count is 0 or the zone name does not appear, timezone tables are likely not fully loaded. Merely seeing some zone names does not guarantee the latest transition data is installed.

## 5. Loading Timezone Tables on Linux/Unix

On many Linux/Unix systems, MySQL provides the `mysql_tzinfo_to_sql` utility to read OS zoneinfo data and generate SQL statements to populate the `mysql` schema.

First, install or update the OS timezone database package (typically `tzdata`) via your distribution's administrative process. Then run a command such as:

```bash
mysql_tzinfo_to_sql /usr/share/zoneinfo | mysql -u root -p mysql
```

This command reads data from `/usr/share/zoneinfo`, converts it to SQL, and pipes it into the `mysql` database. Depending on the OS, the zoneinfo directory may reside elsewhere; verify the actual path. Enter the password interactively when prompted rather than placing administrative passwords directly on the command line.

A controlled update procedure:

1. Identify the MySQL version and current timezone data.
2. Update the `tzdata` package on the host or obtain an approved IANA dataset.
3. Reload data using `mysql_tzinfo_to_sql` into the `mysql` schema.
4. Restart MySQL during a maintenance window so cached timezone data is reloaded.
5. Verify critical region names and run `CONVERT_TZ()` queries at known test timestamps.
6. Monitor applications for any time or schedule discrepancies after the update.

Do not load timezone data from an arbitrary unverified directory. DST rules can change due to national legislation; fresh data must come from a trusted timezone source and be deployed consistently across environments.

## 6. Loading Timezone Tables on Windows

Windows does not have a standard zoneinfo directory structure like Linux's `/usr/share/zoneinfo`. Therefore, running `mysql_tzinfo_to_sql` against that directory does not apply directly.

Use the official MySQL/Windows SQL timezone tables package matching your version, or a DBA-approved timezone data package. Import the tables into the `mysql` schema according to the distribution's instructions. After loading, restart MySQL and verify the required named zones.

Do not take Windows time zone names like `Pacific Standard Time` and assume MySQL recognizes them as IANA names. MySQL region names follow IANA conventions such as `America/Los_Angeles`, `Asia/Ho_Chi_Minh`, or `Europe/London`. If an application receives a Windows time zone ID, map it to an IANA time zone ID in the application tier using a managed library or mapping table.

## 7. Updating Timezone Data When DST Laws Change

Timezone data is not immutable. Legislatures can shift DST start/end dates, abolish DST, or alter UTC offsets. The IANA Time Zone Database (tzdb) releases updates whenever historical or future rules change.

If the server retains outdated timezone tables, `CONVERT_TZ()` can return wrong results for instants after the new law takes effect, even when the SQL and zone name are completely valid. Consequently, updating timezone data is an operational responsibility for time-aware systems.

### Update Management Workflow

- Track tzdb releases and OS timezone package updates.
- Audit which geographic regions the application actually uses, especially regions with DST or frequent statutory changes.
- Load updated data into timezone tables using a tested procedure.
- Restart MySQL when necessary to clear cached timezone data inside the server process.
- Run regression tests covering past and future transition instants.
- Keep timezone data synchronized across primary, replicas, batch environments, and reporting environments.
- Record the timezone data version and update timestamp for traceability if report outputs change.

If MySQL has already cached metadata for a time zone, updating system tables does not necessarily make all active sessions pick up the new rules immediately. Restarting the server after loading new data is the clearest way to ensure the process reloads timezone definitions. Schedule restarts in a maintenance window compatible with your HA/replication topology.

## 8. What Is Daylight Saving Time (DST)?

Some regions adjust clocks seasonally. At the start of DST, clocks typically jump forward (for example, from 01:59:59 to 03:00:00), creating a nonexistent gap in local time. When DST ends, clocks fall back, causing a local time interval to occur twice.

Two scenarios to understand:

- **DST gap:** nonexistent local time. For instance, an appointment scheduled at 02:30 on the day clocks jump from 02:00 to 03:00 does not naturally map to any real instant.
- **DST overlap/fold:** repeated local time. For instance, 01:30 can occur once before clocks fall back and once after clocks fall back; those two occurrences are two distinct UTC instants.

Accordingly, converting from UTC to local time is deterministic when timezone data is complete: every instant has a single display representation under the rules at that moment. Converting from local wall time to UTC can be ambiguous or invalid during a DST gap or overlap.

## 9. Observing DST with `CONVERT_TZ()`

### Start of DST: Clocks Spring Forward

In `America/New_York`, on 2024-03-10 clocks transitioned from standard time to summer time. These two consecutive UTC instants display as local times right before and after the jump:

```sql
SELECT
    utc_time,
    CONVERT_TZ(utc_time, '+00:00', 'America/New_York') AS new_york_time,
    TIMESTAMPDIFF(
        MINUTE,
        utc_time,
        CONVERT_TZ(utc_time, '+00:00', 'America/New_York')
    ) AS utc_offset_minutes
FROM (
    SELECT CAST('2024-03-10 06:59:59' AS DATETIME) AS utc_time
    UNION ALL
    SELECT CAST('2024-03-10 07:00:00' AS DATETIME) AS utc_time
) AS samples
ORDER BY utc_time;
```

When timezone tables contain the proper data, local time jumps from `01:59:59` to `03:00:00`; the interval from `02:00` to just before `03:00` does not exist in that region on the DST transition day.

### End of DST: Clocks Fall Back

On 2024-11-03, New York ended DST. Two distinct UTC instants both display locally as 01:30:

```sql
SELECT
    utc_time,
    CONVERT_TZ(utc_time, '+00:00', 'America/New_York') AS new_york_time,
    TIMESTAMPDIFF(
        MINUTE,
        utc_time,
        CONVERT_TZ(utc_time, '+00:00', 'America/New_York')
    ) AS utc_offset_minutes
FROM (
    SELECT CAST('2024-11-03 05:30:00' AS DATETIME) AS utc_time
    UNION ALL
    SELECT CAST('2024-11-03 06:30:00' AS DATETIME) AS utc_time
) AS samples
ORDER BY utc_time;
```

Both rows show local time `01:30:00`, yet their offsets are `-240` and `-300` minutes, respectively. If you store only `2024-11-03 01:30:00` without storing the timezone/offset or resolved UTC instant, you cannot tell whether it refers to the first or second 01:30.

### Never Assume Local Time Always Maps One-to-One to UTC

A local time inside a DST gap does not represent a valid instant under the region's rules. A local time inside a DST overlap corresponds to two valid instants. When accepting user-entered appointments, the application needs an explicit policy: reject nonexistent times, advance to the next valid time, or ask the user to select the offset/occurrence for repeated times.

Do not rely on a bare `CONVERT_TZ(local_time, zone, 'UTC')` call to resolve every gap/overlap automatically without an explicit policy. Test actual behavior on your MySQL version and handle ambiguity in the business layer.

## 10. Distinguishing `TIMESTAMP`, `DATETIME`, and Session Time Zone

`CONVERT_TZ()` is a function that converts a date/time value; it does not alter a column's data type or storage convention. When designing schemas, note that `TIMESTAMP` and `DATETIME` behave differently:

| Type | Time Zone Behavior |
|---|---|
| `TIMESTAMP` | MySQL converts values from the session time zone to UTC on write, and from UTC to the session time zone on read. |
| `DATETIME` | Stores date/time values exactly as supplied; does not auto-convert by session time zone. |

A common pattern is storing event instants in UTC—using `TIMESTAMP` when the year range fits, or `DATETIME` with a strictly enforced UTC convention. When storing recurring local schedules (e.g. 09:00 daily in Paris time), store both local date/time and the named time zone because the corresponding UTC instant shifts across DST transitions.

Check session configuration:

```sql
SELECT
    @@global.time_zone AS global_time_zone,
    @@session.time_zone AS session_time_zone,
    @@system_time_zone AS system_time_zone;
```

`SYSTEM` means MySQL relies on the OS time zone for that setting. You can set the session separately:

```sql
SET SESSION time_zone = '+00:00';
```

Setting the session to UTC gives applications a clear convention when reading/writing `TIMESTAMP`. It does not replace timezone tables when named-zone conversions are needed. With connection pools, configure the session time zone whenever a connection is initialized or ensure the pool resets session state properly.

## 11. Design Patterns for Events and Local Schedules

### Past Events: Store UTC Instants

Example of an order created at an absolute instant:

```sql
CREATE TABLE order_events (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id BIGINT UNSIGNED NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    occurred_at_utc DATETIME NOT NULL,
    source_time_zone VARCHAR(64) NULL,
    PRIMARY KEY (id),
    KEY idx_order_events_time (occurred_at_utc)
) ENGINE=InnoDB;
```

Here, the application commits to always sending `occurred_at_utc` in UTC. `TIMESTAMP` can replace `DATETIME` if the year range and session conversion behavior fit. The `source_time_zone` column is useful metadata if you need to reconstruct how the timestamp was presented to the user, though it does not replace the UTC instant.

### Future Local Schedules: Store the Zone ID

Example of a meeting booked for 09:00 Paris time on a future date:

```sql
CREATE TABLE local_appointments (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    local_start DATETIME NOT NULL,
    time_zone_id VARCHAR(64) NOT NULL,
    resolved_start_utc DATETIME NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB;
```

`local_start` stores the local calendar clock time; `time_zone_id` stores an IANA name such as `Europe/Paris`. The application uses its timezone database to resolve the UTC instant. `resolved_start_utc` can store the instant calculated at booking time if the business needs to lock in a specific instant. If DST laws change before the scheduled date, decide whether the appointment keeps the local clock time or the locked UTC instant; this is a business rule and must not be left implicit.

## 12. Handling Queries by Local Date

A report for “orders on March 10 in New York” must determine the UTC interval corresponding to that local day. A DST day can be 23 or 25 hours long, so never simply add 24 hours to the UTC day start.

Correct workflow:

1. Construct the local day start `00:00:00` in the named time zone.
2. Construct the next local day start `00:00:00` in the same zone.
3. Convert both bounds to UTC using timezone rules.
4. Query data using the half-open interval `[start_utc, next_start_utc)`.

Illustrative example using Vietnam time, which currently does not observe DST:

```sql
SET @start_local = '2026-01-15 00:00:00';
SET @next_local  = '2026-01-16 00:00:00';

SET @start_utc = CONVERT_TZ(
    @start_local,
    'Asia/Ho_Chi_Minh',
    '+00:00'
);

SET @next_utc = CONVERT_TZ(
    @next_local,
    'Asia/Ho_Chi_Minh',
    '+00:00'
);

SELECT id, order_id, occurred_at_utc
FROM order_events
WHERE occurred_at_utc >= @start_utc
  AND occurred_at_utc < @next_utc
ORDER BY occurred_at_utc;
```

For DST regions, the UTC span between the two bounds can be 23, 24, or 25 hours. Computing the two local boundaries separately still captures the exact calendar day. Using a half-open condition also avoids fractional-second precision issues at the end of the day and remains index-friendly on temporal columns.

## 13. Diagnosing Timezone and DST Bugs

| Symptom | Possible Cause | Diagnostic Approach |
|---|---|---|
| `CONVERT_TZ()` returns `NULL` for named zone | Timezone tables unloaded, missing zone, or typo | Check `mysql.time_zone_name`, IANA spelling, and compare with a fixed-offset query. |
| Wrong summer offset | Outdated timezone tables | Check tzdb version, reload data, and restart MySQL per procedure. |
| Works in dev, fails in production | Environments differ in timezone tables or session settings | Compare MySQL version, tzdb, `@@session.time_zone`, and system table rows. |
| Displayed time shifts per user | `TIMESTAMP` read under different session time zones | Check `@@session.time_zone` and driver/pool conventions. |
| Appointment time occurs twice | DST overlap | Store zone ID and define an occurrence/offset selection policy. |
| Appointment time does not exist | DST gap | Reject or adjust per defined business policy. |
| Daily report misses or includes extra rows | Used fixed 24-hour span instead of local day boundaries | Convert start-of-day and start-of-next-day separately to UTC. |

Diagnostic checklist:

```sql
SELECT VERSION();

SELECT
    @@global.time_zone,
    @@session.time_zone,
    @@system_time_zone;

SELECT COUNT(*) FROM mysql.time_zone_name;

SELECT Name
FROM mysql.time_zone_name
WHERE Name IN ('Asia/Ho_Chi_Minh', 'America/New_York');

SELECT
    CONVERT_TZ('2024-07-01 12:00:00', 'UTC', 'America/New_York') AS summer_time,
    CONVERT_TZ('2024-01-01 12:00:00', 'UTC', 'America/New_York') AS winter_time;
```

If `UTC` or named zones are not recognized in timezone tables, load the appropriate timezone data. For long-running systems, include named-zone checks in health checks or integration tests to catch missing data before users encounter errors.

## 14. Practice Exercises

### Exercise A — Inspecting Timezone Tables

1. Run `SELECT VERSION()` and inspect `@@global.time_zone`, `@@session.time_zone`, and `@@system_time_zone`.
2. Count rows in `mysql.time_zone_name`.
3. Check for `Asia/Ho_Chi_Minh`, `America/New_York`, and `Europe/Paris`.
4. Run `CONVERT_TZ()` from UTC to each region.
5. Document how to recognize failures caused by unloaded named zones.

### Exercise B — Observing DST Gaps and Overlaps

1. Query UTC instants immediately before and after New York begins DST.
2. Observe the jump from `01:59:59` to `03:00:00`.
3. Query two UTC instants inside the repeated hour when DST ends.
4. Compare the local time and `utc_offset_minutes`.
5. Explain why storing only local `01:30:00` is insufficient to identify an instant.

### Exercise C — Designing Appointments

1. Create a table storing `local_start` and `time_zone_id`.
2. Pick an appointment in a DST region on a transition day.
3. Define policies for nonexistent times and repeated times.
4. Convert to UTC after resolving the policy.
5. Describe how to handle a DST law change occurring before the scheduled date.

### Exercise D — Local-Day Reporting

1. Choose a normal day and a DST transition day in New York.
2. Compute the UTC instants for the start of the day and start of the next day.
3. Calculate the hours between the two bounds.
4. Query the events table over `[start_utc, next_start_utc)`.
5. Explain why you should not blindly add 24 hours to determine the next day.

You have completed this lesson when you can load and verify timezone tables, use `CONVERT_TZ()` with named zones, distinguish fixed offsets from regional rules, explain DST gaps/overlaps, design storage for instants and local schedules, and compute accurate UTC intervals for daily reports.

## 15. Key Principles to Remember

- Use IANA names like `Asia/Ho_Chi_Minh` and `America/New_York` when regional rules matter; offsets like `+07:00` are fixed shifts only.
- `CONVERT_TZ()` requires loaded timezone tables for named-zone conversions; unrecognized names typically cause the function to return `NULL`.
- Load timezone tables from trusted tzdb data and update them whenever DST laws change.
- After updating timezone tables, restart MySQL per operational procedures to refresh cached timezone data.
- A DST gap creates nonexistent local times; a DST overlap creates local times occurring twice.
- Converting UTC to local time is deterministic under timezone rules; converting local time to UTC may require a gap/overlap resolution policy.
- Set a consistent session time zone, typically UTC for applications; pool configurations must preserve proper session state.
- Store event instants in UTC; for future local schedules, store both local time and the named time zone.
- Build report intervals from two separate local day boundaries converted individually to UTC; never assume every day is 24 hours long.

When you understand how `CONVERT_TZ()`, timezone tables, and DST interact, you can handle time consistently between MySQL and your application, update timezone rules safely, and prevent scheduling or reporting bugs when local clocks shift.
