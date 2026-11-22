# Choosing Component Types Instead of Arbitrary Integers or Strings

## 1. Data types should make it clear what the data means

An integer `2` could be February, the 2nd day of the month, a lesson count, or a status code. A string `"2024-02"` could be a reporting period, yet the `String` type still accepts `"next month"`, `"2024-13"`, and an empty string.

When data carries clear calendar meaning, the component types in `java.time` help bring that meaning into the model:

- `Year`: a year.
- `YearMonth`: a year-month.
- `MonthDay`: a month-day without an attached year.
- `Month`: a month of the year.
- `DayOfWeek`: a day of the week.

The goal is not to replace every number and string with an object. The goal is to use structured types that match what the business domain actually knows. If the data is just a lesson count, `int` may be appropriate; if the data is the February 2024 study period, `YearMonth` expresses it more accurately than an unvalidated number or string.

The `java.time` types used in this article are immutable values based on the ISO calendar. They provide creation, parsing, comparison, and manipulation operations according to calendar semantics, rather than leaving each place to handle characters or numbers on its own. An overview of the model is available at [java.time](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/package-summary.html).

## 2. Choosing a type based on the information you actually have

| Business data | Appropriate type | Why |
| --- | --- | --- |
| Graduation year or reporting year | `Year` | No specific month/day yet |
| Reporting period for February 2024 | `YearMonth` | Needs both year and month, no day needed yet |
| Recurring anniversary on Dec 25 | `MonthDay` | Needs month-day, without specifying which year's occurrence |
| Starting month of a season, such as June | `Month` | It is a month of the year, not a specific period |
| Weekly study day, such as Monday | `DayOfWeek` | It is a day of the week, without a calendar date yet |
| Full birth date for calculating age | `LocalDate` | Needs to keep birth year, month, and day |

Two important distinctions:

- `Month.FEBRUARY` does not substitute for `YearMonth.of(2024, 2)`: a month value does not contain a year.
- `MonthDay.of(12, 25)` does not substitute for a full birth date: dropping the birth year leaves insufficient data to calculate age.

Do not add day 1 to a monthly period just to use `LocalDate` if the business domain does not have that day. Similarly, do not add the current year to an anniversary just to make the data look complete. When a specific date needs to be created, the added part must come from an explicit requirement.

## 3. What bugs do arbitrary integers and strings cause?

### 3.1. Parameters of the same type are easy to swap

A function taking separate `int year` and `int month` parameters does not help the compiler distinguish between those two roles. Swapping the arguments still compiles, even though month 2024 makes no sense.

A function taking a `YearMonth period` groups both parts into a single validly constructed value. The caller must pass the right kind of object; a lesson count cannot accidentally be passed where a monthly period is expected.

This does not eliminate every bug: two parameters that are both `YearMonth`, such as the first period and the last period, can still be swapped. The relationship "first period is not after last period" requires a separate check.

### 3.2. Strings have many representations and many invalid states

A monthly period might be written as `"2024-02"`, `"2024-2"`, `"02/2024"`, or `"Feb 2024"`. If the entire business layer accepts `String`, each place has to decide on the format, parsing logic, and error handling.

Parsing once at the data ingestion boundary, then using `YearMonth` internally, helps standardize how the value is understood. For example, this article chooses `"2024-02"` as the interchange format for a monthly period. The string `"2024-2"` is rejected by default parsing, even though a human reader can guess its meaning.

Choosing a broader input format is a separate decision. If a form allows `"02/2024"`, parse it with a defined formatter and still convert it to a calendar type before performing calculations; do not spread multiple string conventions across every function.

### 3.3. Manual numeric arithmetic easily misses calendar rules

For a monthly period, incrementing the month by 1 must handle rolling over from month 12 to month 1 and incrementing the year. `YearMonth.plusMonths(1)` directly expresses moving to the next period.

For a year, checking for a leap year must also handle century-year exceptions. `Year.isLeap` helps avoid having each place write its own "divisible by 4" version.

The benefit lies in operating according to a standard calendar model, not just in wrapping data inside a class.

## 4. What do the types protect?

### 4.1. Year and YearMonth

`Year.of(number)` checks the year range supported by Java. `YearMonth.of(year, month)` checks both the year and the month; month 13 is rejected.

`YearMonth` holds a year-month period as a single value. You can:

- Compare two periods with `isBefore`, `isAfter`, or `compareTo`.
- Shift periods with `plusMonths`, `minusMonths`.
- Find the number of days in the month with `lengthOfMonth`.
- Create a specific date with `atDay` or the last day of the period with `atEndOfMonth`.

A valid monthly period is not yet a full date, and there is no reason to always pick the first or last day of the period. See the definitions of [Year](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Year.html) and [YearMonth](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/YearMonth.html).

### 4.2. Month and DayOfWeek

`Month.of(2)` yields `Month.FEBRUARY`; `DayOfWeek.of(1)` yields `DayOfWeek.MONDAY`. Both enums reject out-of-range numbers while making function signatures more expressive.

Standard month numbers are 1..12. ISO day-of-week numbers are 1..7, with Monday as 1. Do not bring 0-based conventions or Sunday-as-1 conventions from other APIs here.

When you need a number for interchange, use `getValue()`, not `ordinal()`. `ordinal()` is the enum declaration position, not a calendar numbering convention for external data. See [Month](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Month.html) and [DayOfWeek](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/DayOfWeek.html).

### 4.3. MonthDay

`MonthDay.of(4, 31)` is rejected because April 31 does not exist. However, `MonthDay.of(2, 29)` is accepted because that date exists in leap years.

This is not a validation flaw: the type represents a month-day **without a year**, so it cannot yet determine whether February 29 exists in a particular target year.

When attaching a year, you need to choose a policy. `MonthDay.atYear` adjusts February 29 back to February 28 if the year is not a leap year. If the business domain wants to reject it, check `Year.isValidMonthDay` before creating the date. The type represents the structure, while the policy must be explicit; see [MonthDay](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/MonthDay.html).

## 5. Types do not automatically enforce all business rules

A valid `YearMonth` object does not by itself answer:

- Is that period within the range allowed by the system?
- Is the first period before or equal to the last period?
- Does the report allow a negative number of completed lessons?
- Is this field allowed to be missing?
- How is a February 29 anniversary handled in a non-leap year?

Therefore, three layers should be distinguished:

| Validation layer | Example |
| --- | --- |
| External data syntax | Does the period string match the published format? |
| Calendar structure | Is the year-month valid, and is the month within 1..12? |
| Business rules | Is the first period after the last period, is the count negative, is the field required? |

A `record` can group data together with business checks in its constructor. Merely declaring a `record` does not automatically eliminate `null` or guarantee period ordering; you must write the necessary checks.

If two concepts use the same calendar type but have distinct explicit constraints, you can create a domain wrapper type. For example, an "academic year" may span two calendar years and therefore is not necessarily synonymous with a single `Year`. Do not simply rename a calendar year and assume you have fully modeled an academic year.

## 6. Parse at the input boundary, keep calendar types during computation

A controllable processing flow is:

```text
External data: string or number with an explicit convention
        ↓ parse and validate
Typed value: Year / YearMonth / MonthDay / Month / DayOfWeek
        ↓ business validation
Compute, compare, and store in the model
        ↓ format according to the output contract
Interchange data or display content
```

Some default forms used in this article:

| Type | Illustrative input data | How to create |
| --- | --- | --- |
| `Year` | `"2024"` | `Year.parse(text)` |
| `YearMonth` | `"2024-02"` | `YearMonth.parse(text)` |
| `MonthDay` | `"--02-29"` | `MonthDay.parse(text)` |
| `Month` | ISO number 2 | `Month.of(number)` |
| `DayOfWeek` | ISO number 1 | `DayOfWeek.of(number)` |

The `--` prefix in `MonthDay`'s default representation indicates that the year part is omitted. This is not a full date string.

English enum names such as `FEBRUARY` and display labels such as `"tháng 2"` serve different purposes. Do not use localized labels as persisted data unless there is a corresponding parsing contract.

When serializing to JSON or storing in a database, define the format and conversion rules explicitly. Do not assume all libraries map component types in the same way. Whether the storage layer uses strings or numbers, the computation layer can still keep calendar types and convert at the I/O boundary.

If data is allowed to be missing, represent the missing state intentionally in the application's model. Do not use month `0`, year `-1`, or an empty string as placeholder values that downstream functions might mistake for real data. Year `-1` is even a valid year in `Year`'s ISO model, making it even less suitable as a built-in missing marker.

## 7. A Java 17+ program with a monthly report model

Save the following code as `ComponentTypeChoices.java`. The program uses `record` to give meaningful names and check business relationships; no external libraries are required.

`MonthlyReport` stores the period as a `YearMonth` and keeps the completed lesson count as an `int`. `ReportWindow` holds two periods and checks their ordering. The `readReport` method parses the string once before creating the report.

```java
import java.time.DateTimeException;
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.Month;
import java.time.MonthDay;
import java.time.Year;
import java.time.YearMonth;
import java.time.format.DateTimeParseException;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class ComponentTypeChoices {
    public record MonthlyReport(YearMonth period, int completedLessons) {
        public MonthlyReport {
            Objects.requireNonNull(period, "period");
            if (completedLessons < 0) {
                throw new IllegalArgumentException("completedLessons must be non-negative");
            }
        }
    }

    public record ReportWindow(YearMonth first, YearMonth last) {
        public ReportWindow {
            Objects.requireNonNull(first, "first");
            Objects.requireNonNull(last, "last");
            if (first.isAfter(last)) {
                throw new IllegalArgumentException("first must not be after last");
            }
        }
    }

    private static int checks;

    private static MonthlyReport readReport(String rawPeriod, int completedLessons) {
        return new MonthlyReport(YearMonth.parse(rawPeriod), completedLessons);
    }

    private static LocalDate strictOccurrence(Year year, MonthDay day) {
        Objects.requireNonNull(year, "year");
        Objects.requireNonNull(day, "day");
        if (!year.isValidMonthDay(day)) {
            throw new DateTimeException("Month-day does not exist in year " + year);
        }
        return year.atMonthDay(day);
    }

    private static void eq(Object actual, Object expected) {
        if (!Objects.equals(actual, expected)) {
            throw new AssertionError("expected=" + expected + ", actual=" + actual);
        }
        checks++;
    }

    private static void rejects(Class<? extends RuntimeException> type,
                                Runnable action) {
        try {
            action.run();
        } catch (RuntimeException ex) {
            if (!type.isInstance(ex)) {
                throw new AssertionError("Unexpected exception", ex);
            }
            checks++;
            return;
        }
        throw new AssertionError("Expected " + type.getSimpleName());
    }

    public static void main(String[] args) {
        MonthlyReport report = readReport("2024-02", 12);
        eq(report.period(), YearMonth.of(2024, 2));
        eq(report.completedLessons(), 12);
        eq(report.period().plusMonths(1), YearMonth.of(2024, 3));
        eq(report.period().atEndOfMonth(), LocalDate.of(2024, 2, 29));
        eq(Year.parse("2024"), Year.of(2024));
        eq(MonthDay.parse("--02-29"), MonthDay.of(2, 29));
        eq(Month.of(2), Month.FEBRUARY);
        eq(Month.FEBRUARY.getValue(), 2);
        eq(DayOfWeek.of(1), DayOfWeek.MONDAY);
        eq(YearMonth.parse(report.period().toString()), report.period());

        Map<YearMonth, Integer> counts = new HashMap<>();
        counts.put(report.period(), report.completedLessons());
        eq(counts.get(YearMonth.parse("2024-02")), Integer.valueOf(12));

        ReportWindow window = new ReportWindow(YearMonth.of(2024, 1),
                YearMonth.of(2024, 3));
        eq(window.first().isBefore(window.last()), true);
        rejects(IllegalArgumentException.class,
                () -> new ReportWindow(window.last(), window.first()));
        rejects(IllegalArgumentException.class,
                () -> new MonthlyReport(report.period(), -1));
        rejects(NullPointerException.class, () -> new MonthlyReport(null, 1));
        rejects(DateTimeParseException.class, () -> readReport("2024-13", 1));
        rejects(DateTimeParseException.class, () -> readReport("202402", 1));
        rejects(DateTimeParseException.class, () -> readReport("2024-2", 1));
        rejects(DateTimeException.class, () -> Month.of(0));
        rejects(DateTimeException.class, () -> DayOfWeek.of(0));
        rejects(DateTimeException.class, () -> MonthDay.of(4, 31));

        MonthDay anniversary = MonthDay.of(2, 29);
        eq(strictOccurrence(Year.of(2024), anniversary), LocalDate.of(2024, 2, 29));
        rejects(DateTimeException.class,
                () -> strictOccurrence(Year.of(2023), anniversary));
        eq(anniversary.atYear(2023), LocalDate.of(2023, 2, 28));

        System.out.println("period=" + report.period());
        System.out.println("nextPeriod=" + report.period().plusMonths(1));
        System.out.println("periodEnd=" + report.period().atEndOfMonth());
        System.out.println("samePeriodCount=" + counts.get(YearMonth.of(2024, 2)));
        System.out.println("strictOccurrence=" + strictOccurrence(Year.of(2024), anniversary));
        System.out.println("adjustedOccurrence=" + anniversary.atYear(2023));
        System.out.println("PASS checks=" + checks);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 ComponentTypeChoices.java
java ComponentTypeChoices
```

Stdout:

```text
period=2024-02
nextPeriod=2024-03
periodEnd=2024-02-29
samePeriodCount=12
strictOccurrence=2024-02-29
adjustedOccurrence=2023-02-28
PASS checks=24
```

The `samePeriodCount` line shows that two separately created `YearMonth` objects with the same value can be used as the same key in a `Map`. Standard component types are immutable and have value-based equality; there is no need to compare with `==`.

The two anniversary lines show that choosing a type does not replace choosing a policy. The `strictOccurrence` method requires the month-day to exist in the target year, whereas calling `atYear` directly has the adjustment behavior noted earlier.

The `eq` method actively throws `AssertionError` on mismatch, so enabling `-ea` is not required. The `rejects` method verifies the exact exception type rather than silently accepting any failure. The test suite distinguishes malformed strings, invalid calendar structures, missing required fields, and inverted period relationships.

## 8. Migrating a model that uses numbers/strings to appropriate types

You can migrate piece by piece in a concrete sequence:

1. **Document the current meaning.** Is the `month` field a month of the year or a monthly period belonging to a specific year? Does the `birthday` string include the birth year?
2. **Choose a type that retains enough information.** Use `YearMonth` for periods, `Month` for general months, and `LocalDate` for full dates.
3. **Define input conventions.** Publish the string format or numeric convention; do not leave multiple places guessing.
4. **Convert at the data ingestion boundary.** After parsing succeeds, calculation functions accept calendar types.
5. **Preserve business constraints.** Do not remove checks for allowed periods, range ordering, or counts just because a new type is used.
6. **Audit legacy data before migrating.** Malformed strings or sentinel values marking missing data must be handled explicitly; do not silently shift them to a nearby date/period.
7. **Format on output.** Do not convert to a string midway and then split the string again to compute the next period.

Migration is most useful when it reduces the number of places that must remember calendar conventions and helps function signatures state clearly what data they accept. There is no need to create many wrapper classes if there is no difference in meaning or constraints yet.

## 9. Common mistakes and selection exercises

Mistakes to avoid:

- Choosing `Month` for a monthly period that has a year, losing the year information.
- Choosing `MonthDay` for a birth date used to calculate age, losing the birth year.
- Choosing `LocalDate` for a year-month and forgetting that day 1 is fabricated data.
- Keeping `String` across all layers and repeatedly splitting, joining, and comparing strings.
- Assuming that a valid type means valid business semantics.
- Using `ordinal()` as the month or day-of-week number for interchange.
- Silently adjusting invalid data just to get past the conversion step.
- Assuming that using `record` automatically eliminates `null` and validates relationships between fields.

Practice:

1. **“Release month: 3” with no year.** If this is a recurring calendar month, use `Month.MARCH`; if it is the March 2025 release period, you need `YearMonth.of(2025, 3)`.

2. **“Birth date: 2000-02-29”, need to calculate age.** Keep `LocalDate`. You can extract `MonthDay` to create reminders, but do not use the extracted value to replace the original birth date.

3. **“Start period 2024-05, end period 2024-02”.** Both periods are valid calendar-wise, but the range is inverted; the business model must reject it.

4. **“Reminder for Feb 29 in 2023”.** `MonthDay` is still the right value to describe the recurring date pattern; generating a specific occurrence requires a policy to either report an error or adjust it.

5. **“Graduation year 2026”.** `Year.of(2026)` retains the exact level of information. If the field is required and has year bounds according to the training program, check those conditions separately.

Choose types based on meaning and level of information, then define input/output conventions along with business conditions. A good calendar type reduces the invalid states that can be represented, but it does not replace understanding what the data is being used for.
