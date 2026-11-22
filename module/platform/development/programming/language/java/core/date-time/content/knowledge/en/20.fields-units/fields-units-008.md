# TemporalQuery and Built-in Queries in TemporalQueries

## 1. Why Are Queries Needed Beyond Numeric Fields?

A date-time object does not only have numbers such as year, month, and hour. We may also want to know which calendar system it uses, whether it has a time zone, whether a local date can be obtained, or what smallest unit it supports.

`get(TemporalField)` and `getLong(TemporalField)` are suitable for reading a **numeric field**. `TemporalQuery<R>` describes a **way to query and return a result of type R**, such as `LocalDate`, `ZoneId`, `Chronology`, or a custom business result.

For example, two questions with different natures:

```java
int day = date.get(ChronoField.DAY_OF_MONTH);
LocalDate localDate = temporal.query(TemporalQueries.localDate());
```

The snippet above illustrates how to call them; `date` is a `LocalDate`, while `temporal` is a `TemporalAccessor`. The first line gets the day of the month. The second line asks whether the input can provide a `LocalDate`.

According to [TemporalQuery](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/TemporalQuery.html), queries decouple how information is extracted from the object being queried. Because of this, the same query can be applied to many date-time types without writing a chain of `instanceof` checks for each type.

However, a query does not create missing information. A `LocalTime` does not contain a date; a `LocalDateTime` does not contain a time zone. Passing a query to them does not make those objects magically know additional data.

## 2. How Does TemporalQuery<R> Work?

`TemporalQuery<R>` is a functional interface with one main method:

```java
R queryFrom(TemporalAccessor temporal);
```

`R` is the result type. It can be a Java class, an application-defined record, or a wrapper type such as `Boolean`. The method receives the object to be read and returns a result according to the query's contract.

Typical usage:

```java
TemporalQuery<LocalDate> query = TemporalQueries.localDate();
LocalDate result = temporal.query(query);
```

You can also call `query.queryFrom(temporal)` directly. For queries implemented according to the contract, the two expressions are equivalent; `temporal.query(query)` usually expresses intent more clearly in calling code.

It is important to distinguish the **query object** from the **query result**:

- `TemporalQueries.localDate()` creates/provides a `TemporalQuery<LocalDate>`.
- `temporal.query(TemporalQueries.localDate())` actually executes the query on `temporal` and may return a `LocalDate` or `null`.
- The returned standard query object is never `null`; its result may be `null` because the input lacks information.

A query is for reading; it must not modify the input object. This differs from `TemporalAdjuster`, which expresses an adjustment to produce a new temporal result.

## 3. Seven Built-in Queries

[TemporalQueries](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/TemporalQueries.html) provides seven standard methods:

| Method | Result Type | Question Answered |
| --- | --- | --- |
| `localDate()` | `LocalDate` | Can a local date in the ISO calendar be obtained? |
| `localTime()` | `LocalTime` | Can a local time be obtained? |
| `zoneId()` | `ZoneId` | Does the object contain a `ZoneId` according to its model? |
| `zone()` | `ZoneId` | Is there a `ZoneId`, or if missing, a `ZoneOffset`? |
| `offset()` | `ZoneOffset` | Can a UTC offset be obtained? |
| `chronology()` | `Chronology` | Which calendar system does the object use to represent dates? |
| `precision()` | `TemporalUnit` | What is the smallest unit supported by the object's type? |

The result depends on the information in the input. `null` should not be treated as a broken object: it usually expresses that the question has no answer in the model being used.

### 3.1. localDate(): Local Date, Not Default UTC Date

For `LocalDate`, the result is that same date in value. For `LocalDateTime`, `OffsetDateTime`, or `ZonedDateTime`, the query extracts the local date part of the object.

It does not automatically convert to UTC before extracting the date. If a `ZonedDateTime` is in `Asia/Ho_Chi_Minh`, the extracted date is the local date in that object. To get the date in another time zone, you must convert the same instant to the desired time zone first and then extract the date.

For `Instant`, this query returns `null`. A point on the timeline does not determine a unique local date without choosing a time zone. To get the date in a zone, you must perform an explicit zone-selection step, such as `instant.atZone(zone).toLocalDate()`.

The standard query extracts the date using information equivalent to `EPOCH_DAY` and returns a `LocalDate` in the ISO calendar. When the input uses a different calendar system, the result is not a date preserving the original calendar class; if calendar system information is needed, also query `chronology()` or use the appropriate calendar-specific date type.

### 3.2. localTime(): Local Time That the Object Has

`LocalTime`, `LocalDateTime`, `OffsetDateTime`, and `ZonedDateTime` have time information so they can provide a `LocalTime`. `LocalDate` has no time; the query does not default to `00:00`.

Similarly to the local date, the time result does not include an offset or time zone. After extracting only `LocalTime`, we no longer have enough information to identify a unique point on the timeline.

The standard query is based on information equivalent to `NANO_OF_DAY`. It does not guess the time from a display string or from the machine's default time zone.

### 3.3. chronology(): Calendar System

`chronology()` returns the calendar system that the object uses to represent dates. `LocalDate`, `LocalDateTime`, `YearMonth`, and `ZonedDateTime` normally use `IsoChronology`, usually printed as `ISO`.

`LocalTime` only represents time, so it has no date calendar system to report. `Instant` represents an instant, not a local calendar date, so it also does not provide a chronology via this query.

Do not unconditionally replace `null` with `ISO` if the calendar system is an important constraint of the calculation. That would be an additional application policy, not information actually obtained from the input.

### 3.4. precision(): Representational Capability, Not Measurement Accuracy

`precision()` returns the smallest unit supported by that type, for example:

| Type | Typical Result |
| --- | --- |
| `LocalDate` | `ChronoUnit.DAYS` |
| `YearMonth` | `ChronoUnit.MONTHS` |
| `Year` | `ChronoUnit.YEARS` |
| `LocalTime` | `ChronoUnit.NANOS` |
| `LocalDateTime` | `ChronoUnit.NANOS` |
| `Instant` | `ChronoUnit.NANOS` |

An `Instant` parsed from a string with only seconds still supports nanoseconds; `precision()` still returns `NANOS`. It does not remember "how many fractional digits the input string had".

It also does not prove that the operating system clock or measuring device is actually accurate to the nanosecond. Storage capability, source data resolution, and measurement accuracy are separate concerns.

An object that does not represent a complete date/time in the relevant sense, such as `MonthDay`, may return `null`. You should not assume every `TemporalAccessor` has a precision.

## 4. zoneId(), zone(), and offset(): Three Different Questions

### 4.1. ZoneId and ZoneOffset

`ZoneId` represents a time-zone identifier; it can be a region such as `Asia/Ho_Chi_Minh` or a fixed offset. `ZoneOffset` represents an offset from UTC, such as `+07:00`, and is also a subclass of `ZoneId`.

A fixed offset does not store the region identity or all the offset-change rules of that region. Multiple regions can share the same offset at a given time; from `+07:00`, you cannot uniquely recover the original region name.

### 4.2. zoneId() Does Not Automatically Convert an Offset into an Answer

`zoneId()` requires the input to contain a `ZoneId` according to the type's model:

- `ZonedDateTime` returns `getZone()`.
- `OffsetDateTime` only has an offset, so it returns `null`.
- `LocalDateTime` has neither a zone nor an offset, so it returns `null`.

"Stricter requirement" here does not mean accepting only region names. A `ZonedDateTime` created with a fixed zone `+07:00` still contains a valid `ZoneId`; `zoneId()` can return `+07:00` itself. To check whether the input carries a region name or only a fixed offset, you must add an explicit condition.

### 4.3. zone() Allows Using Offset When Zone Is Missing

`zone()` looks for `zoneId()` first; if not present, it tries `offset()`. Because `ZoneOffset` is also a `ZoneId`, the result type is still `ZoneId`.

| Input | `zoneId()` | `zone()` | `offset()` |
| --- | --- | --- | --- |
| `ZonedDateTime` with region `Asia/Ho_Chi_Minh` in the example | `Asia/Ho_Chi_Minh` | `Asia/Ho_Chi_Minh` | `+07:00` |
| `OffsetDateTime` with offset `+07:00` | `null` | `+07:00` | `+07:00` |
| `ZonedDateTime` with fixed zone `+07:00` | `+07:00` | `+07:00` | `+07:00` |
| `LocalDateTime` | `null` | `null` | `null` |
| `Instant` | `null` | `null` | `null` |

The `Instant` row is easy to misunderstand because `Instant.toString()` usually ends with `Z`. That formatting does not mean the object contains a local zone/offset that the standard queries will return. If you want an object with the UTC zone, use `instant.atZone(ZoneOffset.UTC)` explicitly.

### 4.4. offset() Does Not Replace Time-Zone Rules

For `ZonedDateTime`, `offset()` returns the offset in effect at that date-time. It does not return all rules of the region and does not guarantee that the offset will be identical at another point in time.

Choose the query based on business conditions:

- Only need a zone or offset to continue an operation: consider `zone()`.
- Need to know that the object already carries a `ZoneId`: use `zoneId()` and handle absence.
- Need a specific UTC offset: use `offset()`.
- Need the region identity and zone rules to interpret other dates: validate the zone data according to the contract, do not infer it backwards from an offset.

## 5. Complete Java 17+ Program

Save as `TemporalQueriesDemo.java`:

```java
import java.time.DateTimeException;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.OffsetDateTime;
import java.time.YearMonth;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.temporal.TemporalAccessor;
import java.time.temporal.TemporalQueries;
import java.time.temporal.TemporalQuery;

public class TemporalQueriesDemo {
    static final TemporalQuery<Boolean> IS_MONTH_END = temporal -> {
        LocalDate date = temporal.query(TemporalQueries.localDate());
        if (date == null) {
            return null;
        }
        return date.getDayOfMonth() == date.lengthOfMonth();
    };

    static void showZones(String label, TemporalAccessor temporal) {
        System.out.println(label
                + ": zoneId=" + temporal.query(TemporalQueries.zoneId())
                + ", zone=" + temporal.query(TemporalQueries.zone())
                + ", offset=" + temporal.query(TemporalQueries.offset()));
    }

    public static void main(String[] args) {
        OffsetDateTime offset = OffsetDateTime.parse(
                "2024-06-15T10:20:30+07:00");
        ZonedDateTime zoned = offset.atZoneSameInstant(
                ZoneId.of("Asia/Ho_Chi_Minh"));

        System.out.println("date = "
                + zoned.query(TemporalQueries.localDate()));
        System.out.println("time = "
                + zoned.query(TemporalQueries.localTime()));
        System.out.println("zoneId = "
                + zoned.query(TemporalQueries.zoneId()));
        System.out.println("zone = "
                + zoned.query(TemporalQueries.zone()));
        System.out.println("offset = "
                + zoned.query(TemporalQueries.offset()));
        System.out.println("chronology = "
                + zoned.query(TemporalQueries.chronology()));
        System.out.println("precision = "
                + zoned.query(TemporalQueries.precision()));

        showZones("OffsetDateTime", offset);
        showZones("LocalDateTime", offset.toLocalDateTime());
        showZones("fixed ZonedDateTime",
                offset.atZoneSameInstant(ZoneOffset.ofHours(7)));

        Instant instant = Instant.parse("2024-06-15T03:20:30Z");
        showZones("Instant", instant);
        System.out.println("instant date = "
                + instant.query(TemporalQueries.localDate()));
        System.out.println("instant precision = "
                + instant.query(TemporalQueries.precision()));
        System.out.println("date precision = "
                + LocalDate.of(2024, 6, 15)
                        .query(TemporalQueries.precision()));
        System.out.println("month precision = "
                + YearMonth.of(2024, 6)
                        .query(TemporalQueries.precision()));

        LocalDate last = LocalDate.of(2024, 2, 29);
        LocalDate first = LocalDate.of(2024, 2, 1);
        System.out.println("month-end true = " + last.query(IS_MONTH_END));
        System.out.println("month-end false = " + first.query(IS_MONTH_END));
        System.out.println("month-end absent = "
                + YearMonth.of(2024, 2).query(IS_MONTH_END));

        LocalTime time = LocalTime.of(10, 20, 30);
        System.out.println("optional date = "
                + time.query(TemporalQueries.localDate()));
        try {
            time.query(LocalDate::from);
        } catch (DateTimeException ex) {
            System.out.println("required date -> "
                    + ex.getClass().getSimpleName());
        }

        LocalDate viaMethod = zoned.query(TemporalQueries.localDate());
        LocalDate viaQueryFrom =
                TemporalQueries.localDate().queryFrom(zoned);
        System.out.println("equivalent calls = "
                + viaMethod.equals(viaQueryFrom));

        LocalDateTime local = LocalDateTime.of(2024, 6, 15, 10, 20, 30);
        System.out.println("original local = " + local);
        System.out.println("local has zone = "
                + (local.query(TemporalQueries.zone()) != null));
    }
}
```

Compile and run:

```shell
javac --release 17 TemporalQueriesDemo.java
java TemporalQueriesDemo
```

Stdout:

```text
date = 2024-06-15
time = 10:20:30
zoneId = Asia/Ho_Chi_Minh
zone = Asia/Ho_Chi_Minh
offset = +07:00
chronology = ISO
precision = Nanos
OffsetDateTime: zoneId=null, zone=+07:00, offset=+07:00
LocalDateTime: zoneId=null, zone=null, offset=null
fixed ZonedDateTime: zoneId=+07:00, zone=+07:00, offset=+07:00
Instant: zoneId=null, zone=null, offset=null
instant date = null
instant precision = Nanos
date precision = Days
month precision = Months
month-end true = true
month-end false = false
month-end absent = null
optional date = null
required date -> DateTimeException
equivalent calls = true
original local = 2024-06-15T10:20:30
local has zone = false
```

The program provides fixed inputs and chooses zones explicitly, without relying on the current date or the machine's default time zone. The first lines demonstrate all seven queries. Subsequent lines contrast cases with a zone, with only an offset, and with neither.

`atZoneSameInstant` in the example converts from `OffsetDateTime` to `ZonedDateTime` while keeping the same instant. That is an explicit data conversion step before querying, not automatic behavior of `TemporalQueries`.

## 6. null, false, and Exceptions Must Have Distinct Meanings

### 6.1. Standard Queries May Not Find Information

Reading the date from a `LocalTime`:

```java
LocalDate date = time.query(TemporalQueries.localDate());
```

The result is `null` because a standalone time does not contain a date. If the information is optional, the caller can check for `null` or wrap the result with `Optional.ofNullable` at the application boundary.

Do not fill in today's date to avoid `null`. Doing so makes the result depend on the clock, environment, and run date, while hiding the fact that the input lacks data.

### 6.2. Method References Can Use a Stricter Contract

A method such as `LocalDate.from(TemporalAccessor)` can be used as a query:

```java
LocalDate requiredDate = temporal.query(LocalDate::from);
```

If a date cannot be obtained, `LocalDate.from` throws `DateTimeException` instead of returning `null`. Therefore, `TemporalQueries.localDate()` and `LocalDate::from` are similar in the kind of information they retrieve, but **differ in their contract when information is missing**.

The program uses `LocalTime` to clearly observe this: the standard query returns `null`; the method reference throws an exception. Choose the approach that matches whether the date is optional or required.

Similarly, `ZoneId::from` can be used as a query that requires obtaining a zone, allowing an offset when appropriate and throwing an error if none can be obtained; it should not be treated as an alias for the stricter `zoneId()` query.

### 6.3. The Contract of a Custom Query Is Decided by Its Author

The `TemporalQuery<R>` interface does not force all queries to use the same failure signal. A custom query can:

- Return `null` when information is unavailable.
- Return a result type that explicitly represents the missing state.
- Throw an exception if the input does not satisfy a required condition.

What matters is stating the contract clearly and staying consistent. `false` should express a proposition that was evaluated and found untrue; it should not be used by default in place of "insufficient data to evaluate".

## 7. Writing a Small Reusable TemporalQuery

In the program, `IS_MONTH_END` answers "is this the last day of the month?":

1. Query `LocalDate` from the input.
2. If the date is missing, return `null`.
3. If a date is present, compare the day of the month with the length of the month.

The results are distinguished:

| Input | Result | Meaning |
| --- | --- | --- |
| `LocalDate.of(2024, 2, 29)` | `true` | Has a date and it is the last day of the month |
| `LocalDate.of(2024, 2, 1)` | `false` | Has a date but it is not the last day of the month |
| `YearMonth.of(2024, 2)` | `null` | Knows the month, but has no specific day to evaluate |

The calculation does not need custom leap-year rules; `LocalDate.lengthOfMonth()` provides the correct month length in context.

Because the result is a nullable `Boolean`, writing `if (temporal.query(IS_MONTH_END))` can cause a `NullPointerException` due to unboxing. If the three states are meaningful, handle them separately. `Boolean.TRUE.equals(result)` avoids the unboxing error, but merges `false` and `null` into the false branch; use it only when the caller's policy accepts that merging.

This query evaluates the ISO date obtained from `localDate()`. If the requirement is "end of month according to the input's original calendar system", a different query with an explicit calendar contract is needed. Do not extract an ISO date and claim the result is valid for every calendar.

### 7.1. Avoid Recursion Calling the Query Itself

An implementation like the following performs no reading and only calls itself:

```java
TemporalQuery<LocalDate> broken = new TemporalQuery<>() {
    @Override
    public LocalDate queryFrom(TemporalAccessor temporal) {
        return temporal.query(this);
    }
};
```

This is **buggy demonstration code; do not call it to run**. For an input type that does not handle that query specially, `query` delegates back to `queryFrom`, creating recursion and potentially leading to a `StackOverflowError`.

In a custom query, actually read fields or use another query whose contract is known, such as `TemporalQueries.localDate()` in `IS_MONTH_END`.

### 7.2. Avoid Mutable State in Shared Queries

A query may be used from multiple threads. A lambda that only reads the input and uses immutable data is easier to keep thread-safe than a query object with counters or lists mutated at runtime.

Do not mutate the input, do not implicitly depend on the system time zone, and do not read the current date unless that is part of the stated contract. If the query needs external data, supply it explicitly and keep a stable snapshot when repeatable results are required.

## 8. Choosing a Query or a Specific Method?

Use a specific type's method when it expresses the intent clearly enough:

```java
LocalDate date = zonedDateTime.toLocalDate();
ZoneId zone = zonedDateTime.getZone();
```

Use a query when you need a reusable way to extract information across multiple `TemporalAccessor` types, or when you want to pass the extraction strategy into another component:

```java
TemporalQuery<LocalDate> dateQuery = TemporalQueries.localDate();
```

There is no need to turn every simple operation into a separate query class. The value of `TemporalQuery` lies in expressing a question with a clear contract that can be applied uniformly, not in increasing the number of intermediary classes.

Also remember that the same date query on `OffsetDateTime` and `ZonedDateTime` extracts each object's own local date. If the application needs a reporting date in a fixed time zone, normalize the instant to the reporting zone first. Using the same query object alone is not enough to guarantee the same time-zone policy.

## 9. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Treating `TemporalQueries.zone()` as the retrieved zone | Confusing the query object with the result | Call `temporal.query(...)` |
| Reading `zoneId()` from `OffsetDateTime` and concluding all offset info is missing | Ignoring the available offset | Use `offset()` or `zone()` as needed |
| Treating every `zoneId()` result as a region name | Overlooking fixed zones | Check the contract requiring a region explicitly |
| Extracting a date from `Instant` without choosing a zone | Missing local date | Choose a zone with `atZone` first |
| Seeing `Z` in `Instant`'s string and expecting `offset()` to return UTC | Confusing formatting with query data | Convert to a UTC-zoned object if needed |
| Interpreting `precision = NANOS` as nanosecond measurement accuracy | Equating the model with the data source | Separate representational capability from accuracy |
| Assuming every query returns `null` on failure | Missing exception-throwing contracts | Read each query's contract |
| Auto-unboxing a nullable `Boolean` | `NullPointerException` | Handle the missing state explicitly |
| Calling only `temporal.query(this)` inside `queryFrom` | Recursion | Implement actual reading logic |
| Extracting an ISO date and evaluating month rules of another calendar | Incorrect calendar semantics | Specify the calendar system in the contract |

## 10. Self-Check and Practice

1. Query `localDate()`, `localTime()`, and `chronology()` on `LocalDate`, `LocalTime`, and `LocalDateTime`. Predict which cases return `null` before checking.
2. Create an `OffsetDateTime` with offset `+07:00`. Explain why `zone()` has a value while `zoneId()` does not.
3. Convert it to a `ZonedDateTime` with the fixed zone `ZoneOffset.ofHours(7)`. Verify that `zoneId()` now has a value, even though there is still no region name.
4. Use an `Instant` near a day boundary, such as `2024-06-14T18:30:00Z`, then choose UTC and `Asia/Ho_Chi_Minh`. The UTC date is June 14, while the date in the `+07:00` zone in the example is June 15. Distinguish the zone-selection step from the date-extraction step.
5. Compare `precision()` of an `Instant` with a zero nano part and an `Instant` with a non-zero nano part. Both still support `NANOS`.
6. Use `IS_MONTH_END` on a `LocalDateTime` at the end of a month and on a `YearMonth`. Explain why having only the month is not enough to conclude anything about a specific day.
7. Write a query that returns the ISO quarter as an `Integer`, returning `null` if no date can be obtained. Test months 1, 3, 4, and 12; state clearly that the result is based on the ISO date.
8. Change the month-end query's contract to require a date using `LocalDate.from`. Note how the caller must handle a time-only input.

When using `TemporalQuery`, what matters is knowing exactly what information is being asked for, whether the input can provide it, and how the contract represents missing information.
