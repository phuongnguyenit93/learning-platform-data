# DateTimeFormatter.withLocale vs. localizedBy in Java

## 1. The Problem: Does Changing the Display Language Mean Changing Calendar, Digits, and Time Zone?

In Java localization, `java.time.format.DateTimeFormatter` supports both methods:

- `withLocale(Locale)`: returns a new formatter with the **locale used to select localized text and format patterns**.
- `localizedBy(Locale)`: returns a new formatter that can additionally apply **calendar (chronology), numbering system (decimal style), region, and time zone (zone)** from information in the locale, especially Unicode locale extensions.

The two methods are not synonymous, even though they sometimes produce identical strings when using a simple locale like `en-US` or `vi-VN` and the formatter has no overrides to replace.

**Practical difference:** `withLocale` is appropriate when the goal is *to keep the chosen instant/calendar/time zone and change only the language or format pattern*. `localizedBy` is appropriate when you want *to apply accepted extended localization preferences*, including calendar, numbering system, region override, or time zone. When the `Locale` carries `ca`, `nu`, `rg`, or `tz` in its language tag, the results can differ noticeably.

Do not treat a locale as domain time data. `Instant` stores a point on the timeline; `ZoneId` determines how local time is derived; `Chronology` determines the calendar system; `Locale` determines localization conventions. They are related, yet **cannot be used interchangeably**.

## 2. Both Methods Operate on an Immutable Formatter

`DateTimeFormatter` is **immutable** and thread-safe across threads. Both calls return a new formatter (or may reuse an instance when nothing changes), **without mutating** the original formatter:

~~~java
DateTimeFormatter base = DateTimeFormatter.ofPattern("d MMM uuuu", Locale.US);

DateTimeFormatter vietnamese =
        base.withLocale(Locale.forLanguageTag("vi-VN"));

DateTimeFormatter extended =
        base.localizedBy(Locale.forLanguageTag("vi-VN"));
~~~

This is an **illustrative snippet inside a method**, requiring imports for `java.time.format.DateTimeFormatter` and `java.util.Locale`. A complete program and verified output are in section 7.

| Aspect | `withLocale(locale)` | `localizedBy(locale)` |
| --- | --- | --- |
| Returns a new formatter without mutating `base` | Yes | Yes |
| Changes `getLocale()` | Yes | Yes |
| Affects month/day names and localized patterns | Yes | Yes |
| Changes `getChronology()` per Unicode `ca` | **Not** automatically | Potentially |
| Changes `getDecimalStyle()` per Unicode `nu` | **Not** automatically | Potentially |
| Changes `getZone()` per Unicode `tz` | **Not** automatically | Potentially |
| Considers region override `rg` when picking local data | Locale is stored and may be used on lookup | Can apply deeper into calendar/digits/zone per locale |
| Order relative to `withZone`, `withChronology`, `withDecimalStyle` | Updates only the locale field, preserving other overrides | **Can overwrite** previous overrides depending on call order |

The word "potentially" matters: `localizedBy` depends on **what data the locale provides** and what the runtime's locale provider supports. Not every locale specifies a calendar or time-zone override.

## 3. withLocale: Changing the Source of Localized Text and Patterns

Java SE 17 signature:

~~~java
DateTimeFormatter withLocale(Locale locale)
~~~

By the API contract, the locale is stored exactly as passed; the formatter uses it to look up localized elements such as month names, weekday names, and locale-specific date-time patterns. Existing overrides such as chronology, zone, and decimal style **are preserved**.

Illustrative example:

~~~java
LocalDate date = LocalDate.of(2024, 3, 1);
DateTimeFormatter english =
        DateTimeFormatter.ofPattern("d MMM uuuu", Locale.US);

String usText = english.format(date);
String viText = english.withLocale(
        Locale.forLanguageTag("vi-VN")).format(date);
~~~

The snippet above needs `import java.time.LocalDate;` along with the formatter/locale imports. Month names may appear as abbreviations per the JDK's CLDR data; avoid hardcoding output unless you control the environment. Both strings represent **the same date 2024-03-01**, while the month language can differ.

### 3.1. Localized styles are also affected by withLocale

The following factories create formatters by **style**, without fixing a literal text pattern at creation time:

~~~java
DateTimeFormatter dateStyle =
        DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG);

DateTimeFormatter us = dateStyle.withLocale(Locale.US);
DateTimeFormatter vietnam = dateStyle.withLocale(
        Locale.forLanguageTag("vi-VN"));
~~~

These are illustrative statements requiring `import java.time.format.FormatStyle;`. A formatter created by `ofLocalizedDate` uses the localized pattern matching the locale at format/parse time, and the pattern may be resolved **lazily**. Thus it is **incorrect** to say `withLocale` only translates month names without changing day/month/year order: with localized styles, the pattern itself also changes.

By contrast, a formatter created with `DateTimeFormatter.ofPattern("uuuu-MM-dd")` has a **fixed pattern structure**; `withLocale` does not convert it into US month/day/year order. To use regional date-time conventions, use `ofLocalizedDate`/`ofLocalizedDateTime` or a specifically designed pattern.

### 3.2. withLocale does not resolve Unicode extensions into overrides

When the locale is `en-US-u-ca-japanese-nu-thai-tz-jptyo`, `withLocale` **stores the locale including its extensions**. That does not mean the formatter automatically switched:

- `getChronology()` to Japanese calendar;
- `getDecimalStyle()` to Thai digits;
- `getZone()` to `Asia/Tokyo`.

Localized parts **can still inspect the locale extensions when looking up text or patterns**. However, to have chronology, zone, and decimal style configured on the formatter from those extensions, look at `localizedBy`.

When you want to change only one specific setting explicitly, `withChronology(Chronology)`, `withZone(ZoneId)`, and `withDecimalStyle(DecimalStyle)` express intent much more clearly than embedding business configuration inside a locale string.

## 4. localizedBy: Applying Calendar, Numbering System, Region, and Timezone

Java SE 17 signature:

~~~java
DateTimeFormatter localizedBy(Locale locale)
~~~

This method was added in **Java 10**. It returns a new formatter with localized values for locale, calendar, region, decimal style, and/or time zone that can **override** those currently held by the formatter.

Unicode locale extension keys to remember:

| Key | Function | Example in a language tag |
| --- | --- | --- |
| `ca` | Requested calendar/chronology | `en-US-u-ca-japanese` |
| `nu` | Numbering system | `en-US-u-nu-thai` |
| `tz` | Requested time zone, via Unicode timezone code | `en-US-u-tz-jptyo` |
| `rg` | Region override | `en-US-u-rg-gbzzzz` |

In `en-US-u-ca-japanese-nu-thai-tz-jptyo`:

- `en-US` is the standard language and country.
- `u` introduces Unicode extensions.
- `ca-japanese` requests the Japanese calendar.
- `nu-thai` requests the Thai numbering system.
- `tz-jptyo` identifies the registered timezone code for Tokyo. Do **not** arbitrarily write `tz-Asia/Tokyo` in BCP 47: Unicode timezone types use their own registry codes, distinct from IANA ZoneId strings.

The locale can be constructed via:

~~~java
Locale preference = Locale.forLanguageTag(
        "en-US-u-ca-japanese-nu-thai-tz-jptyo");
DateTimeFormatter enriched = base.localizedBy(preference);
~~~

This is an illustrative snippet assuming `base` is an existing formatter. With a formatter capable of representing these fields, `enriched` can carry:

- `getChronology().getId()`: `Japanese`;
- `getZone().getId()`: `Asia/Tokyo`;
- `getDecimalStyle().getZeroDigit()`: Thai zero digit `๐` (Unicode `U+0E50`).

**Precedence among extensions:** if both `ca` and `rg` are present, the chronology specified by `ca` takes precedence over any chronology implied by `rg`; the same rule applies to `nu` when selecting the numbering system. Do not assume the base country `US` governs all formatting when a region override is present.

### 4.1. localizedBy does not "change the instant" of an Instant

When given an `Instant` input, the time zone in the formatter affects **how the time is expressed for a region**. An `Instant` at `2024-03-01T03:04:00Z` corresponds to `03:04` in UTC yet `12:04` in Tokyo (UTC+9 at that time). **The Instant remains the exact same point in time.**

If the source data is a `LocalDateTime` without a zone or offset, formatting with a zone override cannot be treated as a meaningful time conversion without first associating the source data with a zone. For calendar/event systems, model `Instant` or `ZonedDateTime`/domain zone properly before formatting.

### 4.2. Chronology is calendar interpretation, not text translation

A different chronology, such as `JapaneseChronology`, has its own era names, year-of-era numbering, and calendar rules. When formatting a date object under another calendar, the formatter can convert to the overridden chronology before generating text. Thus, when using `localizedBy` with `ca`, consider date semantics, digits, and eras rather than treating it as pure "language switching".

Formatters using the `uuuu` pattern may still print the proleptic year `2024` even when `getChronology()` is `Japanese`; to see the era in the output, use an appropriate pattern such as `G y`. Do not rely on a single year string to conclude the chronology did not change: inspect `getChronology()` and era/year fields when the task requires it.

## 5. Method Call Order Matters with localizedBy

Formatters are immutable and `withXXX` methods return copies. Since `withLocale` does not overwrite chronology/zone/decimal style, those overrides can generally be configured independently.

**With `localizedBy`, call order can change the result** because `localizedBy` can replace attributes that were already set earlier:

~~~java
Locale pref = Locale.forLanguageTag("en-US-u-tz-jptyo");

DateTimeFormatter a = base
        .localizedBy(pref)
        .withZone(ZoneId.of("UTC"));

DateTimeFormatter b = base
        .withZone(ZoneId.of("UTC"))
        .localizedBy(pref);
~~~

This is an illustrative snippet; `base` is an existing formatter, requiring imports for `Locale` and `ZoneId`.

- In **a**, `localizedBy` picks up the Tokyo timezone from `tz`, and then `withZone(UTC)` **overrides it last**: `a.getZone()` is `UTC`.
- In **b**, `withZone(UTC)` is applied first, then `localizedBy` processes the `tz-jptyo` extension: `b.getZone()` is `Asia/Tokyo` on JDKs with that mapping.

The same thing can happen when `withChronology` or `withDecimalStyle` appears before or after `localizedBy`. To prevent implicit configuration surprises:

1. Call `localizedBy(pref)` first if you want to accept permitted localized defaults.
2. Then call `withZone(businessZone)`, `withChronology(businessChronology)`, and `withDecimalStyle(requiredStyle)` **last** if application policy requires keeping them fixed.
3. Never accept client-supplied Unicode extensions as commands to alter business time zones or calendars without checking permissions, allowlists, and data boundaries.
4. Write tests asserting `getLocale()`, `getChronology()`, `getZone()`, and `getDecimalStyle()` for configurations prone to confusion.

## 6. Do Not Confuse DecimalStyle with Full Localization

`DateTimeFormatter` has `DecimalStyle` to control digits, plus/minus signs, and decimal separators used during formatting/parsing. It is **not** `java.text.DecimalFormat` for general number formatting.

Example:

~~~java
DecimalStyle style = DecimalStyle.STANDARD;
char zeroDigit = style.getZeroDigit(); // '0' (U+0030)
~~~

This is an illustrative snippet requiring `import java.time.format.DecimalStyle;`.

`withLocale(Locale.forLanguageTag("th-TH"))` can change localized text/patterns according to the locale, yet **does not automatically alter** an already configured `DecimalStyle.STANDARD`. Conversely, `localizedBy(Locale.forLanguageTag("th-TH-u-nu-thai"))` can select Thai digits per the `nu` extension.

Nor should locale be equated with `ZoneId`: not every language/region maps to a single time zone. One country can span multiple zones or vary over time. A `tz` extension is a **timezone preference encoded in a locale**, not a fact about the user's physical location.

## 7. Standalone Java 17 Example Verifying Both Metadata and Output

Place the code in **`LocaleMethodDemo.java`**:

~~~java
import java.time.*;
import java.time.chrono.*;
import java.time.format.*;
import java.util.*;

public class LocaleMethodDemo {
    static void state(String name, DateTimeFormatter f) {
        String chrono = f.getChronology() == null
                ? "none" : f.getChronology().getId();
        String zone = f.getZone() == null
                ? "none" : f.getZone().getId();
        int digit = (int) f.getDecimalStyle().getZeroDigit();

        System.out.println(name + ": locale="
                + f.getLocale().toLanguageTag()
                + ", chronology=" + chrono
                + ", zone=" + zone
                + ", zeroDigitU+"
                + String.format(Locale.ROOT, "%04X", digit));
    }

    public static void main(String[] args) {
        Locale target = Locale.forLanguageTag(
                "en-US-u-ca-japanese-nu-thai-tz-jptyo");

        DateTimeFormatter base = DateTimeFormatter
                .ofPattern("uuuu-MM-dd HH:mm", Locale.US)
                .withChronology(IsoChronology.INSTANCE)
                .withZone(ZoneId.of("UTC"))
                .withDecimalStyle(DecimalStyle.STANDARD);

        DateTimeFormatter with = base.withLocale(target);
        DateTimeFormatter localized = base.localizedBy(target);

        state("base", base);
        state("withLocale", with);
        state("localizedBy", localized);
        state("zoneAfter",
                base.localizedBy(target).withZone(ZoneId.of("UTC")));
        state("localeAfter",
                base.withZone(ZoneId.of("UTC")).localizedBy(target));

        System.out.println("unchanged="
                + base.getLocale().equals(Locale.US));

        Instant instant = Instant.parse("2024-03-01T03:04:00Z");
        System.out.println("withLocale text=" + with.format(instant));
        System.out.println("localizedBy text=" + localized.format(instant));
    }
}
~~~

Compile and run with **Java 17 or later**:

~~~bash
javac -encoding UTF-8 LocaleMethodDemo.java
java LocaleMethodDemo
~~~

**Verified stdout** on a JDK with the corresponding calendar, numbering system, and time-zone data:

~~~text
base: locale=en-US, chronology=ISO, zone=UTC, zeroDigitU+0030
withLocale: locale=en-US-u-ca-japanese-nu-thai-tz-jptyo, chronology=ISO, zone=UTC, zeroDigitU+0030
localizedBy: locale=en-US-u-ca-japanese-nu-thai-tz-jptyo, chronology=Japanese, zone=Asia/Tokyo, zeroDigitU+0E50
zoneAfter: locale=en-US-u-ca-japanese-nu-thai-tz-jptyo, chronology=Japanese, zone=UTC, zeroDigitU+0E50
localeAfter: locale=en-US-u-ca-japanese-nu-thai-tz-jptyo, chronology=Japanese, zone=Asia/Tokyo, zeroDigitU+0E50
unchanged=true
withLocale text=2024-03-01 03:04
localizedBy text=๒๐๒๔-๐๓-๐๑ ๑๒:๐๔
~~~

Reading the output:

1. **base** holds `ISO`, `UTC`, and ASCII digit `0` (`U+0030`).
2. **withLocale** updates the stored locale to the tag with extensions while keeping all three overrides from `base`.
3. **localizedBy** switches to the Japanese calendar, Tokyo timezone, and Thai digits (`U+0E50`) per `ca`, `tz`, and `nu`.
4. **zoneAfter** yields `UTC` because `withZone(UTC)` was called last.
5. **localeAfter** yields `Asia/Tokyo` because `localizedBy` was called last and interpreted `tz`.
6. **unchanged=true** proves the original `base` formatter was not mutated.
7. **withLocale text** uses UTC time and ASCII digits: `2024-03-01 03:04`.
8. **localizedBy text** uses Tokyo time (UTC+9) and Thai digits: `๒๐๒๔-๐๓-๐๑ ๑๒:๐๔`.

The last line **does not mean a new `Instant` was created**. Both strings format the same `Instant.parse("2024-03-01T03:04:00Z")`; the difference comes from the formatter's zone and numbering system.

If the JDK does not support a requested calendar, region code, or numbering system, the exact output may vary. In deployment, test against the chosen runtime/locale provider and avoid cross-version Unicode text snapshots without pinning data. In the example, printing `zeroDigitU+` is a clearer way to verify metadata than relying on console font rendering.

## 8. withLocale vs. localizedBy: Choosing by Scenario

| Need | Usually suitable choice | Reason |
| --- | --- | --- |
| Translate month/day names and switch date style by locale | `withLocale(locale)` on an appropriate formatter | Changes text source and localized pattern |
| Use `ofLocalizedDate(FormatStyle.LONG)` per user locale | `withLocale(locale)` | Localized style already looks up the pattern by locale |
| Keep ISO calendar and a domain zone | `withLocale(locale)` with explicit `withChronology`/`withZone` | Prevents locale extensions from replacing overrides |
| Allow users to choose Japanese calendar via `ca-japanese` | `localizedBy(locale)` if policy permits | Applies chronology from locale extension |
| Allow Thai numbering system via `nu-thai` | `localizedBy(locale)` or explicit `withDecimalStyle` | Applies numbering system |
| Allow time zone from `tz` | `localizedBy(locale)` after policy validation | Can pick up zone from extension |
| Meeting time zone must stay `Asia/Ho_Chi_Minh` regardless of client locale | `localizedBy(locale).withZone(businessZone)` or `withLocale(locale).withZone(businessZone)` | Overrides zone after localization |
| Produce canonical strings for DB/API storage | Standard/fixed ISO formatter per contract | Independent of presentation locale |
| One server handling many requests | Pass locale per request, use immutable formatters | Avoids JVM-wide `Locale.setDefault` |

**No single method can be declared "right for every case".** The choice must reflect the role of calendar systems, time zones, and numbering systems in your product.

## 9. Common Mistakes

### Mistake 1: Assuming withLocale changes the timezone

~~~java
DateTimeFormatter f = DateTimeFormatter.ofPattern("HH:mm")
        .withZone(ZoneId.of("UTC"))
        .withLocale(Locale.forLanguageTag("ja-JP"));
~~~

This is an illustrative snippet requiring the corresponding imports. `getZone()` is still `UTC`. A Japanese locale does not automatically convert timestamps to Tokyo time.

**Proper approach:** if you need Tokyo time, call `withZone(ZoneId.of("Asia/Tokyo"))` explicitly, or use `localizedBy` when the user actually has a valid `tz` extension and the product permits it.

### Mistake 2: Assuming localizedBy only changes month names

If the locale contains `ca`, `nu`, or `tz`, this method can overwrite the configured calendar, digits, and zone. Do **not** call `localizedBy` at the end of a pipeline if business rules mandate a fixed `ZoneId` without understanding this risk.

### Mistake 3: Discarding the returned formatter

~~~java
DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern("d MMM uuuu", Locale.US);
formatter.withLocale(Locale.FRANCE); // Returned object ignored!
~~~

Formatters are immutable, so `formatter` still holds `en-US`. Use `formatter = formatter.withLocale(Locale.FRANCE);` or assign to a new variable.

### Mistake 4: Using locale as a substitute for temporal data

Switching the UI to `vi-VN` does not determine which time zone a `LocalDateTime` belongs to. If the application receives instants from a backend, store/transmit `Instant` or `OffsetDateTime`/`ZonedDateTime` with clear semantics; apply locale at the presentation step. Do not treat a zone-less date-time as an instant and add/subtract hours by country.

### Mistake 5: Forcing locale-based formatters for machine-readable data

An ISO-formatted string `2024-03-01` is far more stable over APIs than localized date text whose day/month order and digits can vary. Serializers should follow an explicit contract rather than borrowing UI display formatters as a storage format.

### Mistake 6: Letting clients dictate chronology/zone via unvalidated extensions

A client-supplied locale header can contain `u-ca-...`, `u-nu-...`, or `u-tz-...`. Never use it directly to change calendars for due-date calculations, appointments, or historical processing when the system needs zones/chronologies from a trusted source. Parse and allowlist locales, then apply separate domain rules.

## 10. Tests You Should Write

To verify your API choice accurately, write tests covering:

1. **Immutability:** the original formatter is unchanged after both methods.
2. **Locale text/style:** month names, weekday names, or localized patterns change with `withLocale` on formatters that have localized parts.
3. **No hidden overrides:** `withLocale` with `ca/nu/tz` preserves the base formatter's explicit chronology/zone/decimal style.
4. **Extended localization:** `localizedBy` with valid extensions updates the expected metadata.
5. **Chaining order:** `localizedBy(tz).withZone(UTC)` differs from `withZone(UTC).localizedBy(tz)`.
6. **Same Instant:** formatting the same `Instant` in UTC and Tokyo checks the exact hour offset while leaving the `Instant` unchanged.
7. **Input edge cases:** `null` throws `NullPointerException`; locales without extensions and locales with unsupported extensions must follow the JDK contract and application policy.
8. **Parsing:** if using `localizedBy` with a non-ISO chronology, verify the parsed date has the right meaning; do not infer `LocalDate` blindly under a different calendar system.
9. **Provider/CLDR differences:** snapshot month names, eras, and digits under the committed Java/locale-data version.
10. **Multi-threading:** immutable formatters can be safely shared; per-request locale context must be managed separately instead of changing the JVM default.

For parsers and formats that must remain stable across a protocol, use fixed standard formatters and test round-trips independently of language preferences.

## 11. Practice Exercises

- Replace `Locale.US` on `base` with `Locale.forLanguageTag("vi-VN")`, then use `DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG)` to observe the locale pattern.
- Remove `tz-jptyo` from `target`; compare `getZone()` on `base`, `withLocale`, and `localizedBy` on your runtime.
- Remove `ca-japanese`; compare `getChronology()`.
- Remove `nu-thai`; compare `getDecimalStyle().getZeroDigit()`.
- Change the pattern to `"G y-MM-dd HH:mm"`; observe how the Japanese chronology formats era and year-of-era, noting that era names depend on locale/provider.
- Reverse the order of `withChronology(IsoChronology.INSTANCE)` and `localizedBy(target)`; explain the final value on the formatter.
- Pass the same `Instant` through the formatters while setting the business zone last with `withZone(ZoneId.of("Asia/Ho_Chi_Minh"))`; verify the time-zone offset relative to UTC on the chosen date.
- Write a factory `formatterFor(Locale locale, ZoneId requiredZone)` taking locale from the request and zone from the domain, and demonstrate that `Locale.setDefault` is unnecessary.

## 12. Summary

**`withLocale` changes the source of localized text and patterns; `localizedBy` can also apply chronology, numbering system, region, and time zone from the locale.** Both return a new immutable formatter. The difference is clearest when the locale carries Unicode extensions `ca`, `nu`, `rg`, `tz`, or when the formatter already has `withZone`, `withChronology`, or `withDecimalStyle`.

When a system only needs to change the language or date-time layout while preserving the business zone and calendar, `withLocale` is usually easier to control. When an application **intentionally** supports calendar/digit/zone preferences encoded in a locale, consider `localizedBy`, validate inputs, and apply mandatory overrides **after** localization. Never confuse display formatting with how instants are stored or computed.

**References:**

- Java SE 17, `DateTimeFormatter` (`withLocale`, `localizedBy`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html
- Java SE 17, `DecimalStyle`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DecimalStyle.html
- Java SE 17, `Locale` and Unicode extensions: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html
- Java SE 17, `Chronology`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/chrono/Chronology.html
- Java SE 17, `ZoneId`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZoneId.html
