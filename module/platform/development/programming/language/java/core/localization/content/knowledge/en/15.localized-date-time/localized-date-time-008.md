# Month Names, Day Names, Day Periods, and TextStyle in Java

When displaying dates and times to users, a Java program does more than turn **28/10/2026** into a string of digits. The UI also needs **month names** (tháng Mười, October), **weekday names** (thứ Tư, Wednesday), **day periods** (AM/PM or morning, afternoon, evening), and how those names change by language, position in a sentence, label length, and locale data. In Java 17+, the primary APIs are **java.time.Month**, **java.time.DayOfWeek**, **java.time.format.TextStyle**, **DateTimeFormatter**, **DateTimeFormatterBuilder**, and **ChronoField**.

Key point: **TextStyle is not a CSS or JavaFX font style**. It is an enum describing the **textual form of a temporal value**: full, short, narrow, and standalone variants. Choosing the right `Locale` together with the right `TextStyle` makes dates and times read naturally and avoids implicitly depending on the server's language.

## 1. Which Date/Time Components Need Localization?

Consider the date-time **28/10/2026** at **09:30**. The data consists of typed values:

- **Month.OCTOBER**: the 10th month in the ISO calendar.
- **DayOfWeek.WEDNESDAY**: Wednesday, ISO value 3 (Monday = 1).
- **LocalDate.of(2026, 10, 28)**: a calendar date, with no time zone.
- **LocalTime.of(9, 30)**: local time 09:30, not bound to a date or time zone.
- **ChronoField.AMPM_OF_DAY**: half-day period, **0** for AM and **1** for PM.

With the same data, an English UI might display **Wednesday, October 28, 2026 at 9:30 AM**. A Vietnamese UI can use different weekday names, month names, and time labels. Characters, abbreviations, component ordering, and prepositions depend on the locale and pattern.

**Distinguish three layers:**

| Layer | Representation | Responsibility |
| --- | --- | --- |
| Date/time data | `LocalDate`, `LocalTime`, `LocalDateTime`, `ZonedDateTime` | Typed temporal values |
| Names and linguistic rules | `Locale`, `TextStyle`, JDK CLDR data | Month names, weekday names, day periods |
| Sentence assembly | `DateTimeFormatter` patterns, `ResourceBundle` translations | Component ordering, connectors, punctuation |

**Locale** does not select a time zone automatically, nor does it determine the language of fixed literal text you write inside a pattern.

## 2. What Is TextStyle?

**java.time.format.TextStyle** has six constants:

| TextStyle | Meaning | When to consider |
| --- | --- | --- |
| **FULL** | Full name in formatting context | Day/month inside a sentence or full date |
| **SHORT** | Abbreviated name in formatting context | Shorter labels, lists, charts |
| **NARROW** | Very short form in formatting context | Extremely narrow calendar cells where ambiguity is acceptable |
| **FULL_STANDALONE** | Full name when standing alone | Month header or standalone label |
| **SHORT_STANDALONE** | Short form when standing alone | Self-contained standalone label |
| **NARROW_STANDALONE** | Narrow form when standing alone | Standalone calendar label with very little space |

Java also provides **TextStyle.isStandalone()** to query whether a style belongs to the standalone group, and **TextStyle.asStandalone()** or **TextStyle.asNormal()** to convert between the two groups.

**FULL differs from FULL_STANDALONE in grammatical context**, not merely length. Some languages inflect month names depending on whether they appear with a day or stand alone. For example, in Russian, the spelling of a month name next to a day can differ from the month name used as a heading. Languages without that distinction may return the same string for both styles. Do not assume every locale has six distinct strings.

**NARROW is not guaranteed to be unique.** Multiple months or weekdays can start with the same letter, so narrow forms are often insufficient for users to distinguish without extra context. For accessible calendars, provide a full label alongside or in an accessibility attribute.

## 3. Getting Month Names with Month.getDisplayName

**Month** is a Java Time enum:

~~~java
import java.time.Month;
import java.time.format.TextStyle;
import java.util.Locale;

public class MonthNameDemo {
    public static void main(String[] args) {
        Month month = Month.OCTOBER;

        System.out.println(
                month.getDisplayName(TextStyle.FULL, Locale.US));
        System.out.println(
                month.getDisplayName(TextStyle.SHORT, Locale.US));
        System.out.println(
                month.getDisplayName(
                        TextStyle.FULL_STANDALONE, Locale.US));
    }
}
~~~

Save as **MonthNameDemo.java** and run with Java 17+:

~~~bash
javac -encoding UTF-8 MonthNameDemo.java
java MonthNameDemo
~~~

With standard JDK 17 US English locale data, the corresponding names are **October**, **Oct**, and **October**. The same word appears for `FULL` and `FULL_STANDALONE` because English does not inflect months here. In languages with grammatical inflection, the returned strings can differ.

**getDisplayName(style, locale)** fetches the name for the style and locale you specify. You do not need to call **Locale.setDefault()** to switch languages. The `Month` value remains October even as the display string changes.

Example exploring Vietnamese and Russian:

~~~java
Month october = Month.OCTOBER;

Locale vi = Locale.forLanguageTag("vi-VN");
Locale ru = Locale.forLanguageTag("ru-RU");

System.out.println(
        october.getDisplayName(TextStyle.FULL, vi));
System.out.println(
        october.getDisplayName(TextStyle.FULL_STANDALONE, ru));
~~~

This is an illustrative snippet inside a method, requiring imports for **Month**, **TextStyle**, and **Locale**. The exact text depends on the runtime's locale data. Do not assume Vietnamese month names always have a single capitalization, or that all JDKs share identical Russian inflection forms in every style.

## 4. Getting Day-of-Week Names with DayOfWeek

Like `Month`, **DayOfWeek** provides:

~~~java
DayOfWeek day = DayOfWeek.WEDNESDAY;
String label = day.getDisplayName(
        TextStyle.FULL, Locale.US);
~~~

This snippet requires importing **java.time.DayOfWeek**, **java.time.format.TextStyle**, and **java.util.Locale**; **label** is the English name for Wednesday (**Wednesday**).

The `DayOfWeek` constants are defined from **MONDAY** to **SUNDAY**, regardless of locale:

~~~text
MONDAY.getValue() = 1
TUESDAY.getValue() = 2
WEDNESDAY.getValue() = 3
THURSDAY.getValue() = 4
FRIDAY.getValue() = 5
SATURDAY.getValue() = 6
SUNDAY.getValue() = 7
~~~

**getValue() is always ISO-8601**; it does not change to Sunday = 1 just because `en-US` is used. Locale affects the day's name, whereas **the local calendar's first day of the week** is a separate decision, available via **WeekFields.of(locale).getFirstDayOfWeek()**.

Example:

~~~java
import java.time.DayOfWeek;
import java.time.temporal.WeekFields;
import java.util.Locale;

public class WeekStartDemo {
    public static void main(String[] args) {
        System.out.println(
                DayOfWeek.WEDNESDAY.getValue());

        System.out.println(
                WeekFields.ISO.getFirstDayOfWeek());

        System.out.println(
                WeekFields.of(Locale.US).getFirstDayOfWeek());
    }
}
~~~

Run **javac WeekStartDemo.java** and **java WeekStartDemo**. Stdout:

~~~text
3
MONDAY
SUNDAY
~~~

This experiment shows that **Wednesday's ISO value remains 3**, while the US locale's week model puts Sunday at the start of the week. Do not use **getDisplayName** or **getValue** to deduce calendar column order; use `WeekFields` or product policy.

## 5. Complete Example: Month Name, Weekday Name, and AM/PM

This example uses fixed data and an explicit **Locale.US** for easy observation. It does not depend on the machine's default locale.

**File MonthDayPeriodDemo.java**

~~~java
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.time.format.TextStyle;
import java.util.Locale;

public class MonthDayPeriodDemo {
    public static void main(String[] args) {
        Locale locale = Locale.US;
        LocalDate date = LocalDate.of(2026, 10, 28);
        LocalTime morning = LocalTime.of(9, 30);
        LocalTime evening = LocalTime.of(21, 30);

        System.out.println("month="
                + date.getMonth()
                      .getDisplayName(TextStyle.FULL, locale));
        System.out.println("weekday="
                + date.getDayOfWeek()
                      .getDisplayName(TextStyle.FULL, locale));

        DateTimeFormatter amPm =
                DateTimeFormatter.ofPattern("a", locale);

        System.out.println("morning=" + amPm.format(morning));
        System.out.println("evening=" + amPm.format(evening));

        DateTimeFormatter full = DateTimeFormatter.ofPattern(
                "EEEE, MMMM d, uuuu 'at' h:mm a", locale);

        LocalDateTime moment = LocalDateTime.of(date, morning);
        System.out.println("full=" + full.format(moment));
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 MonthDayPeriodDemo.java
java MonthDayPeriodDemo
~~~

Output with JDK 17 `en-US` data:

~~~text
month=October
weekday=Wednesday
morning=AM
evening=PM
full=Wednesday, October 28, 2026 at 9:30 AM
~~~

How the pieces connect:

- **getDisplayName(TextStyle.FULL, Locale.US)** produces the standalone/display name of `Month`/`DayOfWeek` for the locale.
- **"a"** in a `DateTimeFormatter` pattern requests the AM/PM label.
- **"h"** is the 12-hour clock hour, **"mm"** is minutes.
- **"EEEE"** is the full weekday name.
- **"MMMM"** is the full month name in formatting context.
- **"uuuu"** is the proleptic year, suitable for many ISO-based formats.
- **'at'** is quoted in the pattern because it is fixed literal text, not a format symbol.

**Learning point:** if you replace **Locale.US** with **Locale.forLanguageTag("vi-VN")**, Java will use Vietnamese locale data for month/day names and day-period labels; however, the literal **at** remains in English because it is hardcoded in the pattern. A complete sentence requires a pattern or resource in the right language, not merely changing the locale.

## 6. DateTimeFormatter Patterns: M and L

Several symbols in **java.time.format.DateTimeFormatter** correspond to different `TextStyle` contexts:

| Pattern | Typical meaning |
| --- | --- |
| **M** | Numeric month, unpadded if not needed |
| **MM** | Numeric month, typically padded to two digits |
| **MMM** | Short month name in formatting context |
| **MMMM** | Full month name in formatting context |
| **MMMMM** | Narrow month name in formatting context |
| **L** / **LL** | Numeric month in standalone context |
| **LLL** | Short month name in standalone form |
| **LLLL** | Full month name in standalone form |
| **LLLLL** | Narrow month name in standalone form |

**M** and **L** are not two different month numbers: they represent two **grammatical contexts**. For a full date string like **28 October 2026**, the formatting form (**MMMM**) is typically used, whereas a standalone month heading can use **LLLL**. Always test per locale, since some languages return the same string for both forms.

### 6.1. Russian illustration

Illustrative example:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class ContextualMonthDemo {
    public static void main(String[] args) {
        Locale russian = Locale.forLanguageTag("ru-RU");
        LocalDate day = LocalDate.of(2026, 10, 28);

        System.out.println(
                DateTimeFormatter.ofPattern("d MMMM uuuu", russian)
                        .format(day));
        System.out.println(
                DateTimeFormatter.ofPattern("LLLL", russian)
                        .format(day));
    }
}
~~~

Save **ContextualMonthDemo.java** and run:

~~~bash
javac -encoding UTF-8 ContextualMonthDemo.java
java ContextualMonthDemo
~~~

The program prints **a date with the month name in formatting context** on the first line and **the standalone month name** on the second line. Some Russian locale data versions distinguish the inflected month spelling between the two lines. Because the goal here is to observe the JDK's CLDR data, do not assert one Russian string as an invariant stdout across all runtimes.

**Mistake to avoid:** plugging a standalone name straight into a sentence structure where the language requires an inflected form, or using a formatting-context form as a standalone month heading. In English the bug may stay hidden; in other languages it produces unnatural phrasing.

### 6.2. `getDisplayName` and matching patterns

~~~java
Month month = Month.OCTOBER;
Locale locale = Locale.US;

String full = month.getDisplayName(TextStyle.FULL, locale);
String standalone = month.getDisplayName(
        TextStyle.FULL_STANDALONE, locale);
~~~

This snippet requires importing **Month**, **TextStyle**, and **Locale**. Correspondingly, a formatter using **MMMM** requests the full name in formatting context; a formatter using **LLLL** requests the full name in standalone context. The final output also depends on the pattern, sentence grammar, and locale data.

## 7. Weekday Patterns: E, e, and c

**DateTimeFormatter** supports several symbols for day of week:

| Pattern | Usage |
| --- | --- |
| **E**, **EE**, **EEE** | Short weekday name |
| **EEEE** | Full weekday name |
| **EEEEE** | Narrow weekday name |
| **EEEEEE** | Shorter weekday name per data |
| **e** or **ee** | Day-of-week number per the locale's localized week rules |
| **eee** | Short weekday name |
| **eeee** | Full weekday name |
| **eeeee** | Narrow weekday name |
| **c** | Day-of-week number per locale rules |
| **ccc** | Short weekday name in standalone form |
| **cccc** | Full weekday name in standalone form |
| **ccccc** | Narrow weekday name in standalone form |

With **e**/**c**, localized day-of-week numbers can differ from **DayOfWeek.getValue()**. For example, in a locale where Sunday starts the week, **e = 1** can be Sunday even though **DayOfWeek.SUNDAY.getValue() = 7**. Do not use those symbols to store weekday numbers as data keys when the contract expects ISO codes.

On the other hand, **E** primarily represents **textual** forms rather than ordinal numbers. For standalone calendar labels, the standalone **c** variants can be appropriate if the language distinguishes them. Some languages have no separate data, so the same label may appear.

**Pattern limits:** not every repetition count is valid. For instance, two letters **cc** is not a supported pattern like **ee**. Write patterns documented by the API and verify them with tests rather than mechanically doubling letters.

## 8. Day Periods: What Is AM/PM?

**AM/PM** divides the day into two halves:

| ChronoField.AMPM_OF_DAY | 24-hour time | Meaning |
| ---: | --- | --- |
| **0** | 00:00–11:59:59… | Ante meridiem, AM |
| **1** | 12:00–23:59:59… | Post meridiem, PM |

In Java:

~~~java
import java.time.LocalTime;
import java.time.temporal.ChronoField;

public class HalfDayDemo {
    public static void main(String[] args) {
        System.out.println(
                LocalTime.MIDNIGHT.get(ChronoField.AMPM_OF_DAY));
        System.out.println(
                LocalTime.NOON.get(ChronoField.AMPM_OF_DAY));
        System.out.println(
                LocalTime.of(23, 59).get(ChronoField.AMPM_OF_DAY));
    }
}
~~~

Run **javac HalfDayDemo.java** and **java HalfDayDemo**. Exact, locale-independent stdout:

~~~text
0
1
1
~~~

Use **DateTimeFormatter.ofPattern("a", locale)** to print the label for a locale. In `en-US`, the familiar labels are **AM** and **PM**; in other locales, the names can be localized and use different punctuation or phrasing. Never hardcode **"AM"** or **"PM"** in a multilingual UI when users expect localized wording.

### 8.1. Combining `a` with the 12-hour clock

Several hour pattern letters:

| Pattern | Hour range | Meaning example |
| --- | --- | --- |
| **H** / **HH** | 0–23 | 24-hour clock |
| **h** / **hh** | 1–12 | 12-hour clock, usually paired with **a** |
| **K** / **KK** | 0–11 | Hour in AM/PM on a 0–11 scale |
| **k** / **kk** | 1–24 | Clock hour on a 1–24 scale |
| **a** | AM/PM label | Half of day |
| **m** / **mm** | Minute | Unrelated to month **M** |

Example with `Locale.US`:

~~~java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class TwelveHourDemo {
    public static void main(String[] args) {
        DateTimeFormatter format =
                DateTimeFormatter.ofPattern("h:mm a", Locale.US);

        for (LocalTime time : new LocalTime[] {
                LocalTime.MIDNIGHT,
                LocalTime.NOON,
                LocalTime.of(21, 5)
        }) {
            System.out.println(format.format(time));
        }
    }
}
~~~

Save **TwelveHourDemo.java** and run:

~~~bash
javac TwelveHourDemo.java
java TwelveHourDemo
~~~

Stdout with `en-US`:

~~~text
12:00 AM
12:00 PM
9:05 PM
~~~

**00:00 is not 00:00 AM when using `h`; it is 12:00 AM.** **12:00** is 12:00 PM, not AM. Using 24-hour **H** together with **a** is usually redundant and confusing in a UI. For machine-to-machine exchange data, ISO-8601 time strings are generally preferable to AM/PM labels.

## 9. TextStyle for Day Periods with DateTimeFormatterBuilder

The **Month** and **DayOfWeek** enums have **getDisplayName(...)** directly, whereas there is no equivalent **AMPM** enum with that method. For half-day period text, you can format **ChronoField.AMPM_OF_DAY** with **DateTimeFormatterBuilder.appendText(...)**:

~~~java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.time.format.TextStyle;
import java.time.temporal.ChronoField;
import java.util.Locale;

public class AmPmTextStyleDemo {
    public static void main(String[] args) {
        Locale locale = Locale.US;

        DateTimeFormatter label = new DateTimeFormatterBuilder()
                .appendText(
                        ChronoField.AMPM_OF_DAY,
                        TextStyle.SHORT)
                .toFormatter(locale);

        System.out.println(label.format(LocalTime.of(8, 0)));
        System.out.println(label.format(LocalTime.of(20, 0)));
    }
}
~~~

Save **AmPmTextStyleDemo.java** and run:

~~~bash
javac AmPmTextStyleDemo.java
java AmPmTextStyleDemo
~~~

With `en-US` in Java 17, the two common labels produced are:

~~~text
AM
PM
~~~

Here **TextStyle.SHORT** selects the text form level for the AM/PM field. However, a locale does not necessarily have three distinct labels for FULL, SHORT, and NARROW. Locale data may supply the same label or a fallback. If the product has custom label rules, **DateTimeFormatterBuilder.appendText(field, Map<Long,String>)** lets you define an explicit text mapping; in that case, clearly scope the map's locale and language.

**Do not confuse AM/PM labels with granular day periods** such as early morning, noon, afternoon, and night. AM/PM splits the day into only two halves, whereas flexible day periods can divide it into multiple intervals.

## 10. Pattern B: Flexible Day Periods

Java 17 **DateTimeFormatter** supports the pattern letter **B** for flexible **period-of-day**. Unlike **a**, which is based on AM/PM, **B** enables locale-rule-based day-period names such as "in the morning", "in the afternoon", "at night", "noon", and "midnight" when supported by locale data.

Exploratory example:

~~~java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.Locale;

public class FlexiblePeriodDemo {
    public static void main(String[] args) {
        DateTimeFormatter amPm =
                DateTimeFormatter.ofPattern("h:mm a", Locale.US);
        DateTimeFormatter flexible =
                DateTimeFormatter.ofPattern("h:mm B", Locale.US);

        for (LocalTime time : List.of(
                LocalTime.MIDNIGHT,
                LocalTime.of(9, 30),
                LocalTime.NOON,
                LocalTime.of(15, 15),
                LocalTime.of(22, 0))) {
            System.out.println(
                    "a=" + amPm.format(time)
                    + " | B=" + flexible.format(time));
        }
    }
}
~~~

Save **FlexiblePeriodDemo.java** and run:

~~~bash
javac FlexiblePeriodDemo.java
java FlexiblePeriodDemo
~~~

The program prints **five lines**, each showing the **a** and **B** labels at a given time. Calling **a** yields AM/PM labels; calling **B** can express more specific periods of the day. **Do not assert a single verbatim stdout for `B`**, because period names and boundaries are defined by the runtime's locale data and can change across JDK versions or locale providers.

In Java 17, the count of `B` letters in a pattern can request contextual text styles; use valid forms such as **B**, **BBBB**, or **BBBBB** and test them. Do not assign a fixed "morning" label to an arbitrary hour range and treat it as universal behavior across all locales.

### 10.1. `B` is not a transformation of `a`

Both **09:00** and **11:59** are AM. However, depending on the language, there may be specific day-period names or special labels for "noon". **a** distinguishes only the two halves of the day; **B** looks up multi-period rules.

Therefore, in a multilingual application, choose the tool by sentence semantics:

- Entering or displaying times like **9:30 AM**: use **h:mm a** when that is the locale's convention.
- English phrasing like **9:30 in the morning**: consider **h:mm B** when locale data and UI requirements align.
- Displaying a 24-hour timetable: use **HH:mm**, usually without AM/PM.
- Domain sentences with custom shifts like "morning shift" or "night shift": those are **business-domain definitions**; do not equate them with CLDR day periods.

## 11. Month/Day Names in a Sentence Are More Than TextStyle

A `DateTimeFormatter` takes a **pattern and locale**, yet does not translate literal text automatically:

~~~java
DateTimeFormatter en = DateTimeFormatter.ofPattern(
        "EEEE, MMMM d 'at' h:mm a", Locale.US);
~~~

In the pattern above, the word **at** is hardcoded. Switching to **Locale.forLanguageTag("vi-VN")** replaces localized names and components, yet **at** remains. Therefore:

1. **Locale** selects month/day/day-period names from localized data.
2. **Pattern** chooses component order and parts.
3. **Connectors and prepositions** must live in a translated pattern or localized content source (such as a `ResourceBundle`).

For multilingual apps, define patterns/formatters per viewer locale instead of using an English template with translated day names swapped in. Some languages require specific day/month placement, commas, or different prepositional phrasing.

For typical short/long date displays, **DateTimeFormatter.ofLocalizedDate(FormatStyle.FULL)** combined with **withLocale(locale)** is usually more convenient than ordering month/day names manually. Java uses the localized date pattern supplied by the runtime instead of a fixed pattern you write.

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public class LocalizedFullDate {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2026, 10, 28);

        DateTimeFormatter formatter =
                DateTimeFormatter.ofLocalizedDate(FormatStyle.FULL)
                        .withLocale(
                                Locale.forLanguageTag("vi-VN"));

        System.out.println(formatter.format(date));
    }
}
~~~

Save **LocalizedFullDate.java**, compile with **javac**, and run with **java**. The output is the JDK's full `vi-VN` date presentation, which may include day name, month, and local conventions. Do not pin one exact stdout here because the goal of the example is to use the runtime's localized format.

## 12. Reference Table: Which TextStyle or Pattern to Choose?

| UI need | Option to consider | Reason |
| --- | --- | --- |
| Month heading in a calendar | **Month.getDisplayName(FULL_STANDALONE, locale)** or **LLLL** | Standalone month context |
| Month name in a full date | **MMMM** or `DateTimeFormatter` localized style | Formatting context |
| Short month label in a chart | **MMM** / **TextStyle.SHORT** | Compact, though watch for collisions |
| Ultra-short month label | **MMMMM** / **TextStyle.NARROW** | Saves space; often not unique |
| Weekday column heading | **DayOfWeek.getDisplayName(...)** | Uses explicit locale and style |
| Day in a long sentence | **EEEE** | Full weekday name |
| Local week day number | **e** or `WeekFields` | Do not equate with ISO `getValue` |
| 12-hour clock time | **h:mm a** | AM/PM label |
| Flexible day period | **B** | Period names from Java 17 locale data |
| Machine data needing 24h | **HH:mm** or ISO formatter | Independent of day-period names |
| Natural full date string | **ofLocalizedDate(FormatStyle.FULL)** | Uses locale-appropriate order and punctuation |
| Translator-controlled pattern | **ofPattern(pattern, locale)** | Complete translated sentence structure |

**The same TextStyle does not guarantee a fixed character count**: SHORT/NARROW are name categories, not string-truncation algorithms. Never take FULL and call `substring` to fake SHORT or NARROW, because proper abbreviations can differ from the leading letters of the full name.

## 13. Differences Between Locales and JDK/CLDR Data

Even when specifying **Locale.forLanguageTag("vi-VN")** explicitly, textual results can change across runtimes:

- Different JDK releases bundle different versions of localization data.
- CLDR updates capitalization, abbreviations, or punctuation.
- Configured locale providers may differ.
- A style without dedicated data may cause the formatter to fall back to another text form or numeric representation.
- Script/region variants of a language should not be conflated with another variant.

Thus, **passing an explicit locale avoids depending on the machine's default locale**, yet does not turn month/day names into invariant constants across every JDK release. If a system uses exact full-text snapshot tests, pin the supported runtime version or write assertions over meaningful properties.

For common English names such as October/Wednesday, output is usually very stable. For inflected languages, NARROW forms, accented abbreviations, or **B** day periods, do not assume exact output strings without running tests on the deployment runtime.

## 14. Parsing Month and Weekday Names

`DateTimeFormatter` can parse localized text as well as format it. However, if the input string contains textual month/day names, you must know the **locale and style** of the input source.

Full English example:

**File ParseMonthNameDemo.java**

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.Locale;

public class ParseMonthNameDemo {
    public static void main(String[] args) {
        DateTimeFormatter formatter =
                DateTimeFormatter.ofPattern(
                        "d MMMM uuuu", Locale.US);

        String input = "28 October 2026";

        try {
            LocalDate date =
                    LocalDate.parse(input, formatter);

            System.out.println(date);
        } catch (DateTimeParseException ex) {
            System.out.println("Invalid localized date");
        }
    }
}
~~~

Compile and run:

~~~bash
javac ParseMonthNameDemo.java
java ParseMonthNameDemo
~~~

Stdout:

~~~text
2026-10-28
~~~

This case uses **MMMM** matching the full month name and explicit **Locale.US**. If users enter Vietnamese or Russian month names, you need the corresponding formatter and style. Never use the server's locale to parse data in a user's language.

### 14.1. NARROW names can be ambiguous

When **TextStyle.NARROW** uses a single character for multiple months or weekdays, the same string can match multiple values. Therefore:

- Use NARROW for **visual labels** only when sufficient context exists.
- Do not use NARROW as a primary date input format when the system needs unambiguous decoding.
- Prefer ISO numeric formats for APIs or structured date pickers.
- For free-form user input, design validation and localized error messages.

### 14.2. Case, punctuation, and Unicode characters

Month/day names can include diacritics, abbreviation periods, or varying capitalization. By default, **DateTimeFormatter** uses case-sensitive parsing in standard setups; for case-insensitive parsing, call **DateTimeFormatterBuilder.parseCaseInsensitive()** before appending the pattern. Still, **case-insensitive does not strip diacritics or perform full Unicode normalization**.

Example building a formatter inside a method:

~~~java
DateTimeFormatter formatter =
        new DateTimeFormatterBuilder()
                .parseCaseInsensitive()
                .appendPattern("d MMMM uuuu")
                .toFormatter(Locale.US);
~~~

This snippet requires importing **DateTimeFormatterBuilder**, **DateTimeFormatter**, and **Locale**. Test real strings and handle **DateTimeParseException**; for languages with complex case mappings, do not assume every typed variant will be accepted.

## 15. WeekFields and Which Day Starts the Week

Weekday names and calendar positions are related, yet distinct:

- **DayOfWeek.MONDAY.getValue()** is always 1 per ISO.
- **WeekFields.of(Locale.US)** typically uses Sunday as the first day of the week.
- Other locales may have a different first day of the week and minimum days in the first week of the year.

When rendering localized calendar labels, you may need **getDisplayName(TextStyle.SHORT_STANDALONE, locale)** for column headers. When ordering columns, use **WeekFields.of(locale).getFirstDayOfWeek()** or a user-chosen preference, rather than starting on Monday just because ISO assigns it 1.

Code snippet computing the order of seven columns for a locale:

~~~java
DayOfWeek first =
        WeekFields.of(locale).getFirstDayOfWeek();

for (int i = 0; i < 7; i++) {
    DayOfWeek day = first.plus(i);
    String label = day.getDisplayName(
            TextStyle.SHORT_STANDALONE, locale);
    // Place label into calendar column i.
}
~~~

This snippet requires importing **DayOfWeek**, **WeekFields**, **TextStyle**, and **Locale**, plus a `locale` variable. **DayOfWeek.plus(...)** wraps around automatically after Sunday, so manual modulo arithmetic is unnecessary.

**Do not confuse a locale's week with a time zone**: knowing which day starts the week does not tell you what calendar day it currently is for a user without knowing the time zone for that instant.

## 16. Locale Differs from Time Zone and 12/24-Hour Clock

An actual instant is represented by **Instant**, while the date/time a user sees requires a **ZoneId**. Locale determines month names, day names, and formatting conventions, yet **does not automatically convert an instant to local time**.

Example:

~~~java
Instant instant =
        Instant.parse("2026-10-28T00:30:00Z");
ZonedDateTime inVietnam =
        instant.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));

DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern(
                "EEEE, d MMMM uuuu HH:mm",
                Locale.forLanguageTag("vi-VN"));

String output = formatter.format(inVietnam);
~~~

This snippet requires importing **Instant**, **ZonedDateTime**, **ZoneId**, **DateTimeFormatter**, and **Locale**. **instant** identifies the point in time; **ZoneId** determines the Vietnam date/time; **Locale** chooses the corresponding day/month names and punctuation. Do not pin a fixed localized stdout string because names come from JDK data.

When using a zone-less **LocalDateTime**, it is a local calendar date + wall-clock time and does not automatically map to an `Instant`. Do not take a server's `LocalDateTime` and treat it as the actual instant for all users.

**12/24-hour conventions** also differ from time zone. A locale may favor one clock style, yet the pattern **h:mm a** explicitly selects 12-hour format and **HH:mm** selects 24-hour format. If the UI lets users pick their preferred clock format, choose the pattern according to that preference rather than solely from locale.

## 17. ResourceBundle and Translated Text

When writing sentences containing dates in a specific language, patterns can be stored in a `ResourceBundle`:

~~~properties
# messages_en.properties
appointment=Appointment: {0}
~~~

~~~properties
# messages_vi.properties
appointment=Lịch hẹn: {0}
~~~

These are two illustrative files on the classpath. Inside a Java method, you can:

1. Resolve the user's locale against the application's supported list.
2. Format the date/time with `DateTimeFormatter` using the appropriate locale/zone.
3. Look up the sentence template from `ResourceBundle` using the same locale and fallback policy.
4. Use **MessageFormat** or a safe formatting helper to insert the formatted text.

Do not expect **ResourceBundle** to generate month/day names when a literal string is hardcoded. It only selects pre-translated templates. If passing a **LocalDate** directly into **MessageFormat** with **{0,date}**, note that Java 17 `MessageFormat` still uses legacy **java.text.DateFormat** for traditional date placeholders; explicitly use the **DateTimeFormatter.toFormat()** adapter or pre-format into a `String`.

A translated sentence may place the date before or after connecting words, so design patterns/structures per language rather than swapping a few words in one fixed English template.

## 18. Common Mistakes

### Mistake 1: Thinking TextStyle is CSS

**TextStyle.FULL/SHORT/NARROW** are linguistic forms for day/month names, not font-size, font-weight, or color. You cannot use NARROW to guarantee a string fits within a fixed pixel width.

### Mistake 2: Using FULL instead of FULL_STANDALONE in headings

In inflected languages, a month name standing alone differs from a month name paired with a day. Use **LLLL** or **FULL_STANDALONE** for headings when appropriate.

### Mistake 3: Hardcoding the first letter as a NARROW label

The initial letter of a full name is not guaranteed to match the official narrow form and can collide across months or days. Use `TextStyle.NARROW`/`NARROW_STANDALONE` from locale data, or an intentionally designed product label.

### Mistake 4: Confusing `getValue` with local calendar weekday numbers

**DayOfWeek.getValue()** is ISO; localized column order should use `WeekFields` and does not always start with Monday.

### Mistake 5: Using `h` and forgetting `a`

Formatting **9:30** on a 12-hour clock fails to distinguish 09:30 from 21:30. When needed, use **h:mm a**; or use **HH:mm** to avoid ambiguity.

### Mistake 6: Thinking 12:00 is AM

**LocalTime.NOON** is PM; **LocalTime.MIDNIGHT** is AM. On a 12-hour clock, midnight is 12:00 AM and noon is 12:00 PM.

### Mistake 7: Treating `B` as synonymous with `a`

**B** is flexible period-of-day, whereas **a** is strictly AM/PM. Labels and boundaries for `B` depend on locale data; do not map business concepts like "morning shift/evening shift" onto it blindly.

### Mistake 8: Assuming changing Locale translates pattern literals

The pattern **"EEEE 'at' HH:mm"** always keeps the word **at**; the weekday name changes by locale, while the connector does not. Use fully translated patterns or `ResourceBundle` entries.

### Mistake 9: Assuming month/day names never change across JDKs

CLDR data, providers, and Java releases can update wording. For exact snapshot tests, pin the runtime or assert meaningful properties.

### Mistake 10: Parsing with NARROW or the wrong locale

Narrow names can be ambiguous; Russian/Vietnamese month names may not parse under an `en-US` formatter. Choose a formatter matching the input's language and style, and handle parse errors.

### Mistake 11: Using TextStyle to infer a time zone

`TextStyle` and `Locale` do not determine a `ZoneId`. One `Instant` can fall on different calendar dates in two time zones. Select the zone from user/domain data.

### Mistake 12: Using DateTimeFormatter without passing a locale on a server

**DateTimeFormatter.ofPattern(pattern)** without an explicit locale can use the environment's default locale. Two servers can produce different month/day names or AM/PM labels. For user-facing output, use **ofPattern(pattern, locale)** or **withLocale(locale)**.

## 19. Testing Localization of Month Names, Day Names, and Day Periods

| Scenario | What to verify |
| --- | --- |
| **Month.OCTOBER** in `en-US`/`vi-VN`/`ru-RU` | Locale-accurate names; full/standalone as required |
| **DayOfWeek.WEDNESDAY** FULL/SHORT/NARROW | Full, abbreviated, and narrow forms in context |
| `en-US` vs. ISO week | Different first day of week while ISO `getValue` stays unchanged |
| **MMMM** vs. **LLLL** | Month name in sentence vs. standalone heading |
| **EEEE** vs. **cccc** | Weekday name context |
| **00:00**, **12:00**, **21:05** with **h:mm a** | AM/PM and 12-hour clock without confusion |
| **B** at 00:00, 09:30, 12:00, 15:15, 22:00 | Day-period labels per locale data |
| Parsing **28 October 2026** in `en-US` | Returns exact `LocalDate` |
| Parsing accented abbreviations | Does not silently strip accents/case without a policy |
| Pattern string with English literal | Verifies literals do not auto-translate when changing locale |
| Same locale across two supported JDKs | Identifies CLDR/provider differences if needed |
| Same `Instant` across two `ZoneId`s | Local calendar date/time computed accurately for each zone |
| Very narrow calendar space | `TextStyle.NARROW` does not break distinguishability/accessibility |

Separate **typed-logic tests** (`LocalDate`, `LocalTime`, `Month`, `DayOfWeek`, `AMPM_OF_DAY`) from **localized-content tests**. For locale data, pin exact verbatim strings only when the product strictly requires them and the environment is pinned. For logic, assert ISO values or `Instant` rather than relying on textual month or weekday names.

### 19.1. Stable tests under different JVM default locales

A program that passes explicit locales to every formatter can be run under different default environments using startup properties in separate processes:

~~~bash
java -Duser.language=en -Duser.country=US MonthDayPeriodDemo
java -Duser.language=de -Duser.country=DE MonthDayPeriodDemo
~~~

These commands run the same compiled class. Because the program uses explicit **Locale.US**, `en-US` labels should not change just because the JVM default differs. Avoid calling **Locale.setDefault()** in parallel tests; it is JVM-global state and prone to races.

**For tests involving `B` or version-sensitive locales**, run on the target runtime supported by the application and document the localization data used rather than forcing every JDK to return an identical string.

## 20. Self-Check Exercises

1. Writing a month heading for Russian users: should you try **MMMM** or **LLLL**? Why?
2. Why does **DayOfWeek.SUNDAY.getValue()** still equal 7 even though the US calendar starts on Sunday?
3. What is the risk of using `TextStyle.NARROW` as the sole label for weekday input?
4. Why can **h:mm** be ambiguous, whereas **h:mm a** is less ambiguous?
5. How do **B** and **a** differ when formatting `LocalTime` 09:30?
6. Does changing only the formatter's locale translate the literal **'at'** in a pattern?
7. When displaying the same `Instant` in Vietnam and the United States, why must `ZoneId` be specified?
8. If a Vietnamese snapshot changes after a JDK upgrade while `LocalDate` stays the same, what should you check?

**Answer hints:** (1) **LLLL** for standalone headings, tested by locale; (2) `getValue` is ISO, while `WeekFields` governs local calendar weeks; (3) narrow labels can collide or be hard to read; (4) without AM/PM, the two halves of the day are indistinguishable; (5) `a` splits two halves, `B` uses flexible period rules; (6) no; (7) `Instant` has no local date/time until a zone is chosen; (8) JDK/CLDR version, locale provider, and pattern/style.

## 21. Practical Checklist

- Use **Month.getDisplayName(TextStyle, Locale)** for month names and **DayOfWeek.getDisplayName(TextStyle, Locale)** for weekday names.
- Choose **FULL/SHORT/NARROW** based on display space and readability, never manual string slicing.
- Use **STANDALONE** when the language and context require standalone month/day names.
- Distinguish **MMMM** from **LLLL**, **EEEE** from **cccc**, and local week numbers **e/c** from ISO `DayOfWeek.getValue`.
- Use **a** for AM/PM; consider **B** when flexible period-of-day is needed in Java 17.
- Do not confuse **H**, **h**, **K**, and **k**, especially at 00:00 and 12:00.
- For textual AM/PM periods, you can use **DateTimeFormatterBuilder.appendText(ChronoField.AMPM_OF_DAY, TextStyle)**.
- Use **DateTimeFormatter.ofPattern(pattern, locale)** or localized formats with **withLocale(locale)**, never relying accidentally on JVM defaults.
- Ensure literals, prepositions, and surrounding prose are translated; do not assume `TextStyle` translates the entire pattern.
- When formatting an `Instant`, pass an explicit **ZoneId** from user/domain data.
- When parsing, use the input's matching locale and style, avoid ambiguous NARROW forms, and handle `DateTimeParseException`.
- Test localized names across supported JDKs, especially `FULL_STANDALONE`, `SHORT`, and pattern `B`.
- For APIs and machine data, prefer ISO numeric formats over localized month, weekday, or day-period names.

## 22. Conclusion

**`TextStyle` in Java Time determines the textual form of month names, day names, and certain temporal fields; it does not replace `Locale` or patterns.** **Month** and **DayOfWeek** provide **getDisplayName(TextStyle, Locale)**; **DateTimeFormatter** uses **M/L**, **E/e/c**, and **a/B** to express names, standalone context, and day periods. For AM/PM, **ChronoField.AMPM_OF_DAY** represents the two halves of the day, while pattern **B** uses flexible day-period rules from Java 17 locale data.

To keep programs clear and testable, always identify the **viewer's locale**, use **STANDALONE** where appropriate, keep typed date/time values separate from localized text, and manage **ZoneId** when converting an `Instant` to local time. Avoid hardcoding month names or slicing abbreviations, and test against your target JDK/CLDR version to handle intentional localization data updates cleanly.
