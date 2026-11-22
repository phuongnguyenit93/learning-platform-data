# Handling February 29 MonthDay When Binding a Year

## 1. A valid month/day pair may not exist in every year

`MonthDay.of(2, 29)` represents February 29 without a chosen year. This value is valid because some years contain that date. Once combined with a year, the result must be a `LocalDate` that actually exists.

These are two different questions:

- **Can the month/day pair exist?** `MonthDay` allows Feb 29, but does not allow Feb 30.
- **Does the month/day pair exist in the chosen year?** You need to know whether that year is a leap year.

The most common pitfall is assuming `atYear` always keeps the exact day or always throws an exception when it cannot. Its actual contract has a clear adjustment rule.

## 2. Default behavior of atYear

For a `MonthDay` of Feb 29:

| Call | Result |
| --- | --- |
| `atYear(2024)` | `2024-02-29` |
| `atYear(2023)` | `2023-02-28` |
| `atYear(2000)` | `2000-02-29` |
| `atYear(2100)` | `2100-02-28` |

`atYear` falls back to **February 28** if the year is not a leap year. It does not roll over to March 1, and it does not retain an invalid date inside `LocalDate`. The original `MonthDay` remains `--02-29`, because these values are immutable. [MonthDay.atYear](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/MonthDay.html#atYear(int))

If the business logic accepts the Feb 28 rule, you can use `atYear` directly. If the business logic requires preserving the exact day or skipping non-leap years, you must check and apply a different policy before converting.

## 3. isValidYear to check whether the month/day can be preserved

Illustration inside a method:

```java
MonthDay leapDay = MonthDay.of(2, 29);
boolean valid2024 = leapDay.isValidYear(2024); // true
boolean valid2023 = leapDay.isValidYear(2023); // false
```

Here `false` means that exact date Feb 29 does not exist in that year; it does not mean the `MonthDay` object is invalid. For an ordinary pair like Aug 15, whether a year is a leap year does not affect the date's existence.

You also need to validate the **year range** when accepting external input. Do not use `isValidYear` as a catch-all validator for the year parameter: it does not replace checking representation bounds. Use `Year.of(year)` or an appropriate date factory to verify that the year is within the supported range.

An ISO year is a leap year if it is divisible by 4, except years divisible by 100 that are not divisible by 400. Use `Year.isLeap(year)` instead of just writing `year % 4 == 0`. This explains why 2000 is a leap year while 2100 is not. [Year.isLeap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Year.html#isLeap(long))

## 4. Choosing a policy for years without Feb 29

| Policy | Date for year 2023 | Use when the intended meaning is |
| --- | --- | --- |
| Fall back to the last day of February | `2023-02-28` | Still have a representative date in February |
| Move to the first day of March | `2023-03-01` | Pick the day after Feb 28 |
| Skip non-leap years | No date for that year | The event only occurs on Feb 29 |
| Reject year binding | Report an error | Data must preserve the exact month/day pair |

This is a business choice; the library only provides the default behavior. Name the policy explicitly in code rather than forcing readers to infer it from adding or subtracting a day.

"Skip" differs from "reject": having no occurrence in a year can be a valid result for a recurring schedule, whereas a date input requirement that must preserve Feb 29 may need to fail immediately. `Optional<LocalDate>` represents absence more clearly than `null` or a silent substitute date.

## 5. Complete program with four policies

Save as `LeapDayBindingDemo.java`. The `bind` method accepts any `MonthDay`, but only applies the special policy when the month/day does not exist in the target year.

```java
import java.time.DateTimeException;
import java.time.LocalDate;
import java.time.MonthDay;
import java.time.Year;
import java.util.Objects;
import java.util.Optional;

public class LeapDayBindingDemo {
    enum MissingDatePolicy { FEBRUARY_28, MARCH_1, SKIP, REJECT }

    static Optional<LocalDate> bind(
            MonthDay value, int year, MissingDatePolicy policy) {
        Objects.requireNonNull(value, "value");
        Objects.requireNonNull(policy, "policy");
        Year.of(year);

        if (value.isValidYear(year)) {
            return Optional.of(value.atYear(year));
        }

        // Valid MonthDay that does not exist in the target year: only the Feb 29 case.
        return switch (policy) {
            case FEBRUARY_28 -> Optional.of(LocalDate.of(year, 2, 28));
            case MARCH_1 -> Optional.of(LocalDate.of(year, 3, 1));
            case SKIP -> Optional.empty();
            case REJECT -> throw new DateTimeException(
                    "Month/day does not exist in target year");
        };
    }

    public static void main(String[] args) {
        MonthDay leapDay = MonthDay.of(2, 29);

        System.out.println("default2023=" + leapDay.atYear(2023));
        System.out.println("default2024=" + leapDay.atYear(2024));
        System.out.println("leap2000=" + Year.isLeap(2000));
        System.out.println("leap2100=" + Year.isLeap(2100));
        System.out.println("valid2100=" + leapDay.isValidYear(2100));

        System.out.println("february="
                + bind(leapDay, 2023, MissingDatePolicy.FEBRUARY_28));
        System.out.println("march="
                + bind(leapDay, 2023, MissingDatePolicy.MARCH_1));
        System.out.println("skip="
                + bind(leapDay, 2023, MissingDatePolicy.SKIP));
        System.out.println("leapYear="
                + bind(leapDay, 2024, MissingDatePolicy.REJECT));
        System.out.println("ordinary="
                + bind(MonthDay.of(8, 15), 2023, MissingDatePolicy.SKIP));

        try {
            bind(leapDay, 2023, MissingDatePolicy.REJECT);
        } catch (DateTimeException ex) {
            System.out.println("rejected2023");
        }

        try {
            LocalDate.of(2023, 2, 29);
        } catch (DateTimeException ex) {
            System.out.println("strictConstructionRejected");
        }

        System.out.println("changedYear="
                + LocalDate.of(2024, 2, 29).withYear(2023));
        System.out.println("monthDayStill=" + leapDay);
    }
}
```

Compile and run with JDK 17 or later:

```shell
javac -encoding UTF-8 --release 17 LeapDayBindingDemo.java
java LeapDayBindingDemo
```

Exact stdout:

```text
default2023=2023-02-28
default2024=2024-02-29
leap2000=true
leap2100=false
valid2100=false
february=Optional[2023-02-28]
march=Optional[2023-03-01]
skip=Optional.empty
leapYear=Optional[2024-02-29]
ordinary=Optional[2023-08-15]
rejected2023
strictConstructionRejected
changedYear=2023-02-28
monthDayStill=--02-29
```

`Year.of(year)` runs before the policy check so that an out-of-range year is not treated as an occurrence to be skipped. Likewise, the `REJECT` branch does not reject every date: it only rejects when the specific date genuinely does not exist in the target year.

## 6. Strict date construction vs. adjusting an existing date

`LocalDate.of(2023, 2, 29)` constructs a specific date and must validate the full year/month/day; it throws `DateTimeException`. You can use this approach for strict binding:

```java
LocalDate exact = LocalDate.of(
        year, monthDay.getMonthValue(), monthDay.getDayOfMonth());
```

This is a snippet inside a method, with `year` and `monthDay` as inputs. If you want a custom business error message, check `isValidYear` first after validating the year range. [LocalDate.of](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDate.html#of(int,int,int))

By contrast, `LocalDate.of(2024, 2, 29).withYear(2023)` adjusts an existing date; it selects the last valid day of the month, which is Feb 28. Do not use `withYear` as a validation check for "must stay on Feb 29". [LocalDate.withYear](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDate.html#withYear(int))

This distinction helps avoid a subtle bug: invalid input data can be silently turned into a valid date if you choose the wrong adjustment API.

## 7. Preserving the original data when computing across multiple years

When generating annual occurrences, always bind again from the **original `MonthDay`** for each year. Do not use the adjusted result from a previous year as the source for subsequent years.

Example of a bug against intent: binding `--02-29` to 2023 yields `2023-02-28`, and then calling `withYear(2024)` on that result produces `2024-02-28`. The fact that "the original day was Feb 29" has been lost from the intermediate date. If you bind `MonthDay.of(2, 29).atYear(2024)` again, the result matching the original data is `2024-02-29`.

Once converted to `LocalDate`, calling `MonthDay.from(adjustedDate)` also only recovers Feb 28 from the adjusted date and has no way to know it used to be a Feb 29 event. Store the original rule separately from the resulting date of each occurrence.

With the `SKIP` policy, `Optional.empty()` only indicates that the queried year has no date; finding the next occurrence is a separate task that must inspect subsequent years. Do not assume the next leap year is always 4 years away, because of century exceptions.

## 8. Edge cases to test

- A normal leap year such as 2024 and a common year such as 2023.
- Century years: 2000 is a leap year, 2100 is not.
- A `MonthDay` other than Feb 29: every policy must preserve the month and day when bound.
- Years outside the supported range and `null` inputs: report an input error instead of silently turning them into a fallback date.
- Multi-year consecutive calculations from the original data, especially a leap year following a year that used Feb 28.

After binding, `LocalDate` is still just a date without a time of day or time zone. If you use the result to send reminders, add those rules in the scheduling step; the Feb 29 policy does not determine the delivery time.

## 9. Practice exercises

1. Print the result of `MonthDay.of(2, 29).atYear(2100)` and explain why there is no Feb 29.
2. Apply all four policies to `MonthDay.of(3, 15)` in year 2023.
3. Compare binding from the original `MonthDay` to 2024 with changing the year on the adjusted result from 2023.
4. Write a binding operation that throws an error instead of adjusting when a common year is chosen for Feb 29.

Check: (1) `2100-02-28`; 2100 is divisible by 100 but not by 400; (2) all yield `2023-03-15`; (3) Feb 29 and Feb 28, respectively; (4) use the `REJECT` policy or construct `LocalDate` directly from all three components.