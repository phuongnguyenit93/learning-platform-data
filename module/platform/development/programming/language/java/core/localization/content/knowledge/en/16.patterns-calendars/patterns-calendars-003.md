# Formatting 12-Hour, 24-Hour, and Day-Period Markers in Java

## 1. The Problem: One Moment in Time, Multiple Ways to Write the Hour

The time 13 hours and 05 minutes on a 24-hour clock can be written as **13:05**, **1:05 PM**, or a localized day-period expression such as **1:05 in the afternoon**. These notations are not necessarily in the same language, yet all can describe **13:05 in the same time zone**.

In a localized application, you need to answer three distinct questions:

1. Is the user accustomed to a **12-hour or 24-hour clock**?
2. If using a 12-hour clock, which **locale** governs how **AM/PM markers** or phrases like "in the morning", "in the afternoon", and "at night" are presented?
3. Which **region's local time** is the hour being formatted for? A locale does not determine the time zone by itself.

Java 17+ uses `java.time.format.DateTimeFormatter` to format time. The patterns `H`, `h`, `k`, `K`, `a`, and `B` address the first two questions. `ZoneId` and temporal types such as `ZonedDateTime` address the third question.

**Goal:** clearly distinguish the hour field types, choose the right pattern, use an explicit `Locale`, test midnight and noon, understand day-period markers, parse safely, and avoid turning display formats into business rules.

## 2. Two Ways to Number Hours

### The 24-hour system

The 24-hour system typically represents hours of the day from **00** to **23**:

| Hour value in `LocalTime` | Written as `HH:mm` |
| ---: | --- |
| `00:00` | `00:00` |
| `09:30` | `09:30` |
| `12:00` | `12:00` |
| `13:05` | `13:05` |
| `23:45` | `23:45` |

`HH` produces two digits: `09` instead of `9`. `H` does not force a leading zero. For example, `"H:mm"` can print `"9:30"`, whereas `"HH:mm"` prints `"09:30"`.

### The 12-hour system

The 12-hour clock uses the numbers **1 through 12**, paired with a day-period marker:

| Actual time | `hh:mm a` with `Locale.US` |
| --- | --- |
| `00:00` | `12:00 AM` |
| `00:05` | `12:05 AM` |
| `09:30` | `09:30 AM` |
| `11:59` | `11:59 AM` |
| `12:00` | `12:00 PM` |
| `13:05` | `01:05 PM` |
| `23:45` | `11:45 PM` |

On a 12-hour clock, `12:00 AM` is **midnight**, while `12:00 PM` is **noon**. This pair is easy to confuse, so when users are less familiar with the 12-hour system, UIs may choose `00:00`, `12:00`, or clearer phrasing.

`hh` also adds a leading zero: `01:05 PM`; `h` prints `1:05 PM`. Both represent the 12-hour clock hour, differing only in display width.

## 3. Key Pattern Letters in DateTimeFormatter

| Pattern | `java.time` Field | Meaning & Range | Example at 00:00 |
| --- | --- | --- | --- |
| `H` / `HH` | Hour of day | 0–23 | `0` / `00` |
| `k` / `kk` | Clock-hour of day | 1–24 | `24` / `24` |
| `h` / `hh` | Clock-hour of AM/PM | 1–12 | `12` / `12` |
| `K` / `KK` | Hour of AM/PM | 0–11 | `0` / `00` |
| `a` | AM/PM of day | Marker for the two halves of the day | `AM` with `Locale.US` |
| `B` | Period of day | Locale-specific day period | Can be `midnight` in US |
| `m` / `mm` | Minute of hour | Minutes 0–59 | `0` / `00` |
| `s` / `ss` | Second of minute | Seconds 0–59 | `0` / `00` |

Commonly used patterns:

```text
HH:mm        13:05
H:mm         13:05
hh:mm a      01:05 PM
h:mm a       1:05 PM
h:mm B       1:05 in the afternoon   (Locale.US)
kk:mm        13:05
KK:mm a      01:05 PM               (not the usual h representation)
```

**Special caution:** `K` and `h` are **not equivalent**. At 13:05, `h` is `1`, and `K` is also `1`; looking at only one example makes them easy to confuse. At 12:00, `h` is `12`, while `K` is `0`. Similarly, `k` is **24** at `00:00`, whereas `H` is **0**.

Do not use `a` alone to infer an exact hour; it only provides the AM/PM half. Do not use `h` to display hours without `a`/a period marker if users need to distinguish morning from afternoon: `"1:05"` alone can be ambiguous.

## 4. Java 17+ Program Demonstrating 12-Hour and 24-Hour Formats

Create the file `ClockFormatDemo.java`:

```java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class ClockFormatDemo {
    public static void main(String[] args) {
        DateTimeFormatter twentyFour =
                DateTimeFormatter.ofPattern("HH:mm", Locale.US);
        DateTimeFormatter twelve =
                DateTimeFormatter.ofPattern("hh:mm a", Locale.US);

        LocalTime[] times = {
                LocalTime.MIDNIGHT,
                LocalTime.of(9, 30),
                LocalTime.NOON,
                LocalTime.of(13, 5),
                LocalTime.of(23, 45)
        };

        for (LocalTime time : times) {
            System.out.println(
                    twentyFour.format(time)
                    + " -> " + twelve.format(time));
        }
    }
}
```

Save as UTF-8 and run:

```bash
javac -encoding UTF-8 ClockFormatDemo.java
java ClockFormatDemo
```

Stdout:

```text
00:00 -> 12:00 AM
09:30 -> 09:30 AM
12:00 -> 12:00 PM
13:05 -> 01:05 PM
23:45 -> 11:45 PM
```

`LocalTime` stores **hour and minute**, not a 12/24-hour formatting preference. `DateTimeFormatter` changes the presentation without modifying `LocalTime`. By explicitly passing `Locale.US`, the example does not depend on the OS default locale when displaying `AM` and `PM`.

If you call `DateTimeFormatter.ofPattern("hh:mm a")` without a `Locale`, Java uses the appropriate default locale at the time the formatter is created. A server with a different locale may produce a different string. In multi-user applications, passing `Locale` for each display context is critical.

## 5. Comparing the Four Hour Representations: H, k, h, K

These four letters cause logic bugs more easily than syntax errors. Know their value ranges:

```java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class HourFieldsDemo {
    public static void main(String[] args) {
        DateTimeFormatter fields =
                DateTimeFormatter.ofPattern("H k K h a", Locale.US);

        for (LocalTime time : new LocalTime[] {
                LocalTime.MIDNIGHT,
                LocalTime.NOON,
                LocalTime.of(23, 45)}) {
            System.out.println(time + " -> "
                    + fields.format(time));
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 HourFieldsDemo.java
java HourFieldsDemo
```

Stdout:

```text
00:00 -> 0 24 0 12 AM
12:00 -> 12 12 0 12 PM
23:45 -> 23 23 11 11 PM
```

Essence:

- **`H`** — hours since midnight on a 0–23 scale. This is the standard choice for 24-hour clocks.
- **`k`** — clock-hour-of-day 1–24, displaying midnight as `24`; most standard UIs **do not** use this style because `24:00` can be interpreted as the end-of-day boundary into the next day.
- **`h`** — clock-hour-of-am-pm 1–12, displaying both midnight and noon as 12; requires AM/PM or other context to distinguish them.
- **`K`** — hour-of-am-pm 0–11; both midnight and noon are 0. This is not the usual choice for user-facing 12-hour clock labels.

If you need a **00:00-style 24-hour clock**, use `HH:mm`, not `kk:mm`. If you need a **1:05 PM-style 12-hour clock**, use `h:mm a`; if you need fixed two-digit hours, use `hh:mm a`.

## 6. AM/PM Markers Localized via Locale

The pattern letter `a` represents **AM/PM of day**, but the printed text is **not necessarily the two English words AM/PM** in every locale.

Program `AmPmLocaleDemo.java`:

```java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class AmPmLocaleDemo {
    public static void main(String[] args) {
        DateTimeFormatter us =
                DateTimeFormatter.ofPattern("hh:mm a", Locale.US);
        DateTimeFormatter vi =
                us.withLocale(Locale.forLanguageTag("vi-VN"));

        LocalTime morning = LocalTime.of(9, 30);
        LocalTime afternoon = LocalTime.of(13, 5);

        System.out.println("US morning: " + us.format(morning));
        System.out.println("US afternoon: " + us.format(afternoon));
        System.out.println("VI morning: " + vi.format(morning));
        System.out.println("VI afternoon: " + vi.format(afternoon));
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 AmPmLocaleDemo.java
java AmPmLocaleDemo
```

Example stdout with locale data tested on OpenJDK 24:

```text
US morning: 09:30 AM
US afternoon: 01:05 PM
VI morning: 09:30 SA
VI afternoon: 01:05 CH
```

In this example, Vietnamese locale data uses `SA` and `CH` corresponding to morning/afternoon. Localized data can vary by JDK version, CLDR source, or locale provider, so do not turn those exact two abbreviations into a rigid contract across all Java releases.

`withLocale` creates a **new formatter**; it does not mutate the `us` formatter. `DateTimeFormatter` is immutable and thread-safe, so keeping a base formatter and creating per-locale copies is safer than changing JVM-wide default state on each request.

**Distinction:** the `a` marker is AM/PM, meaning **the two halves of the day**. It does not carry all natural-language nuances such as "morning, noon, afternoon, evening, night".

## 7. Flexible Day-Period Marker: `B`

In `DateTimeFormatter`, the pattern letter **`B`** represents the locale-specific *period-of-day*: it can produce text like "midnight", "in the morning", "noon", "in the afternoon", or "at night" in English data. This is a richer model than `a` (AM/PM).

Runnable example in Java 17+:

```java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class DayPeriodDemo {
    public static void main(String[] args) {
        DateTimeFormatter us =
                DateTimeFormatter.ofPattern("h:mm B", Locale.US);
        DateTimeFormatter vi = us.withLocale(
                Locale.forLanguageTag("vi-VN"));

        for (LocalTime time : new LocalTime[] {
                LocalTime.MIDNIGHT,
                LocalTime.of(9, 30),
                LocalTime.NOON,
                LocalTime.of(13, 5),
                LocalTime.of(23, 45)}) {

            System.out.println(time + " | "
                    + us.format(time) + " | "
                    + vi.format(time));
        }
    }
}
```

Save as `DayPeriodDemo.java`, then run:

```bash
javac -encoding UTF-8 DayPeriodDemo.java
java DayPeriodDemo
```

Verified stdout on OpenJDK 24/CLDR:

```text
00:00 | 12:00 midnight | 12:00 nửa đêm
09:30 | 9:30 in the morning | 9:30 sáng
12:00 | 12:00 noon | 12:00 trưa
13:05 | 1:05 in the afternoon | 1:05 chiều
23:45 | 11:45 at night | 11:45 đêm
```

Here `B` is text **supplied by locale data**. The cutoff boundaries for "morning", "noon", "afternoon", "evening", and "night" can vary across languages and CLDR data; do not write `if (hour < 12) "morning" else "evening"` yourself and assume it fits every language.

A string like `12:00 noon` can read slightly redundantly if users already understand 12 o'clock; a product may choose `h B` or a localized style depending on context. Do not force one pattern across every message and device without testing with real users.

**Important:** `B` does not promise that every locale provides the same number of day-period categories or the same hour boundaries. If the application enforces business rules such as "reservations allowed only in the morning", do not inspect the output of formatter `B` to enforce the constraint; store explicit start/end times per business rules.

## 8. Using Localized Time Styles: You Do Not Always Need Manual h, H, a

When you want to display time **according to the locale's conventions**, `DateTimeFormatter.ofLocalizedTime(style).withLocale(locale)` is often more suitable than manually writing `"hh:mm a"` or `"HH:mm"`.

Example:

```java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public class LocalizedClockDemo {
    public static void main(String[] args) {
        LocalTime time = LocalTime.of(13, 5);

        DateTimeFormatter base =
                DateTimeFormatter.ofLocalizedTime(FormatStyle.SHORT);

        Locale[] locales = {
                Locale.US,
                Locale.UK,
                Locale.forLanguageTag("vi-VN"),
                Locale.FRANCE
        };

        for (Locale locale : locales) {
            System.out.println(locale.toLanguageTag() + ": "
                    + base.withLocale(locale).format(time));
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 LocalizedClockDemo.java
java LocalizedClockDemo
```

Example output from OpenJDK 24:

```text
en-US: 1:05 PM
en-GB: 13:05
vi-VN: 13:05
fr-FR: 13:05
```

In the `en-US` line, the space before `PM` may be a **narrow no-break space** U+202F, not an ASCII space. This is a valid localization detail; do not rely on hardcoded string comparisons unless you control the provider/JDK. Locale data can change across runtimes and updated localization standards.

`FormatStyle.SHORT` requests a short presentation style. `MEDIUM`, `LONG`, and `FULL` may add seconds, time-zone identifiers, or other details depending on locale data; because some styles require a temporal with sufficient time-zone fields, do not assume every `LocalTime` can be formatted with every style.

**Recommended practices:**

- Use `ofLocalizedTime(FormatStyle.SHORT).withLocale(locale)` for UIs that should follow the locale's 12/24-hour convention.
- Use `ofPattern("HH:mm", locale)` if the product **mandates** a 24-hour interface, such as certain operations dashboards.
- Use `ofPattern("h:mm a", locale)` if the design mandates a 12-hour clock with AM/PM.
- Use `ofPattern("h:mm B", locale)` when natural locale-based day-period expressions are desired and tested.

Not everyone within the same locale prefers the same clock format. If the product offers a personal "12-hour/24-hour" setting, honor that setting first and use the locale only to derive the default when no user preference exists.

## 9. Parsing 12-Hour Strings: The Day Period Must Be Present

The input `"1:05"` without AM/PM does not contain enough information to tell 01:05 from 13:05. When parsing user data in 12-hour format, you need `a` (or an equivalent unambiguous rule) and the matching locale.

Standalone example `ParseClockDemo.java`:

```java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.time.format.DateTimeParseException;
import java.util.Locale;

public class ParseClockDemo {
    public static void main(String[] args) {
        DateTimeFormatter twelve =
                DateTimeFormatter.ofPattern("h:mm a", Locale.US)
                        .withResolverStyle(ResolverStyle.STRICT);

        System.out.println(
                "12 AM -> " + LocalTime.parse("12:00 AM", twelve));
        System.out.println(
                "12 PM -> " + LocalTime.parse("12:00 PM", twelve));
        System.out.println(
                "1 PM -> " + LocalTime.parse("1:05 PM", twelve));

        try {
            LocalTime.parse("00:30 AM", twelve);
        } catch (DateTimeParseException error) {
            System.out.println("Invalid 12-hour input");
        }
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 ParseClockDemo.java
java ParseClockDemo
```

Stdout:

```text
12 AM -> 00:00
12 PM -> 12:00
1 PM -> 13:05
Invalid 12-hour input
```

This is a key example of midnight/noon handling:

- `12:00 AM` is `LocalTime.MIDNIGHT`.
- `12:00 PM` is `LocalTime.NOON`.
- `1:05 PM` is `13:05`.
- `00:30 AM` is **not** a valid 12-hour clock-hour under `STRICT`; inputs with hour `00` should use the `H`/`HH` system.

When parsing AM/PM in Vietnamese strings, use the matching locale and the marker spelling supported by the JDK's parser, rather than always sending English `"AM"` and `"PM"`.

When reading data from an API, do not use a locale-specific string like `1:05 PM` if the API contract can use ISO `13:05:00`. Human-facing display formats do not need to become wire protocol formats.

## 10. Reading 24:00: Distinguishing `H` and `k` When Parsing

The characteristic of `k` is its **1–24** range. When formatting `LocalTime.MIDNIGHT`, `kk:mm` produces `24:00`, whereas `HH:mm` produces `00:00`.

With `ResolverStyle.STRICT`, an `HH:mm` formatter rejects `24:00` because `HOUR_OF_DAY` must be in 0–23. A `kk:mm` formatter can parse `24:00` into `LocalTime.MIDNIGHT`.

Example:

```java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;

public class MidnightParseDemo {
    public static void main(String[] args) {
        DateTimeFormatter hourOfDay =
                DateTimeFormatter.ofPattern("HH:mm", Locale.US)
                        .withResolverStyle(ResolverStyle.STRICT);

        DateTimeFormatter clockHour =
                DateTimeFormatter.ofPattern("kk:mm", Locale.US)
                        .withResolverStyle(ResolverStyle.STRICT);

        System.out.println(
                "k: " + LocalTime.parse("24:00", clockHour));

        try {
            LocalTime.parse("24:00", hourOfDay);
        } catch (DateTimeParseException error) {
            System.out.println("H: Invalid hour");
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 MidnightParseDemo.java
java MidnightParseDemo
```

Stdout:

```text
k: 00:00
H: Invalid hour
```

Even though `24:00` may appear in some schedule conventions to indicate end-of-day, do not assume `LocalTime` retains "next day" information. `LocalTime` only stores hour-minute within a day, and `00:00` carries no date. If the domain distinguishes **end-of-day 24:00** from **start-of-day 00:00**, you need a model that includes the date, boundary rules, or a dedicated domain object.

The Java API has different parsing modes: do not conflate conclusions from `ResolverStyle.STRICT` with defaults like `SMART`/`LENIENT` without testing. Input rules should be clearly defined and tested at the ingestion boundary.

## 11. Locale Is Not a Time Zone: Avoid Turning 13:05 into the Wrong Hour

An `Instant` is a point on the UTC timeline; to know what time it is in Vietnam or another country, you need a time zone:

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class TimeZoneClockDemo {
    public static void main(String[] args) {
        Instant instant = Instant.parse("2026-10-28T03:30:00Z");

        DateTimeFormatter clock =
                DateTimeFormatter.ofPattern(
                        "uuuu-MM-dd HH:mm XXX", Locale.US);

        System.out.println("UTC: " + clock
                .withZone(ZoneId.of("UTC")).format(instant));

        System.out.println("HCM: " + clock
                .withZone(ZoneId.of("Asia/Ho_Chi_Minh"))
                .format(instant));
    }
}
```

Run:

```bash
javac -encoding UTF-8 TimeZoneClockDemo.java
java TimeZoneClockDemo
```

Stdout:

```text
UTC: 2026-10-28 03:30 Z
HCM: 2026-10-28 10:30 +07:00
```

`Locale.US` here only governs text phrasing; the digits and offset remain unambiguous. Changing `Locale.US` to `vi-VN` **does not convert** the `Instant` from UTC to `Asia/Ho_Chi_Minh`. It is the `withZone` call that determines the actual time zone.

Conversely, `LocalTime.of(13, 5)` contains **neither** a time zone nor a date, so you cannot infer what UTC instant it corresponds to. When managing international meeting times, store an instant or zoned representation with sufficient information, and only then format it as a 12- or 24-hour clock according to the viewer's preference.

## 12. 12/24-Hour Selection in UI and Domain Logic

A clean design separates three layers:

1. **Data:** store `LocalTime`, `ZonedDateTime`, or `Instant` according to domain semantics; never store a plain `"1:05 PM"` string as the source of truth.
2. **Viewer settings:** locale, time zone, and 12/24-hour preference (if available).
3. **Presentation:** choose the corresponding formatter, then render the result.

Example compilable utility class without `main`:

```java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public final class ClockView {
    private ClockView() {}

    public static String display(
            LocalTime time, Locale locale, boolean use24Hour) {

        if (time == null || locale == null) {
            throw new IllegalArgumentException(
                    "time and locale must not be null");
        }

        String pattern = use24Hour ? "HH:mm" : "h:mm a";
        return DateTimeFormatter.ofPattern(pattern, locale)
                .format(time);
    }
}
```

Save `ClockView.java` and compile:

```bash
javac -encoding UTF-8 ClockView.java
```

This is a **utility class** with no `main`, so there is no stdout and it is not run with `java ClockView`. If no personal preference is set, you can use `ofLocalizedTime(FormatStyle.SHORT)` to follow the locale default; if an explicit preference exists, honor it.

Do not write in a request handler:

```java
Locale.setDefault(userLocale); // Avoid this approach.
```

`Locale.setDefault` mutates JVM-wide configuration and can affect other requests in a multi-threaded environment. `DateTimeFormatter.ofPattern(pattern, locale)` and `withLocale(locale)` let you choose per usage without touching global state.

For products offering a 12/24-hour toggle, **user settings** should take precedence; the locale is a default suggestion, not an absolute rule overriding individual preference.

## 13. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using `hh:mm` without `a` | Cannot tell morning from evening | Add `a` or use 24-hour format |
| Confusing `hh` with `HH` | 13:00 turns into 01:00, or vice versa | Choose 12- vs 24-hour explicitly |
| Confusing `k` with `H` | Midnight displays as `24:00` instead of `00:00` | Use `HH` for a 00–23 clock |
| Confusing `K` with `h` | Noon/midnight displays as `0` instead of `12` | Use `h` for a 1–12 clock |
| Assuming `a` always prints `AM`/`PM` | Display does not match localization | Pass `Locale` explicitly |
| Thinking `B` is just the two AM/PM halves | Misinterprets morning/noon/afternoon/night | Understand `B` is locale-aware period-of-day |
| Using `B` to determine operating hours | Policy shifts with CLDR updates | Store explicit business-hour rules |
| Calling `ofPattern(pattern)` without a locale | Relies on JVM default locale | Use the overload taking `Locale` |
| Hardcoding `"1:05 PM"` in JSON APIs | Protocol becomes language-dependent | Use ISO format / structured time types |
| Parsing `12:00 AM` as 12:00 | Off by 12 hours at midnight | Test the `12 AM` and `12 PM` pair |
| Parsing `24:00` as next day while storing only `LocalTime` | Date information is lost | Use a type/structure that includes date |
| Thinking Locale switches time zones | Displays wrong time offset | Select `ZoneId` separately |
| Forcing AM/PM onto every language | Unnatural, ignores user preference | Use localized style or 12/24 config |
| Hardcoding localized output strings in tests across all runtimes | False failures when CLDR updates | Test on target runtime or assert semantically |

**Remember:** day-period markers are **display data**, not business codes. A store that "opens in the morning" needs explicit start/end hours and a time zone, rather than checking a string like `"sáng"` generated by `DateTimeFormatter`.

## 14. Testing Strategy for Multilingual Applications

Use fixed test data rather than `LocalTime.now()` so stdout and assertions are reproducible.

A baseline test suite should cover:

- **Boundaries:** `00:00`, `00:05`, `11:59`, `12:00`, `12:01`, `13:05`, `23:45`.
- **12-hour:** `00:00` -> `12:00 AM`, `12:00` -> `12:00 PM`, `13:05` -> `01:05 PM` with `Locale.US`.
- **24-hour:** `00:00` -> `00:00`, `13:05` -> `13:05` with `HH:mm`.
- **`H/k/h/K` differences:** verify the output of `HourFieldsDemo` at midnight and noon.
- **Locale:** `a` and `B` render in the JDK data's language for `en-US`, `vi-VN`, and supported product locales.
- **Localized style:** one locale may use 12-hour while another uses 24-hour; do not assume every JDK returns the exact same whitespace character.
- **Parsing:** `12:00 AM` -> `00:00`, `12:00 PM` -> `12:00`; reject `00:30 AM` in strict 12-hour parsing.
- **`24:00`:** verify `HH:mm` vs `kk:mm` and the business policy for the next day.
- **Time zone:** the same `Instant` renders differently in `UTC` and `Asia/Ho_Chi_Minh`; independent of locale.
- **Concurrency:** never call `Locale.setDefault` per request; immutable formatters can be shared.
- **Readability:** respect the user's 12/24-hour preference, especially in regions with mixed conventions.

For tests that compare localized output directly, pin the JDK/locale provider version or test against the deployment environment. CLDR data can adjust day-period wording and whitespace characters; minor localization data changes do not mean a bug in time calculations.

## 15. Practice Exercises

1. Run `ClockFormatDemo`, adding `LocalTime.of(0, 5)` and `LocalTime.of(11, 59)`. Explain why `00:05` becomes `12:05 AM`.
2. Compare `HH:mm`, `H:mm`, `hh:mm a`, and `h:mm a` on `LocalTime.of(9, 3)` and `LocalTime.of(21, 3)`. Identify the effect of pattern letter counts.
3. Inspect `HourFieldsDemo` with `LocalTime.NOON`. Why are `K=0`, `h=12`, and `a=PM`?
4. Try `B` with `LocalTime.of(0, 0)`, `LocalTime.of(12, 0)`, and `LocalTime.of(20, 0)` for `Locale.US` and `vi-VN`. Compare against the JDK data in use.
5. Replace `FormatStyle.SHORT` with `MEDIUM` in `LocalizedClockDemo`; observe whether locales show seconds.
6. Parse `"01:05 PM"` and `"1:05 PM"` using `DateTimeFormatter.ofPattern("h:mm a", Locale.US)` (noting pattern width and related fields), then compare with `"hh:mm a"`.
7. Build a small app with `use24Hour` and `Locale` options. When toggling 12/24, verify the `LocalTime` data stays unchanged; only the rendered string changes.
8. Create a fixed `Instant`, convert it across at least two `ZoneId` values, and use the same locale to demonstrate that the hour difference belongs to the time zone, not the language.

## 16. Summary

To represent **24-hour time**, use `H`/`HH` for the 0–23 range; `k` is 1–24 so midnight can appear as `24:00`. To represent **12-hour time**, use `h`/`hh` for 1–12 and include `a` when AM/PM distinction is needed; `K` is the 0–11 field and should not arbitrarily replace `h`.

`a` denotes **AM/PM**, whereas `B` denotes the **flexible locale-aware period of day**. When UIs should follow local conventions, use `DateTimeFormatter.ofLocalizedTime(FormatStyle.SHORT).withLocale(locale)`; if the user has chosen an explicit 12/24-hour mode, honor that choice. Finally, remember that **locale controls formatting**, **time zone controls local wall-clock time**, and date-time data should be stored in semantically appropriate types.

## References

- [Oracle JDK 21 — DateTimeFormatter: Pattern Letters and Localized Styles](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html)
- [Oracle JDK 21 — LocalTime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalTime.html)
- [Oracle JDK 21 — ResolverStyle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/ResolverStyle.html)
- [Oracle JDK 21 — Locale](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.html)
- [Oracle JDK 21 — ZoneId](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZoneId.html)
