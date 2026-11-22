# Provider and Data Differences Across JDK Versions

## 1. Why can identical Java code yield changing localization outputs?

`Locale` merely represents a request for a language, region, and certain options. It is **not a fixed copy of the data** used to display dates, numbers, month names, or compare strings. APIs such as `NumberFormat`, `DateFormat`, `DateTimeFormatter`, and `Collator` typically draw upon locale data bundled in the Java runtime.

Consequently, an application running the exact same source code and the same `Locale.FRANCE` can still produce different strings when upgrading the JDK, switching data providers, running on another OS, or using a minimally packaged runtime image.

Three components must be distinguished:

| Component | Example | Role |
| --- | --- | --- |
| Locale identifier | `Locale.forLanguageTag("vi-VN")` | Requests Vietnamese conventions in Vietnam |
| Locale-sensitive API | `NumberFormat`, `DateFormat`, `Collator` | Formats, parses, or compares |
| Data source | `CLDR`, `SPI`, `HOST`, legacy `COMPAT/JRE` | Supplies date patterns, number symbols, display names, and sorting rules |

```text
Requested Locale
   ↓
Locale-sensitive API
   ↓
Provider order read by JVM at startup
   ├── CLDR
   ├── SPI
   ├── HOST (if supported by environment)
   └── COMPAT/JRE (legacy data, only in JDKs prior to 23)
   ↓
Display string / parse result / comparison order
```

**A valid locale does not mean every API has complete dedicated data for that locale.** A provider may support number formatting yet lack another service; the runtime may perform provider or locale fallback. When guaranteed behavior is needed, test the exact API on the deployment runtime.

## 2. CLDR and key JDK milestones

CLDR (*Common Locale Data Repository*) is the internationalization data source maintained by the Unicode Consortium. Relevant data includes date/time display patterns, grouping separators, decimal separators, month/day names, region/language names, currency symbols, and various rules.

- **JDK 8:** included legacy JRE data; CLDR was integrated but was not the default prioritized source as in later versions.
- **JDK 9:** CLDR data became the default prioritized source.
- **JDK 9–22:** legacy `COMPAT` data (historical alias `JRE`) remained available to ease migration.
- **JDK 21:** specifying legacy data emitted warnings ahead of removal.
- **JDK 23 onward:** legacy `COMPAT/JRE` locale data **was removed**. Merely adding `COMPAT` to the JVM property does not restore legacy data.

Selected CLDR versions per JDK documentation:

| JDK | CLDR |
| --- | --- |
| 17 | 39 |
| 21 | 43 |
| 22 | 44 |
| 23 | 45 |
| 24 | 46 |
| 25 | 47 |
| 26 | 48 |

These numbers denote **data versions**; not every locale changes in every release. Even so, data differences can break snapshot tests or parsers reading older strings. JDK releases sharing the same Java language level are not guaranteed to carry identical locale data.

## 3. Four locale providers

### `CLDR`

The default prioritized provider since JDK 9, backed by CLDR data bundled in the JDK. Newer JDK releases may bundle newer CLDR versions. To specify explicitly:

```bash
java -Djava.locale.providers=CLDR -cp . LocaleDataProbe
```

This example runs the `LocaleDataProbe` program defined later in this lesson.

### `COMPAT/JRE`

In JDK 9–22, supplies data compatible with pre-JDK 9 behavior. Useful for diagnosing migrations from JDK 8:

```bash
java -Djava.locale.providers=COMPAT,CLDR -cp . LocaleDataProbe
```

Use only for testing on JDK versions **that still retain legacy data**. Starting in JDK 23, this mechanism is no longer a way to revert to legacy formats; if strict compatibility is required, maintain a custom parser/pattern or implement an appropriate service.

### `SPI`

*Service Provider Interface* allows applications to supply locale services via classes such as `NumberFormatProvider`, `DateFormatProvider`, `DecimalFormatSymbolsProvider`, `CollatorProvider`, and `LocaleNameProvider`.

A provider can be packaged on the classpath via `META-INF/services/…` or as a module declaring `provides … with …`. It must advertise the locales it supports. To prioritize external providers, use:

```text
-Djava.locale.providers=SPI,CLDR
```

**Listing SPI does not automatically create a provider**; an implementation must be installed and registered. For any service/locale not supported by the provider, the runtime may fall back to CLDR.

### `HOST`

Can reflect certain OS/user locale settings, particularly for numbers, dates, times, and currencies. Support varies across JDKs, vendors, and operating systems.

```text
-Djava.locale.providers=HOST,CLDR
```

For multi-user backends, relying on the server OS configuration is rarely ideal when the application requires uniform results.

## 4. `java.locale.providers`: configuring at JVM startup

The `java.locale.providers` system property selects the **provider priority order**. Examples:

```bash
java -Djava.locale.providers=CLDR -cp . Main
java -Djava.locale.providers=SPI,CLDR -cp . Main
java -Djava.locale.providers=HOST,SPI,CLDR -cp . Main
```

Rules:

1. Pass the property to the **JVM launcher**, before the class name or JAR.
2. It is read and cached when locale services initialize; **do not** rely on `System.setProperty` inside a request to switch providers on a running JVM.
3. The first provider is used only when it supports the requested service/locale. Some APIs apply fallback mechanisms.
4. `java.locale.providers` differs from `Locale.getDefault()`. The provider is the data source; the default locale is the value used when you omit a locale argument.
5. Starting in JDK 23, `COMPAT`/`JRE` no longer restores legacy data.
6. In multi-user systems, **pass locales explicitly** rather than calling `Locale.setDefault` on every request.

The same property does not guarantee identical output if JDKs bundle different CLDR versions, lack data modules, or pull SPI/HOST from distinct environments.

## 5. Affected areas

### Numbers and separator symbols

`NumberFormat`, `DecimalFormatSymbols`, and `DecimalFormat` may use different grouping/decimal separators. In particular, these spaces are easily confused:

| Unicode | Character |
| --- | --- |
| `U+0020` | ASCII space |
| `U+00A0` | No-break space |
| `U+202F` | Narrow no-break space |

They may look alike yet differ in code point. Byte-comparison tests, copy/pasted inputs, or parsers hardcoded to a fixed character can fail. Print the Unicode code points of separators rather than relying only on visual inspection.

### Dates and times

`DateFormat.getDateInstance(style, locale)` and `DateTimeFormatter.ofLocalizedDate(style)` use localized patterns; day/month/year ordering, delimiters, month names, year width, and time formatting may differ.

If data was stored as strings generated from `FormatStyle.SHORT` or `DateFormat.SHORT`, a newer runtime might not parse them identically to an older runtime. **Display formatting is not a storage or protocol schema.** Store `LocalDate`/`Instant` or explicit ISO text, then format per locale when displaying.

### Currency and percentages

Currency symbol placement, currency names/symbols, spacing, and percentage patterns can depend on locale data. `NumberFormat.getCurrencyInstance(locale)` **does not perform currency conversion**. Always store the currency code, amount, and rounding rules per business logic.

### Language-sensitive sorting

`Collator.getInstance(locale)` can change ordering or string equivalence depending on locale data and strength. This affects sorting, searching, `TreeSet`/`TreeMap` with comparators, caches, and pagination.

Do not store collation keys as an unversioned permanent format. When collation data changes, check whether indexes need rebuilding and use an ID tie-breaker.

### Display names

`Locale.getDisplayName(displayLocale)` and `Currency.getDisplayName(locale)` are also affected by data updates. Never use translated country/language names as long-lived keys; store standard codes separately.

## 6. Java 17+ program: inspecting the actual runtime

One way to detect differences is to print **Java version, provider property, and symbols as code points**.

Create the file **`LocaleDataProbe.java`**:

```java
import java.text.Collator;
import java.text.DecimalFormatSymbols;
import java.text.NumberFormat;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public class LocaleDataProbe {
    private static String hex(int cp) {
        return String.format(Locale.ROOT, "U+%04X", cp);
    }

    private static void inspect(Locale locale) {
        DecimalFormatSymbols symbols =
                DecimalFormatSymbols.getInstance(locale);
        String number = NumberFormat.getNumberInstance(locale)
                .format(1234567.89);
        String date = DateTimeFormatter
                .ofLocalizedDate(FormatStyle.SHORT)
                .withLocale(locale)
                .format(LocalDate.of(2026, 10, 28));
        Collator c = Collator.getInstance(locale);

        System.out.println("locale=" + locale.toLanguageTag());
        System.out.println("  grouping=" +
                hex(symbols.getGroupingSeparator()));
        System.out.println("  decimal=" +
                hex(symbols.getDecimalSeparator()));
        System.out.println("  number=" + number);
        System.out.println("  date=" + date);
        System.out.println("  compare(a,ä)=" +
                Integer.signum(c.compare("a", "ä")));
    }

    public static void main(String[] args) {
        System.out.println("java.version=" +
                System.getProperty("java.version"));
        System.out.println("java.vendor=" +
                System.getProperty("java.vendor"));
        System.out.println("providers=" +
                System.getProperty(
                        "java.locale.providers", "<unset>"));

        inspect(Locale.US);
        inspect(Locale.GERMANY);
        inspect(Locale.FRANCE);
        inspect(Locale.forLanguageTag("vi-VN"));
    }
}
```

Commands:

```bash
javac -encoding UTF-8 LocaleDataProbe.java
java -Djava.locale.providers=CLDR -cp . LocaleDataProbe
```

**Outputs depend on the environment, so there is no single exact fixed stdout across all JDKs.** The program prints three runtime lines (`java.version`, `java.vendor`, `providers`), followed by five lines per locale covering grouping/decimal/number/date/collator.

```text
java.version=<JDK version>
java.vendor=<JDK vendor>
providers=<CLDR or passed configuration>
locale=en-US
  grouping=U+....
  decimal=U+....
  number=...
  date=...
  compare(a,ä)=...
...
```

This is solely an **output schema**, not an exact snapshot. `System.getProperty("java.locale.providers")` indicates the passed configuration, **not proof** that the provider handled every service. Compare results directly across JVM processes using the same locales.

## 7. Explicit patterns and Java 17+ results

An explicit pattern reduces dependence on **default number patterns** while still sourcing symbols from locale data.

Create **`ExplicitLocalePatternDemo.java`**:

```java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParsePosition;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class ExplicitLocalePatternDemo {
    private static DecimalFormat number(Locale locale) {
        return new DecimalFormat(
                "#,##0.00",
                DecimalFormatSymbols.getInstance(locale));
    }

    public static void main(String[] args) {
        DecimalFormat us = number(Locale.US);
        DecimalFormat de = number(Locale.GERMANY);

        System.out.println("US=" + us.format(1234567.89));
        System.out.println("DE=" + de.format(1234567.89));

        System.out.println("ISO=" +
                DateTimeFormatter.ISO_LOCAL_DATE.format(
                        LocalDate.of(2026, 10, 28)));

        ParsePosition position = new ParsePosition(0);
        Number parsed = de.parse("1.234,56", position);
        System.out.println("parsed=" + parsed +
                ", end=" + position.getIndex() +
                ", error=" + position.getErrorIndex());
    }
}
```

Run:

```bash
javac -encoding UTF-8 ExplicitLocalePatternDemo.java
java -cp . ExplicitLocalePatternDemo
```

Output on modern JDKs with standard German/US symbols:

```text
US=1,234,567.89
DE=1.234.567,89
ISO=2026-10-28
parsed=1234.56, end=8, error=-1
```

Distinguish the **structural pattern** `#,##0.00` from the **actual display symbols** supplied by `DecimalFormatSymbols`. The pattern does not pin the Unicode code point of separators across every runtime. For machine-to-machine data, ISO dates and explicit protocol formats are more appropriate than localized text.

## 8. Contract testing without freezing every local symbol

Fixed-output golden tests are useful when a product requires that exact pattern and pins the JDK/provider. General contract tests, however, should verify **semantics**, avoiding treating every CLDR space character as immutable.

Create **`LocaleDataContractChecks.java`**:

```java
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class LocaleDataContractChecks {
    private static void check(boolean valid) {
        if (!valid) throw new AssertionError("Check failed");
    }

    private static void roundTrip(Locale locale) {
        NumberFormat f = NumberFormat.getIntegerInstance(locale);
        f.setGroupingUsed(false);
        String text = f.format(1234567L);
        ParsePosition p = new ParsePosition(0);
        Number value = f.parse(text, p);

        check(value != null);
        check(p.getIndex() == text.length());
        check(value.longValue() == 1234567L);
    }

    public static void main(String[] args) {
        check(DateTimeFormatter.ISO_LOCAL_DATE.format(
                LocalDate.of(2026, 10, 28))
                .equals("2026-10-28"));

        roundTrip(Locale.US);
        roundTrip(Locale.GERMANY);
        roundTrip(Locale.forLanguageTag("vi-VN"));

        System.out.println("4 contract groups passed");
    }
}
```

Run:

```bash
javac -encoding UTF-8 LocaleDataContractChecks.java
java -cp . LocaleDataContractChecks
```

Output when all conditions pass:

```text
4 contract groups passed
```

There is one ISO group and three integer groups. Each numeric group checks the parsed value and full consumption of the text. **A round-trip on the same runtime does not prove a newer runtime can read strings written by an older JDK**; that requires dedicated migration tests.

## 9. Procedure for comparing two JDKs

1. Record the JDK feature/update version, vendor/build, OS, and runtime image.
2. Compile the same source for a shared Java version (e.g., `javac --release 17` on the newer JDK).
3. Run **each JDK in a fresh process** with the chosen `java.locale.providers`.
4. Use identical language tags, inputs, zones, styles, and API calls.
5. Compare separator code points, format/parse values, and collation order.
6. If differences appear only in containers, check the default locale, `jdk.localedata` module, and HOST/SPI.
7. Evaluate whether the change is acceptable to the product or requires parser migration, rather than blindly updating snapshots.
8. Do not try `COMPAT` to roll back JDK 23+, where legacy data has been removed.

Illustrative example on Linux/macOS with two Java paths:

```bash
/path/to/jdk17/bin/java -Djava.locale.providers=CLDR -cp . LocaleDataProbe > jdk17.txt
/path/to/jdk25/bin/java -Djava.locale.providers=CLDR -cp . LocaleDataProbe > jdk25.txt
diff -u jdk17.txt jdk25.txt
```

On Windows PowerShell, use the `&` call operator with real Java paths and a comparison tool like `Compare-Object`. Do not treat the example paths as pre-installed JDKs.

Information to capture in a diagnostic report:

```text
JDK version + vendor + build
java.locale.providers at startup
locale tag + Unicode extensions
API/style/pattern/strength used
zone/chronology/currency (if applicable)
separator code points
format result, parse result, and end index
runtime modules, jdk.localedata, OS
```

## 10. `jlink` and the `jdk.localedata` module

A custom runtime image built with `jlink` might not contain the same set of locales as a full JDK. The `jdk.localedata` module supplies additional locale data; `jlink` provides the `--include-locales` plugin.

Example:

```bash
jlink --add-modules java.base,jdk.localedata --include-locales=en,vi,fr --output custom-runtime
```

This only illustrates locale packaging; real applications also require other modules per their dependencies. Inspect the runtime with `java --list-modules` and run `LocaleDataProbe` **on the exact deployment image**.

Even with the same JDK major version, different vendors, startup providers, custom modules, or OSes can alter outputs. Do not conclude every discrepancy stems from CLDR.

## 11. Do not confuse CLDR with other data and mechanisms

| Symptom | What to investigate |
| --- | --- |
| Different numbers, grouping separators | CLDR, providers, DecimalFormatSymbols |
| Different date patterns/month names | Locale data and FormatStyle |
| Shifted hours, different DST | `ZoneId`, `tzdb` timezone database |
| Different timezone display names | Locale display names and timezone information |
| Different name sorting | `Collator`, strength, version |
| Garbled Vietnamese characters | Encoding/decoding, not necessarily CLDR |
| Correct code points rendered as boxes | Fonts/glyphs/renderer |
| Untranslated business labels | `ResourceBundle`/application translations |

CLDR **does not automatically provide translations for product messages**. `ResourceBundle` still requires application-managed translation files/sources.

## 12. Migration strategy

**Before upgrading:** inventory `DateFormat`, `NumberFormat`, `DecimalFormatSymbols`, `Collator`, `DateTimeFormatter.ofLocalized...`, `Locale.getDisplayName`, calls omitting `Locale`, and `java.locale.providers` settings. Audit places storing locale-formatted dates/numbers as data.

**When testing the new JDK:** run the probe on the target runtime and test numbers/dates/currencies/sorting for key locales; test both formatting and parsing, especially for legacy data. A parser might only read a valid prefix, so validate full input consumption using `ParsePosition` or strict APIs.

**After evaluation:** accept CLDR changes that align with display policy; fix business contracts or legacy stored data if impacted. Use locale-independent ISO/wire formats, versioned collation/indexes, and CI/CD tests. Never resort to stripping all whitespace or hardcoding one English format as a blanket fix.

## 13. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Thinking `Locale.forLanguageTag` guarantees full locale data | Fallback or missing service | Test on the target runtime |
| Using the server's default locale for all users | Output varies by environment | Pass locales explicitly |
| Expecting `COMPAT` to work on JDK 23+ | Legacy data is not restored | Plan a controlled migration |
| Calling `System.setProperty` after startup to change providers | Property may already be cached | Pass in JVM arguments |
| Assuming all LTS JDKs share identical data | CLDR versions differ | Test per JDK build |
| Comparing spaces visually | Confuses U+0020/U+00A0/U+202F | Print Unicode code points |
| Storing display-style numbers/dates as wire formats | Newer JDKs may parse differently | Use ISO/standard structures |
| Testing only formatting | Misses parsing failures on old data | Test both directions |
| Not inspecting custom runtimes | Missing `jdk.localedata` | Test inside the deployment image |
| Using unversioned collation keys | Indexes can go stale | Reindex on policy changes |
| Confusing locale with timezone | Displays the wrong instant | Pass `ZoneId` separately |

## 14. Pre-release checklist

- [ ] Record JDK version, vendor/build, and runtime image.
- [ ] Know the actual `java.locale.providers` passed at startup.
- [ ] Use explicit locales for user-facing formatting APIs.
- [ ] Verify decimal/grouping separators, Unicode separators, percentages/currencies.
- [ ] Verify dates/times, month names, legacy parsing, timezones, and DST.
- [ ] Verify `Collator` sorting, equality, and pagination.
- [ ] Verify fallback/SPI/HOST and the `jdk.localedata` module.
- [ ] Separate wire formats from localized display text.
- [ ] Test old/new JDKs in separate processes and save fingerprints.
- [ ] Assess impact and update golden tests with clear justification.

## 15. Official references

- [Java 17 — LocaleServiceProvider API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/spi/LocaleServiceProvider.html): providers and properties in JDK 17.
- [Java 25 — LocaleServiceProvider API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/spi/LocaleServiceProvider.html): CLDR data across JDK lines.
- [JDK 23 — Removed Tools and Components](https://docs.oracle.com/en/java/javase/23/migrate/removed-tools-and-components.html): removal of legacy COMPAT/JRE.
- [JDK 26 — jlink reference](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jlink.html): `--include-locales` and custom runtimes.

## 16. Takeaways

- **`Locale` is a request, not an immutable locale dataset.**
- **CLDR has been prioritized by default since JDK 9; COMPAT/JRE was removed in JDK 23.**
- **SPI/HOST have support limits** and depend on configuration/OS.
- **Identical code + locale can produce different outputs** when CLDR, providers, or runtime images change.
- **Use locales for the UI and standard wire formats for storage**—never swap those two goals.
- **Verify using two separate JVMs, code points, and regression tests**, especially for formatting/parsing and collation.
