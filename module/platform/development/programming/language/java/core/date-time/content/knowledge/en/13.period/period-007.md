# Calculating Age and Handling February 29 Birthdays in Java

Calculating age might seem as simple as subtracting the birth year from the current year, but that subtraction can be wrong before the birthday in the current year. The case of a **February 29** birthday requires an even clearer definition: in a non-leap year, February 29 does not exist, so is the birthday observed on February 28 or March 1?

In Java, you should use `LocalDate` to represent the birth date and the calculation date, and then apply a clear business rule. Do not calculate age by dividing elapsed milliseconds by the average number of seconds in a year, because leap years and calendar birthdays are not accurately represented that way.

## 1. Why Year Subtraction Is Not Enough

Suppose a person was born on `2000-06-20`. When calculating their age on `2025-01-10`, the subtraction `2025 - 2000 = 25`, but that person **has not yet reached their 25th birthday**. Their completed age on that date is 24.

The common calculation for a birth date other than February 29:

1. Compute the difference between the two years: `age = asOf.getYear() - birthDate.getYear()`.
2. Determine the birthday in the target year.
3. If the date being evaluated is still before the birthday in that year, subtract one from the age.

General formula:

```text
age = target year - birth year

if target date < birthday in that year:
    age = age - 1
```

Comparing the **full day/month/year** properly handles the case where this year's birthday is still ahead. However, to calculate accurately for someone born on February 29, you need to determine the substitute birthday in a non-leap year before applying step 3.

`LocalDate` is suitable because it holds a calendar date without time or time zone. Conventional age is the number of completed calendar years, not the number of elapsed 365-day cycles.

## 2. Leap Years and February 29

According to the ISO calendar used by `java.time`, a year is a leap year if:

- It is divisible by 4;
- except years divisible by 100 are not leap years;
- however, years divisible by 400 are leap years.

Therefore:

| Year | Leap Year? | Has February 29? |
| --- | --- | --- |
| 2024 | Yes | Yes |
| 2025 | No | No |
| 1900 | No | No |
| 2000 | Yes | Yes |
| 2100 | No | No |
| 2400 | Yes | Yes |

In Java, use `Year.isLeap(year)` instead of writing your own leap-year logic unless there is a special requirement. For example:

```java
System.out.println(Year.isLeap(2024)); // true
System.out.println(Year.isLeap(2025)); // false
System.out.println(Year.isLeap(2000)); // true
System.out.println(Year.isLeap(2100)); // false
```

The snippet requires `import java.time.Year;` and can be placed inside a `main` method. `LocalDate.of(2025, 2, 29)` will throw a `DateTimeException` because that date does not exist; Java does not automatically convert the birth date to February 28 or March 1. This policy must be defined by the application.

## 3. Choosing a Birthday Rule in Non-Leap Years

For someone born on `29/02` (February 29), two business rules are commonly used:

**Policy A — observed on February 28.** In a non-leap year, the substitute birthday is the last day of February. If the age calculation date is `28/02/2025`, a person born on `29/02/2000` has already increased in age under this policy.

**Policy B — observed on March 1.** In a non-leap year, the substitute birthday is the first day of March. On `28/02/2025`, that person still keeps their previous age; on `01/03/2025`, their age increases.

You should not silently pick one policy and apply it to every system. Legal applications, civil records, contracts, insurance, schools, and international business operations may have to follow regional rules or specific regulations. This article presents two common programming policies; the application must confirm the rule that fits its business domain.

Example for a person born on `2000-02-29`:

| Date Being Evaluated | Feb 28 Birthday Policy | Mar 1 Birthday Policy |
| --- | ---: | ---: |
| 2024-02-28 (leap year) | 23 | 23 |
| 2024-02-29 (leap year) | 24 | 24 |
| 2025-02-28 (non-leap year) | 25 | 24 |
| 2025-03-01 (non-leap year) | 25 | 25 |
| 2028-02-28 (leap year) | 27 | 27 |
| 2028-02-29 (leap year) | 28 | 28 |

The table assumes the person is alive and calculates age strictly by the stated calendar dates; the result columns show the number of completed years. For 2028, the actual birthday February 29 exists, so both policies produce the same result.

## 4. Building a Function to Find the Birthday in a Given Year

To avoid scattering February 29 logic across multiple places, create a single method that accepts the birth date, target year, and policy. If the birth date is not February 29, you can replace the year of the birth date to produce the corresponding month/day in the target year. Specifically for February 29 in a non-leap year, return the chosen conventional date.

An enum makes these business choices much more readable than a boolean value:

```java
enum LeapDayPolicy {
    FEBRUARY_28,
    MARCH_1
}
```

The enum can reside in the same Java file as the class containing the age calculation method (only one class should be `public` if saved in a simple single file).

Method to find the birthday anniversary:

```java
static LocalDate anniversaryInYear(
        LocalDate birthDate,
        int year,
        LeapDayPolicy policy) {

    boolean leapDayBirth = birthDate.getMonthValue() == 2
            && birthDate.getDayOfMonth() == 29;

    if (leapDayBirth && !Year.isLeap(year)) {
        return policy == LeapDayPolicy.FEBRUARY_28
                ? LocalDate.of(year, 2, 28)
                : LocalDate.of(year, 3, 1);
    }

    return birthDate.withYear(year);
}
```

The method requires `import java.time.*;`. For a birth date of `29/02` in a leap year, `withYear(year)` preserves February 29. For other birth dates, such as `31/05`, changing the year does not alter the month/day because that date is valid in every year. The special branch only needs to apply to February 29 in a non-leap year.

The method requires `year` to be within the year range supported by `LocalDate`. In applications with untrusted input, validate the target year and handle `DateTimeException` if the data is out of the valid range. The `policy` enum should also be ensured to be non-null.

## 5. Calculating Age on Any Date Using `LocalDate`

Once you know the valid birthday according to the policy in the target year, calculate the completed age:

```java
static int ageOn(
        LocalDate birthDate,
        LocalDate asOf,
        LeapDayPolicy policy) {

    if (asOf.isBefore(birthDate)) {
        throw new IllegalArgumentException(
                "Ngày tính tuổi phải bằng hoặc sau ngày sinh"
        );
    }

    int age = asOf.getYear() - birthDate.getYear();
    LocalDate anniversary =
            anniversaryInYear(birthDate, asOf.getYear(), policy);

    if (asOf.isBefore(anniversary)) {
        age--;
    }
    return age;
}
```

This is a method that shares the enum and `anniversaryInYear` function from the previous section; it is not a complete standalone program. It works as follows:

1. Reject a calculation date that is before the birth date. Without this check, year subtraction could return a negative or business-invalid result.
2. Provisionally compute the difference in calendar years.
3. Find the birthday anniversary in the target year, with the February 29 policy applied.
4. If the target date is still before the anniversary date, subtract one from the age; if it is on or after that date, keep the result.

**Boundary operator note:** use `asOf.isBefore(anniversary)`, not `!asOf.isAfter(anniversary)`, because the birthday itself is already the day the age increases. That is, under the March 1 policy, `2025-03-01` gives the new age without waiting until March 2.

## 6. Runnable Example on Java 17+

The complete example below lets you switch policies and test multiple dates, helping verify error-prone cases around February 28, February 29, and March 1.

Save as **`LeapDayAgeDemo.java`**:

```java
import java.time.LocalDate;
import java.time.Year;

public class LeapDayAgeDemo {
    enum LeapDayPolicy {
        FEBRUARY_28,
        MARCH_1
    }

    static LocalDate anniversaryInYear(
            LocalDate birthDate, int year, LeapDayPolicy policy) {

        boolean leapDayBirth = birthDate.getMonthValue() == 2
                && birthDate.getDayOfMonth() == 29;

        if (leapDayBirth && !Year.isLeap(year)) {
            return policy == LeapDayPolicy.FEBRUARY_28
                    ? LocalDate.of(year, 2, 28)
                    : LocalDate.of(year, 3, 1);
        }

        return birthDate.withYear(year);
    }

    static int ageOn(
            LocalDate birthDate,
            LocalDate asOf,
            LeapDayPolicy policy) {

        if (asOf.isBefore(birthDate)) {
            throw new IllegalArgumentException(
                    "asOf must be on or after birthDate"
            );
        }

        int age = asOf.getYear() - birthDate.getYear();
        LocalDate anniversary =
                anniversaryInYear(birthDate, asOf.getYear(), policy);

        if (asOf.isBefore(anniversary)) {
            age--;
        }
        return age;
    }

    public static void main(String[] args) {
        LocalDate birth = LocalDate.of(2000, 2, 29);

        System.out.println("Feb28 policy on Feb28 : "
                + ageOn(birth, LocalDate.of(2025, 2, 28),
                        LeapDayPolicy.FEBRUARY_28));
        System.out.println("Mar1 policy on Feb28  : "
                + ageOn(birth, LocalDate.of(2025, 2, 28),
                        LeapDayPolicy.MARCH_1));
        System.out.println("Mar1 policy on Mar1   : "
                + ageOn(birth, LocalDate.of(2025, 3, 1),
                        LeapDayPolicy.MARCH_1));
        System.out.println("Feb28 policy on leap day: "
                + ageOn(birth, LocalDate.of(2024, 2, 29),
                        LeapDayPolicy.FEBRUARY_28));
        System.out.println("Next leap anniversary : "
                + anniversaryInYear(birth, 2028, LeapDayPolicy.MARCH_1));
        System.out.println("ChronoUnit years      : "
                + java.time.temporal.ChronoUnit.YEARS.between(
                        birth, LocalDate.of(2025, 2, 28)));
    }
}
```

Compile and run with JDK 17+:

```bash
javac LeapDayAgeDemo.java
java LeapDayAgeDemo
```

Actual compiled/run output:

```text
Feb28 policy on Feb28 : 25
Mar1 policy on Feb28  : 24
Mar1 policy on Mar1   : 25
Feb28 policy on leap day: 24
Next leap anniversary : 2028-02-29
ChronoUnit years      : 24
```

Analysis:

- On `2025-02-28`, the `FEBRUARY_28` policy calculates age 25; the `MARCH_1` policy still gives 24.
- On `2025-03-01`, the `MARCH_1` policy also calculates age 25.
- Leap year 2024 has February 29, so on that date a person born on `2000-02-29` turns 24 under both policies.
- `anniversaryInYear` returns `2028-02-29` for the leap year; there is no need to convert the date to February 28 or March 1 when the actual birthday exists.
- `ChronoUnit.YEARS.between(birth, asOf)` returns 24 on `2025-02-28` in the example. That is a year difference according to `Temporal` rules, **and does not automatically apply the application's specific birthday policy**. If a consistent February 29 rule is needed, use an explicit business function.

## 7. Why Not Just Call `Period.between()` or `ChronoUnit.YEARS.between()`?

`Period.between(birthDate, asOf)` returns a `Period` consisting of years, months, and days between two `LocalDate` instances. `ChronoUnit.YEARS.between(birthDate, asOf)` returns the number of completed years according to the rules of the given dates. Both are useful for many general date-time operations; however, **they do not accept a business policy for "whether a February 29 birthday in a non-leap year is February 28 or March 1"**.

Example:

```java
LocalDate birth = LocalDate.of(2000, 2, 29);
LocalDate check = LocalDate.of(2025, 2, 28);

int years = (int) java.time.temporal.ChronoUnit.YEARS
        .between(birth, check);
// years = 24
```

If the business chooses `FEBRUARY_28`, the completed age on this date is 25; therefore, you cannot replace that policy with `between` without adjusting the rule. `Period` also returns months and days, which can be useful for elapsed time from a birth date to today, but legal/commercial age must still follow the policy the system needs to enforce.

A good design approach is to clearly separate:

- **Calendar interval**: `Period.between(...)`, when a breakdown of years/months/days is needed.
- **Completed years per `Temporal` rules**: `ChronoUnit.YEARS.between(...)` for standard needs.
- **Age by birth date with a specific February 29 policy**: `ageOn(...)` with `LeapDayPolicy`.

Do not write critical logic in a way that forces readers to guess how the default API handles February 29. Making the policy a parameter/enum makes the decision easy to review, test, and change.

## 8. Using "Today" in the Right Time Zone

`LocalDate.now()` uses the system's default time zone. If the server runs in UTC while the application serves users in Vietnam, times near midnight can cause "today" to differ from the date on the user's clock.

You should choose the zone based on the business context:

```java
ZoneId userZone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate todayForUser = LocalDate.now(userZone);

int userAge = ageOn(
        birthDate,
        todayForUser,
        LeapDayPolicy.FEBRUARY_28
);
```

This is a code snippet inside a method with `import java.time.*;` and the variables already declared. If age is calculated based on place of residence, place of transaction, or legal jurisdiction, obtain the `ZoneId` appropriate for that business domain. Do not assume the server's time zone is the user's time zone.

For testing, you can pass an explicit `asOf` date as in the `main` example instead of calling `LocalDate.now()`. This ensures tests run identically today, tomorrow, and in CI.

## 9. Invalid Birth Dates, Boundaries, and Input Validation

### A. Rejecting Future Birth Dates

`ageOn` should throw an error if `asOf.isBefore(birthDate)`. For applications receiving user input, validate at the request boundary and turn the error into a helpful message; do not silently return a negative age.

### B. When Is February 29 Valid?

`LocalDate.of(2000, 2, 29)` is valid; `LocalDate.of(1900, 2, 29)` and `LocalDate.of(2025, 2, 29)` are invalid in the ISO calendar. Java throws `DateTimeException` if you create a nonexistent date. You should not automatically "fix" an invalid birth date, because changing February 29 to February 28 alters personal data.

### C. Do Not Assume Only Two Policies Exist Everywhere

In general programming problems, the two options February 28 and March 1 are clear examples. If the business must comply with local laws, contracts, or specific regulations, verify the effective policy; do not treat this example enum as universal legal advice.

### D. Calendar Dates Differ from Exact Instants

Age by birth date is normally calculated from calendar dates, so `LocalDate` is appropriate. If a requirement demands instant-level precision (for example, a cutoff exactly 24 hours before the birth date), you must determine the time zone and instant before calculating. Do not divide a millisecond difference by an average year value to determine age, because year length is not fixed on the calendar.

## 10. Boundary Test Suite to Include

For a person born on `2000-02-29`, test both policies and the dates surrounding the birthday:

| Calculation Date | Feb 28 Policy | Mar 1 Policy | What It Proves |
| --- | ---: | ---: | --- |
| 2025-02-27 | 24 | 24 | Before both conventional dates. |
| 2025-02-28 | 25 | 24 | Difference between the two policies. |
| 2025-03-01 | 25 | 25 | Both have reached the conventional birthday. |
| 2024-02-28 | 23 | 23 | Leap year, not yet the birth date. |
| 2024-02-29 | 24 | 24 | Exact actual birthday in a leap year. |
| 2028-02-29 | 28 | 28 | A subsequent leap year. |

In addition, test someone born on a regular date such as `2000-06-20`: age before June 20 must be one less than age on June 20; leap years and non-leap years do not change the normal birthday rule. Testing a calculation date before the birth date must throw an error as designed.

When writing unit tests, pass fixed dates directly. There is no need for `Thread.sleep`, no need to mock a duration, and you should not depend on the machine's current date. If a function obtains today from a `Clock`, inject a fixed `Clock` so dates can be controlled in tests.

## 11. How to Apply This in Applications

- **User profiles:** store the birth date using `LocalDate`, because a birth date does not need hours/minutes.
- **Calculating age displayed on profiles:** pass today's date in the product's or user's time zone, applying the finalized February 29 policy.
- **Calculating age in critical workflows:** document the source of the rule (local/legal/contractual) and write boundary tests for February 28, February 29, and March 1.
- **Reports with a fixed cutoff date:** use `ageOn(birthDate, reportingDate, policy)`. Do not call "today" internally if the report needs reproducible results.
- **APIs:** represent the birth date as an ISO string `YYYY-MM-DD` or an equivalent date-without-time type; do not force a birth date into a timestamp with a time zone if that has no meaning.
- **Databases:** a `DATE` column is usually more suitable than a timestamp with a time-of-day; mapping configuration should follow the actual driver and DBMS.

Name the parameter `asOf` or `calculationDate`, rather than an ambiguous name like `now` if the value is actually a user-selected reporting date. This clearly indicates that the age calculation function can be used for past, present, or scheduled future dates.

## 12. Common Mistakes

1. **Only subtracting the birth year from the current year.** The result is wrong when this year's birthday has not yet arrived.
2. **Ignoring February 29 in non-leap years.** A clear convention is required before calculating age.
3. **Automatically using February 28 or March 1 without confirming requirements.** The two rules can produce different ages on February 28.
4. **Trying to create `LocalDate.of(year, 2, 29)` in every year.** Non-leap years will throw `DateTimeException`; use `Year.isLeap(year)` to choose the branch.
5. **Using `ChronoUnit.YEARS.between` as the sole rule for all business cases.** The API does not know the February 29 policy the product requires.
6. **Using `Duration` or milliseconds and dividing into years.** A calendar year is not a fixed number of seconds; age is a calendar concept.
7. **Using the server's default time zone for "today".** The date can differ near midnight between the server and the user; pass the appropriate `ZoneId`.
8. **Not checking for a calculation date before the birth date.** Without defining this case, the function can produce negative ages or business-invalid results.
9. **Calling a method without saving its return value.** `LocalDate` is immutable; calendar addition/subtraction operations return a new object.
10. **Not testing boundary dates.** Age bugs usually occur on the day right before, the exact day of, and the day right after the birthday.

## 13. Self-Check

**Question 1.** A person was born on `2000-06-20`, and age is calculated on `2025-01-10`. Why is it not 25?

**Answer:** Because the 25th birthday has not yet arrived in 2025; the completed age is still 24.

**Question 2.** For a person born on `2000-02-29`, on `2025-02-28`, what two results can the February 28 and March 1 policies give?

**Answer:** The February 28 policy returns 25; the March 1 policy returns 24.

**Question 3.** Should `LocalDate.of(2025, 2, 29)` be used to represent a birthday in a non-leap year?

**Answer:** No. That date does not exist in the ISO calendar and Java throws `DateTimeException`. Construct the anniversary date according to the policy.

**Question 4.** Why is `Year.isLeap(2100)` false, while `Year.isLeap(2000)` is true?

**Answer:** Years divisible by 100 are not leap years, unless they are also divisible by 400.

**Question 5.** Can age be calculated on a fixed reporting date?

**Answer:** Yes. Pass the reporting `LocalDate` as `asOf` to the function; the result is reproducible and does not depend on the system date.

**Question 6.** If the system runs on a UTC server and users are in Vietnam, how should the current date be obtained for the UI?

**Answer:** Choose `ZoneId.of("Asia/Ho_Chi_Minh")` and call `LocalDate.now(zone)` when the product rule requires the local date in Vietnam.

## Key Takeaways

**Calculate age using calendar dates, not millisecond division.** Take the difference of the two years, determine the birthday in the target year, and subtract one if the calculation date is still before the birthday. For someone born on **February 29**, define the non-leap-year birthday policy as **February 28** or **March 1** according to business requirements, encode the choice explicitly, and test on both boundary dates. Use `LocalDate`, `Year.isLeap`, and an explicit `asOf` date so the result is accurate, easy to test, and independent of the server's default time zone.
