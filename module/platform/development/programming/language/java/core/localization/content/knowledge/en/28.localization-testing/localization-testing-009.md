# Diffing Output Changes When Upgrading JDK, CLDR, or Runtime Images

Upgrading a JDK version does not necessarily break Java code, yet it can cause **identical input data to produce different display strings than before**. This is especially important in the **Java core - localization** module, where applications rely on `Locale`, `NumberFormat`, `DateFormat`, `DateTimeFormatter`, `MessageFormat`, `Currency`, `ResourceBundle`, time-zone names, or regional calendar rules.

For example, a numeric grouping separator can change from **U+00A0 NO-BREAK SPACE** to **U+202F NARROW NO-BREAK SPACE**; month names, long date formats, currency symbols, time formatting, or locale messages can also shift when **CLDR data** or the JDK's locale provider selection is updated. Two strings may **look identical** in the UI while failing `String.equals`. Sometimes the change is completely valid under updated linguistic data; sometimes it is an application regression.

With **`jlink` runtime images**, the scope is broader still: a minimal image may **not include the same set of modules and locale data** as a full JDK. A test passing on a developer laptop does not prove the deployed image has equivalent formatting data.

This lesson shows how to establish an **output baseline**, run the same **fixed input set** across **old/new JDKs and actual runtime images**, emit evidence at the Unicode code-point level, classify changes, and approve only reviewed differences. The goal is **diffing upgrade outcomes**, not forcing every JDK release to forever return identical phrasing.

## 1. Components That Can Alter Output

| Upgraded / changed component | Observable impact | Examples to test |
| --- | --- | --- |
| **JDK feature/update/build** | API implementation, locale data, Unicode, TZDB, bug fixes | Months/days, digits, currencies |
| **CLDR data** | Month/day names, numbers, symbols, locale patterns, abbreviations | `NumberFormat`, `DateTimeFormatter` |
| **`java.locale.providers`** | Provider lookup precedence | `CLDR`, `SPI`, `HOST`; legacy `COMPAT` in older JDKs |
| **Vendor/distribution** | Build data and packaging configs may differ | Two JDKs with the same feature number |
| **`jdk.localedata`** | Availability of extended locale data | `jlink` image with/without the module |
| **`--include-locales`** | Subset of locales retained in the image | `fr-FR`, `vi-VN`, `ja-JP` |
| **Time-zone database (TZDB)** | Historical/future offsets, zone names, DST rules | `ZoneId`, `ZonedDateTime` |
| **Default locale/timezone** | Host-dependent output | `Locale.getDefault`, `ZoneId.systemDefault` |
| **Application and bundles** | Patterns, resources, custom providers | `ResourceBundle`, `MessageFormat` |

**Classification point:** Not every formatting change is a bug. CLDR data reflects updated localization conventions; in some cases **newer output is more accurate than older output**. Your test process must reveal **what changed, why, and how it affects users or contracts**.

## 2. Distinguishing JDK, CLDR, Unicode, TZDB, and Application Code

Do not lump everything together as a "new Java bug":

- **JDK/runtime** ships the API implementations and bundled dataset versions.
- **CLDR (Common Locale Data Repository)** supplies formatting patterns and linguistic data used by Java via its locale provider.
- **Unicode character data** affects functions like `Character.isLetter`, `isDigit`, case mappings, normalization, and code-point names.
- **TZDB** is the time-zone rules database used by `java.time` for `ZoneId` and time conversions.
- **Application resource bundles** can be independent of CLDR. A project-maintained `Messages_vi.properties` does not retranslate itself on a CLDR upgrade.
- **Default environment** settings such as default locale, default time zone, or charset can change when containers, OSes, or launch configs change.

When a diff appears, ask first **whether it originates from locale data, time-zone rules, Unicode data, or application translations**, and only then decide on a fix.

## 3. CLDR in the JDK: Linguistic Data Is Not an Immutable Constant

Since **JDK 9**, CLDR is the default locale data source in Java. On **JDK 17**, `java.locale.providers` can specify provider precedence such as `CLDR`, `COMPAT`, `SPI`, and `HOST` depending on the environment and installed providers.

Startup example:

~~~bash
java -Djava.locale.providers=CLDR -cp out LocaleSnapshot
~~~

The line above illustrates running a compiled class in `out`, **not launching a general JDK library**. This property must be set **at JVM startup**; do not call `System.setProperty` after locale-sensitive services have initialized and expect all provider selection to change.

**Key migration milestone:** legacy `JRE`/`COMPAT` locale data **was removed in JDK 23**. Consequently, advice like "just set `COMPAT` to preserve old output" can **only be a temporary stopgap on JDKs that still support it**, never a long-term upgrade strategy.

Oracle documentation:
- [Internationalization Enhancements, JDK 17](https://docs.oracle.com/en/java/javase/17/intl/internationalization-enhancements1.html).
- [Removed Tools and Components, JDK 23](https://docs.oracle.com/en/java/javase/23/migrate/removed-tools-and-components.html).

### Provider Order Is an Independent Variable to Record

On runtimes that support them, the configurations:

~~~text
-Djava.locale.providers=CLDR
-Djava.locale.providers=SPI,CLDR
-Djava.locale.providers=HOST,CLDR
~~~

can pull from different data sources. `HOST` depends on the OS platform and user settings; `SPI` depends on installed service providers. Not every provider supplies every locale or service; the JDK can fall through to the next provider.

In a controlled comparison, **keep provider order identical across both runs** unless testing a provider change itself.

## 4. Beyond Just Major Version `17` or `21`

Two runtimes sharing the same feature version can still differ due to:
- different patch/update releases;
- different vendors;
- different bundled CLDR/TZDB data;
- one being a **full JDK** and the other a **`jlink` image**;
- different provider selection and service providers;
- different startup flags, default locale, or time zone.

Attach an **environment fingerprint** to every baseline result:

| Metadata | Where to obtain it |
| --- | --- |
| Version/build | `java -version`, `java.runtime.version` |
| Vendor | `java.vendor` |
| Runtime image | `java.home` or image identifier/hash in the pipeline |
| Locale provider order | Startup flags and `java.locale.providers` |
| Default `FORMAT` locale | `Locale.getDefault(Locale.Category.FORMAT)` |
| Default `DISPLAY` locale | `Locale.getDefault(Locale.Category.DISPLAY)` |
| Default time zone | `ZoneId.systemDefault()` |
| TZDB version | `ZoneRulesProvider.getVersions(zoneId).lastKey()` when supported by provider |
| Module/locale coverage | `java --list-modules`, `jdk.localedata`, and `jlink` configuration |

Metadata helps explain diffs; it **does not by itself tell you whether the new string is semantically right**.

Never publish machine paths containing usernames, hostnames, API tokens, or real user data in public CI artifacts. Record an **image digest/ID** instead of the full `java.home` path.

## 5. Every Probe Must Use Stable Inputs

If a test writes:

~~~java
NumberFormat.getInstance().format(12345.67);
LocalDate.now();
ZoneId.systemDefault();
Locale.getDefault();
~~~

results depend on the host machine's locale, clock, and time zone. A diff may come from the environment, **not the JDK upgrade**.

Fix all inputs:

~~~java
Locale locale = Locale.forLanguageTag("fr-FR");
LocalDate date = LocalDate.of(2024, 1, 2);
BigDecimal amount = new BigDecimal("12345.67");
ZoneId zone = ZoneId.of("Europe/Paris");
Instant instant = Instant.parse("2024-03-31T01:30:00Z");
~~~

This is a snippet inside a method, requiring imports for `Locale`, `LocalDate`, `BigDecimal`, `ZoneId`, and `Instant`.

**Separate two kinds of tests:**
1. **Locale explicitly specified:** use fixed locale/timezone/amount to detect data/provider/runtime changes.
2. **Default environment behavior:** intentionally rely on default locale/timezone to verify that container or CLI configuration was applied properly.

Never mix both goals in one snapshot and blame every discrepancy on CLDR.

## 6. High-Value Measurement Probes

A probe suite can include:

- `NumberFormat.getNumberInstance(locale)`: grouping, decimal separators, rounding, and digit symbols.
- `NumberFormat.getCurrencyInstance(locale)`: currency symbol, symbol placement, special spaces.
- `DecimalFormatSymbols.getInstance(locale)`: decimal/grouping characters.
- `DateTimeFormatter.ofLocalizedDate(FormatStyle.SHORT/MEDIUM/LONG/FULL)`: patterns and day/month names.
- `DateFormat.getDateInstance(...)`: comparing `java.text` APIs against `java.time`.
- `Month.getDisplayName(TextStyle.FULL, locale)`: month names.
- `DayOfWeek.getDisplayName(...)`: weekday names.
- `WeekFields.of(locale)`: first day of week and minimal days in first week (can also change with locale data).
- `Currency.getInstance(locale)`: code and symbol.
- `MessageFormat(pattern, locale)`: locale-applied number/date subformats.
- `ResourceBundle`: actually resolved locale and fallback.
- `ZoneId`/`ZonedDateTime`: offsets and zone names at specific instants.
- `Character`/`Normalizer`: relevant code points when Unicode data updates.

You do not need to snapshot **every** locale and API on day one. Prioritize **product-supported locales** and critical screens: checkout, orders, transaction timestamps, emails, notifications, and calendars.

## 7. Unicode Spaces: Visually Alike, Different Values

A key example is the French grouping space:

~~~text
U+0020  SPACE
U+00A0  NO-BREAK SPACE
U+202F  NARROW NO-BREAK SPACE
~~~

In the UI, they can all look like ordinary spaces. Yet:

~~~java
"12 345".equals("12\u202F345");
~~~

evaluates to `false` because the code points differ. This is a valid Java expression snippet, not a standalone program.

A test printing display strings:

~~~text
expected: 12 345,67
actual:   12 345,67
~~~

can cause reviewers to miss the change. Therefore, **never rely solely on screenshots** or console rendering; output Unicode code points or escape ambiguous characters.

**Do not normalize all Unicode whitespace to U+0020 before diffing** when your goal is checking exact localization behavior; doing so hides changes that can affect line wrapping, copy/paste, or downstream parsers.

## 8. Building a Byte-for-Byte Comparable Unicode Measurement

Create a Java 17+ helper that prints every code point as `U+XXXX`:

~~~java
import java.util.Locale;
import java.util.stream.Collectors;

public final class CodePoints {
    private CodePoints() {}

    public static String show(String text) {
        return text.codePoints()
                .mapToObj(cp ->
                        String.format(Locale.ROOT,
                                "U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    public static void main(String[] args) {
        System.out.println(show(
                "A" + (char) 0x00A0 + "B"));
        System.out.println(show(
                "A" + (char) 0x202F + "B"));
    }
}
~~~

~~~bash
javac -encoding UTF-8 CodePoints.java
java CodePoints
~~~

**Deterministic** output:

~~~text
U+0041 U+00A0 U+0042
U+0041 U+202F U+0042
~~~

Code-point notation also highlights the difference between precomposed `é` and `e + COMBINING ACUTE ACCENT`. A diff tool can display **exact code-point values** instead of forcing humans to tell them apart visually.

`String.length()` counts UTF-16 code units, not Unicode code points. `codePoints()` is better suited for Unicode reporting.

## 9. A Runnable Java 17+ Snapshot Program

The example below emits two record types:
- **`META`** records the environment fingerprint.
- **`DATA`** records formatting results **for fixed inputs**.

`DATA` fields are serialized as `U+XXXX` strings, making exact diffing easy and independent of how a console renders glyphs.

Save as **`LocaleSnapshot.java`**:

~~~java
import java.math.BigDecimal;
import java.text.DateFormat;
import java.text.DecimalFormatSymbols;
import java.text.MessageFormat;
import java.text.NumberFormat;
import java.time.Instant;
import java.time.LocalDate;
import java.time.Month;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.time.format.TextStyle;
import java.time.temporal.WeekFields;
import java.time.zone.ZoneRulesProvider;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class LocaleSnapshot {
    static String points(String input) {
        return input.codePoints()
                .mapToObj(cp -> String.format(
                        Locale.ROOT, "U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    static void meta(String name, String value) {
        System.out.println("META\t" + name + "\t" + value);
    }

    static void data(String name, String value) {
        System.out.println("DATA\t" + name
                + "\t" + points(value));
    }

    public static void main(String[] args) {
        meta("java.runtime.version",
                System.getProperty("java.runtime.version"));
        meta("java.vendor",
                System.getProperty("java.vendor"));
        meta("java.locale.providers",
                System.getProperty("java.locale.providers",
                        "(unset)"));
        meta("default.format.locale",
                Locale.getDefault(
                        Locale.Category.FORMAT).toLanguageTag());
        meta("default.zone",
                ZoneId.systemDefault().toString());
        meta("tzdb.Europe/Paris",
                ZoneRulesProvider.getVersions(
                        "Europe/Paris").lastKey());

        LocalDate date = LocalDate.of(2024, 1, 2);
        BigDecimal amount = new BigDecimal("12345.67");

        Map<String, Locale> locales = new TreeMap<>();
        locales.put("en-US", Locale.US);
        locales.put("fr-FR", Locale.FRANCE);
        locales.put("ja-JP", Locale.JAPAN);
        locales.put("vi-VN",
                Locale.forLanguageTag("vi-VN"));

        for (var entry : locales.entrySet()) {
            String key = entry.getKey();
            Locale locale = entry.getValue();

            data(key + ".number",
                    NumberFormat.getNumberInstance(
                            locale).format(amount));
            data(key + ".currency",
                    NumberFormat.getCurrencyInstance(
                            locale).format(amount));
            data(key + ".date.long",
                    DateTimeFormatter.ofLocalizedDate(
                            FormatStyle.LONG)
                            .withLocale(locale).format(date));
            data(key + ".month",
                    Month.JANUARY.getDisplayName(
                            TextStyle.FULL, locale));

            DecimalFormatSymbols symbols =
                    DecimalFormatSymbols.getInstance(locale);
            data(key + ".symbols",
                    "" + symbols.getGroupingSeparator()
                            + symbols.getDecimalSeparator());

            WeekFields weeks = WeekFields.of(locale);
            data(key + ".weekFields",
                    weeks.getFirstDayOfWeek()
                            + "/" + weeks.getMinimalDaysInFirstWeek());

            data(key + ".message",
                    new MessageFormat(
                            "Items: {0,number,integer}",
                            locale).format(
                                    new Object[]{12345}));

            DateFormat legacy = DateFormat.getDateInstance(
                    DateFormat.LONG, locale);
            legacy.setTimeZone(TimeZone.getTimeZone("UTC"));
            data(key + ".legacyDate",
                    legacy.format(new Date(0)));
        }

        Instant fixed =
                Instant.parse("2024-03-31T01:30:00Z");
        ZoneId zone = ZoneId.of("Europe/Paris");
        data("Europe-Paris.offset",
                zone.getRules().getOffset(
                        fixed).toString());
    }
}
~~~

~~~bash
javac -encoding UTF-8 LocaleSnapshot.java
java -Djava.locale.providers=CLDR LocaleSnapshot
~~~

**Output is measured data; do not hard-code one expected table for every JDK.** Each line has the format:

~~~text
META\tjava.runtime.version\t<runtime version>
META\tjava.locale.providers\tCLDR
DATA\ten-US.number\t<Unicode code-point sequence>
DATA\tfr-FR.currency\t<Unicode code-point sequence>
...
~~~

In the description above, `\t` represents a TAB character for readability; the program outputs actual tabs (see the note immediately below).

**Note when copying code:** in Java source, use `"\t"` to emit a tab. If copying code displayed in an environment that auto-escapes backslashes, verify the actual string and adjust; in particular, `META`/`DATA` lines must use a consistent delimiter for the diff program below to parse them.

You can quickly verify the compiled file by running it and inspecting output: each line must start with `META` or `DATA`, followed by a **tab**, key, **tab**, and payload.

## 10. Snapshots Should Not Implicitly Contain Dynamic Data

The program above pins the test date to `2024-01-02` and instant to `2024-03-31T01:30:00Z` to avoid depending on when the test runs. The legacy `DateFormat` is also set to UTC explicitly, and `DateTimeFormatter` calls specify explicit locales.

If a snapshot uses:
- `LocalDate.now()`;
- `new Date()`;
- `NumberFormat.getInstance()` without a locale;
- `DateFormat.getDateInstance()` without a locale;
- the default time zone;
- live data pulled from production;

diffs become noisy and fail to isolate JDK/CLDR impacts.

**Rule:** let only metadata vary with the runtime; `DATA` should come from well-defined inputs. If intentionally testing default behavior, put the default locale/time zone in a separate test name and record them in the baseline.

## 11. Running Baseline/Candidate Across Two JDKs

Assume `LocaleSnapshot.class` was compiled for Java 17, and two runtimes exist:

~~~text
/path/to/jdk-old/bin/java
/path/to/jdk-new/bin/java
~~~

An illustrative shell workflow on Linux/macOS:

~~~bash
/path/to/jdk-old/bin/java -Djava.locale.providers=CLDR \
  -cp . LocaleSnapshot > baseline.txt

/path/to/jdk-new/bin/java -Djava.locale.providers=CLDR \
  -cp . LocaleSnapshot > candidate.txt

diff -u baseline.txt candidate.txt
~~~

The JDK paths are **configuration placeholders**, not files guaranteed on the learner's machine. Substitute the actual paths of your two runtimes. On Windows, use `java.exe` at the corresponding paths and a UTF-8-aware file comparison tool.

In CI, pin:
1. JDK feature/update/vendor or image digest;
2. `-Djava.locale.providers` flag;
3. time zone / default locale if testing defaults;
4. the exact same `LocaleSnapshot.class`, inputs, and module/classpath;
5. identical UTF-8 file writing and newlines if comparing raw bytes.

**Do not conclude from `diff` alone that a discrepancy belongs to CLDR.** Inspect every changed key and trace its provenance: provider, locale coverage, TZDB, or application code.

## 12. Separating Metadata Drift from Data Drift

When the JDK version changes, `META java.runtime.version` **naturally differs**. That belongs in the record, yet is not a formatting regression.

Separate your report into:
- **Environment drift**: Java version, vendor, tzdb, image ID, provider.
- **Behavior drift**: `DATA` for numbers/dates/money/formats/zone offsets.
- **Product acceptance**: whether each difference is approved or rejected.

A clear report:

~~~text
ENVIRONMENT:
  JDK old: 17.x
  JDK new: 21.x
  locale providers: CLDR in both
  runtime image modules: compared

BEHAVIOR:
  CHANGED fr-FR.number
  CHANGED fr-FR.date.long
  UNCHANGED en-US.number

DECISION:
  fr-FR.number: accepted locale-data update
  fr-FR.date.long: requires translator/UI review
~~~

This is an **illustrative report template**, not an asserted result from a specific pair of JDKs. Never label a change `accepted` before evidence-backed review.

## 13. A Java Tool to Diff Two Snapshots

You can write a small utility that compares **only `DATA` lines**, ignoring `META` lines kept for traceability. Since data is emitted as code points, there is no dependence on font/console rendering.

Create **`SnapshotDiff.java`**:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.SortedMap;
import java.util.TreeMap;
import java.util.TreeSet;

public class SnapshotDiff {
    static SortedMap<String, String> read(Path file)
            throws Exception {
        SortedMap<String, String> data = new TreeMap<>();

        for (String line : Files.readAllLines(
                file, StandardCharsets.UTF_8)) {
            if (!line.startsWith("DATA\t")) {
                continue;
            }
            String[] parts = line.split("\t", 3);
            if (parts.length != 3 || parts[1].isBlank()) {
                throw new IllegalArgumentException(
                        "Bad DATA line: " + line);
            }
            if (data.putIfAbsent(
                    parts[1], parts[2]) != null) {
                throw new IllegalArgumentException(
                        "Duplicate key: " + parts[1]);
            }
        }
        return data;
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println(
                    "Usage: SnapshotDiff baseline candidate");
            System.exit(2);
        }

        Map<String, String> before =
                read(Path.of(args[0]));
        Map<String, String> after =
                read(Path.of(args[1]));

        TreeSet<String> keys = new TreeSet<>();
        keys.addAll(before.keySet());
        keys.addAll(after.keySet());

        int changes = 0;
        for (String key : keys) {
            String a = before.get(key);
            String b = after.get(key);

            if (a == null) {
                System.out.println("ADDED " + key);
                changes++;
            } else if (b == null) {
                System.out.println("REMOVED " + key);
                changes++;
            } else if (!a.equals(b)) {
                System.out.println("CHANGED " + key);
                System.out.println("  old: " + a);
                System.out.println("  new: " + b);
                changes++;
            }
        }

        if (changes > 0) {
            System.out.println("DIFF count=" + changes);
            System.exit(1);
        }
        System.out.println("PASS data identical");
    }
}
~~~

~~~bash
javac -encoding UTF-8 SnapshotDiff.java
java SnapshotDiff baseline.txt candidate.txt
~~~

Returns `exit code 0` when no `DATA` differences exist, `exit code 1` when differences exist, and `exit code 2` for wrong argument count. On file read errors or duplicate keys, Java throws and does not count as PASS.

For example, with a changed grouping separator:

~~~text
CHANGED fr-FR.number
  old: U+0031 U+0032 U+00A0 U+0033
  new: U+0031 U+0032 U+202F U+0033
DIFF count=1
~~~

This is a **simulated scenario**, not guaranteed output for every JDK release. The program reports changes; it **does not decide whether a change is right or wrong**.

### A Note on Snapshot Source Code

When writing literal delimiters in `LocaleSnapshot.java`, `System.out.println` lines require `"\t"` with **a single Java tab escape**. If copying through a system that adds another escaping layer, you can rewrite it as:

~~~java
System.out.println("DATA" + (char) 9
        + name + (char) 9 + points(value));
~~~

This **snippet replaces the entire body of `data`**. It avoids multiple layers of `\` confusion when code travels through Markdown, JSON, or templates.

## 14. Code-Point Comparison vs. Semantic Comparison

There are at least three levels of accepting changes:

**Level A — Exact string parity**

~~~text
String.equals / Unicode code points identical
~~~

Appropriate when:
- A protocol mandates exact notation;
- A formatted snapshot must remain stable by contract;
- A human explicitly approves every presentation change.

**Level B — Structural/semantic parity**

For example, two date strings swap month/day order yet still represent the **same `LocalDate`** for their locale. Verify by parsing back with the corresponding formatter and comparing values:

~~~java
LocalDate parsed = LocalDate.parse(
        formatted, formatter);

boolean sameDate =
        parsed.equals(LocalDate.of(2024, 1, 2));
~~~

This is a **snippet** assuming `formatted` and `formatter` exist. With locale formatters that are not lossless round-trips in certain styles or ambiguous formats, parsing may be imperfect; choose appropriate test cases.

**Level C — UX/linguistic acceptance**

For example, a narrow space, updated month name, or changed currency symbol that conforms to updated CLDR rules. Review:
- whether localization meets user expectations;
- whether UI width remains sufficient;
- whether accessibility/screen readers read cleanly;
- whether copy/paste into external systems stays safe;
- whether representation affects reports, CSVs, or logs.

Do not **normalize all Unicode whitespace before exact diffing** and lose the signal needed for Level C review.

## 15. NumberFormat: Grouping, Decimals, and Currency

Change categories worth probing:
- U+00A0 and U+202F in grouping or between numbers and symbols;
- decimal and grouping marks;
- currency symbol placement before/after numbers;
- localized digits (e.g., ASCII vs. Arabic digits if locale/numbering system changes);
- fraction digit counts and default rounding;
- minus signs, percent symbols, and non-breaking spaces.

Do not use locale-less `NumberFormat.getInstance()` in CLDR comparison tests. Use:

~~~java
Locale fr = Locale.FRANCE;
NumberFormat number = NumberFormat.getNumberInstance(fr);
NumberFormat money = NumberFormat.getCurrencyInstance(fr);

String amountText = number.format(12345.67);
String currencyText = money.format(12345.67);
~~~

This is a **snippet**, requiring imports for `Locale` and `NumberFormat`. Exact values are **data to measure on the JDK**, never overwritten by "close enough" expected examples.

When **exact notation is required for inter-system data exchange**, use explicitly contracted formats (JSON numbers, canonical decimals) instead of treating CLDR-dependent UI strings as a protocol.

## 16. DateTimeFormatter and java.text.DateFormat Do Not Necessarily Produce Identical Output

`DateTimeFormatter` and `DateFormat` are two separate API families. Both perform locale-sensitive formatting, yet you should not assume they share identical patterns or always render identically.

Example:

~~~java
DateTimeFormatter modern =
        DateTimeFormatter.ofLocalizedDate(
                FormatStyle.LONG).withLocale(Locale.FRANCE);

DateFormat legacy =
        DateFormat.getDateInstance(
                DateFormat.LONG, Locale.FRANCE);
legacy.setTimeZone(TimeZone.getTimeZone("UTC"));
~~~

This is a **snippet** importing `java.time.format.DateTimeFormatter`, `FormatStyle`, `java.text.DateFormat`, `Locale`, and `TimeZone`.

When taking snapshots:
- Use a fixed `LocalDate` with `DateTimeFormatter`;
- Use a fixed instant with an explicit time zone for `DateFormat`;
- Never compare the two APIs on two **different dates** and conclude a bug exists;
- Inspect month/weekday names, component ordering, and punctuation.

In particular, parsing a short date can be ambiguous if the year is missing or `dd/MM` vs. `MM/dd` ordering applies. Never turn display snapshots into canonical protocol data sources.

## 17. Time Zones and TZDB: An Independent Source of Drift

When a country adjusts DST or UTC offsets, a TZDB update can alter conversion outcomes:

~~~java
Instant event =
        Instant.parse("2024-03-31T01:30:00Z");

ZonedDateTime local =
        event.atZone(ZoneId.of("Europe/Paris"));
~~~

This is a snippet requiring imports for `Instant`, `ZonedDateTime`, and `ZoneId`.

**Keep both `Instant` and `ZoneId` fixed.** If `ZoneId` varies with the CI host's time zone, the test can no longer isolate TZDB changes.

You can query the version supplied by the provider:

~~~java
String tzdbVersion =
        ZoneRulesProvider.getVersions(
                "Europe/Paris").lastKey();
~~~

This is a snippet importing `ZoneRulesProvider`. Normally the JDK TZDB provider populates the version map. For custom providers, handle missing or differing version metadata per the provider's contract.

Tests should cover:
- instants around DST transitions;
- historically significant business instants;
- future instants if long-term scheduling is used;
- specific zones such as `Asia/Ho_Chi_Minh`, `Europe/Paris`, and `America/New_York` where relevant.

**Do not call every time-zone difference a CLDR bug.** TZDB and CLDR serve different data domains.

## 18. `MessageFormat` and Application Translations

A message:

~~~text
Order {0}: {1,number,currency}
~~~

is formatted by `MessageFormat` using `Locale`. When upgrading JDK/CLDR, the `{1,number,currency}` subformat output can change even while the translation pattern stays untouched.

To pinpoint the source:
1. Keep `ResourceBundle` and the message pattern version unchanged.
2. Run with identical locale, amount, and rounding.
3. Snapshot both the **pattern** and the **formatted output**.
4. If only output changed, investigate locale data / formatter behavior.
5. If the pattern changed, investigate application translations, build, or version.

Do not mix JDK `MessageFormat` with ICU `plural`/`select` syntax. If the project uses ICU4J, the library version and ICU data are an **independent variable** to track separately from the JDK version.

## 19. A `jlink` Runtime Image Can Strip Locale Data

A full JDK and a `jlink`-built runtime image do not automatically share the same modules and data.

A minimal image:

~~~bash
jlink --add-modules java.base --output image-min
~~~

works for services inside `java.base` yet **lacks the extended locale-data module `jdk.localedata`**. Output for locales outside the base dataset can differ or fall back according to the runtime's providers/rules.

An image with extended locales:

~~~bash
jlink --add-modules java.base,jdk.localedata \
  --include-locales=en,fr,vi,ja \
  --output image-localized
~~~

This is an **illustrative command** for shells supporting `\` line continuation. `--include-locales` is a `jlink` plugin retaining only locales matching the tag list per supported matching rules; you must **include the `jdk.localedata` module** when using this plugin.

Do not treat `--include-locales=fr,vi` as guaranteeing every locale extension, calendar/numbering system, or custom provider exists. Verify the **actual language tags and features** of your app on the built image.

Documentation: [jlink Tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jlink.html).

## 20. Checking Available Modules vs. Resolved Modules

Two distinct concepts:

- **Module available in image**: the image contains the module artifact.
- **Module resolved into boot layer**: the module is included in the active runtime configuration.

Example snippet:

~~~java
boolean available = ModuleFinder.ofSystem()
        .find("jdk.localedata").isPresent();

boolean resolved = ModuleLayer.boot()
        .findModule("jdk.localedata").isPresent();
~~~

Import `java.lang.module.ModuleFinder`; `ModuleLayer` is in `java.lang`.

You can inspect modules inside an image:

~~~bash
./image-localized/bin/java --list-modules
~~~

On Windows, the executable path uses `image-localized\bin\java.exe`. Never infer from "the dev machine's JDK has `jdk.localedata`" that the production container image has it too.

**Especially important:** a test invoking `java` from `PATH` may accidentally run the full JDK instead of the newly built `image-localized/bin/java`. CI must execute the **exact binary of the deployed application image**.

## 21. Comparing Two Runtime Images Fairly

Separate your test matrix:

| Run | JDK | Runtime image | Locale data | Purpose |
| --- | --- | --- | --- | --- |
| A | Old | Full JDK | Full/expected | Baseline |
| B | New | Full JDK | Full/expected | Measure JDK/data upgrade drift |
| C | New | `jlink` image with all needed locales | Has `jdk.localedata`/include-locale | Measure image packaging impact |
| D | New | Minimal `jlink` image | Incomplete locale coverage | Negative/compatibility test |

Never compare A directly against D and conclude "upgrading the JDK broke formatting" when you **simultaneously** changed the JDK, module graph, locale data, and image packaging.

Change one variable at a time when possible:
- A → B isolates JDK/distribution changes;
- B → C isolates full JDK vs. target image differences;
- C → D identifies the impact of stripped locale data.

When all variables cannot be held constant (e.g., switching vendors), document it and **avoid overconfident attribution**.

## 22. Available Locales and Fallback Must Be Measured Separately

APIs such as:

~~~java
NumberFormat.getAvailableLocales();
DateFormat.getAvailableLocales();
Locale.getAvailableLocales();
~~~

return availability lists **per service**, which need not be identical. A locale appearing in one list does not guarantee **every translation/date/number API** has the same coverage.

`Locale.forLanguageTag("vi-VN")` can always construct a valid `Locale` object even if the runtime lacks dedicated data for that locale. Constructing the object **does not prove** native formatting data is present.

To verify a runtime image, you must:
1. Construct formatters for product-used locales.
2. Run date/number/currency/message probes.
3. Inspect outputs and metadata.
4. Confirm specific locales/providers are included/resolved.
5. Include a **negative test** for missing locale data if verifying image minimization.

`ResourceBundle.getBundle` has its own fallback chain. Never use `ResourceBundle` fallback behavior to conclude that CLDR data for `NumberFormat` was packaged completely.

## 23. Startup Properties and Environment Are Part of the Snapshot

Properties such as:

~~~text
-Djava.locale.providers=CLDR
-Duser.language=vi
-Duser.country=VN
-Duser.timezone=Asia/Ho_Chi_Minh
~~~

can affect startup defaults. In controlled comparisons, it is best to **pass `Locale` and `ZoneId` directly to APIs** rather than relying on defaults.

If you have a reason to test default locales, configure them at startup and record **both `FORMAT` and `DISPLAY` locales**. `Locale.getDefault()` does not always reflect category distinctions if the app modifies defaults per category.

Do not call `System.setProperty("java.locale.providers", ...)` mid-program and compare two results in the same JVM as if providers hot-swapped. **Provider selection must be tested in separate JVM processes** with distinct startup flags.

## 24. Compare Parser Behavior Too, Not Just Formatters

CLDR/JDK upgrades can also alter **which strings parsers accept** or how parsers interpret grouping/decimal characters.

For instance, a user submits:

~~~text
12 345,67
12 345,67
12 345,67
~~~

These three lines can contain **U+0020**, **U+00A0**, and **U+202F**. Never assume they are identical just because a font renders them similarly.

A parser probe should check:
- Does `NumberFormat.parse` return a result?
- Did the parser consume **the entire string** or only a prefix?
- Is the parsed numeric value correct?
- Which locale/provider was used?
- Were any invalid characters silently ignored?

`ParsePosition` verifies consumed length:

~~~java
ParsePosition pos = new ParsePosition(0);
Number value = numberFormat.parse(input, pos);

boolean complete = value != null
        && pos.getIndex() == input.length();
~~~

This is a snippet requiring imports for `ParsePosition` and `NumberFormat`, assuming `numberFormat` and `input` are initialized.

**Do not equate a non-throwing parse with a fully valid string**: a parser may read only a prefix. Across JDK upgrades, tests must track both **parsed values** and **consumed indexes**, not just exceptions.

## 25. Handling Golden Tests When Valid Differences Occur

A *golden file* snapshot catches unexpected changes, yet rigidly forcing new outputs to match byte-for-byte forever blocks legitimate CLDR upgrades.

Review workflow:

1. **Generate a metadata-tagged baseline** from the current production runtime.
2. **Generate a candidate** on the new runtime/image.
3. **Diff by Unicode code points** across all `DATA` entries.
4. **Group by category**: number, currency, date/time, week/calendar, timezone, `ResourceBundle`, message.
5. **Identify root cause** from CLDR/provider/TZDB/image evidence rather than guessing from a lone string.
6. **Review impact**: UI, parsers, serialization, tests, reports, customers.
7. **Approve or fix** with traceable rationale.
8. **Update golden files only after review**, archiving old baseline/diff and decision notes.

If a grouping separator shifts from U+00A0 to U+202F and that matches updated CLDR locale conventions, updating UI snapshots may be acceptable. If that same format was written into CSVs as machine-readable data and broke parsers, the right fix is **stopping the use of UI formats as protocols**, not forcing Java to emit the old character everywhere forever.

## 26. Protocol Formatting Tests Differ from UI Formatting Tests

**Data protocols** normally require stable, locale-independent notation: ISO 8601 for timestamps, JSON numbers, or explicitly specified number/currency schemas.

**UIs** follow per-locale conventions and may evolve when CLDR data updates.

Examples:
- Sending timestamps between services: use `Instant` and an explicit serialization standard.
- Displaying timestamps in Vietnamese emails: use `DateTimeFormatter` with the right locale/time zone.
- Storing monetary amounts: store `BigDecimal` plus ISO currency code, never `NumberFormat.getCurrencyInstance` output as source data.
- Displaying prices: format `BigDecimal` for the chosen locale and currency.

Never "solve" changing snapshot tests by locking the entire application to one locale. Keep **stable contracts** separate from **valid presentation updates**.

## 27. Testing Unicode and Character Data Sources

A JDK upgrade can update Unicode data. A code point classified as `UNASSIGNED` in an older release can become a letter or symbol in a newer release. Methods to check if your app relies on them:

~~~java
Character.isLetter(codePoint);
Character.isDigit(codePoint);
Character.getType(codePoint);
Character.UnicodeScript.of(codePoint);
Normalizer.normalize(text, Normalizer.Form.NFC);
~~~

This is a snippet assuming `codePoint` and `text` exist.

If username validation, search, digit classification, or case folding relies on Unicode properties, test **boundary code points** in your policy. Never confuse a Unicode property change with a CLDR locale formatting change.

**Safety:** never automatically relax security identifier policies simply because a newer runtime recognizes more code points. Application rules should adopt an explicitly chosen profile/version, upgrading data intentionally when appropriate.

## 28. When a `jlink` Image Lacks Providers or Resource Bundles

When moving to a runtime image:
- `jdk.localedata` may be absent;
- custom service providers may be missing from the module graph;
- `.properties` resources may be omitted from the artifact;
- apps using `ResourceBundleProvider`/SPI may need module bindings/config;
- locale fallback may return a different string without throwing an exception.

For `ResourceBundle`, tests must verify **files/providers are packaged** and **keys/locales resolve from the right source**. For CLDR, tests must verify **formatter output** on the runtime image itself.

**Do not "fix" everything with `--add-modules jdk.localedata`** if the real bug is forgetting to copy `Messages_vi.properties`. Conversely, do not fix a missing properties file by tweaking `java.locale.providers`. These two resource layers are related yet **not the same mechanism**.

## 29. Tests to Include in CI

Organize tests into three groups:

**Group 1 — Behavioral contract, run on every PR**
- Fixed `Locale`/`ZoneId`.
- Fixed date/number/money/pattern inputs.
- Parser round-trip and full consumption.
- `ResourceBundle` keys and `MessageFormat` arguments.
- Product rules that are **strictly invariant**.

**Group 2 — Snapshot drift, run on JDK/image upgrades**
- Golden code-point outputs for core locales.
- Metadata for Java vendor/build/provider/TZDB/modules.
- String-exact diffs categorized by service/locale.
- Critical templates: invoices, emails, payments, calendars.
- Manual review before updating expected snapshots.

**Group 3 — Image integration, run on the deployed artifact**
- Actual `bin/java` binary of the `jlink` image.
- Module list, `jdk.localedata`, provider availability.
- `ResourceBundle` module/provider lookup.
- Formatting and parsing for key locales.
- Root fallback or missing-locale behavior per policy.

Archive baseline/candidate/diff results as versioned CI artifacts. Never save only UI screenshots or strip metadata so future diffs cannot tell which environment produced the output.

## 30. How to Triage Failures When Tests Break

| Observation | Likely area to check | Next step |
| --- | --- | --- |
| `fr-FR.number` changed grouping mark | CLDR/provider | Compare code points, provider order |
| `fr-FR.currency` changed symbol/placement | Locale/currency data | Review UI and amounts |
| Date/time text differs | CLDR/format provider | Compare locale, style, pattern |
| Zoned date offset differs | TZDB | Compare fixed instant, zone, TZDB version |
| Only `jlink` image differs from full JDK | Module/locale coverage | Check `jdk.localedata` and `--include-locales` |
| Every locale differs due to default | Startup config | Log `FORMAT` locale/timezone; pass explicitly |
| `MessageFormat` differs while raw pattern matches | Formatter locale/provider | Compare fixed args and format data |
| Translated text differs and raw bundle differs too | Application/packaging | Compare bundle version and keys |
| Parser fails after upgrade | Number/date parsing rules | Check `ParsePosition`, locale |
| Failure appears only in CI | Different environment or image | Run the exact CI runtime binary |

These are **investigation hypotheses**, not automatic diagnoses. A single key can change for multiple reasons at once, especially when upgrading container base images and the JDK together.

## 31. Common Mistakes to Avoid

1. **Snapshotting `String` by eye alone**: misses NBSP, NNBSP, combining marks.
2. **Omitting JDK vendor/update**: makes data provenance unreproducible.
3. **Omitting provider order**: hides whether CLDR, HOST, or SPI ran.
4. **Comparing an old full JDK with a new `jlink` image and blaming the JDK**: changes multiple variables at once.
5. **Using today's date / default time zone**: snapshots shift with wall-clock time.
6. **Relying on implicit default locale**: diverges between developer laptops and CI.
7. **Checking only that `Locale.forLanguageTag` constructs an object**: proves nothing about locale data availability.
8. **Treating available-locale count as coverage for every API**: each service has its own coverage.
9. **Treating `COMPAT` as a permanent option**: legacy data was removed in JDK 23.
10. **Treating every diff as a regression**: valid CLDR updates can legitimately change output.
11. **Treating every diff as acceptable**: may silently break protocol or UI contracts.
12. **Normalizing Unicode whitespace before exact diffing**: hides real differences.
13. **Auto-updating golden files to match candidates**: eliminates human review.
14. **Forgetting parser checks**: valid rendering does not prove legacy inputs still parse.
15. **Forgetting TZDB checks**: DST offsets can shift independently of CLDR.
16. **Omitting `jdk.localedata` when building images**: leaves locale coverage incomplete.
17. **Testing `PATH` `java` instead of the real image**: results fail to represent production.
18. **Conflating app `ResourceBundle`s with CLDR**: leads to misdiagnosis.
19. **Snapshotting real user data**: risks leaking PII or secrets.
20. **Trying to freeze every UI format forever**: blocks beneficial linguistic updates.

## 32. Review Questions and Answers

**Question 1.** Why can identical Java code produce different `NumberFormat` output after a JDK upgrade?

**Answer:** CLDR/provider data, locale configuration, or JDK implementations can change without any application code edits.

**Question 2.** Can `java.locale.providers=COMPAT` be used indefinitely to preserve legacy output?

**Answer:** No. Legacy `COMPAT`/`JRE` locale data was removed in JDK 23; migrate to CLDR and re-test.

**Question 3.** Why is visually comparing formatted number grouping insufficient?

**Answer:** U+0020, U+00A0, and U+202F can look alike yet have different code points.

**Question 4.** Does a `jlink` image without `jdk.localedata` necessarily match a full JDK?

**Answer:** No. The image may lack extended locale data, so test directly on the real built image.

**Question 5.** What must you watch out for with `--include-locales`?

**Answer:** Include the `jdk.localedata` module when using the plugin and verify the locales/services your app actually needs are retained.

**Question 6.** Why record `TZDB version` when testing time zones?

**Answer:** DST/offset rules can update independently of CLDR and alter conversions at a fixed instant.

**Question 7.** Should JDK upgrade golden tests use `LocalDate.now()`?

**Answer:** No, if you want to isolate runtime changes. Use a fixed `LocalDate`.

**Question 8.** If only Java version metadata differs while all `DATA` lines match, is there a formatting regression?

**Answer:** There is no evidence of regression within the measured probe set; you still cannot extrapolate beyond what the probes cover.

**Question 9.** If a parser reads only a prefix of a new string without throwing an exception, does it pass?

**Answer:** No. Check `ParsePosition.getIndex() == input.length()` to ensure the entire input was consumed.

**Question 10.** Why must golden files never be auto-updated for every difference?

**Answer:** Doing so can mask regressions. Classify the cause, review impact, and approve intentionally per product decision.

## 33. Practical Upgrade Checklist

- [ ] List all product-supported locales, currencies, calendars, and time zones.
- [ ] Record version/build/vendor for both baseline and candidate runtimes.
- [ ] Record `java.locale.providers`, default `FORMAT`/`DISPLAY` locales, and default time zone.
- [ ] Record TZDB version, image ID, and module/locale coverage.
- [ ] Compile the same source/probe suite compatible with both runtimes.
- [ ] Pin `BigDecimal`, `LocalDate`, `Instant`, and sample argument inputs.
- [ ] Emit formatted text as Unicode code points.
- [ ] Compare `NumberFormat`, `DateTimeFormatter`, `DateFormat`, `MessageFormat`, `ResourceBundle`, and parsers.
- [ ] Run separately on the full JDK and the **actual deployed runtime image**.
- [ ] Verify `jdk.localedata` and `--include-locales` if using `jlink`.
- [ ] Classify diffs by CLDR/provider, TZDB, app resources, or environment.
- [ ] Review UI/format/protocol impact and linguistic accuracy.
- [ ] Update golden files only after review, recording the rationale.
- [ ] Archive comparison artifacts for the next migration.

## 34. Conclusion

A JDK, CLDR, or runtime image upgrade **cannot be judged merely by "the code still compiles."** Localization requires reproducible measurements: **identical inputs, identical locales, identical time zones, identical provider policy, with only the runtime varying under control**.

Build **snapshots tagged with environment fingerprints**, export **Unicode code points** of the output, and run a **reviewed diff**. Keep **UI formatting bugs** separate from **machine-readable data contracts**; separate **CLDR** from **TZDB**; separate JDK locale data from **application resource bundles**. For `jlink`, test directly on the deployed image, not only on a developer machine's full JDK.

**Key takeaway:** **An output difference is a signal to investigate**, neither automatically a bug nor automatically safe to ignore. A sound migration workflow is **detect → reproduce → isolate root cause → assess impact → approve or fix → update baseline under control**.

**Java and Oracle References:**
- [Oracle JDK 17 Internationalization Enhancements](https://docs.oracle.com/en/java/javase/17/intl/internationalization-enhancements1.html).
- [Java 17 LocaleServiceProvider](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/spi/LocaleServiceProvider.html).
- [JDK 23 Removed Tools and Components](https://docs.oracle.com/en/java/javase/23/migrate/removed-tools-and-components.html).
- [JDK 17 jlink](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jlink.html).
- [Java 17 NumberFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html).
- [Java 17 DateTimeFormatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html).
- [Java 17 ZoneRulesProvider](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/zone/ZoneRulesProvider.html).
