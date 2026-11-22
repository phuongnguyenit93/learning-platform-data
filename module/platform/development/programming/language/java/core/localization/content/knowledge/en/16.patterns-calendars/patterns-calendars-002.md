# Distinguishing M from L and Stand-Alone Month Name Forms in Java

## 1. Why Can the Same Month Have Two Different Names?

When formatting dates by `Locale`, some languages use a **contextual month name form within a date** that differs from the **stand-alone month name form**. In Java, the two key pattern letters are:

- **`M`** (*month-of-year*, contextual form): used when the month name is part of a date expression, such as "5 March" (e.g., genitive case in inflected languages).
- **`L`** (*stand-alone month-of-year*, stand-alone form): used when the month name is a separate calendar label, month header, or month selector item, not inside a phrase containing a day.

These are **not two different kinds of months**. Both `M` and `L` refer to the **same month-of-year value**, such as month 3. The difference lies in **how the month name is represented**, depending on the language and locale data.

For example, with `Locale.forLanguageTag("ru-RU")` in Java 17+ with standard locale data:

| Context | Java Pattern | Russian Output | Meaning |
| --- | --- | --- | --- |
| Full date | `d MMMM uuuu` | `5 марта 2025` | `марта` is the month form used with a day |
| Separate month name | `LLLL` | `март` | `март` is the stand-alone month name |
| Taking only the month field in contextual form | `MMMM` | `марта` | Unsuitable as a stand-alone month header in this locale |
| Numeric month | `MM` or `LL` | `03` | In numeric form, both can be identical |

For English `en-US`, `MMMM` and `LLLL` both normally produce `March`. That is why a program tested only in English can **fail to catch** using the wrong month name form in Russian, Polish, or Czech.

**Rule:** When displaying a date with a day number, prefer `M` following the locale's date pattern; when displaying a **stand-alone month name**, prefer `L` and test on the locales your application supports. Do not assume all languages share English grammatical rules.

## 2. M and L in DateTimeFormatter

`java.time.format.DateTimeFormatter` uses pattern letters to choose the temporal field, representation width, and text style. For months:

| Pattern | `M` — contextual form | `L` — stand-alone form |
| --- | --- | --- |
| `M` / `L` | Numeric month, e.g. `3` | Numeric month, e.g. `3` |
| `MM` / `LL` | Two-digit numeric month, e.g. `03` | Two-digit numeric month, e.g. `03` |
| `MMM` / `LLL` | Contextual short name, e.g. Russian can be `мар.` | Stand-alone short name, e.g. Russian can be `март` |
| `MMMM` / `LLLL` | Contextual full name, e.g. `марта` | Stand-alone full name, e.g. `март` |
| `MMMMM` / `LLLLL` | Contextual very short (*narrow*) form | Stand-alone very short (*narrow stand-alone*) form |

This table describes **pattern semantics**, not a guarantee that the output differs in every locale. Depending on the language and JDK data, forms may be identical, some abbreviated forms may not exist separately, or the provider may fall back to an available form.

In `java.time`, the repetition count of `M`/`L` means:

- **One letter:** numeric month representation without requiring a leading zero.
- **Two letters:** two-digit numeric month representation.
- **Three letters:** short month name.
- **Four letters:** full month name.
- **Five letters:** *narrow* form, usually very short and potentially ambiguous across multiple months.

**Watch out for letter casing:** `M` (uppercase) is month; `m` (lowercase) is **minute**. `L` (uppercase L) is stand-alone month, not the digit `1`. For example, `"HH:mm"` has `mm` for minutes, while `"uuuu-MM-dd"` has `MM` for month.

### "Stand-alone" here is a grammatical form, not a different data type

A `LocalDate` holds year, month, and day fields. When formatting the same date with `MMMM` and `LLLL`, the numeric month in the data is still `3`. Only the rule for naming the month differs.

Do not interpret `L` as a "different calendar", a "different time zone", or "converting the month to another value". Both `M` and `L` operate on `MONTH_OF_YEAR`, according to the formatter's chronology and locale.

## 3. Complete Java 17+ Example: March in Four Locales

Create the file `MonthContextDemo.java`:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.Locale;

public class MonthContextDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2025, 3, 5);
        List<String> tags = List.of(
                "ru-RU", "pl-PL", "cs-CZ", "en-US"
        );

        for (String tag : tags) {
            Locale locale = Locale.forLanguageTag(tag);

            DateTimeFormatter dayAndMonth =
                    DateTimeFormatter.ofPattern("d MMMM uuuu", locale);
            DateTimeFormatter standalone =
                    DateTimeFormatter.ofPattern("LLLL", locale);

            System.out.println(tag);
            System.out.println("  In a date: "
                    + date.format(dayAndMonth));
            System.out.println("  Month title: "
                    + date.format(standalone));
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 MonthContextDemo.java
java MonthContextDemo
~~~

With common CLDR locale data on modern JDKs, reference output:

~~~text
ru-RU
  In a date: 5 марта 2025
  Month title: март
pl-PL
  In a date: 5 marca 2025
  Month title: marzec
cs-CZ
  In a date: 5 března 2025
  Month title: březen
en-US
  In a date: 5 March 2025
  Month title: March
~~~

### Explaining the output

**Russian (ru-RU).** When writing a full date, the month typically takes the form `марта`. When a title contains only the month name, the stand-alone form `март` is appropriate.

**Polish (pl-PL).** In the date `5 marca 2025`, the month name is `marca`; standing alone it is `marzec`.

**Czech (cs-CZ).** The date pattern has `března`; the stand-alone month name has `březen`.

**English (en-US).** Both situations use `March`, so testing only this language can hide design bugs.

Exact strings depend on the JDK version's locale data and provider. Do not hardcode expectations across all Java environments and treat every difference as an API bug; test on the actual target environment and confirm the desired linguistic policy.

## 4. Choosing M or L Based on UI Context

### 4.1. Full date in a sentence or appointment schedule

If the UI prints a date such as "5 March 2025", use the contextual month name form:

~~~java
Locale ru = Locale.forLanguageTag("ru-RU");
LocalDate day = LocalDate.of(2025, 3, 5);

DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern("d MMMM uuuu", ru);

String text = day.format(formatter);
~~~

The code above is an **illustrative snippet inside a method**, requiring imports `java.time.LocalDate`, `java.time.format.DateTimeFormatter`, and `java.util.Locale`.

In `ru-RU`, `text` is typically `5 марта 2025`.

**Do not replace `MMMM` with `LLLL` merely to get the full month name.** `LLLL` forces the month name into its stand-alone form even inside a date expression with a day. For example, `"d LLLL uuuu"` can produce `"5 март 2025"`, which is not normal Russian grammatical morphology.

### 4.2. Single-month header in a calendar

When printing a label like `March 2025` above a monthly calendar, no specific day appears. Choose `LLLL uuuu`:

~~~java
Locale ru = Locale.forLanguageTag("ru-RU");
LocalDate day = LocalDate.of(2025, 3, 5);

DateTimeFormatter header =
        DateTimeFormatter.ofPattern("LLLL uuuu", ru);

String title = day.format(header);
~~~

Typical Russian output: `март 2025`.

For headers, date pickers, month selection dropdowns, "Month" filter boxes, or charts whose titles contain only the month, using `L` is the clear choice. If a design calls for a specific grammatical phrase like "in March", you may need a translated message or a different template rather than assuming one pattern resolves all grammatical inflections.

### 4.3. Short and narrow names

For Russian, in typical JDK/CLDR data:

~~~java
DateTimeFormatter contextShort =
        DateTimeFormatter.ofPattern("MMM", ru);
DateTimeFormatter standaloneShort =
        DateTimeFormatter.ofPattern("LLL", ru);
~~~

The above is an **in-method snippet**, with `ru` already set to the appropriate `Locale`. They can yield `мар.` and `март`. This shows **the difference is not limited to `MMMM`/`LLLL`**: short forms can also differ.

The pattern `MMMMM` or `LLLLL` typically produces a *narrow* form such as a single letter. It can be ambiguous because multiple months share the same initial letter. Only use the narrow form when the UI provides supporting context (such as a calendar grid where the month is identified by year/position), and do not assume it is sufficient for users to distinguish months by name alone.

### 4.4. Numeric month

For a date in March:

~~~java
DateTimeFormatter numericM =
        DateTimeFormatter.ofPattern("MM", Locale.US);
DateTimeFormatter numericL =
        DateTimeFormatter.ofPattern("LL", Locale.US);
~~~

Both typically return `03`. When only the month number is needed, morphological differences in month names do not appear. However, for readability and common convention, when constructing ISO dates like `"uuuu-MM-dd"` use `MM`; reserve `L` for **stand-alone month name forms** when text is needed.

## 5. Direct Comparison of M/MM/MMM/MMMM/MMMMM with L/LL/LLL/LLLL/LLLLL

Create `MonthWidthsDemo.java` to observe the same date:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class MonthWidthsDemo {
    public static void main(String[] args) {
        LocalDate day = LocalDate.of(2025, 3, 5);
        Locale ru = Locale.forLanguageTag("ru-RU");

        for (int width = 1; width <= 5; width++) {
            String mPattern = "M".repeat(width);
            String lPattern = "L".repeat(width);

            String contextual = day.format(
                    DateTimeFormatter.ofPattern(mPattern, ru)
            );
            String standalone = day.format(
                    DateTimeFormatter.ofPattern(lPattern, ru)
            );

            System.out.println(mPattern + ": " + contextual
                    + " | " + lPattern + ": " + standalone);
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 MonthWidthsDemo.java
java MonthWidthsDemo
~~~

On a JDK with Russian locale data as illustrated:

~~~text
M: 3 | L: 3
MM: 03 | LL: 03
MMM: мар. | LLL: март
MMMM: марта | LLLL: март
MMMMM: М | LLLLL: М
~~~

Takeaways from the output table:

- Identical numeric forms do not make the two pattern letters equivalent across all widths.
- Short forms `MMM`/`LLL` can differ.
- Full forms `MMMM`/`LLLL` can show the clearest difference.
- Very short forms `MMMMM`/`LLLLL` may be identical even when full forms differ, because the abbreviated name is too short to show inflection.

`String.repeat(int)` has been available since Java 11; hence the loop using `"M".repeat(width)` runs cleanly on Java 17+.

## 6. Using TextStyle to Express Month Name Forms Directly

`DateTimeFormatter` does not only support pattern strings. It also offers `DateTimeFormatterBuilder.appendText` and `java.time.format.TextStyle`. The pairs to know:

| `TextStyle` Name | Meaning | Equivalent Month Pattern |
| --- | --- | --- |
| `FULL` | Contextual full name | `MMMM` |
| `FULL_STANDALONE` | Stand-alone full name | `LLLL` |
| `SHORT` | Contextual short name | `MMM` |
| `SHORT_STANDALONE` | Stand-alone short name | `LLL` |
| `NARROW` | Contextual narrow name | `MMMMM` |
| `NARROW_STANDALONE` | Stand-alone narrow name | `LLLLL` |

For the month field, both groups draw values from `ChronoField.MONTH_OF_YEAR`.

### Complete example: pattern and builder equivalent in intent

Save `MonthTextStyleDemo.java`:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.time.format.TextStyle;
import java.time.temporal.ChronoField;
import java.util.Locale;

public class MonthTextStyleDemo {
    public static void main(String[] args) {
        Locale ru = Locale.forLanguageTag("ru-RU");
        LocalDate day = LocalDate.of(2025, 3, 5);

        DateTimeFormatter fromPattern =
                DateTimeFormatter.ofPattern("LLLL", ru);

        DateTimeFormatter fromBuilder =
                new DateTimeFormatterBuilder()
                        .appendText(ChronoField.MONTH_OF_YEAR,
                                TextStyle.FULL_STANDALONE)
                        .toFormatter(ru);

        DateTimeFormatter contextual =
                new DateTimeFormatterBuilder()
                        .appendText(ChronoField.MONTH_OF_YEAR,
                                TextStyle.FULL)
                        .toFormatter(ru);

        System.out.println("LLLL: " + day.format(fromPattern));
        System.out.println("FULL_STANDALONE: "
                + day.format(fromBuilder));
        System.out.println("FULL: " + day.format(contextual));
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 MonthTextStyleDemo.java
java MonthTextStyleDemo
~~~

Reference output with typical Russian locale data:

~~~text
LLLL: март
FULL_STANDALONE: март
FULL: марта
~~~

### Choosing pattern or TextStyle?

- `ofPattern("LLLL", locale)` is concise when the date/month pattern is configured as a string.
- `DateTimeFormatterBuilder` suits building formatters in code, combining multiple fields, or expressing `TextStyle` explicitly by intent.
- `TextStyle.FULL_STANDALONE` directly expresses "stand-alone month name form", which can be easier to read than a single letter `L` for readers unfamiliar with pattern syntax.
- Both still depend on the **locale** and locale data for month names; the builder does not translate or invent grammatical inflections on its own.

Do not mistake `TextStyle.FULL` for "use everywhere a long name is wanted". `FULL` is the **contextual form**, whereas `FULL_STANDALONE` is the **stand-alone form**.

## 7. Parsing: Should M and L Differ When Reading Strings?

Beyond formatting, `DateTimeFormatter` can also **parse** month names from text. The parser's pattern must match the month name form being written.

For example, when reading a Russian title containing a stand-alone month name and year, use `LLLL uuuu` instead of forcing the parser to expect a full-date form:

~~~java
Locale ru = Locale.forLanguageTag("ru-RU");
DateTimeFormatter monthTitle =
        DateTimeFormatter.ofPattern("LLLL uuuu", ru);

YearMonth input = YearMonth.parse("март 2025", monthTitle);
~~~

This is an **illustrative snippet inside a method**, requiring imports `java.time.YearMonth`, `java.time.format.DateTimeFormatter`, and `java.util.Locale`. In an environment with corresponding Russian month-name data, `input` holds the value `2025-03`.

### Runnable example avoiding Cyrillic typing dependencies

Save `MonthRoundTripDemo.java`:

~~~java
import java.time.YearMonth;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class MonthRoundTripDemo {
    public static void main(String[] args) {
        Locale ru = Locale.forLanguageTag("ru-RU");
        YearMonth original = YearMonth.of(2025, 3);

        DateTimeFormatter standalone =
                DateTimeFormatter.ofPattern("LLLL uuuu", ru);
        DateTimeFormatter contextual =
                DateTimeFormatter.ofPattern("MMMM uuuu", ru);

        String title = original.format(standalone);
        String contextualText = original.format(contextual);

        YearMonth parsedTitle = YearMonth.parse(title, standalone);
        YearMonth parsedContext =
                YearMonth.parse(contextualText, contextual);

        System.out.println("Standalone title: " + title);
        System.out.println("Contextual month: " + contextualText);
        System.out.println("Parsed title: " + parsedTitle);
        System.out.println("Parsed context: " + parsedContext);
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 MonthRoundTripDemo.java
java MonthRoundTripDemo
~~~

Output with typical Russian locale data:

~~~text
Standalone title: март 2025
Contextual month: марта 2025
Parsed title: 2025-03
Parsed context: 2025-03
~~~

**Both strings can parse back to the same `YearMonth`**: the difference is the morphology of the month name in text. When integrating with forms, you should not generate a string with `LLLL` and parse it with `MMMM` hoping the parser will always accept the other form. Parsing policy can depend on the provider, locale data, and the formatter's strictness settings.

### Do not use the narrow form as sole input

The very short form `MMMMM`/`LLLLL` is sometimes just a single character. Multiple months can share the same starting letter, such as starting with `M`. Therefore it is unsuitable for uniquely parsing a month without supporting information. For user input, choose full month forms, numeric forms, or structured date/month controls.

For data exchange between services, prefer month numbers `1–12`, `YearMonth`/ISO `uuuu-MM`, or structured objects rather than turning localized month names into a machine protocol.

## 8. DateTimeFormatter.ofLocalizedDate vs. Custom Patterns

An option that is often better than imposing a single date pattern on all users is:

~~~java
DateTimeFormatter localized = DateTimeFormatter
        .ofLocalizedDate(FormatStyle.LONG)
        .withLocale(Locale.forLanguageTag("ru-RU"));
~~~

This is an **illustrative snippet inside a method**, requiring imports `java.time.format.DateTimeFormatter`, `java.time.format.FormatStyle`, and `java.util.Locale`.

`ofLocalizedDate(FormatStyle.LONG)` lets the locale/provider determine **the ordering and presentation of date components**. When formatting a `LocalDate`, the result can have the proper grammatical form for a full date without having to pick individual pattern letters manually.

Comparison:

- **Custom pattern** `"d MMMM uuuu"`: you control the date layout and choose the contextual month form. Suitable when the UI requires a uniform layout.
- **Localized style**: lets the locale define the full date style. Usually better for international user-facing interfaces with diverse date conventions.
- **Stand-alone month name** `"LLLL"`: when only a month label is needed, not a complete date.

You should not take `"d MMMM uuuu"` and apply it verbatim to every locale claiming it is always natural: some regions have different day/month/year orders or different prepositions, punctuation, and character forms. The exact pattern should come from product requirements or appropriate locale data.

## 9. SimpleDateFormat: M and L in the Legacy API

Java also has `java.text.SimpleDateFormat` from the legacy date-time API. For many locales, it supports:

- `M`: contextual month name;
- `L`: stand-alone month name.

Create `LegacyMonthDemo.java`:

~~~java
import java.text.SimpleDateFormat;
import java.util.Calendar;
import java.util.Date;
import java.util.GregorianCalendar;
import java.util.Locale;

public class LegacyMonthDemo {
    public static void main(String[] args) {
        Locale ru = Locale.forLanguageTag("ru-RU");

        Calendar calendar = new GregorianCalendar(
                2025, Calendar.MARCH, 5
        );
        Date date = calendar.getTime();

        SimpleDateFormat inDate =
                new SimpleDateFormat("d MMMM yyyy", ru);
        SimpleDateFormat standalone =
                new SimpleDateFormat("LLLL", ru);

        System.out.println("Date: " + inDate.format(date));
        System.out.println("Month title: " + standalone.format(date));
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 LegacyMonthDemo.java
java LegacyMonthDemo
~~~

Reference output:

~~~text
Date: 5 марта 2025
Month title: март
~~~

**Design distinctions:**

- `SimpleDateFormat` is tied to `java.util.Date`/`Calendar` and has **mutable** state, making it unsafe to share across multiple threads without synchronization.
- `DateTimeFormatter` belongs to `java.time`, is **immutable and thread-safe**, and is suited for modern Java.
- `Calendar.MARCH` is a constant representing March in the legacy API, where `Calendar` months are 0-based. In `java.time`, `Month.MARCH` has month value `3` and `LocalDate.of(2025, 3, 5)` uses months 1–12. **Do not confuse Calendar's month numbering with M/L patterns**.
- `SimpleDateFormat` has its own pattern rules and calendar/leniency handling. Do not assume all `java.time` constructs share the exact same parsing behavior as the legacy API.

For new projects, prefer `LocalDate`, `YearMonth`, and `DateTimeFormatter`. When maintaining legacy code, you still need to recognize `L` to avoid ungrammatical month labels.

## 10. Which Locales Require Special Attention?

There is no immutable list that applies across every data version, but some instructive examples are:

| Locale | Pattern `d MMMM uuuu`, March | Pattern `LLLL`, March | Notes |
| --- | --- | --- | --- |
| `ru-RU` | `5 марта 2025` | `март` | Clear grammatical inflection |
| `pl-PL` | `5 marca 2025` | `marzec` | Month name in date differs from stand-alone |
| `cs-CZ` | `5 března 2025` | `březen` | Month name depends on context |
| `en-US` | `5 March 2025` | `March` | Both forms are typically identical |
| `vi-VN` | May use Vietnamese month name/number per Vietnamese data | Stand-alone month name per Vietnamese data | Do not assume every language has two distinct forms |

March is only one illustrative case. When a locale has multiple month-name variations, the degree of difference can vary by month, width (short/full/narrow), and CLDR data.

**Do not generalize Russian rules to every language:** `LLLL` means *stand-alone* per the API, not a fixed rule to "switch to nominative case". If a language lacks a separate morphology, the month name may match `MMMM`.

## 11. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using `MMMM` as a monthly calendar header in all locales | Some languages show the in-date form | Use `LLLL` for stand-alone month names |
| Using `LLLL` in a date pattern with a day number | Can produce ungrammatical phrases like `5 март 2025` | Use `MMMM` or `ofLocalizedDate` |
| Testing only `en-US` | Difference between `MMMM` and `LLLL` goes unseen | Test `ru-RU`, `pl-PL`, or relevant locales |
| Thinking `M` and `L` have different month values | Misunderstanding temporal data | Both represent `MONTH_OF_YEAR`, differing in text context |
| Confusing `MM` and `mm` | Prints minutes where month is wanted | `MM` is month, `mm` is minute |
| Using `MMMMM`/`LLLLL` strings as month identifiers | Narrow names can collide | Store month number/`YearMonth` or internal key |
| Forcing `MMMM` everywhere for "full" names | Wrong for stand-alone cases | Choose `M`/`L` group by context first, then width |
| Replacing month names with a `switch` per locale | Hard to maintain, misses morphology/CLDR | Use `DateTimeFormatter` with locale |
| Using `Locale.getDefault()` for multi-region users | Output follows server rather than recipient | Pass `Locale` explicitly |
| Assuming `L` handles every inflection in a sentence | A specific sentence may need prepositions/other structures | Use translations/ResourceBundle if grammar exceeds a date pattern |
| Sharing `SimpleDateFormat` across threads | Can corrupt state and output | Use immutable `DateTimeFormatter` or guard legacy formatter |
| Mixing 0-based `Calendar` months with 1-based `LocalDate` | Off-by-one month errors when converting | Check each API's indexing, never assign blindly |

## 12. Application Design: Keep Dates Structured

A calendar UI may simultaneously need:

1. **Event date:** `LocalDate`, e.g. `2025-03-05`.
2. **Displayed date line:** locale-aware formatter with `M` form and proper date structure.
3. **Calendar header:** formatter for stand-alone month name `LLLL`, optionally with year `uuuu`.
4. **Machine value:** keep `YearMonth.of(2025,3)` or numeric month, never use localized strings as keys.
5. **UI language:** user-selected `Locale`, not defaulted to the JVM.

Example utility class:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public final class CalendarLabels {
    private CalendarLabels() {}

    public static String dayLabel(LocalDate day, Locale locale) {
        DateTimeFormatter format =
                DateTimeFormatter.ofPattern("d MMMM uuuu", locale);
        return day.format(format);
    }

    public static String monthHeader(LocalDate day, Locale locale) {
        DateTimeFormatter format =
                DateTimeFormatter.ofPattern("LLLL uuuu", locale);
        return day.format(format);
    }
}
~~~

Create the file `CalendarLabels.java`. The class above has two independent methods that clearly express intent. When the system needs multiple date orderings, replace `dayLabel` with a localized-style formatter matching application policy. To use the class:

~~~java
LocalDate day = LocalDate.of(2025, 3, 5);
Locale ru = Locale.forLanguageTag("ru-RU");

System.out.println(CalendarLabels.dayLabel(day, ru));
System.out.println(CalendarLabels.monthHeader(day, ru));
~~~

This is an **in-method snippet** requiring imports `java.time.LocalDate` and `java.util.Locale`, with `CalendarLabels` compiled. With typical Russian data, output is `5 марта 2025` and `март 2025`.

**Do not store `"март 2025"` in place of `YearMonth`.** Header strings can change when users switch languages or when the JDK updates locale data; structured date data remains independent of presentation formatting.

## 13. M and L Do Not Replace Chronology and Time Zone

Some localization requirements involve a distinct calendar system (chronology), a different numbering system, or a specific time zone. Choosing `MMMM` or `LLLL` **does not automatically determine**:

- Calendar system (ISO, Buddhist, Japanese, or another system).
- Time zone when displaying an `Instant`.
- Numbering system for day/month fields.
- Language of the surrounding sentence outside the month name.

`LocalDate` in the examples uses the ISO chronology. For `Instant`, you must choose a `ZoneId` before interpreting it as a local date; locale is a separate factor. When using a non-ISO chronology, month-name lookup also depends on the formatter, chronology, and provider data.

For example, a date in `Asia/Ho_Chi_Minh` can differ from the date of the same `Instant` in `America/Los_Angeles`. You cannot fix a date discrepancy by changing `M` to `L`. The two letters only govern **how the month is rendered**, not time conversion.

## 14. Practical Testing Across Multiple Locales

### 14.1. Checklist

- With `ru-RU` and `pl-PL`, test the same `LocalDate.of(2025,3,5)` under `d MMMM uuuu` and `LLLL`.
- Test `MMM` and `LLL` to inspect abbreviated forms.
- Test `MM` and `LL` to verify both use the same numeric month value.
- Compare outputs between `TextStyle.FULL` and `TextStyle.FULL_STANDALONE`.
- Check `ofLocalizedDate(FormatStyle.LONG)` for natural date displays.
- When parsing month names, test `YearMonth.parse` with the exact formatter used for formatting.
- Do not rely solely on `en-US` tests, as month names can match between the two contexts.
- If testing exact text, run on the same JDK, provider configuration, and locale data as production.
- Test multiple different months, not only March, especially if the app uses the *narrow* form.
- Use `YearMonth`/`LocalDate` as primary data; month strings are purely presentation layer.

### 14.2. Exercises

1. Using `Locale.forLanguageTag("ru-RU")`, format `2025-03-05` with `"d MMMM uuuu"` and `"LLLL uuuu"`. Explain why they should not be swapped in the same UI slot.
2. Try the same with `pl-PL`: why is the stand-alone month name usually `marzec` while inside a date it is `marca`?
3. Write a loop comparing `M`/`L`, `MM`/`LL`, `MMM`/`LLL`, `MMMM`/`LLLL`, `MMMMM`/`LLLLL`. Note which widths differ and which can coincide.
4. Use `TextStyle.FULL_STANDALONE` to build a month-header formatter with `DateTimeFormatterBuilder` without using `ofPattern("LLLL")`.
5. Use `YearMonth` to format and then parse a stand-alone month name and year. If you change the parser formatter from `LLLL` to `MMMM`, why is the result no longer guaranteed?
6. Compare `SimpleDateFormat` and `DateTimeFormatter` in Java 17 regarding date object types and thread safety.
7. A date picker needs to show the month name `LLLL`, and a delivery notification needs a full date. Choose the appropriate API/pattern and explain how to separate the model from the display string.
8. Why can `"MM"` produce the same output as `"LL"`, while `"MMMM"` can differ from `"LLLL"`?

**Takeaway:** In `DateTimeFormatter`, `M` is the **contextual text form of the month**, while `L` is the **stand-alone month name**. In numeric form, `M` and `L` are usually identical; when using short or full names, many locales such as Russian and Polish exhibit clear grammatical differences. **Date with a day number → prefer `MMMM` or a localized date formatter; stand-alone month/header → prefer `LLLL`.** Choose the locale explicitly, keep date values structured, and test on languages that genuinely have two month-name forms.

### References

- [Java SE 17 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html) — pattern letters `M`/`L` and locale-based date formatting.
- [Java SE 17 — DateTimeFormatterBuilder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html) — `appendText` and month fields.
- [Java SE 17 — TextStyle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/TextStyle.html) — `FULL_STANDALONE` and month-name styles.
- [Java SE 17 — SimpleDateFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/SimpleDateFormat.html) — contextual and stand-alone month patterns in the legacy API.
- [Java SE 17 — YearMonth](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/YearMonth.html) — year/month object independent of localized names.
