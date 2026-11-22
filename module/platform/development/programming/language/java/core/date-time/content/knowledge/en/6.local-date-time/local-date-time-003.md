# Splitting Date and Time Parts from LocalDateTime in Java

`LocalDateTime` represents a **local date and time in a single value**, such as `2025-04-09T14:30:45.123456789`. When a business requirement only needs the **calendar date** or only needs the **clock time**, Java provides two direct operations:

~~~java
LocalDate date = dateTime.toLocalDate();
LocalTime time = dateTime.toLocalTime();
~~~

The result is two objects that are independent in type and meaning: `LocalDate` contains year–month–day; `LocalTime` contains hour–minute–second–nanosecond-of-second. All three types belong to `java.time`, are immutable, and do not contain a time zone or UTC offset.

## 1. Understand the Data Before Splitting

Example input:

~~~text
2025-04-09T14:30:45.123456789
└─ date ─┘ └───── time ──────┘
~~~

In ISO-8601 syntax, `T` separates the date part and the time part. From this value:

| Component | Java Type | Result |
| --- | --- | --- |
| Full date | `LocalDate` | `2025-04-09` |
| Full time | `LocalTime` | `14:30:45.123456789` |
| Year | `int` | `2025` |
| Month | `int` | `4` |
| Day of month | `int` | `9` |
| Hour of day | `int` | `14` |
| Minute | `int` | `30` |
| Second | `int` | `45` |
| Nanosecond of second | `int` | `123456789` |

Key point: `LocalDateTime` **has no `ZoneId`, `ZoneOffset`, or `Instant` inside**. Therefore, splitting the date and time **does not perform any time zone conversion** and does not confirm that the data is in UTC. It simply extracts the two parts already present in the same local date-time.

## 2. Using toLocalDate() and toLocalTime()

This is the clearest approach when you want to split by data type:

~~~java
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;

LocalDateTime dateTime =
        LocalDateTime.parse("2025-04-09T14:30:45.123456789");

LocalDate date = dateTime.toLocalDate();
LocalTime time = dateTime.toLocalTime();

// date = 2025-04-09
// time = 14:30:45.123456789
~~~

`toLocalDate()` extracts only the date part without modifying `dateTime`. Similarly, `toLocalTime()` preserves the existing hour, minute, second, and nanosecond precision. There is no rounding, truncation of fractional seconds, or automatic zone conversion.

After splitting, use the API appropriate for the meaning of each part:

~~~java
int year = date.getYear();        // 2025
int month = date.getMonthValue(); // 4
int day = date.getDayOfMonth();   // 9

int hour = time.getHour();        // 14
int minute = time.getMinute();    // 30
int second = time.getSecond();    // 45
int nano = time.getNano();        // 123456789
~~~

The difference is that `toLocalDate()` returns **a date object** that can be processed as an independent calendar value, whereas `getDayOfMonth()` only returns **an integer field**, which is not enough to identify a date. Similarly, `toLocalTime()` returns the full time, unlike `getHour()` which only returns a number from 0–23.

If you need to categorize orders by **order date**, use `toLocalDate()`; if you need to check whether an order was placed **before 17:00 on that day**, use `toLocalTime()`. When categorizing based on a specific time zone, you must ensure the data is already interpreted in the business time zone before splitting.

## 3. Complete Java 17+ Example and Exact Output

Save as `LocalDateTimeSplitDemo.java`:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoUnit;
import java.util.Locale;

public class LocalDateTimeSplitDemo {
    public static void main(String[] args) {
        LocalDateTime original =
                LocalDateTime.parse("2025-04-09T14:30:45.123456789");

        LocalDate date = original.toLocalDate();
        LocalTime time = original.toLocalTime();

        System.out.println("original=" + original);
        System.out.println("date=" + date);
        System.out.println("time=" + time);
        System.out.println("parts=" + date.getYear()
                + "/" + date.getMonthValue()
                + "/" + date.getDayOfMonth());
        System.out.println("clock=" + time.getHour()
                + ":" + time.getMinute()
                + ":" + time.getSecond()
                + " nanos=" + time.getNano());

        LocalDateTime recombined = LocalDateTime.of(date, time);
        System.out.println("recombine=" + recombined);
        System.out.println("same="
                + original.equals(date.atTime(time)));
        System.out.println("midnight=" + date.atStartOfDay());
        System.out.println("noon=" + date.atTime(12, 0));

        DateTimeFormatter display = DateTimeFormatter.ofPattern(
                "dd/MM/uuuu HH:mm:ss.SSS", Locale.ROOT);
        System.out.println("display=" + original.format(display));
        System.out.println("trunc="
                + original.truncatedTo(ChronoUnit.MINUTES));

        LocalDateTime acrossMidnight =
                LocalDateTime.of(2025, 4, 9, 23, 59).plusMinutes(2);
        System.out.println("across=" + acrossMidnight);

        ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
        ZonedDateTime withZone = original.atZone(zone);
        Instant instant = withZone.toInstant();
        System.out.println("withZone=" + withZone);
        System.out.println("instant=" + instant);
        System.out.println("recovered="
                + instant.atZone(zone).toLocalDateTime());
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac LocalDateTimeSplitDemo.java
java LocalDateTimeSplitDemo
~~~

Output with the fixed data in the program:

~~~text
original=2025-04-09T14:30:45.123456789
date=2025-04-09
time=14:30:45.123456789
parts=2025/4/9
clock=14:30:45 nanos=123456789
recombine=2025-04-09T14:30:45.123456789
same=true
midnight=2025-04-09T00:00
noon=2025-04-09T12:00
display=09/04/2025 14:30:45.123
trunc=2025-04-09T14:30
across=2025-04-10T00:01
withZone=2025-04-09T14:30:45.123456789+07:00[Asia/Ho_Chi_Minh]
instant=2025-04-09T07:30:45.123456789Z
recovered=2025-04-09T14:30:45.123456789
~~~

The result `same=true` proves that splitting into `LocalDate` and `LocalTime` and then recombining **loses no date, time, or nanosecond information** from `LocalDateTime`. The `display` line only prints three fractional digits according to the pattern and does not mutate the original object; the `trunc` line intentionally creates a new object with seconds and fractional seconds removed. The `withZone` and `instant` lines illustrate **attaching time zone context**, rather than an automatic consequence of splitting.

## 4. Reading Numeric Fields Directly When Only Numbers Are Needed

If the business logic only needs an integer and does not require a separate `LocalDate`/`LocalTime` object, `LocalDateTime` already provides direct getters:

~~~java
LocalDateTime value =
        LocalDateTime.of(2025, 4, 9, 14, 30, 45, 123_456_789);

int year = value.getYear();          // 2025
int month = value.getMonthValue();   // 4
int day = value.getDayOfMonth();     // 9
int hour = value.getHour();          // 14
int minute = value.getMinute();      // 30
int second = value.getSecond();      // 45
int nano = value.getNano();          // 123456789
~~~

Both ways of reading below produce the same numeric results:

~~~java
int directHour = value.getHour();
int hourFromTime = value.toLocalTime().getHour();

int directDay = value.getDayOfMonth();
int dayFromDate = value.toLocalDate().getDayOfMonth();
~~~

Choose `toLocalDate()` when you need the **full date** for calendar calculations, date comparisons, holidays, or date-based queries. Choose `toLocalTime()` when you need the **full time** to compare business hours or format the time. Choose direct getters when you only want to display or check a single component.

Be careful to distinguish `getDayOfMonth()` from `getDayOfYear()` and `getDayOfWeek()`: they represent the day of the month, the day of the year, and the day of the week respectively, and cannot be used interchangeably.

## 5. Recombining Date and Time: LocalDateTime.of, atTime, and atDate

After splitting, there are three common ways to recombine:

~~~java
LocalDate date = LocalDate.of(2025, 4, 9);
LocalTime time = LocalTime.of(14, 30, 45, 123_456_789);

LocalDateTime a = LocalDateTime.of(date, time);
LocalDateTime b = date.atTime(time);
LocalDateTime c = time.atDate(date);

// a.equals(b) && b.equals(c) is true
~~~

- `LocalDateTime.of(date, time)` directly expresses the intent to combine the two components.
- `date.atTime(time)` is convenient when the processing flow starts from a date.
- `time.atDate(date)` is convenient when the processing flow starts from a time.

The returned values are still `LocalDateTime` **without a zone**. If the two components come from different sources, you must ensure they belong to the same **business context**. Combining a "UTC date" with a "Vietnam time" without converting first will produce a value that looks valid but has the wrong meaning.

To intentionally set a time for a date:

~~~java
LocalDate date = LocalDate.of(2025, 4, 9);
LocalDateTime begin = date.atStartOfDay(); // 2025-04-09T00:00
LocalDateTime noon = date.atTime(12, 0);  // 2025-04-09T12:00
~~~

`date.atStartOfDay()` with no arguments returns a **LocalDateTime** at 00:00, **not a UTC instant**. The method `date.atStartOfDay(ZoneId)` is a different overload that returns a `ZonedDateTime` based on time zone rules; be sure to distinguish between these two results.

## 6. Changing Only the Date or Only the Time While Keeping the Other Component

Temporal types in `java.time` are immutable, so every modification creates a new value. To keep the time unchanged while replacing the date:

~~~java
LocalDateTime original =
        LocalDateTime.parse("2025-04-09T14:30:45.123456789");
LocalDate replacementDate = LocalDate.of(2025, 4, 10);
LocalDateTime changedDate =
        LocalDateTime.of(replacementDate, original.toLocalTime());
// 2025-04-10T14:30:45.123456789
~~~

To keep the date unchanged while replacing the time:

~~~java
LocalTime replacementTime = LocalTime.of(9, 0);
LocalDateTime changedTime =
        LocalDateTime.of(original.toLocalDate(), replacementTime);
// 2025-04-09T09:00
~~~

In some cases, you only need `withYear`, `withMonth`, `withDayOfMonth`, `withHour`, or `withMinute`:

~~~java
LocalDateTime atNine = original.withHour(9).withMinute(0);
// 2025-04-09T09:00:45.123456789
~~~

Note: `withHour(9).withMinute(0)` **preserves the seconds and nanoseconds** of `original`, unlike combining with `LocalTime.of(9, 0)` (which defaults seconds and nanoseconds to 0). When you want to replace it completely with "meeting time at 09:00 sharp", combine with an explicit `LocalTime` or reset the seconds and fractional seconds.

If adding time crosses midnight, `LocalDateTime` will also change the date:

~~~java
LocalDateTime nearMidnight =
        LocalDateTime.of(2025, 4, 9, 23, 59);
LocalDateTime later = nearMidnight.plusMinutes(2);
// 2025-04-10T00:01
~~~

In this example, splitting `nearMidnight` first and adding `2` minutes **only on `LocalTime`** would give `00:01` but lose the rollover to April 10. Perform the arithmetic on `LocalDateTime` if the duration can cross a day boundary.

## 7. Formatting and Parsing Split Date and Time

By default, `LocalDateTime.parse(...)` accepts ISO-8601 format with a date part, `T`, and a time part, for example:

~~~java
LocalDateTime dateTime =
        LocalDateTime.parse("2025-04-09T14:30:45.123456789");
LocalDate date = dateTime.toLocalDate();
LocalTime time = dateTime.toLocalTime();

String dateText = date.toString(); // "2025-04-09"
String timeText = time.toString(); // "14:30:45.123456789"
~~~

You can parse two separate strings and then combine them:

~~~java
LocalDate parsedDate = LocalDate.parse("2025-04-09");
LocalTime parsedTime = LocalTime.parse("14:30:45.123456789");
LocalDateTime recombined =
        LocalDateTime.of(parsedDate, parsedTime);
~~~

To display in `dd/MM/uuuu HH:mm:ss` format:

~~~java
DateTimeFormatter formatter = DateTimeFormatter.ofPattern(
        "dd/MM/uuuu HH:mm:ss");
String text = dateTime.format(formatter);
// "09/04/2025 14:30:45"
~~~

If the formatter pattern only goes down to seconds, the nanosecond part is **not printed**. This does not erase the fractional seconds of `dateTime`. However, if you **re-parse the string that omitted the fractional part**, the new object will have nanosecond = 0, meaning precision was lost through the string conversion.

In patterns:

| Symbol | Meaning | Notes |
| --- | --- | --- |
| `uuuu` | Proleptic ISO calendar year | Usually preferred over `YYYY` when you want the calendar year |
| `MM` | Month | Different from `mm` (minutes) |
| `dd` | Day of month | Different from `DD` (day of year) |
| `HH` | 24-hour clock | Different from `hh` (12-hour clock) |
| `mm` | Minute | Lowercase |
| `ss` | Second | Lowercase |
| `SSS` | Three digits of fraction-of-second | Prints milliseconds by taking the first three digits |

Do not manually split strings using `substring(0, 10)` or `split("T")` as your primary data processing mechanism. That approach is error-prone when formats change or inputs are invalid; parsing with `LocalDateTime.parse` and then calling `toLocalDate()/toLocalTime()` provides proper types and date-time validation.

## 8. Splitting Date and Time Does Not Automatically Convert Time Zones

This is the most important boundary when an application receives data from APIs, databases, or different regions. The following value:

~~~text
2025-04-09T14:30:45
~~~

does not indicate whether it is 14:30 in Vietnam or in London. `LocalDateTime.toLocalDate()` returns `2025-04-09` under both interpretations; however, **the two actual instants in time** will differ if you attach different zones.

If the data is originally an instant and you want the date/time **in Vietnam**, first convert the instant to that zone:

~~~java
Instant occurredAt =
        Instant.parse("2025-04-09T07:30:45.123456789Z");
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

LocalDateTime local =
        occurredAt.atZone(zone).toLocalDateTime();
LocalDate date = local.toLocalDate();
LocalTime time = local.toLocalTime();
// date = 2025-04-09
// time = 14:30:45.123456789
~~~

Conversely, only when `LocalDateTime` has been business-confirmed as Vietnam time do you have enough information to attach the zone and convert to an instant:

~~~java
LocalDateTime local =
        LocalDateTime.parse("2025-04-09T14:30:45.123456789");
ZonedDateTime zoned =
        local.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
Instant instant = zoned.toInstant();
// 2025-04-09T07:30:45.123456789Z
~~~

**Do not blindly attach `ZoneOffset.UTC` or a `Z` suffix** to a `LocalDateTime` just because you want to "store UTC": doing so changes the meaning of the instant if the original time was actually a local time.

In zones with DST, a local date-time may not exist or may occur twice. For example, `2025-11-02T01:30` in `America/New_York` can correspond to two different offsets. `atZone(zone)` has a default resolution rule; if the business logic needs to determine the exact choice, check `zone.getRules().getValidOffsets(local)` and choose an explicit policy. Splitting into `LocalDate` and `LocalTime` **does not resolve DST ambiguity**.

## 9. Applications in Data and Business Logic

### Case 1: Grouping events by date

If each `LocalDateTime` value already accurately represents the business local time, group by date:

~~~java
Map<LocalDate, List<LocalDateTime>> byDay =
        events.stream().collect(
                java.util.stream.Collectors.groupingBy(
                        LocalDateTime::toLocalDate));
~~~

The snippet above is illustrative code inside a method with an `events` variable of type `List<LocalDateTime>` and `java.util.*` imported; it is **not a standalone program**. The result groups by **the date of the input LocalDateTime values**. If `events` are instants from multiple time zones, convert each instant to the same reporting zone before grouping.

### Case 2: Checking operating hours within a day

~~~java
LocalTime workStart = LocalTime.of(9, 0);
LocalTime workEnd = LocalTime.of(17, 0);

LocalTime eventTime = dateTime.toLocalTime();
boolean inBusinessHours =
        !eventTime.isBefore(workStart)
                && eventTime.isBefore(workEnd);
~~~

This is a half-open interval **[09:00, 17:00)**: exactly 09:00 is included, and exactly 17:00 is excluded. This expression is suitable for shifts that **do not cross midnight**. If a shift crosses midnight, you must change the logic or use both date and time. Before checking, also verify that `dateTime` is in the local time of the operating unit.

### Case 3: Keeping date and time separate for forms

A user interface may provide independent date and time inputs:

~~~java
LocalDate inputDate = LocalDate.parse("2025-04-09");
LocalTime inputTime = LocalTime.parse("14:30");

LocalDateTime appointment = inputDate.atTime(inputTime);
// 2025-04-09T14:30
~~~

If the data represents an appointment in a specific city, the application also needs to know the `ZoneId` of that city when scheduling or sending notifications. `LocalDateTime` only carries the date and time chosen by the user.

### Case 4: DTOs or databases

A DTO may separate fields so the UI can handle them easily:

~~~java
public record AppointmentInput(
        LocalDate date,
        LocalTime time,
        String zoneId
) {}
~~~

This is an illustrative record declaration and requires importing the `java.time` types; it is not a standalone runnable program. When processing the data, the application needs to validate the date, time, and `zoneId`, and then combine them according to a DST policy. If you only want to store a local date-time value, you can use `LocalDateTime`, but do not assume the `TIMESTAMP` type in a database always has the same zone semantics across all DBMSs/drivers.

## 10. Common Mistakes

| Mistake | Consequence | Correct Approach |
| --- | --- | --- |
| Assuming `toLocalDate()` returns a timestamp at 00:00 | A date has no time or instant | Use `LocalDate` as a calendar date, and attach a time/zone when truly needed |
| Assuming `toLocalTime()` retains the date | Loses date information when crossing midnight | Use `LocalDateTime` for calculations that may change the date |
| Using `getDayOfMonth()` instead of `toLocalDate()` | Only keeps the day number 1–31, losing year and month | Use `toLocalDate()` |
| Using `getHour()` instead of `toLocalTime()` | Loses minutes, seconds, and nanoseconds | Use `toLocalTime()` |
| Splitting with `substring` and custom parsing | Format errors, hard to validate data | Parse into a date-time type first, then split |
| Thinking splitting date/time converts the timezone | Data is misinterpreted as UTC | Convert `Instant` to `ZoneId` first if you need a zone's date/time |
| Formatting with `SSS` and re-parsing, thinking nanoseconds are preserved | Precision is lost through string conversion | Pass the full data type or format all digits |
| Combining a date and time from two different zones | Creates a syntactically valid `LocalDateTime` with wrong business meaning | Normalize to the same context before combining |
| Using `LocalDateTime.now()` in unit tests that need fixed results | Depends on the environment's clock and zone | Provide an appropriate `Clock` and test against fixed timestamps |
| Assuming a local date-time always maps to one instant | DST can create a gap or overlap | Specify the zone and DST handling rules |

## 11. Self-Check Questions

**Question 1.** With `LocalDateTime.parse("2025-04-09T14:30:45.123456789")`, what are the results of `toLocalDate()` and `toLocalTime()`?

**Answer:** `2025-04-09` and `14:30:45.123456789`. No offset or time zone is added automatically.

**Question 2.** Does recombining the results of the two calls above with `LocalDateTime.of(date, time)` lose nanoseconds?

**Answer:** No. `LocalTime` preserves the full nanosecond fraction, so recombining recreates the exact original date-time, provided the components have not been modified.

**Question 3.** Why is `date.atStartOfDay()` not yet a UTC timestamp?

**Answer:** This call returns a `LocalDateTime` at `00:00`, which contains no zone. To obtain a UTC instant, you must specify an appropriate zone, such as `date.atStartOfDay(zone).toInstant()`.

**Question 4.** What date and time does `2025-04-09T23:59` plus two minutes produce?

**Answer:** `2025-04-10T00:01`. If you only calculate with `LocalTime`, the rollover to April 10 is lost.

**Question 5.** When you have an `Instant` from an API and need to group by Vietnam date, which step should you take before `toLocalDate()`?

**Answer:** Convert the instant to `Asia/Ho_Chi_Minh` using `instant.atZone(zone)` and then take the date. The UTC date and the Vietnam date can differ at the same instant.

**Key takeaway:** `toLocalDate()` extracts the **date**, `toLocalTime()` extracts the **time**, and `LocalDateTime.of(date, time)` or `date.atTime(time)` recombines them **without changing the time zone**. Only when `ZoneId`/offset information is present can the position of that date-time on the UTC timeline be determined.