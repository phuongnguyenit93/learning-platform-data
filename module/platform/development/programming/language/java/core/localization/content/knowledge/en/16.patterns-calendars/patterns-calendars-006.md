# Chronology and Calendar Systems Supported by Java

## 1. Why Do Multilingual Applications Need to Understand Calendar Systems?

The same real-world date can be written using different **calendar systems**. For example, the ISO date **2026-10-28** can be presented with year **2569** in the Thai Buddhist calendar, year **115** in the Minguo (Republic of China) calendar, or **year 8 of the Reiwa era** in the Japanese calendar. The actual day has not changed: **the rules for numbering years, eras, and calendar fields differ across calendar systems**.

Java's `java.time` uses **ISO-8601** (the proleptic Gregorian calendar following ISO rules) as its common foundation, while also providing the `java.time.chrono` package for several other calendar systems. The common abstraction is the `Chronology` interface.

When implementing localization, distinguish three separate decisions:

1. **Which business date or instant is it?** `LocalDate`, `Instant`, and temporal types describe the underlying data.
2. **Which calendar system represents that date?** `IsoChronology`, `JapaneseChronology`, `ThaiBuddhistChronology`, etc.
3. **Which language and formatting pattern expresses it?** `Locale`, `DateTimeFormatter`, `FormatStyle`, month names, and era names.

If you only change `Locale.JAPAN` without changing the chronology, do not assume Java will automatically convert ISO year 2026 into Reiwa year 8. If you only change the chronology without choosing an appropriate locale, words such as era names may still appear in an unintended language.

### Lesson Goals

You will learn the chronologies built into Java 17, how to select them via API or Unicode locale extensions, how to convert a date across chronologies without shifting the day on the timeline, how to distinguish `YEAR` and `YEAR_OF_ERA`, how to use `DateTimeFormatter.withChronology`, how to parse under the matching calendar, and how to avoid mixing calendars with time zones or business rules.

## 2. What Is Chronology?

`Chronology` in `java.time.chrono` represents the **rule set of a calendar system**, including year numbering, month division, days, eras, leap years, and valid date construction. It also acts as a **factory** for creating date objects in that chronology.

| Concept | Java API / Type | Role |
| --- | --- | --- |
| Calendar system | `Chronology` | Identifies and implements calendar rules |
| ISO calendar | `IsoChronology` | Default foundation for `LocalDate` and most of `java.time` |
| Date in a calendar system | `ChronoLocalDate` | Common interface for ISO and non-ISO dates |
| Era | `Era` | Numbered year period such as Reiwa or Heisei |
| Date/time in a calendar system | `ChronoLocalDateTime` | Non-ISO date paired with local time |
| Zoned date/time | `ChronoZonedDateTime` | Non-ISO date-time with a time zone |
| Formatter | `DateTimeFormatter` | Formats dates to strings or parses strings |
| Language / local conventions | `Locale` | Month names, era names, localized patterns |
| Time zone | `ZoneId` | Rules turning an instant into local date/time |

`Chronology` is **not** a translation dictionary, not a `ZoneId`, and not a time-conversion ratio. It governs the meaning of **day/month/year** calendar fields.

The same day can have different `ChronoLocalDate` objects that share the exact same `EPOCH_DAY` — the count of days from ISO `1970-01-01`. This is the key basis for converting and comparing dates across calendar systems. `Chronology.dateEpochDay(long)` constructs a date in the chosen calendar from an epoch-day.

**Java API Guidance:** For most application logic, prefer ISO `LocalDate` for simple storage and calculations, and use another chronology only when localization or domain requirements truly call for it. Do not replace your entire time model with `ChronoLocalDate` merely to display an era name.

## 3. Built-in Calendar Systems in Java 17

Java 17 includes five prominent built-in chronologies; applications can also provide custom chronologies via `ServiceLoader`.

| Chronology | Class | Typical ID | Calendar Type | Key Characteristics |
| --- | --- | --- | --- | --- |
| ISO | `IsoChronology` | `ISO` | `iso8601` | ISO year/month/day; `LocalDate` is the standard type |
| Japanese | `JapaneseChronology` | `Japanese` | `japanese` | Gregorian months/days, but years counted by Japanese imperial eras |
| Minguo | `MinguoChronology` | `Minguo` | `roc` | Minguo years counted from 1912; months/days align with ISO |
| Thai Buddhist | `ThaiBuddhistChronology` | `ThaiBuddhist` | `buddhist` | Current Thai Buddhist year equals ISO year plus 543 |
| Hijrah | `HijrahChronology` | `Hijrah-umalqura` | `islamic-umalqura` | Islamic lunar calendar; months and days depend on the supplied calendar variant data |

The IDs and calendar types above reflect the built-in chronologies in JDK 17; additional chronologies may appear if an application registers extra providers. `Chronology.getAvailableChronologies()` returns the set of calendars available **in the current runtime**, so do not assume this set will always contain exactly five elements in every application.

### 3.1. ISO — the common foundation

`IsoChronology.INSTANCE` is the default chronology for `LocalDate`. For example, `LocalDate.of(2026, 10, 28)` is an ISO date. Most machine protocols, APIs, and business database queries use ISO dates or ISO-8601 representations.

### 3.2. Japanese — era-based calendar

`JapaneseChronology.INSTANCE` implements the Japanese calendar system. It aligns with Gregorian months/days within its supported range, but years are typically expressed with an era and year within that era. For example, **ISO 2026-10-28** corresponds to **Reiwa 8**.

`JapaneseEra` defines constants such as `MEIJI`, `TAISHO`, `SHOWA`, `HEISEI`, and `REIWA`. Each era has start and end boundaries: **Reiwa started on 2019-05-01**. Consequently, the year number "8" without an era is **insufficient** to identify a specific Japanese year. Always preserve/parse the era when using `YEAR_OF_ERA`.

The Japanese calendar in Java does not support arbitrary historical dates: `JapaneseChronology` supports dates from **Meiji 6, ISO 1873-01-01** onward. Do not expect to operate on dates before this range.

### 3.3. Minguo — Republic of China calendar

`MinguoChronology.INSTANCE` sets year 1 at **ISO 1912**. For an ISO date in 2026, the current Minguo year is **115**. This system has eras for Minguo and before-Minguo. Do not mistake "115" for ISO year 115 when exporting to APIs.

### 3.4. Thai Buddhist — Thai Buddhist calendar

`ThaiBuddhistChronology.INSTANCE` uses month/day ordering matching ISO; in the current era, the Thai Buddhist year equals **ISO year + 543**. Thus **2026 → 2569**.

**This is a calendar-system mapping, not a time-zone shift or adding 543 years to a business `LocalDate`.** If you literally call `isoDate.plusYears(543)`, you move to a completely different day on the timeline — wholly different from creating a `ThaiBuddhistDate` for the same epoch-day.

### 3.5. Hijrah — Islamic lunar calendar

`HijrahChronology.INSTANCE` represents the built-in Hijrah variant, commonly **Umm al-Qura**. Because it is a lunar calendar, month lengths, years, and leap-year rules differ from ISO and from offset-year chronologies.

Therefore, you **cannot** convert Hijrah dates to ISO by "adding/subtracting a fixed year offset". Month start dates, valid day ranges, and outputs can depend on the variant and calendar data bundled with the JDK. For legally or religiously significant data, explicitly specify the **calendar variant, data source, and rules** accepted by the product.

## 4. Accessing Chronologies via the Java API

Ways to obtain a chronology:

```java
Chronology iso = IsoChronology.INSTANCE;
Chronology japanese = JapaneseChronology.INSTANCE;
Chronology minguo = MinguoChronology.INSTANCE;
Chronology thai = ThaiBuddhistChronology.INSTANCE;
Chronology hijrah = HijrahChronology.INSTANCE;
```

This is an illustrative snippet inside a method, requiring `import java.time.chrono.*`. Because built-in classes expose singleton `INSTANCE` fields, you do not instantiate them yourself.

You can also use lookup:

```java
Chronology jp = Chronology.of("Japanese");
Chronology buddhist = Chronology.of("buddhist");
Chronology thaiById = Chronology.of("ThaiBuddhist");
```

`Chronology.of(String)` searches by **ID** or **calendar type**. If the ID/type does not exist, it throws `DateTimeException`. Never treat arbitrary strings as valid calendar names.

To inspect what the runtime supports:

```java
for (Chronology chronology : Chronology.getAvailableChronologies()) {
    System.out.println(chronology.getId() + " / "
            + chronology.getCalendarType());
}
```

The returned set **does not guarantee a stable order**. When deterministic ordering is needed for display or tests, sort with an explicit comparator. Never snapshot a `Set` iteration order and treat it as a contract.

## 5. Java 17 Program: One Date, Multiple Calendars, Unchanged EPOCH_DAY

The main example uses a **fixed date**, never `dateNow()`, so output does not depend on the system clock or time zone.

Create the file `ChronologyDemo.java`:

```java
import java.time.LocalDate;
import java.time.chrono.ChronoLocalDate;
import java.time.chrono.JapaneseChronology;
import java.time.chrono.JapaneseEra;
import java.time.chrono.MinguoChronology;
import java.time.chrono.ThaiBuddhistChronology;
import java.time.temporal.ChronoField;

public class ChronologyDemo {
    public static void main(String[] args) {
        LocalDate iso = LocalDate.of(2026, 10, 28);

        ChronoLocalDate thai =
                ThaiBuddhistChronology.INSTANCE.date(iso);
        ChronoLocalDate minguo =
                MinguoChronology.INSTANCE.date(iso);
        ChronoLocalDate japanese =
                JapaneseChronology.INSTANCE.date(iso);

        System.out.println("ISO=" + iso);
        System.out.println("Thai-year=" +
                thai.get(ChronoField.YEAR));
        System.out.println("Minguo-year=" +
                minguo.get(ChronoField.YEAR_OF_ERA));
        System.out.println("Japanese-Reiwa=" +
                japanese.getEra().equals(JapaneseEra.REIWA));
        System.out.println("Japanese-year-of-era=" +
                japanese.get(ChronoField.YEAR_OF_ERA));

        System.out.println("same-day=" +
                (iso.toEpochDay() == thai.toEpochDay()
                && iso.toEpochDay() == minguo.toEpochDay()
                && iso.toEpochDay() == japanese.toEpochDay()));

        System.out.println("back-to-ISO=" +
                LocalDate.from(thai));
    }
}
```

Compile and run with JDK 17+:

```bash
javac -encoding UTF-8 ChronologyDemo.java
java ChronologyDemo
```

Deterministic stdout:

```text
ISO=2026-10-28
Thai-year=2569
Minguo-year=115
Japanese-Reiwa=true
Japanese-year-of-era=8
same-day=true
back-to-ISO=2026-10-28
```

**Interpreting the output:**

- `Thai-year=2569`: year in the Thai chronology.
- `Minguo-year=115`: corresponding Minguo year.
- `Japanese-Reiwa=true` and `Japanese-year-of-era=8`: the same day in the Japanese era.
- `same-day=true`: all objects point to **the same epoch-day**, with no shift of the physical date.
- `back-to-ISO=2026-10-28`: `LocalDate.from(ChronoLocalDate)` converts the representation back to ISO while preserving the exact day.

If an application uses another calendar only to **display** year numbers, do not rewrite ISO date columns in the database to 2569 or 115. Store canonical dates and switch chronology only at the presentation boundary, unless the business domain genuinely requires storing the user's native calendar.

## 6. YEAR, YEAR_OF_ERA, and ERA: Three Non-Interchangeable Fields

These fields in `java.time.temporal.ChronoField` are especially important:

| Field | Meaning |
| --- | --- |
| `YEAR` | Proleptic year on the current chronology's timeline |
| `YEAR_OF_ERA` | Year **within an era**, typically resetting to 1 when a new era begins |
| `ERA` | Identifier of the corresponding era |
| `MONTH_OF_YEAR` | Month in the current calendar |
| `DAY_OF_MONTH` | Day of the month in the current calendar |
| `EPOCH_DAY` | Day count on the shared timeline, used to convert between chronologies |

In the Japanese calendar, Reiwa 8 must be accompanied by **Reiwa** to be fully specified. If a pattern has only `"y/MM/dd"` without era `G`, the output looks plausible yet omits the era needed to disambiguate the year. Likewise, patterns must not assume `YEAR_OF_ERA` always equals the ISO year.

Example formatter expressing era and year structure:

```java
DateTimeFormatter japaneseDisplay =
        DateTimeFormatter.ofPattern("G y/MM/dd", Locale.JAPAN)
                .withChronology(JapaneseChronology.INSTANCE);
```

This snippet is used inside a method with imports `java.time.format.DateTimeFormatter`, `java.time.chrono.JapaneseChronology`, and `java.util.Locale`. When formatting ISO date 2026-10-28, the pattern includes **the Japanese era name/symbol, year-of-era, month, and day**. Exact era text can depend on the JDK's locale data, so no single hardcoded Japanese stdout string is prescribed here.

**Pattern letter note:** in `DateTimeFormatter`, `G` is era, `y` is year-of-era, and `u` is proleptic year. Patterns `"uuuu-MM-dd"` and `"G y-MM-dd"` do not share the same meaning. `Y` is **week-based-year** and must not replace `u` or `y` when outputting ordinary calendar dates.

## 7. DateTimeFormatter.withChronology: Switching Calendars for Formatting and Parsing

`DateTimeFormatter.withChronology(chrono)` returns a **new formatter** with a chronology override. When formatting a date-bearing object, the formatter converts the date into the requested chronology before building the string, **without altering the source date's epoch-day**.

For example, displaying an ISO date in the Thai calendar:

```java
LocalDate date = LocalDate.of(2026, 10, 28);

DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern("uuuu-MM-dd", Locale.ROOT)
                .withChronology(ThaiBuddhistChronology.INSTANCE);

String text = formatter.format(date); // "2569-10-28"
```

This is an in-method snippet requiring imports `java.time.LocalDate`, `java.time.format.DateTimeFormatter`, `java.time.chrono.ThaiBuddhistChronology`, and `java.util.Locale`. The year digits reflect the **chronology**, not merely the `Locale`.

To follow a **localized date style** per locale, you can use:

```java
DateTimeFormatter thaiLocalized =
        DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG)
                .withLocale(Locale.forLanguageTag("th-TH"))
                .withChronology(ThaiBuddhistChronology.INSTANCE);
```

This lets Java pick the pattern from the locale/`FormatStyle` and apply the Thai chronology. Month names, era names, and rendering details depend on locale/JDK/CLDR data. `DateTimeFormatter.ofLocalizedDate` itself is created with the ISO chronology; **you must override the chronology explicitly** if the product wants another calendar system.

### 7.1. withLocale differs from withChronology

| Operation | What It Changes | What It Does NOT Automatically Change |
| --- | --- | --- |
| `withLocale(Locale.JAPAN)` | Locale for localized patterns/text | Does not force chronology to Japanese |
| `withChronology(JapaneseChronology.INSTANCE)` | Calendar used to interpret date fields | Does not switch language to Japanese |
| `withZone(ZoneId.of("Asia/Tokyo"))` | Zone for instants or temporals with time info | Does not pick Japanese calendar |
| `withDecimalStyle(DecimalStyle.of(locale))` | Digit/decimal symbols per decimal style | Does not infer chronology |
| `localizedBy(locale)` | Can read Unicode locale extensions including calendar `ca` | Not a simple synonym for `withLocale` |

A practical UI preference set may keep `languageLocale`, `calendarChronology`, and `zoneId` independent. Never assume Japanese users always want the Japanese imperial calendar or Thai users always want the Buddhist calendar.

### 7.2. Standalone example of formatter chronology

File `ChronologyFormatDemo.java`:

```java
import java.time.LocalDate;
import java.time.chrono.IsoChronology;
import java.time.chrono.ThaiBuddhistChronology;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class ChronologyFormatDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2026, 10, 28);

        DateTimeFormatter base =
                DateTimeFormatter.ofPattern(
                        "uuuu-MM-dd", Locale.ROOT);

        DateTimeFormatter thai =
                base.withChronology(ThaiBuddhistChronology.INSTANCE);
        DateTimeFormatter iso =
                base.withChronology(IsoChronology.INSTANCE);

        System.out.println("source=" + date);
        System.out.println("iso=" + iso.format(date));
        System.out.println("thai=" + thai.format(date));
        System.out.println("source-after=" + date);
    }
}
```

```bash
javac -encoding UTF-8 ChronologyFormatDemo.java
java ChronologyFormatDemo
```

Stdout:

```text
source=2026-10-28
iso=2026-10-28
thai=2569-10-28
source-after=2026-10-28
```

`base` is an immutable formatter. `withChronology` returns a new instance, so formatting in the Thai calendar **mutates neither the original `LocalDate` nor the ISO formatter**.

## 8. Selecting Chronology via Locale and Unicode Extension ca

A `Locale` can carry the Unicode locale extension `u-ca-...`, where `ca` specifies the calendar. Java supports:

```java
Chronology selected = Chronology.ofLocale(locale);
```

**Major pitfall:** `Chronology.ofLocale(Locale.forLanguageTag("th-TH"))` **does not automatically return ThaiBuddhist** just because the region is Thailand. When a locale does not explicitly specify a calendar, the API normally returns `IsoChronology`. To select the Thai calendar explicitly, use `th-TH-u-ca-buddhist`.

Similarly:

| Locale | Meaning |
| --- | --- |
| `en-US` | English in the United States; no non-ISO calendar requested |
| `th-TH` | Thai in Thailand; **does not implicitly specify Buddhist calendar** to `Chronology.ofLocale` |
| `th-TH-u-ca-buddhist` | Thai in Thailand, explicitly requesting the Buddhist calendar |
| `ja-JP-u-ca-japanese` | Japanese in Japan, explicitly requesting the Japanese calendar |
| `en-US-u-ca-roc` | English in the United States, requesting the Minguo/ROC calendar |

Java 17 example:

File `ChronologyLocaleDemo.java`:

```java
import java.time.chrono.Chronology;
import java.util.Locale;

public class ChronologyLocaleDemo {
    public static void main(String[] args) {
        Locale plain = Locale.forLanguageTag("th-TH");
        Locale explicit = Locale.forLanguageTag(
                "th-TH-u-ca-buddhist");
        Locale japan = Locale.forLanguageTag(
                "ja-JP-u-ca-japanese");

        System.out.println("plain=" +
                Chronology.ofLocale(plain).getId());
        System.out.println("buddhist=" +
                Chronology.ofLocale(explicit).getId());
        System.out.println("japanese=" +
                Chronology.ofLocale(japan).getId());
    }
}
```

```bash
javac -encoding UTF-8 ChronologyLocaleDemo.java
java ChronologyLocaleDemo
```

Stdout on standard JDK 17:

```text
plain=ISO
buddhist=ThaiBuddhist
japanese=Japanese
```

`Chronology.ofLocale` can throw `DateTimeException` if `ca` requests a chronology unsupported by the runtime. Enforce a supported-calendars policy and product error/fallback handling; never accept arbitrary calendar tags without validation.

### 8.1. withLocale is not localizedBy

`DateTimeFormatter.withLocale(...)` updates the locale used to select translated text/formatting conventions, without automatically applying the calendar from `u-ca`. `DateTimeFormatter.localizedBy(locale)` is a separate API (Java 10+) that can apply the calendar from the `ca` extension along with other supported extensions such as numbering system `nu` and time zone `tz`.

For applications requiring a specific calendar, two clear approaches are:

- Resolve `Chronology.ofLocale(locale)` and call `formatter.withChronology(chronology)`.
- Use `formatter.localizedBy(locale)` when you want to honor supported Unicode locale extensions and understand override precedence.

In systems needing strict control over history and storage logic, selecting the chronology **explicitly from business configuration** is usually clearer than relying solely on the user's locale tag.

## 9. Parsing Non-ISO Dates: Data and Pattern Must Share the Calendar System

When parsing a date with Thai Buddhist year `2569`, never call ISO `LocalDate.parse("2569-10-28")` expecting 2026. The ISO parser interprets **ISO year 2569**, which is an entirely different date.

To read a date in another calendar, create a formatter with the matching chronology:

File `ChronologyParsingDemo.java`:

```java
import java.time.LocalDate;
import java.time.chrono.ChronoLocalDate;
import java.time.chrono.ThaiBuddhistChronology;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.Locale;

public class ChronologyParsingDemo {
    public static void main(String[] args) {
        DateTimeFormatter thaiParser =
                DateTimeFormatter.ofPattern(
                        "uuuu-MM-dd", Locale.ROOT)
                        .withChronology(ThaiBuddhistChronology.INSTANCE)
                        .withResolverStyle(ResolverStyle.STRICT);

        ChronoLocalDate thaiDate =
                ThaiBuddhistChronology.INSTANCE.date(
                        thaiParser.parse("2569-10-28"));

        LocalDate sameDayInIso = LocalDate.from(thaiDate);

        System.out.println("thaiYear=" +
                thaiDate.get(java.time.temporal.ChronoField.YEAR));
        System.out.println("iso=" + sameDayInIso);
        System.out.println("roundTrip=" +
                thaiParser.format(thaiDate));
    }
}
```

Run:

```bash
javac -encoding UTF-8 ChronologyParsingDemo.java
java ChronologyParsingDemo
```

Stdout:

```text
thaiYear=2569
iso=2026-10-28
roundTrip=2569-10-28
```

When the parser has a chronology override, date fields are resolved according to that chronology. `ResolverStyle.STRICT` rejects dates that are invalid under the requested calendar system. Use pattern `uuuu` for proleptic year during strict testing; `yyyy` is year-of-era and may additionally require `G` or explicit era rules.

**Semantic note:** `2569-10-28` could be a future ISO date or a Thai Buddhist date matching ISO 2026. A numeric string **without calendar metadata** is insufficient to determine its meaning. In machine protocols, include the calendar ID if non-ISO, or standardize on ISO dates with a clear contract.

### 9.1. Parsing Japanese eras

In the Japanese calendar, a string like `"Reiwa 8/10/28"` (shown with English text for illustration) contains **era**, **year-of-era**, and month/day. To parse reliably, use a formatter with the Japanese chronology, a locale matching the era text, a pattern such as `"G y/M/d"`, and an appropriate resolver; never parse year 8 as ISO year 0008. Era names can vary by locale/JDK, so test with the real formatter or use standard era codes in contracts rather than hand-crafted strings.

### 9.2. Parsing Hijrah

In the Hijrah calendar, month lengths can differ from ISO and the calendar data source may have range limits. Never parse under ISO and apply a manual year-offset formula. Use `HijrahChronology` for the chosen variant, check for `DateTimeException`/`DateTimeParseException`, and verify the deployed calendar data.

## 10. Chronology, Locale, and ZoneId Are Not Interchangeable

Consider a timestamp:

```text
Instant: 2026-10-28T07:30:00Z
```

An application might display this instant in `Asia/Ho_Chi_Minh` or `Asia/Tokyo`. Choosing `ZoneId` changes the **local wall-clock date and time**. Choosing `Chronology` changes the **era name and calendar year/month/day numbers**. Choosing `Locale` changes the **language and string formatting conventions**.

One way to visualize this:

```text
                   Source Instant (UTC)
                           |
                    +------v------+
                    |   ZoneId    |  Choose local date/time
                    +------v------+
                           |
                      LocalDate
                           |
                    +------v------+
                    | Chronology  |  Choose calendar system for this date
                    +------v------+
                           |
                   ChronoLocalDate
                           |
                    +------v------+
                    | Locale +    |  Era/month names, display pattern
                    | Formatter   |
                    +------v------+
                           |
                   Text for the user
```

For calendar systems with different day boundaries or religious date-determination rules, display and semantics can be more nuanced than this simplified diagram. In all cases, **never infer ZoneId from Chronology**, and never infer Chronology from a language-region locale when the user has not chosen a calendar.

## 11. Storage and APIs: Which Canonical Form Should You Choose?

Systems that compare dates, compute durations, and communicate across services are far easier to maintain when storing:

- Pure dates (birth dates, due dates in the ISO calendar): `LocalDate` or standard ISO-8601 dates such as `2026-10-28`.
- Absolute points in time: `Instant` / timestamps with explicit offsets in APIs.
- Local wall-clock events: local date/time paired with `ZoneId` when business rules require it.

The user's calendar is **interpretation and presentation metadata**; you can store it in the user profile or a separate field, e.g., `calendarType=buddhist`. If Hijrah input is primary domain data with distinct business significance, store the **calendar ID/variant, individual date fields, and conversion rules/data version** as needed for traceability; never discard source information merely because an ISO conversion was computed.

Illustrative contract example:

```json
{
  "canonicalDate": "2026-10-28",
  "displayCalendar": "buddhist",
  "displayLocale": "th-TH",
  "displayZone": "Asia/Bangkok"
}
```

This is a **data-design example**, not default JSON automatically serialized by `java.time`. Keep the canonical date separate from calendar and region preferences. `displayCalendar=buddhist` does not mean `canonicalDate` holds year 2569; it instructs the application to **present** the underlying date using the Thai chronology.

### Comparing and sorting dates across chronologies

If you have two `ChronoLocalDate` instances from **different calendar systems** and want to compare which occurs earlier, use `ChronoLocalDate.timeLineOrder()` or convert to `EPOCH_DAY`/`LocalDate`. `ChronoLocalDate.compareTo` also factors in the chronology to give a total order in heterogeneous structures; therefore, do not treat `compareTo == 0` as the sole test for "same epoch-day" across different calendar types.

Example:

```java
boolean samePhysicalDay =
        iso.toEpochDay() == thai.toEpochDay();

int chronologicalOrder =
        ChronoLocalDate.timeLineOrder().compare(iso, thai);
```

This snippet belongs inside a method where `iso` is a `LocalDate` and `thai` is a `ChronoLocalDate`. When they share the same epoch-day, `chronologicalOrder` is 0 even though their chronologies differ.

### Date arithmetic and terms

Do not assume `ChronoPeriod`, `Period`, adding months, or computing "one year" are always equivalent across calendars. In Hijrah, month lengths can differ from ISO; in the Japanese chronology, mid-year era transitions follow specific rules. If a contract specifies **ISO date + N days**, perform the arithmetic on `LocalDate`/`ChronoUnit.DAYS` per the contract. If the domain says "the next month in the Hijrah calendar", use that calendar's chronology and month rules. **Never put business logic inside a formatter.**

## 12. Common Mistakes

| Mistake | Why It Is Wrong | How to Handle It |
| --- | --- | --- |
| Assuming `Locale.JAPAN` picks the Japanese era calendar | Language/region locale does not force chronology | Specify `JapaneseChronology` or `u-ca-japanese` explicitly |
| Assuming `th-TH` returns `ThaiBuddhistChronology` | `Chronology.ofLocale` defaults to ISO without `ca` | Use `th-TH-u-ca-buddhist` when truly needed |
| Storing `2569-10-28` while API expects ISO | Year has a different semantic meaning | Include calendar metadata or canonical ISO |
| Adding `543` years to `LocalDate` to "convert" to Thai calendar | Shifts the actual date on the timeline | Use `ThaiBuddhistChronology.INSTANCE.date(iso)` |
| Parsing Reiwa 8 as ISO year 8 | Loses the era | Use `G`, `y`, and Japanese chronology |
| Confusing `y` and `u` | Year-of-era differs from proleptic year | Pick the pattern letter matching the field's meaning |
| Treating `Y` as calendar year | `Y` is week-based-year | Use `u`/`y` as required |
| Computing Hijrah dates via a fixed year offset | Lunar calendar does not match ISO | Use `HijrahChronology` with the specified variant |
| Calling `dateNow()` in tests needing fixed output | Depends on clock/time zone | Use fixed dates or `Clock` |
| Concluding two `ChronoLocalDate` objects from different calendars are different dates | They may share the same `EPOCH_DAY` | Compare epoch-day or `timeLineOrder` |
| Calling `withLocale` and assuming chronology changed | `withLocale` only sets locale | Use `withChronology` or `localizedBy` with `ca` |
| Assuming every chronology has 12 ISO-like months | Not every calendar shares the same structure | Rely on `Chronology` and actual temporal fields |
| Switching chronology without checking date bounds | Japanese/Hijrah have supported range limits | Catch exceptions and validate inputs |
| Hardcoding era names or month strings | Locale data and era boundaries can change | Use formatters, locale data, and tests |

## 13. Proper Functional Testing

### 13.1. Verify date identity

Using `LocalDate.of(2026, 10, 28)`, construct `JapaneseDate`, `MinguoDate`, and `ThaiBuddhistDate` and assert that all share the same `EPOCH_DAY`. This is **semantic** testing, far more reliable than comparing `toString()` outputs across calendars.

### 13.2. Test eras and boundaries

Test Japanese era transitions, such as **2019-04-30** as the end of Heisei and **2019-05-01** as the start of Reiwa. When parsing `YEAR_OF_ERA`, require the matching era; never stuff an era name or year-of-era into an ISO year column.

### 13.3. Inspect available calendars at runtime

Run `Chronology.getAvailableChronologies()` in the deployment environment. Sort by `getId()` for deterministic logs if needed. For unsupported `u-ca` locale extensions, handle the error explicitly rather than silently falling back to a different chronology.

### 13.4. Test localization

Create an `ofLocalizedDate(FormatStyle.LONG)` formatter with `Locale.JAPAN` and the Japanese chronology, and compare against `IsoChronology`. Avoid asserting exact text across different JDKs unless the data provider is pinned; era names, spaces, or digit styles can vary.

### 13.5. Test strict parsing

Parse a Thai Buddhist date using a formatter with `withChronology(ThaiBuddhistChronology.INSTANCE)` and `ResolverStyle.STRICT`; convert back to ISO via `LocalDate.from(...)` and verify the same epoch-day. Also test nonexistent calendar dates, missing Japanese eras, unsupported calendar IDs, and out-of-range dates.

### 13.6. Test business data invariants

If calendars are used solely for UI localization, verify that **changing the calendar never alters orders, due dates, or canonical birth dates**. If the domain genuinely uses lunar or era-based calendars as contractual truth, document the calendar variant, term-calculation rules, and calendar-data updates; review with domain experts when necessary.

## 14. Practice Exercises and Answers

**Exercise 1.** For `LocalDate.of(2026, 10, 28)`, what year does the Thai Buddhist calendar give? Can you use `plusYears(543)` to "convert calendars"?

**Answer:** Year 2569. Do not use `plusYears(543)` because that shifts the physical date; use `ThaiBuddhistChronology.INSTANCE.date(iso)` to represent the **same epoch-day**.

**Exercise 2.** What chronology does `Chronology.ofLocale(Locale.forLanguageTag("th-TH"))` return on JDK 17? Which locale tag explicitly requests Buddhist?

**Answer:** ISO by default; use `th-TH-u-ca-buddhist` to explicitly request the Thai Buddhist calendar.

**Exercise 3.** Why does a `JapaneseDate` for Reiwa 8 require the era when parsing?

**Answer:** The number 8 is the year within an era, not an ISO year. Multiple eras can have a year 8; without the era, a Japanese calendar date is underdetermined.

**Exercise 4.** For ISO 2026-10-28, what year does the Minguo calendar give?

**Answer:** Minguo year 115, since Minguo year 1 corresponds to ISO 1912.

**Exercise 5.** Does `withLocale(Locale.JAPAN)` automatically switch ISO chronology to Japanese?

**Answer:** No. Use `withChronology(JapaneseChronology.INSTANCE)` or a chronology explicitly resolved from a locale containing the `u-ca-japanese` extension.

**Exercise 6.** You need to check whether two `ChronoLocalDate` objects from different calendar systems refer to the same physical day. What should you compare?

**Answer:** Compare `toEpochDay()` or use `ChronoLocalDate.timeLineOrder()`; do not compare raw `YEAR`, month, and day numbers directly.

**Exercise 7.** Why can't you convert a Hijrah date to ISO by subtracting a fixed number from the year?

**Answer:** Because Hijrah is a lunar calendar whose month and year rules differ from ISO; you need the chronology/variant and valid calendar data.

**Exercise 8.** Does `DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG).withLocale(Locale.JAPAN)` guarantee the date displays in Japanese imperial eras?

**Answer:** No, localized formatters default to ISO chronology. To display Japanese eras, attach the Japanese chronology and use an appropriate pattern/style that renders the era.

## 15. Summary

- **`Chronology` models a calendar system**, while `Locale` describes language/region and `ZoneId` describes a time zone.
- Java 17 includes built-in **ISO, Japanese, Minguo, ThaiBuddhist, and Hijrah**; the runtime can be extended with additional providers.
- **Same day, different years:** ISO 2026 corresponds to Thai Buddhist 2569, Minguo 115, and Japanese Reiwa 8 in the 2026-10-28 example.
- **Never add/subtract years manually to convert calendars**; use `Chronology.date(isoDate)`, `dateEpochDay`, or formatter `withChronology`.
- Select calendars explicitly via `Chronology.of(...)`, `INSTANCE`, or `Chronology.ofLocale(locale with `u-ca-...`)`. A plain language-region tag does not select a non-ISO calendar.
- **Era and year-of-era carry essential meaning**, especially in the Japanese chronology; include `G y` when displaying era-based years.
- For applications that primarily need ISO, store and compute with `LocalDate`/`Instant` and **switch chronology at the UI boundary**. Domains truly governed by lunar calendars must manage calendar variants and dedicated rules.
- When parsing non-ISO strings, use the matching chronology and test STRICT mode; compare dates across calendars using `EPOCH_DAY`.

### Official Java 17 References

- [java.time.chrono — Oracle JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/chrono/package-summary.html)
- [Chronology — Oracle JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/chrono/Chronology.html)
- [ChronoLocalDate — Oracle JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/chrono/ChronoLocalDate.html)
- [DateTimeFormatter — Oracle JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html)
