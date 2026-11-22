# Getting Numeric Values and Display Names by Locale

## 1. One Value, Multiple Representations

For the date `2024-03-18`, we may need:

- Month number `3` to pass data according to a contract.
- The constant `Month.MARCH` to write clear, self-explanatory conditions.
- The label `March` for an English UI.
- The label `tháng 3` for a Vietnamese UI.
- The ISO day-of-week number `1` and the label `Thứ Hai` for display.

These representations serve different purposes. **Business values** should be kept in an appropriate type or as numbers following a clear convention. **Display names** are produced at the presentation layer based on language and context.

`Locale` selects the language/region used to obtain labels. It does not change March into another month, nor does it change Monday's ISO number from `1` to another number.

In this lesson, the examples use the ISO calendar of `java.time`, focusing on `Month` and `DayOfWeek`. Part-based types such as `Year`, `YearMonth`, and `MonthDay` also have corresponding numeric getter methods, though not all of them have a `getDisplayName` method.

## 2. Reading Numbers with Business-Meaningful Methods

### 2.1. Month: Months from 1 to 12

[Month](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Month.html) is an enum representing the 12 months. The standard number is obtained via `getValue()`:

| Constant | `getValue()` |
| --- | --- |
| `Month.JANUARY` | `1` |
| `Month.MARCH` | `3` |
| `Month.DECEMBER` | `12` |

Convert from a number to the enum using `Month.of(number)`. Values outside `1..12`, such as `0` or `13`, throw `DateTimeException`; the method does not wrap numbers into a valid month.

If you already have a date or period, you can read it directly:

```java
LocalDate date = LocalDate.of(2024, 3, 18);

Month month = date.getMonth();          // MARCH
int monthNumber = date.getMonthValue(); // 3

YearMonth period = YearMonth.from(date);
int periodMonth = period.getMonthValue(); // 3
```

In business code, `Month.MARCH` usually conveys meaning more clearly than a standalone number `3`. When communicating with a system that uses month numbers, `getValue()` converts according to the known convention.

### 2.2. DayOfWeek: Monday is 1, Sunday is 7

[DayOfWeek](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/DayOfWeek.html) uses ISO numbers:

| Constant | `getValue()` |
| --- | --- |
| `MONDAY` | `1` |
| `TUESDAY` | `2` |
| `WEDNESDAY` | `3` |
| `THURSDAY` | `4` |
| `FRIDAY` | `5` |
| `SATURDAY` | `6` |
| `SUNDAY` | `7` |

`DayOfWeek.of(1)` is `MONDAY`, not Sunday. Numbers outside `1..7` are rejected.

A locale may have a different convention for the first day of the week, but `DayOfWeek.getValue()` still uses ISO. Changing the locale of labels does not change this numbering rule. If you need to number days of the week according to a local week definition, that is a separate requirement where `WeekFields` can be considered; do not alter the meaning of `getValue()`.

When transferring data from legacy APIs or external systems, check the contract. For example, `Calendar.DAY_OF_WEEK` in the legacy API uses Sunday as `1`, which differs from `DayOfWeek`. Do not pass numbers from both systems directly into the same function assuming they are equivalent.

### 2.3. Year and Other Date Parts

Some common getters:

| Type | Method | Meaning |
| --- | --- | --- |
| `Year` | `getValue()` | Year value |
| `YearMonth` | `getYear()` | Year of the period |
| `YearMonth` | `getMonthValue()` | Month number `1..12` |
| `MonthDay` | `getMonthValue()` | Month number `1..12` |
| `MonthDay` | `getDayOfMonth()` | Day of the month |
| `LocalDate` | `getDayOfWeek()` | Day-of-week enum |

Do not see the name `getValue` and assume every type uses `1..12`. The domain and meaning always depend on the type being read.

## 3. ordinal() Is the Enum Position, Not the Calendar Number

`ordinal()` is the declaration position of the enum constant, starting from `0`:

```java
Month.MARCH.getValue();       // 3
Month.MARCH.ordinal();        // 2

DayOfWeek.MONDAY.getValue();  // 1
DayOfWeek.MONDAY.ordinal();   // 0
```

The `Month` and `DayOfWeek` APIs require using `getValue()` for the business numeric representation. Even though `ordinal() + 1` happens to match the standard number for these enums, using `getValue()` directly properly expresses the contract.

`name()` and `toString()` on these two enums are not language translation services either:

```java
Month.MARCH.name();      // MARCH
DayOfWeek.MONDAY.name(); // MONDAY
```

These are constant names in code. Lowercasing them only produces `march` or `monday`, not Vietnamese names. Do not build a multilingual UI using `name().toLowerCase(...)`.

If you need a `0`-based position for an internal array, explicitly indicate that you are converting to an array index, such as `month.getValue() - 1`. Do not pass that index into an API or stored data and call it a "month number".

## 4. Getting Display Names with getDisplayName()

Both `Month` and `DayOfWeek` have:

```java
String getDisplayName(TextStyle style, Locale locale);
```

Example:

```java
Locale vi = Locale.forLanguageTag("vi-VN");

String monthLabel =
        Month.MARCH.getDisplayName(TextStyle.FULL, vi);
String dayLabel =
        DayOfWeek.MONDAY.getDisplayName(TextStyle.FULL, vi);
```

`Locale.forLanguageTag("vi-VN")` selects Vietnamese in Vietnam. `Locale.ENGLISH` selects English. For cases requiring regional distinction, you can use a specific locale such as `en-US` or `en-GB` instead of just the language.

`Locale` is not `ZoneId`. It controls text formatting/representation, not converting date-time to another time zone. To get the month name of an instant in a business region, you must first convert that instant to that zone to obtain the date/month, and only then generate the label.

Do not implicitly rely on `Locale.getDefault()` if the UI already has a user language selection. The server environment and the user may use two different locales.

The `style` and `locale` inputs must be valid values; `null` does not mean "just use the default" in the contract of these calls. Nor should you assume every locale always has its own text mapping: the API may return a numeric representation when a corresponding name cannot be found.

## 5. TextStyle: Length and Usage Context

[TextStyle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/TextStyle.html) has three length levels, each with a normal form and a standalone form:

| Normal Form | Standalone Form | Purpose |
| --- | --- | --- |
| `FULL` | `FULL_STANDALONE` | Full name |
| `SHORT` | `SHORT_STANDALONE` | Abbreviated name |
| `NARROW` | `NARROW_STANDALONE` | Very short name for tight spaces |

### 5.1. FULL, SHORT, and NARROW Are Not String-Truncation Rules

In typical English data:

- `Month.MARCH` with `FULL` is `March`.
- With `SHORT` it is `Mar`.
- With `NARROW` it is `M`.

`SHORT` does not guarantee exactly three characters for every language. `NARROW` also does not guarantee a single Java character or a fixed display width across all writing systems.

Do not take `fullName.substring(0, 3)` yourself to create an abbreviation. Abbreviations belong to language data, not a universal text-slicing operation. With Unicode text, arbitrary slicing can also corrupt display units or split characters improperly.

Choose `TextStyle` based on UI space and semantics, then check the actual labels in supported locales. Long labels in Vietnamese do not necessarily have the same length as English labels.

### 5.2. NARROW Can Collide

Narrow names are designed for tight spaces, not as identifiers. In English, January and June can both display as `J`; July can also collide.

Therefore:

- Do not use `NARROW` names as keys in a `Map` to identify months.
- Do not send narrow names as the unique value of a selection.
- If the UI displays only a single letter, provide additional context or a full name for accessibility descriptions.

Two identical labels do not make two months equal. The `Month` value or standard number still distinguishes them.

### 5.3. STANDALONE Is the Independent Form, Not a Different Font Style

Some languages change the form of a month name when it appears within a full date compared to when it stands alone as a heading or selection item. English usually does not show a difference, so if you only test with English, you might think the two forms are always identical.

For example, with Russian data in the verification environment:

- `Month.MARCH.getDisplayName(TextStyle.FULL, ru)` yields `марта`, the form tied to a date context.
- `Month.MARCH.getDisplayName(TextStyle.FULL_STANDALONE, ru)` yields `март`, the standalone form.

That is a linguistic difference, not a request to change uppercase, bold, or font size. For a month picker list or a standalone month heading, the `STANDALONE` form may be more appropriate. When formatting a full date, let the date formatter apply the appropriate context.

`TextStyle.FULL.asStandalone()` returns the standalone form at the same length level; `asNormal()` converts back to the normal form. These methods do not translate an already-created string; they select the style used when retrieving the label.

## 6. Complete Java 17+ Program

Save as `DatePartDisplayDemo.java`:

```java
import java.time.DateTimeException;
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.Month;
import java.time.Year;
import java.time.YearMonth;
import java.time.format.TextStyle;
import java.util.Locale;

public class DatePartDisplayDemo {
    static void invalid(String label, Runnable operation) {
        try {
            operation.run();
        } catch (DateTimeException ex) {
            System.out.println(label + " -> "
                    + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2024, 3, 18);
        Month month = date.getMonth();
        DayOfWeek day = date.getDayOfWeek();
        Locale vi = Locale.forLanguageTag("vi-VN");

        System.out.println("month value = " + month.getValue());
        System.out.println("month ordinal = " + month.ordinal());
        System.out.println("month enum name = " + month.name());
        System.out.println("date month value = " + date.getMonthValue());
        System.out.println("year-month value = "
                + YearMonth.from(date).getMonthValue());
        System.out.println("year value = " + Year.from(date).getValue());

        System.out.println("day value = " + day.getValue());
        System.out.println("day ordinal = " + day.ordinal());
        System.out.println("month of 3 = " + Month.of(3));
        System.out.println("day of 1 = " + DayOfWeek.of(1));

        System.out.println("month en full = "
                + month.getDisplayName(TextStyle.FULL, Locale.ENGLISH));
        System.out.println("month en short = "
                + month.getDisplayName(TextStyle.SHORT, Locale.ENGLISH));
        System.out.println("month en narrow = "
                + month.getDisplayName(TextStyle.NARROW, Locale.ENGLISH));
        System.out.println("month vi full = "
                + month.getDisplayName(TextStyle.FULL, vi));
        System.out.println("day vi full = "
                + day.getDisplayName(TextStyle.FULL, vi));
        System.out.println("day en full = "
                + day.getDisplayName(TextStyle.FULL, Locale.ENGLISH));
        System.out.println("day en short = "
                + day.getDisplayName(TextStyle.SHORT, Locale.ENGLISH));

        Locale ru = Locale.forLanguageTag("ru");
        System.out.println("month ru contextual = "
                + month.getDisplayName(TextStyle.FULL, ru));
        System.out.println("month ru standalone = "
                + month.getDisplayName(TextStyle.FULL_STANDALONE, ru));

        String january = Month.JANUARY.getDisplayName(
                TextStyle.NARROW, Locale.ENGLISH);
        String june = Month.JUNE.getDisplayName(
                TextStyle.NARROW, Locale.ENGLISH);
        System.out.println("January narrow = " + january);
        System.out.println("June narrow = " + june);
        System.out.println("narrow collision = " + january.equals(june));

        invalid("month zero", () -> Month.of(0));
        invalid("day eight", () -> DayOfWeek.of(8));
        System.out.println("original date = " + date);
    }
}
```

Compile and run:

```shell
javac --release 17 DatePartDisplayDemo.java
java DatePartDisplayDemo
```

The following stdout was verified on OpenJDK 24 with that environment's locale data. The code only uses Java 17-compatible APIs:

```text
month value = 3
month ordinal = 2
month enum name = MARCH
date month value = 3
year-month value = 3
year value = 2024
day value = 1
day ordinal = 0
month of 3 = MARCH
day of 1 = MONDAY
month en full = March
month en short = Mar
month en narrow = M
month vi full = tháng 3
day vi full = Thứ Hai
day en full = Monday
day en short = Mon
month ru contextual = марта
month ru standalone = март
January narrow = J
June narrow = J
narrow collision = true
month zero -> DateTimeException
day eight -> DateTimeException
original date = 2024-03-18
```

The numeric values following the ISO contract are the stable part of the example. Local name spelling, punctuation, or abbreviations may vary depending on locale data and Java runtime version. When running on another JDK, label differences should be examined in terms of language data, rather than concluding that calendar calculations are wrong.

If the terminal shows boxes or garbled characters on the Vietnamese/Russian lines, check the output encoding and terminal font. That is not evidence that `getValue()` or the month/day-of-week determination rules have changed.

## 7. Separating Stored Values from UI Labels

A month selection item can look like:

```java
record MonthOption(int value, String label) {}
```

This is an illustrative record for UI data. `value` holds the standard month number, while `label` is the name according to the selected language and display style.

Example of building a list, assuming `locale` and the corresponding imports are already present:

```java
List<MonthOption> options = Arrays.stream(Month.values())
        .map(month -> new MonthOption(
                month.getValue(),
                month.getDisplayName(
                        TextStyle.FULL_STANDALONE, locale)))
        .toList();
```

`java.util.List` and `java.util.Arrays` are needed for this snippet. The code builds the list in month order; it does not sort alphabetically by label.

When switching language from VI to EN, regenerate the labels for the new locale while keeping `value`. Selecting March is still March; it should not lose the selection just because the text `tháng 3` changes to `March`.

For APIs or stored data:

- Use month numbers `1..12` if the contract chooses numbers.
- Use enum codes if the contract explicitly publishes those codes.
- Use `YearMonth` or a year-month representation when you need to identify a specific period, not just the month of the year.
- Do not use translated labels as long-term identifiers.

If caching labels, the key must reflect the value, `TextStyle`, and `Locale`. Using only the month number as the key will cause Vietnamese labels to be mistakenly reused for English users or vice versa.

## 8. When You Need to Format a Full Date

`getDisplayName` is suitable when retrieving only the month name or day-of-week name. When you want a string containing day of week, day of month, month, and year, use `DateTimeFormatter` so the components are formatted together in context.

Illustrative example using the already-declared `date` and `vi`:

```java
DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern("EEEE, d MMMM uuuu", vi);
String formattedDate = date.format(formatter);
```

This snippet requires `java.time.format.DateTimeFormatter`. Important pattern symbols:

| Symbol | Role |
| --- | --- |
| `EEEE` | Full day-of-week name |
| `d` | Day of month |
| `MMMM` | Full month name in formatting context |
| `LLLL` | Full month name in standalone form |
| `uuuu` | Proleptic year |

Do not concatenate `getDisplayName(FULL_STANDALONE, ...)` into every date string assuming it is grammatically correct for all languages. The standalone form is useful in separate headings, whereas a full date has a different context.

Concatenating strings according to a fixed pattern is also different from choosing day/month ordering based on regional conventions. When an application needs full localized date formatting, you can use `DateTimeFormatter`'s localized formatting capabilities; that is a further presentation step that does not alter the underlying date data.

## 9. Standard Numbers, Display Order, and First Day of the Week

A UI calendar might want to start on Sunday. That does not change `DayOfWeek.SUNDAY.getValue()` from `7` to `1`.

There are three separate decisions:

1. The numeric value of the day of the week according to ISO.
2. The column ordering in the UI.
3. The display name of each column according to the locale.

To arrange columns starting from a chosen first day of the week, you can iterate seven times using `DayOfWeek.plus` and generate the label for each day:

```java
DayOfWeek firstDay = DayOfWeek.SUNDAY;

for (int index = 0; index < 7; index++) {
    DayOfWeek day = firstDay.plus(index);
    String label = day.getDisplayName(TextStyle.SHORT, locale);
    // Use day.getValue() as the ISO value, label for display.
}
```

This is an illustrative snippet showing how to organize it, with `locale` chosen beforehand. The first column is Sunday, yet the ISO value of that column is still `7`. If receiving the first day of the week from regional configuration, determine that configuration separately rather than inferring it from label names.

Similarly, changing the UI language does not automatically determine that Saturday or Sunday is a non-working day. A work schedule is a separate business policy; display names do not contain holiday/weekend rules.

## 10. Common Mistakes

| Mistake | Consequence | Proper Approach |
| --- | --- | --- |
| Using `ordinal()` as the month number | January becomes 0 | Use `getValue()` |
| Treating `DayOfWeek.of(1)` as Sunday | Wrong day of week | Read the ISO convention clearly |
| Passing `Calendar.DAY_OF_WEEK` numbers directly to `DayOfWeek.of` | Mixing numbering conventions | Convert intentionally |
| Using `name()` as a translated label | Only shows English constant names | Use `getDisplayName` |
| Slicing three characters from the full name for an abbreviation | Wrong for other languages or Unicode | Choose `TextStyle.SHORT` |
| Using `NARROW` as a unique code | Month labels can collide | Keep the enum or standard number |
| Using the machine's default locale for all users | Wrong UI language | Pass the user's locale |
| Treating locale as a time zone | Getting the wrong day/month near boundaries | Choose zone first, locale second |
| Using the standalone form in every context | Can be grammatically wrong | Choose the form based on usage |
| Storing labels instead of month data | Hard to switch languages and compare | Separate `value` from `label` |

## 11. Self-Check and Practice

1. Iterate through `Month.values()` and print `getValue()`. Verify all numbers `1..12` are present, with no `0`.
2. Iterate through `DayOfWeek.values()`. Confirm Monday is `1`, Sunday is `7`, and the values do not change when only changing the label's locale.
3. Compare `name()`, `getDisplayName(FULL, vi)`, and `getDisplayName(FULL, Locale.ENGLISH)` for the same month.
4. Create a list of 12 options with standard numbers and labels. Switch the language while preserving the selected item.
5. Find colliding `NARROW` labels in English. Explain why narrow labels are still useful in a calendar that already has context, but unsuitable as identifiers.
6. Compare `FULL` and `FULL_STANDALONE` with English and then with Russian. Note that having the two forms match in one locale does not prove they match in all locales.
7. Test `Month.of(0)`, `Month.of(13)`, and `DayOfWeek.of(8)`. Invalid inputs must report an error instead of auto-correcting.
8. Generate column ordering starting from Sunday while keeping each column's ISO number. Do not replace `getValue()` with the column index.
9. If a system receives an `Instant`, describe the two steps needed before displaying the month name to the user: choose the zone to determine the month, then choose the locale to get the label.
10. Design verification: strictly assert numeric values according to the contract; only compare exact localized labels when the target locale data environment is fixed.

Once standard numbers, enum constants, and locale-based labels are separated, a program can switch languages or presentation styles while preserving the exact meaning of the date.
