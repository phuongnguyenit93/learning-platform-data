# LocalDate, LocalTime, LocalDateTime, and Time Zone Conventions

## 1. Why Choosing the Right Time Type Matters

A system using Spring Data JDBC often stores very different kinds of data that all look like “date and time”:

- A customer's date of birth: a **calendar date**, independent of time zones.
- The daily opening time of a store: a **local wall-clock time**, not yet identifying a single instant.
- An appointment at 09:30 on November 13 in Ho Chi Minh City: a **local date and time**, requiring a time zone to derive a global instant.
- The moment a payment actually occurred: a **specific instant on the timeline**, usable when the system runs across multiple regions.

If everything is stored using `LocalDateTime`, the application can easily confuse calendar dates with real instants, break when server time zones change, or mishandle daylight saving time (DST). The problem is not whether JDBC can write the value, but **what the data means when written, read, compared, and transferred between systems**.

In this lesson, we will:

1. Distinguish `LocalDate`, `LocalTime`, and `LocalDateTime` semantically.
2. Map them to `DATE`, `TIME`, and `TIMESTAMP` when using Spring Data JDBC.
3. Determine clearly when `ZoneId`, `ZoneOffset`, or `Instant` must be added.
4. Write an example entity/repository that saves and reads back all three time types.
5. Establish conventions to keep data consistent across the database, backend, APIs, and users in multiple time zones.

## 2. What Do the Three `java.time` Types Represent?

Java 8 and later provide the `java.time` API. The three types in the title all **contain no time zone or UTC offset information**.

| Java Type | Information Included in Value | Information Absent | Typical SQL Type | Business Example |
| --- | --- | --- | --- | --- |
| `LocalDate` | Year, month, day | Time, time zone, offset | `DATE` | Date of birth, accounting date, policy effective date |
| `LocalTime` | Hour, minute, second, fractional second | Date, time zone, offset | `TIME WITHOUT TIME ZONE` or `TIME` | Daily opening time, recurring alarm time |
| `LocalDateTime` | Local date and time | Time zone, offset, absolute instant | `TIMESTAMP WITHOUT TIME ZONE` or `TIMESTAMP` | Appointment entered against a location's wall clock |
| `Instant` | Point on the UTC timeline | User's display time zone | Dialect-appropriate instant column, e.g., PostgreSQL `TIMESTAMPTZ` | Payment timestamp, event recording time |
| `OffsetDateTime` | Date-time and a fixed UTC offset | Historical/future rules of a geographic time zone | Must match SQL type and driver | API input containing `+07:00` or `Z` |
| `ZonedDateTime` | Date-time, offset, and a `ZoneId` such as `Europe/Paris` | No guarantee the database stores the zone ID intact | Usually requires storing instant and zone ID per policy | Appointment tied to a DST-observing region |

The first three types represent **local** calendar and wall-clock values. You cannot derive a unique UTC instant from `2026-11-13T09:30:00` without knowing where the user meant 09:30.

### `LocalDate`: Calendar Date

```java
import java.time.LocalDate;

LocalDate birthday = LocalDate.of(1998, 5, 12);
LocalDate businessDay = LocalDate.parse("2026-11-13");

System.out.println(birthday);  // 1998-05-12
System.out.println(businessDay); // 2026-11-13
```

A birth date of 1998-05-12 should not shift to 05-11 or 05-13 when a user travels from Vietnam to another country. `LocalDate` preserves the exact “date” meaning without inventing an assumed midnight instant.

### `LocalTime`: Wall-Clock Time

```java
import java.time.LocalTime;

LocalTime openingTime = LocalTime.of(8, 30);
LocalTime closingTime = LocalTime.parse("18:00:00");

System.out.println(openingTime); // 08:30
```

`08:30` does not mean the store opens at 08:30 UTC. If this is the opening time for a store in Ho Chi Minh City, we still need **the store's location/time zone** and a **specific date** when calculating the corresponding opening instant.

### `LocalDateTime`: Date Plus Time, Still Without a Time Zone

```java
import java.time.LocalDateTime;

LocalDateTime appointment =
        LocalDateTime.of(2026, 11, 13, 9, 30);

System.out.println(appointment); // 2026-11-13T09:30
```

This value means “09:30 on the local clock on November 13, 2026”. It is **not UTC**, nor does it carry an implicit offset. Without storing or receiving the accompanying time zone, applications running in other countries may interpret it differently.

## 3. Mapping the Three Local Types to SQL Columns in Spring Data JDBC

Spring Data JDBC uses Spring Data Relational's mapping mechanism and JDBC infrastructure. With a standard database/driver supporting JDBC 4.2, local `java.time` types are typically mapped as follows:

```text
Java domain model                 SQL column
----------------------------------------------
LocalDate                         DATE
LocalTime                         TIME
LocalDateTime                     TIMESTAMP
```

The actual database type name may be `TIME WITHOUT TIME ZONE` or `TIMESTAMP WITHOUT TIME ZONE`. How many fractional second digits are stored depends on the column definition and database/driver capabilities. For instance, if the application writes nanoseconds while the column only stores microseconds, reading the value back may round or truncate fractional seconds.

**Important note:** `TIMESTAMP` does not have the exact same meaning across every database. For example, PostgreSQL distinguishes `TIMESTAMP WITHOUT TIME ZONE` from `TIMESTAMP WITH TIME ZONE` (`TIMESTAMPTZ`), while MySQL has significant differences between `DATETIME` and `TIMESTAMP` regarding session time zone handling. Therefore, consult the documentation for your **database + JDBC driver + dialect** before adopting a system-wide convention.

### Example Table Design

Suppose a system schedules venue tours. Each schedule has:

- `visitDate`: scheduled visit calendar date at the venue.
- `doorOpensAt`: local door-opening time on that day.
- `registrationDeadlineLocal`: registration deadline on the venue's local clock.
- `timeZoneId`: venue's time zone, such as `Asia/Ho_Chi_Minh`.

Minimal schema on H2:

```sql
CREATE TABLE "visit_schedules" (
    "id" BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    "visit_date" DATE NOT NULL,
    "door_opens_at" TIME NOT NULL,
    "registration_deadline_local" TIMESTAMP NOT NULL,
    "time_zone_id" VARCHAR(64) NOT NULL
);
```

Table and column names are quoted consistently so the example clearly aligns with explicit mapping names. When working with PostgreSQL or another database, apply naming/quoting conventions suited to your project's dialect; do not rely on the driver normalizing identifier casing the same way H2 does.

**Key distinction:** the database is preserving the raw date and time components inside the three local columns. The `time_zone_id` column is business metadata indicating which time zone applies to those components; `TIMESTAMP` itself here does not contain a timezone ID.

## 4. Spring Data JDBC Example: Saving and Reading Date-Time Data

This example uses Java 21 and Spring Boot with Spring Data JDBC support. With Gradle Groovy DSL:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jdbc'
    runtimeOnly 'com.h2database:h2'
}
```

Place `schema.sql` at `src/main/resources/schema.sql` and configure:

```properties
spring.datasource.url=jdbc:h2:mem:date_time_demo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always

# Observe SQL statements executed by Spring JDBC infrastructure
logging.level.org.springframework.jdbc=DEBUG
```

### 4.1. Defining the Aggregate Root

Create `src/main/java/com/example/datetime/VisitSchedule.java`:

```java
package com.example.datetime;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("visit_schedules")
public record VisitSchedule(
        @Id Long id,
        @Column("visit_date") LocalDate visitDate,
        @Column("door_opens_at") LocalTime doorOpensAt,
        @Column("registration_deadline_local")
        LocalDateTime registrationDeadlineLocal,
        @Column("time_zone_id") String timeZoneId
) {
}
```

`@Table` and `@Column` explicitly specify table/column names. `@Id` is from `org.springframework.data.annotation`, not `jakarta.persistence.Id`. A record fits this example because values are represented immutably; Spring Data JDBC can instantiate it when reading data and return an instance holding the ID after insert.

In a real system, validate `timeZoneId` using `ZoneId.of(...)`, check the registration deadline against the visit date, and enforce business rules in an appropriate model or service.

### 4.2. Repository

Create `src/main/java/com/example/datetime/VisitScheduleRepository.java`:

```java
package com.example.datetime;

import java.time.LocalDate;
import java.util.List;
import org.springframework.data.repository.CrudRepository;

public interface VisitScheduleRepository
        extends CrudRepository<VisitSchedule, Long> {

    List<VisitSchedule> findByVisitDate(LocalDate visitDate);
}
```

`findByVisitDate(...)` is a derived query accepting a `LocalDate` parameter. There is no need to manually format the date into a string like `"2026-11-13"` to pass to the repository.

### 4.3. Running the Example with `CommandLineRunner`

Create `src/main/java/com/example/datetime/DateTimeApplication.java`:

```java
package com.example.datetime;

import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.ZoneId;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DateTimeApplication {

    public static void main(String[] args) {
        SpringApplication.run(DateTimeApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(VisitScheduleRepository repository) {
        return args -> {
            VisitSchedule newSchedule = new VisitSchedule(
                    null,
                    LocalDate.of(2026, 11, 13),
                    LocalTime.of(8, 30),
                    LocalDateTime.of(2026, 11, 12, 20, 0),
                    "Asia/Ho_Chi_Minh"
            );

            VisitSchedule saved = repository.save(newSchedule);
            VisitSchedule loaded = repository.findById(saved.id())
                    .orElseThrow();

            System.out.println("Visit date: "
                    + loaded.visitDate());
            System.out.println("Door opens at: "
                    + loaded.doorOpensAt());
            System.out.println("Local registration deadline: "
                    + loaded.registrationDeadlineLocal());

            ZoneId venueZone = ZoneId.of(loaded.timeZoneId());
            Instant deadlineInstant = loaded.registrationDeadlineLocal()
                    .atZone(venueZone)
                    .toInstant();
            System.out.println("UTC registration deadline: " + deadlineInstant);

            repository.findByVisitDate(LocalDate.of(2026, 11, 13))
                    .forEach(System.out::println);
        };
    }
}
```

Run in the project directory:

```bash
./gradlew bootRun
```

On Windows:

```powershell
.\gradlew.bat bootRun
```

Expected output values (illustrative representation):

```text
Visit date: 2026-11-13
Door opens at: 08:30
Local registration deadline: 2026-11-12T20:00
UTC registration deadline: 2026-11-12T13:00:00Z
```

For `Asia/Ho_Chi_Minh`, the example date-time has a `+07:00` offset, so `20:00` local equals `13:00Z` on the same day. `save` generates an `INSERT`, while `findById` and `findByVisitDate` generate appropriate `SELECT` queries. The text above is illustrative output, not an actual log captured from a run in this lesson.

**Important point:** the `LocalDateTime` retrieved from the database is still `2026-11-12T20:00`. Conversion to `Instant` occurs **only when the application supplies a `ZoneId` and requests the conversion**. Reading a `TIMESTAMP WITHOUT TIME ZONE` column does not automatically attach `Asia/Ho_Chi_Minh`.

## 5. How Do `ZoneId`, `ZoneOffset`, and `Instant` Differ?

The following three concepts are frequently confused:

| Concept | Example | Meaning |
| --- | --- | --- |
| `ZoneId` | `Asia/Ho_Chi_Minh`, `America/New_York` | Time zone region name with historical and future offset-change rules. |
| `ZoneOffset` | `+07:00`, `-05:00`, `Z` | Fixed offset from UTC at a given moment; does not carry a region's full DST rules. |
| `Instant` | `2026-11-13T02:30:00Z` | A specific point on the timeline; carries no viewer time-zone presentation. |

Example:

```java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

LocalDateTime local = LocalDateTime.of(2026, 11, 13, 9, 30);
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

ZonedDateTime zoned = local.atZone(zone);
Instant instant = zoned.toInstant();

System.out.println(zoned);   // 2026-11-13T09:30+07:00[Asia/Ho_Chi_Minh]
System.out.println(instant); // 2026-11-13T02:30:00Z
```

The same instant can be displayed as different local times:

```java
Instant eventTime = Instant.parse("2026-11-13T02:30:00Z");

System.out.println(
        eventTime.atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
); // 2026-11-13T09:30+07:00[Asia/Ho_Chi_Minh]

System.out.println(
        eventTime.atZone(ZoneId.of("UTC"))
); // 2026-11-13T02:30Z[UTC]
```

**A `ZoneOffset` like `+07:00` is not completely equivalent to a `ZoneId`.** In regions with DST, the offset depends on the specific date. If an event recurs at 09:00 local time, storing only the first occurrence's offset can make subsequent occurrences fall at the wrong hour.

## 6. Rules for Choosing Types by Business Domain

Choose the time type based on **what must remain invariant when the user changes time zones**, and only then decide on SQL column names.

### 6.1. Birth Dates, Holidays, Accounting Dates → `LocalDate`

```java
LocalDate dateOfBirth = LocalDate.of(1998, 5, 12);
```

Do not automatically convert a `LocalDate` to an `Instant` “at 00:00 UTC” when the calendar date is the source truth. A user in UTC-08 could see the previous day after shifting midnight UTC to local time. A calendar date should stay the same regardless of where the server reading it is hosted.

### 6.2. Daily Opening Time → `LocalTime` Plus Location Time Zone

```java
LocalTime opensAt = LocalTime.of(8, 30);
ZoneId storeZone = ZoneId.of("Asia/Ho_Chi_Minh");
```

If a store opens at 08:30 on the local clock every day, store the opening time as `LocalTime` and know the store's time zone. Only when scheduling for a **specific day** should you combine it with a `LocalDate` and convert to an `Instant`:

```java
LocalDate date = LocalDate.of(2026, 11, 13);
Instant openingInstant = date.atTime(opensAt)
        .atZone(storeZone)
        .toInstant();
```

For opening hours spanning midnight, such as 22:00–02:00, simply checking `opensAt.isBefore(closesAt)` is wrong. You must explicitly define the closing time as belonging to the **next day** and apply the location's schedule.

### 6.3. Local Appointments → `LocalDateTime` + `ZoneId`

If a customer books an appointment at a branch for 09:30 on November 13, 2026, we need to store/know both the branch's local date-time and the branch's time zone.

```text
appointment_local = 2026-11-13 09:30:00
zone_id           = Asia/Ho_Chi_Minh
```

This pair lets you compute the corresponding instant while preserving the **local schedule intent**. If a schedule is permanently pinned to a specific instant, the system may also store that instant (in an appropriate column) for accurate querying and triggering, while retaining the zone ID to display the organizer's original intent.

### 6.4. When an Event Occurred → `Instant`

`createdAt`, `paidAt`, `processedAt`, and system events usually answer the question **“at what exact moment did this happen?”**. `Instant` represents this answer better than `LocalDateTime`:

```java
import java.time.Clock;
import java.time.Instant;

Clock clock = Clock.systemUTC();
Instant paidAt = Instant.now(clock);
```

When storing an instant, choose a SQL type and converter/driver with matching semantics. With PostgreSQL, `TIMESTAMP WITH TIME ZONE` (`TIMESTAMPTZ`) is a common choice for storing instants; PostgreSQL **does not preserve the original zone ID name** inside this value. With other DBMSs, check the time zone rules of the type, driver, and session.

Do not replace `Instant` with `LocalDateTime.now()` and implicitly assume every machine in the system always runs in UTC. Even if your convention is “store UTC inside timezone-less TIMESTAMP”, that remains an **application convention that must be explicitly maintained and verified**, not a guarantee enforced by the column type.

## 7. Converting Date-Times: Where Is a Time Zone Needed?

For a local date-time, the following operation requires a time zone:

```java
LocalDateTime localDateTime =
        LocalDateTime.of(2026, 11, 13, 9, 30);
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant instant = localDateTime.atZone(zone).toInstant();
```

In the reverse direction, from an absolute instant to a user's presentation:

```java
Instant instant = Instant.parse("2026-11-13T02:30:00Z");
ZoneId userZone = ZoneId.of("Asia/Ho_Chi_Minh");

LocalDateTime localForUser =
        LocalDateTime.ofInstant(instant, userZone);
```

The two operations have different characteristics:

- **Local → Instant** requires specifying a zone and handling DST nonexistent-hour/repeated-hour cases.
- **Instant → Local** with a valid zone yields a deterministic local value at that instant. However, converting local back to an instant after **losing the offset** can be ambiguous on DST transition days.

### Why Shouldn't You Use `ZoneId.systemDefault()` Carelessly?

```java
LocalDateTime.now();       // Uses JVM's default time zone
LocalDate.now();           // Current date in JVM's default time zone
ZoneId.systemDefault();    // May vary across machines/containers
```

If one machine runs in Vietnam and a container runs in UTC, `LocalDateTime.now()` at the exact same instant produces different local values. That can cause bugs in “today” statistics, cutoffs, or expirations.

A better convention is to explicitly specify the clock source and zone:

```java
import java.time.Clock;
import java.time.LocalDate;
import java.time.ZoneId;

Clock clock = Clock.systemUTC();
ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");

LocalDate todayForBusiness =
        LocalDate.now(clock.withZone(businessZone));
```

Injecting `Clock` via constructor into services also makes it easy to test deadlines, holidays, and year-end transitions with a fixed clock.

## 8. DST: A Local Date-Time Can Be Nonexistent or Occur Twice

Regions such as `America/New_York` adjust clocks seasonally. This creates two situations that Vietnam generally does not encounter in modern calendars.

### 8.1. Skipped Hour (Gap)

When clocks spring forward from 01:59 to 03:00, the 02:00–02:59 window on the transition day **does not exist** in local time. If a user enters 02:30 in that window, the system must have a policy: reject it, ask the user to pick again, or adjust it according to a documented rule.

### 8.2. Repeated Hour (Overlap)

When clocks fall back from 02:00 to 01:00, the value 01:30 occurs **twice** with two different UTC offsets. `LocalDateTime.of(..., 1, 30)` plus `ZoneId` is still insufficient to pick a single instant without an overlap-resolution rule.

The `atZone(...)` API uses default behavior to resolve gaps/overlaps; calling it can therefore **silently shift** a nonexistent time or pick one of the two offsets. For appointments requiring precision, detect these cases upfront:

```java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.List;

public final class LocalTimeResolver {
    private LocalTimeResolver() {}

    public static Instant requireUnambiguousInstant(
            LocalDateTime local,
            ZoneId zone
    ) {
        List<ZoneOffset> offsets =
                zone.getRules().getValidOffsets(local);

        if (offsets.isEmpty()) {
            throw new IllegalArgumentException(
                    "Local date-time does not exist in this zone");
        }
        if (offsets.size() > 1) {
            throw new IllegalArgumentException(
                    "Local date-time occurs twice; choose an offset");
        }
        return local.toInstant(offsets.get(0));
    }
}
```

The code above intentionally rejects both gaps and overlaps, fitting applications that ask the user to confirm. Another system might pick “the earlier offset”, “the later offset”, or advance to the first valid time, but it must document the **business rule** and ensure code applies that same policy across every flow.

If a schedule is “09:00 every day in New York time”, store `LocalTime` and `ZoneId`/recurrence rules, then compute the instant **day by day**. Do not add a fixed 24 hours to the previous day's instant across periods that may cross DST.

## 9. Column and API Design Conventions

A project should document unified conventions rather than letting each team interpret `timestamp` in its own way.

### Recommended Conventions

| Data Kind | Domain Representation | Database Column | JSON/API | Rule |
| --- | --- | --- | --- | --- |
| Calendar date | `LocalDate` | `DATE` | `"2026-11-13"` | Do not coerce to 00:00 UTC. |
| Local time | `LocalTime` | `TIME` without timezone | `"08:30:00"` | Field name must clarify the schedule/location context. |
| Local date-time | `LocalDateTime` | `TIMESTAMP WITHOUT TIME ZONE` | `"2026-11-13T09:30:00"` | Accompanied by `zoneId` when an instant must be derived. |
| Absolute instant | `Instant` | Dialect-appropriate instant column | `"2026-11-13T02:30:00Z"` | Verify driver and mapping mechanism; format in viewer's zone. |
| Location time zone | `ZoneId` in domain; ID can be stored as `String` | `VARCHAR(64)` | `"Asia/Ho_Chi_Minh"` | Validate with `ZoneId.of(...)`; use IANA zone names. |

Clear JSON example for an appointment:

```json
{
  "appointmentLocal": "2026-11-13T09:30:00",
  "zoneId": "Asia/Ho_Chi_Minh"
}
```

If the API wants to send a fixed instant, it can use:

```json
{
  "appointmentInstant": "2026-11-13T02:30:00Z",
  "displayZoneId": "Asia/Ho_Chi_Minh"
}
```

Both contracts can be valid yet **are not equivalent in purpose**:

- The local + zone contract preserves “the appointment is at 09:30 in Ho Chi Minh City”.
- The instant + display zone contract emphasizes “the event takes place at this exact instant”.

If an API returns only `"2026-11-13T09:30:00"` and the client interprets it as UTC or applies the browser's zone, users elsewhere may see the wrong time.

With Spring Boot's Jackson, `java.time` types can serialize in ISO-8601 format when the corresponding module is configured via the JSON starter. Even when the serializer works, **a string without an offset still carries no time zone information**. Avoid using JSON configuration as a band-aid for semantic flaws in data persisted via JDBC.

## 10. Querying Conventions by Date and Time Ranges

### 10.1. Finding Data by `LocalDate`

If the table stores a business date as `DATE`, the query is straightforward:

```sql
SELECT *
FROM "visit_schedules"
WHERE "visit_date" = ?;
```

The repository can accept `LocalDate` directly:

```java
List<VisitSchedule> schedules =
        repository.findByVisitDate(LocalDate.of(2026, 11, 13));
```

Do not convert a date into a range from `2026-11-13T00:00:00Z` to 24 hours later when the underlying data is truly a calendar date.

### 10.2. Filtering Events by Day in a Specific Time Zone

Suppose an events table stores **instants**, and a user asks for “all payments on November 13 in Ho Chi Minh City time”. Convert **the two local day boundaries** into instants:

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

LocalDate targetDay = LocalDate.of(2026, 11, 13);
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant startInclusive =
        targetDay.atStartOfDay(zone).toInstant();

Instant endExclusive =
        targetDay.plusDays(1).atStartOfDay(zone).toInstant();
```

Semantically in SQL:

```sql
SELECT *
FROM payments
WHERE paid_at >= :start_inclusive
  AND paid_at <  :end_exclusive;
```

Here `paid_at` is assumed to be an instant column per the designed convention, such as `TIMESTAMPTZ` in PostgreSQL. Named parameter syntax `:start_inclusive` and `:end_exclusive` belongs to `NamedParameterJdbcTemplate` or APIs supporting named parameters; it is not direct syntax for every SQL client.

**Why a half-open interval `[start, end)`?** An event occurring at the exact start of the next day belongs to the next day; there is no need to guess an “end of day” timestamp with database-dependent sub-second precision.

**Why take the start of the next day instead of adding 24 hours?** In DST regions, a calendar day can be 23 or 25 hours long. `targetDay.plusDays(1).atStartOfDay(zone)` represents the exact local calendar day boundary; adding a fixed 24-hour duration to the day's start instant can yield the wrong boundary.

### 10.3. Comparing Time Values Requires Matching Semantics

`LocalDateTime.isBefore(...)` and `isAfter(...)` only compare year-month-day-time fields. If two values come from **two different time zones**, comparing them directly does not prove which event happened earlier on the timeline.

Example:

```java
LocalDateTime hcm = LocalDateTime.parse("2026-11-13T09:30:00");
LocalDateTime tokyo = LocalDateTime.parse("2026-11-13T10:00:00");
```

On the wall clock, `09:30` is earlier than `10:00`. However, `09:30` in Ho Chi Minh City is `02:30Z`, while `10:00` in Tokyo is `01:00Z`, meaning the Tokyo event **occurred earlier**. To compare actual chronological order, first convert each value to an `Instant` using its respective zone.

## 11. Common Pitfalls When Working with Spring Data JDBC

### Pitfall 1: Storing Real Event Instants with `LocalDateTime.now()` Without a Zone Contract

A server running in UTC writes `2026-11-13T02:30`, while another server running in UTC+07 writes `2026-11-13T09:30` for the same instant. If both write to a timezone-less `TIMESTAMP` column, the data will have inconsistent meaning.

**Best practice:** for event instants, use `Instant` and choose a column/driver with matching semantics; when you must store a local timestamp, explicitly specify the zone and convention.

### Pitfall 2: Assuming `LocalDateTime` Is Always UTC

`LocalDateTime` contains no UTC offset. This value cannot be turned into an `Instant` through a mere cast. If a system standardizes local timestamps to UTC, that is a convention outside the Java type and must be enforced at every read/write point.

**Best practice:** name variables and columns clearly (`createdAtInstant`, `appointmentLocal`) and avoid hiding `ZoneId` inside a helper that uses the default time zone.

### Pitfall 3: Storing a Fixed Offset Instead of a Region Name

`+01:00` may be correct for one day yet wrong on other days in the same city. A recurring schedule spanning summer and winter needs calendar time-zone rules.

**Best practice:** store region IDs like `Europe/Paris`, `America/New_York`, etc., when preserving local-time intent; consider also storing the resolved instant for each concrete occurrence.

### Pitfall 4: Using `DATE`/`TIME` or `TIMESTAMP` and Assuming the Database Remembers `ZoneId`

Timezone-less types do not retain time zone names. Even PostgreSQL `TIMESTAMPTZ` does not retain the original zone ID sent; it represents an instant and formats output according to session settings.

**Best practice:** if you need to display “the exact geographic region the user selected”, store `zone_id` in a separate column.

### Pitfall 5: Fractional Seconds Altered After Reading Back

Java `LocalTime` and `LocalDateTime` can hold nanoseconds. A database or `TIME(0)`/`TIMESTAMP(3)` column has lower precision.

**Best practice:** choose column precision according to business needs and align expectations when serializing/comparing; do not assume every nanosecond survives a round-trip.

### Pitfall 6: Assuming System Configuration Fixes Everything Automatically

JVM time zone, database session, or serializer settings can affect certain code paths and JDBC types, yet they do not turn a `LocalDateTime` into a zoned type. JPA/Hibernate-specific settings also cannot be assumed to apply to Spring Data JDBC.

**Best practice:** specify semantics per data field, verify how your specific database driver binds/reads values, and test from the API down to the database.

### Pitfall 7: Converting Dates to Epoch via `atStartOfDay(ZoneOffset.UTC)` for Every Case

Birth dates, accounting dates, or store opening dates are not UTC instants by default.

**Best practice:** keep `LocalDate` when the data strictly means a calendar date. Only convert to an instant range when a use case requires it and the context's time zone is known.

## 12. When Is a Custom Converter Needed?

For `LocalDate`, `LocalTime`, and `LocalDateTime`, start with standard Spring Data JDBC mapping and an appropriate driver. Do not create a converter just to turn Java types into strings.

Converters may be needed when:

- The driver or dialect does not directly support the desired `java.time` type.
- A legacy schema stores dates/times in `VARCHAR`, epoch milliseconds, numeric columns, or a database-specific type.
- The application has a dedicated value object that needs custom mapping, such as `BusinessZoneId`.
- Storing `Instant`/`OffsetDateTime` requires controlled conversion into a type accepted by the JDBC driver.

Spring Data Relational supports registering custom conversions, but you must clearly define the **read direction**, **write direction**, **intermediate JDBC type**, **dialect**, and **time-zone semantics**. Do not write a converter that “takes `LocalDateTime` and attaches the server's default time zone”, as results will become environment-dependent.

For example, if a legacy system stores epoch milliseconds in a `BIGINT` column, the explicit rule is:

```java
import java.time.Instant;

long storedEpochMillis = 1_800_000_000_000L;
Instant instant = Instant.ofEpochMilli(storedEpochMillis);

long valueToStore = instant.toEpochMilli();
```

An epoch number is an instant, not a local date-time. If a legacy schema stores `2026-11-13 09:30` without storing a zone, **the exact instant cannot be recovered solely from that value** without a known historical timezone convention.

## 13. Testing Time Zone Conventions

You should include test cases verifying data semantics, especially for multi-region systems or database migrations. Example of pure Java business tests using JUnit:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneId;
import org.junit.jupiter.api.Test;

class DateTimeConventionTest {

    @Test
    void localAppointmentInHoChiMinhResolvesToUtcInstant() {
        LocalDateTime appointment =
                LocalDateTime.of(2026, 11, 13, 9, 30);

        Instant actual = appointment
                .atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
                .toInstant();

        assertEquals(
                Instant.parse("2026-11-13T02:30:00Z"),
                actual
        );
    }

    @Test
    void dateOfBirthIsCalendarDate() {
        LocalDate birth = LocalDate.parse("1998-05-12");
        assertEquals(LocalDate.of(1998, 5, 12), birth);
    }
}
```

For the actual persistence layer, test saving and reading `DATE`, `TIME`, `TIMESTAMP`, and precision against your target database/driver. When replacing H2 with PostgreSQL or MySQL, check differences in SQL types, session time zones, JDBC parameter binding, and round-trip results. What matters is testing **the semantics of each field**, not just verifying that SQL statements execute without errors.

For schedules in DST regions, also test skipped hours and repeated hours; for daily reports, test 23-hour and 25-hour days; for containerized systems, verify that code does not depend on the default time zone.

## 14. Self-Practice Exercises

**Exercise 1 — Time-Zone-Invariant Dates.** Add a `customerBirthday` field of type `LocalDate` to an aggregate with a corresponding `DATE` column. Save a birth date, read it back, then run the application in an environment with a different default time zone. Explain why the date value must retain the exact calendar date.

**Exercise 2 — Converting Appointment Display.** Starting from `LocalDateTime.of(2026, 11, 13, 9, 30)` in `Asia/Ho_Chi_Minh`, compute the `Instant` and display that same instant in `Europe/Paris`. Compare the two local values and explain why they represent the exact same event.

**Exercise 3 — Opening Hours Spanning Midnight.** A store opens at 22:00 and closes at 02:00 the next day. Design a function taking `LocalDate`, two `LocalTime` values, and `ZoneId` to compute the opening/closing instant pair. Why can't a single `LocalTime.isBefore` check handle all cases?

**Exercise 4 — Daily Reporting Ranges.** Write a function calculating `startInclusive` and `endExclusive` from a `LocalDate` and `ZoneId`. Test it on a DST transition day in `America/New_York` and compare the duration against adding a fixed 24 hours.

**Exercise 5 — Defining API Contracts.** A system needs to return a payment timestamp and a recurring opening schedule. Choose the Java type, SQL column, and JSON fields for each piece of data; explain why one uses an instant while the other uses local time + zone.

## 15. Summary Notes

**`LocalDate` is a calendar date; `LocalTime` is a wall-clock time; `LocalDateTime` is a local date plus time. All three contain no time zone or UTC offset.** In Spring Data JDBC, they typically map to timezone-less `DATE`, `TIME`, and `TIMESTAMP`; exact column types and precision depend on the database and driver.

When you need to know **at what instant an event occurred**, use `Instant` or convert from a local date-time using an explicitly chosen `ZoneId`. When you need to preserve **local schedule intent**, store both the local date/time and the zone ID, and explicitly handle DST rules. A consistent convention from the Java model, SQL schema, and repository up to the API contract prevents off-by-one-day bugs, shifted hours, and events that cannot be correlated across time zones.

### References

- [Java 21 – `LocalDate`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDate.html), [`LocalTime`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalTime.html), [`LocalDateTime`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDateTime.html)
- [Java 21 – `ZoneId`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZoneId.html), [`Instant`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Instant.html)
- [Spring Data Relational – Mapping](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html)
