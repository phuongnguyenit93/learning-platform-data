# Lenient Calendar and Out-of-Range Value Normalization

## 1. Setting an invalid date but still getting a valid date

In `java.util.Calendar`, a statement that sets the date to 2023-02-29 is not necessarily rejected immediately. When lenient interpretation (`lenient`) is allowed, `GregorianCalendar` can interpret those fields as 2023-03-01.

This is **value normalization**, not validation that the date entered by the user exists. If an application uses the result to store a birth date or document date where the exact entered date must be preserved, normalization can hide the error.

For example, two different questions are:

- "If we go past the start of February by 28 days, what date do we reach?"
- "Is 2023-02-29 a valid date?"

Lenient mode is useful for certain out-of-range value interpretations, but it does not by itself satisfy the goal of the second question.

## 2. What do lenient and non-lenient mean?

`Calendar` has a property that controls how fields are interpreted:

```java
calendar.setLenient(true);  // Allow normalization.
calendar.setLenient(false); // Reject inconsistent fields when computing the value.
```

`isLenient()` reads the current configuration. A newly created `GregorianCalendar` is in lenient mode by default, so it must be configured explicitly if the goal is strict validation.

In the modern examples in this article:

| Fields set | Lenient result in GregorianCalendar/UTC | If non-lenient when computed |
|---|---|---|
| Year 2023, month 2, day 29 | `2023-03-01` | Error |
| Year 2024, month 2, day 30 | `2024-03-01` | Error |
| Year 2023, month field 12, day 1 | `2024-01-01` | Error |
| Year 2023, month 1, day 0 | `2022-12-31` | Error |
| 2026-10-25, hour of day 25 | `2026-10-26T01:00` | Error |

The "month field 12" row must be read according to the `Calendar` convention: months are 0-based, so the value 12 goes past `DECEMBER == 11`, not the ordinary month 12 used by users.

The results are examples with `GregorianCalendar` and an explicitly set group of fields. Do not treat them as a universal formula for every `Calendar` implementation class, every conflicting field combination, or all historical data.

## 3. Calendar defers computation after set

`Calendar` maintains both the instant value and the calendar fields. `set(...)` may only update the fields and mark that recomputation is needed; it is not required to complete all checks immediately at the call site.

A typical flow:

```text
set fields
    |
    v
state needs recomputation
    |
    v
get / getTimeInMillis / getTime / related calculation
    |
    +--> normalize if lenient
    |
    +--> throw IllegalArgumentException if non-lenient and fields are invalid
```

Example:

```java
calendar.setLenient(false);
calendar.set(2023, Calendar.FEBRUARY, 29);
// The set call may not throw an error yet.
long millis = calendar.getTimeInMillis(); // Forces interpretation; invalid date is rejected.
```

This snippet illustrates the sequence and assumes the `calendar` variable has already been created appropriately. The complete program in Section 7 clarifies which calls succeed and which calls throw an exception.

If you want to use `Calendar` to validate legacy input, you must force computation inside an error-handling block. A function that only calls `set` and returns success may not have checked the condition you think it checked.

Also, do not call `get(...)` to print intermediate data before finishing setup and assume that operation is completely harmless: reading can trigger state normalization, affecting what subsequent `set` calls operate on.

## 4. Setting clean input to avoid depending on stale state

A `Calendar` is usually created with the current date and time. Setting only year/month/day does not necessarily clear existing hour, second, or millisecond fields.

A pattern used for independent validation examples:

```java
GregorianCalendar calendar = new GregorianCalendar(
        TimeZone.getTimeZone("UTC"), Locale.ROOT);
calendar.clear();
calendar.setLenient(false);
calendar.set(2024, Calendar.FEBRUARY, 29, 0, 0, 0);
calendar.getTimeInMillis();
```

`clear()` marks fields as unset; when computing, `GregorianCalendar` uses appropriate default values for missing fields. In this snippet, hour/minute/second are set explicitly and milliseconds default to 0, so no millisecond fraction from object creation remains.

`clear()` does not clear the chosen time zone or change the lenient mode on its own. Nor does it mean every configuration of `Calendar` is reset to the same global state; the purpose here is to remove leftover time fields before setting new data.

Choosing UTC keeps field-overflow examples from mixing with skipped/repeated hours caused by DST. For real features based on a specific zone, you need to select that zone and also test non-existent local date-time cases. Do not use UTC to silently alter the meaning of input that was actually user time in another zone.

### Using constant names for the month field

`Calendar.JANUARY` is 0, `Calendar.FEBRUARY` is 1, ..., `Calendar.DECEMBER` is 11. Using constants helps avoid mistakes when reading code.

If you receive months 1–12 from a UI, convert properly at the boundary and then validate. Do not treat lenient mode as a way to automatically fix forgetting to subtract 1: an off-by-one month can still produce a valid date, just in the wrong requested month.

## 5. After normalization, the original invalid fields are no longer preserved

Suppose you set 2023-02-29 in lenient mode and then call `toInstant()`. `Calendar` has already normalized it to 2023-03-01. If you only call `setLenient(false)` afterward, a subsequent read sees a valid date of 2023-03-01; it does not remember and reject the 02-29 fields that were set earlier.

Therefore, the correct sequence for rejecting invalid input is:

1. Create or prepare a clean state.
2. Select non-lenient before forcing computation from the input fields.
3. Set all required fields.
4. Force computation and handle errors.

Keep the original input data separately if you need to report errors or compare values. Do not take the normalized fields back out of `Calendar` and use them to prove that the original input was valid.

If you reuse a `Calendar` across multiple records, state left behind by an earlier error or read operation can be hard to track. Creating a local instance for a single validation is usually easier to reason about than sharing a mutable `Calendar`.

## 6. Per-field range is different from combination validity

Checking that `DAY_OF_MONTH` is within 1–31 is not enough. Day 31 can exist in January, but it does not exist in February.

Two calls return different information:

| Call | Meaning |
|---|---|
| `getMaximum(Calendar.DAY_OF_MONTH)` | The general maximum value the field can have in this calendar |
| `getActualMaximum(Calendar.DAY_OF_MONTH)` | The maximum value in the current context of the `Calendar` |

For February 2023, the general maximum is 31 while the actual maximum is 28. Querying the actual maximum also requires an interpretable day/month/year context; do not use it as a way to bypass validating the input combination as a whole.

`setLenient(false)` focuses on interpreting calendar fields, not a set of business rules. A real calendar date can still be disallowed because it falls outside an allowed time window. Conditions such as "end date is not before start date" must be checked separately after creating a valid value.

The `set`, `add`, and `roll` operations also have different contracts. Non-lenient does not mean every addition to a valid date must fail when month lengths differ; do not infer the behavior of `add` solely from examples that set an invalid combination of fields.

## 7. Complete runnable program

Save the following code to `CalendarLeniencyDemo.java`. The program uses Java 17 or later and requires no external libraries. It explicitly selects `GregorianCalendar`, UTC, and clears fields before setting data so that results do not depend on runtime.

```java
import java.util.Calendar;
import java.util.GregorianCalendar;
import java.util.Locale;
import java.util.TimeZone;

public class CalendarLeniencyDemo {
    private static GregorianCalendar calendar(boolean lenient) {
        GregorianCalendar result = new GregorianCalendar(
                TimeZone.getTimeZone("UTC"), Locale.ROOT);
        result.clear();
        result.setLenient(lenient);
        return result;
    }

    private static void show(String label, int year, int month, int day) {
        Calendar value = calendar(true);
        value.set(year, month, day, 0, 0, 0);
        System.out.println(label + "=" + value.toInstant());
    }

    public static void main(String[] args) {
        Calendar defaultCalendar = new GregorianCalendar(
                TimeZone.getTimeZone("UTC"), Locale.ROOT);
        System.out.println("defaultLenient=" + defaultCalendar.isLenient());

        show("nonLeapFeb29", 2023, Calendar.FEBRUARY, 29);
        show("leapFeb30", 2024, Calendar.FEBRUARY, 30);
        show("month12", 2023, 12, 1);
        show("januaryDayZero", 2023, Calendar.JANUARY, 0);

        Calendar hourOverflow = calendar(true);
        hourOverflow.set(2026, Calendar.OCTOBER, 25, 25, 0, 0);
        System.out.println("hour25=" + hourOverflow.toInstant());

        Calendar strict = calendar(false);
        strict.set(2023, Calendar.FEBRUARY, 29, 0, 0, 0);
        System.out.println("strictSet=accepted");
        try {
            strict.getTimeInMillis();
        } catch (IllegalArgumentException e) {
            System.out.println("strictRead=IllegalArgumentException");
        }

        Calendar lateSwitch = calendar(true);
        lateSwitch.set(2023, Calendar.FEBRUARY, 29, 0, 0, 0);
        System.out.println("normalized=" + lateSwitch.toInstant());
        lateSwitch.setLenient(false);
        System.out.println("strictAfterNormalization=" + lateSwitch.toInstant());

        Calendar february = calendar(false);
        february.set(2023, Calendar.FEBRUARY, 1, 0, 0, 0);
        System.out.println("genericMaximum="
                + february.getMaximum(Calendar.DAY_OF_MONTH));
        System.out.println("actualMaximum="
                + february.getActualMaximum(Calendar.DAY_OF_MONTH));

        Calendar validLeap = calendar(false);
        validLeap.set(2024, Calendar.FEBRUARY, 29, 0, 0, 0);
        System.out.println("strictValid=" + validLeap.toInstant());
    }
}
```

Compile and run:

```shell
javac CalendarLeniencyDemo.java
java CalendarLeniencyDemo
```

Expected output:

```text
defaultLenient=true
nonLeapFeb29=2023-03-01T00:00:00Z
leapFeb30=2024-03-01T00:00:00Z
month12=2024-01-01T00:00:00Z
januaryDayZero=2022-12-31T00:00:00Z
hour25=2026-10-26T01:00:00Z
strictSet=accepted
strictRead=IllegalArgumentException
normalized=2023-03-01T00:00:00Z
strictAfterNormalization=2023-03-01T00:00:00Z
genericMaximum=31
actualMaximum=28
strictValid=2024-02-29T00:00:00Z
```

`strictSet=accepted` describes that the `set` call completed; it does not mean the date was validated. As soon as `getTimeInMillis()` forces computation, the exception is thrown and the program prints the `strictRead` label.

The two lines `normalized` and `strictAfterNormalization` show that switching modes too late does not restore the input data as it was before normalization. The `strictValid` line confirms that non-lenient mode still accepts February 29 in a valid leap year.

The exception names in stdout are labels printed by the code when catching errors, not full JDK messages.

## 8. Relationship to modern parsing and migrating legacy code

`Calendar.setLenient(false)` does not mean every parser in the program has been configured. A `SimpleDateFormat` has its own leniency setting that must be checked on the right object; modern `DateTimeFormatter` uses `ResolverStyle` for the field-resolution step.

If the input is a `uuuu-MM-dd` string and the goal is a valid ISO date in new code, you can use:

```java
DateTimeFormatter strict = DateTimeFormatter
        .ofPattern("uuuu-MM-dd", Locale.ROOT)
        .withResolverStyle(ResolverStyle.STRICT);
LocalDate date = LocalDate.parse(text, strict);
```

This is an illustrative snippet; it requires `java.time`/`java.time.format` imports and a `text` variable. `LocalDate.of(year, month, day)` also directly validates an ISO date triplet when the data is already numeric.

Do not replace a lenient `Calendar` with strict parsing and assume behavior is always preserved: legacy code may have intentionally relied on normalization. Before migrating, decide whether that was behavior to keep or a bug to fix, and add tests for inputs that previously used to be adjusted.

For historical data, `GregorianCalendar` also has a Julian/Gregorian transition configuration, which differs from the proleptic ISO model of `LocalDate`. The examples in this article use modern dates; do not generalize field-conversion results to all past years without checking the calendar system.

## 9. Practice exercises

1. Set `2023, Calendar.APRIL, 31` in lenient mode and predict the result `2023-05-01`; retry in non-lenient mode and confirm the error occurs when computing.
2. For `2024, Calendar.JANUARY, 32`, explain why normalization moves to 2024-02-01 rather than simply changing the day field to 31.
3. Try taking user month input as the number `2` and passing it directly into the `MONTH` field. Recognize that `Calendar` interprets that as March; this is an input-convention bug that leniency will not fix to match the user's intent.
4. Change the order in the `lateSwitch` example so that non-lenient is selected before reading. Confirm that the `2023-02-29` fields are now rejected instead of already being normalized to `2023-03-01`.

References: [Calendar — leniency and setting/getting fields](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Calendar.html) and [GregorianCalendar](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/GregorianCalendar.html) in Java SE 21.