# java.locale.providers and Provider Ordering in the JDK

## 1. Problem: Locale is not a source of locale data

When writing multilingual Java software, we often choose a locale explicitly and call:

```java
Locale fr = Locale.FRANCE;
NumberFormat number = NumberFormat.getNumberInstance(fr);
DateFormat date = DateFormat.getDateInstance(
        DateFormat.LONG, fr);
```

These statements reside in a Java method with appropriate imports. They request formatting numbers and dates according to French conventions in France. Yet **where do the date pattern, decimal separator, thousands grouping symbol, and month names come from?**

JDKs have **locale-sensitive service providers**. The system property `java.locale.providers` controls the **priority order of data/implementation providers for localization services**:

```bash
java -Djava.locale.providers=CLDR,SPI -jar app.jar
```

This property **does not select the user's locale**. It only tells the runtime the lookup order of providers—for example, CLDR first and then SPI. With the same `Locale.FRANCE`, formatted outputs can change when changing providers or upgrading the JDK because the underlying data changes.

This is a core issue when migrating from JDK 8 to JDK 17, or from JDK 17 to JDK 23+: locale datasets have their own lifecycles and can alter punctuation, symbols, Unicode whitespace, or abbreviations. If an application stores formatted strings instead of typed data, what seems like a display-only change can break parsing or tests.

### Target outcomes

After this lesson, readers will be able to:

1. Distinguish `Locale`, locale providers, and APIs that consume locale data.
2. Understand `CLDR`, `COMPAT`/`JRE`, `SPI`, and `HOST`, including version limitations.
3. Explain how provider ordering is evaluated and when fallback occurs.
4. Set `-Djava.locale.providers=...` properly at JVM **startup**.
5. Test two orderings in two separate Java processes and diagnose Unicode code point differences.
6. Understand how an SPI provider is created and registered.
7. Avoid assuming provider ordering affects every library or every service identically.
8. Plan testing when upgrading the JDK, especially around the removal of COMPAT starting in **JDK 23**.

## 2. Three concepts to keep separate

| Component | Answers the question | Example |
| --- | --- | --- |
| **Locale** | For which user/language/region? | `Locale.FRANCE`, `Locale.forLanguageTag("vi-VN")` |
| **Locale provider** | Who supplies the localization data/implementation? | `CLDR`, `SPI`, `HOST`, `COMPAT` on older JDKs |
| **Locale-sensitive API** | Which type of service is being requested? | `NumberFormat`, `DateFormat`, `Currency`, `Locale` display names |

Example:

```java
NumberFormat formatter =
        NumberFormat.getNumberInstance(Locale.FRANCE);
```

`Locale.FRANCE` is the **target locale**, `NumberFormat` is the **service type**, and the runtime queries sources in the property's order when creating the formatter. Changing the property does not mean switching a user from Vietnamese to French.

Conversely, `Locale.getDefault()` and `Locale.setDefault(...)` govern the **JVM's default locale**. When a factory receives no explicit locale, it may use `Locale.getDefault(Locale.Category.FORMAT)`. This is an orthogonal axis from providers. Never change the default locale per web request, as JVM-wide side effects can affect other threads.

`java.locale.providers` is also **not a charset**: UTF-8/UTF-16 governs converting text to bytes. It does not substitute for the application's `ResourceBundle`, does not fix missing translations, and does not determine an `Instant`'s timezone.

## 3. Four important provider groups

### 3.1. CLDR — Unicode localization data

`CLDR` is the source based on Unicode's **Common Locale Data Repository**. The JDK uses this data for many services such as date/time formatting rules, numbers, currency symbols, and display names, depending on the API and version.

**Starting with JDK 9, CLDR became the default prioritized source.** CLDR is not immutable: when a JDK upgrades its CLDR data version, display strings can change. For instance, a thousands grouping space might be U+202F (narrow no-break space) rather than U+0020 (space), even though visually they look similar.

**Do not conclude that every service uses CLDR in the exact same way.** Oracle JDK 17 documentation includes specific caveats regarding `BreakIterator` and `Collator` data. Libraries outside the JDK such as ICU4J or browser engines also maintain their own pipelines and data.

### 3.2. COMPAT/JRE — legacy provider

For **JDK 17**, `COMPAT` is a data source aimed at compatibility with the rules of older JDKs, particularly pre-JDK 9. `JRE` is a historical alias for `COMPAT` and has been deprecated.

Example to **test** compatibility on JDK 17:

```bash
java -Djava.locale.providers=COMPAT,CLDR LocaleProvidersDemo
```

This configuration prioritizes COMPAT before CLDR for applicable locales/services. It may produce formats resembling legacy systems in some places, but **does not guarantee restoring every Java 8 behavior**.

Key milestones:

| Version | Context |
| --- | --- |
| JDK 8 | Traditional JRE source is used by default; CLDR can be configured optionally. |
| JDK 9–20 | CLDR is the prioritized source; COMPAT remains for migration in supported releases. |
| JDK 21–22 | Specifying JRE/COMPAT emits warnings ahead of legacy data removal. |
| **JDK 23 and later** | **Legacy JRE/COMPAT data has been removed.** Listing it in the property does not restore legacy data. |

Therefore, saying "just use COMPAT to keep old outputs" can only be a **transitional measure on JDKs that still ship COMPAT**, not a strategy for all of Java 17+.

### 3.3. SPI — Service Provider Interface

`SPI` is for implementations supplied by developers or libraries via subclasses of providers in `java.text.spi` and `java.util.spi`. Some APIs:

- `NumberFormatProvider` — number, percent, currency, and integer formatters.
- `DateFormatProvider`, `DateFormatSymbolsProvider` — date formatting and symbols.
- `DecimalFormatSymbolsProvider` — number symbols.
- `LocaleNameProvider`, `CurrencyNameProvider` — language/region and currency names.
- `TimeZoneNameProvider` — time zone names.
- `CollatorProvider` and `BreakIteratorProvider` — corresponding services.

If you want SPI prioritized, place it first:

```bash
java -Djava.locale.providers=SPI,CLDR LocaleProvidersDemo
```

**Do not just add the word SPI and expect new data to appear.** The runtime must locate a corresponding implementation on the classpath/module path. If no implementation exists or the provider does not support the requested service/locale, only then does the next provider in the list get a chance to respond.

Conversely, `CLDR,SPI` typically prioritizes CLDR wherever CLDR has support, so a custom SPI might not be used for overlapping requests. The ordering of provider names is the crucial part of the configuration.

### 3.4. HOST — data from the OS when available

`HOST` can reflect the operating system's user locale customizations, such as date/time or number formatting rules. **Not every OS/JDK supports HOST equally.** In Oracle JDK 17, HOST has support on Windows/macOS per the corresponding locale documentation.

Sample configuration:

```bash
java -Djava.locale.providers=HOST,CLDR LocaleProvidersDemo
```

If HOST is unavailable or does not support a specific service/locale, the runtime may continue to the subsequent source. Therefore, **putting HOST in the property does not prove the actual result came from the OS**. Linux/container servers can behave differently from Windows/macOS desktops; do not use HOST when reproducibility is required without verifying the environment.

## 4. Precedence and fallback mechanism

Consider JDK 17 with the property:

```text
java.locale.providers=SPI,CLDR,COMPAT
```

When the application calls `NumberFormat.getNumberInstance(localeX)`, the lookup order **conceptually** is:

```text
Request: NumberFormat for localeX
   |
   v
Does SPI support NumberFormat + localeX?
   | yes -> use matching SPI formatter
   | no
   v
Does CLDR support service + localeX?
   | yes -> use CLDR
   | no
   v
Does COMPAT support it? (only on JDKs still having COMPAT)
   | yes -> use COMPAT
   | no
   v
Locale/root fallback and applicable JDK mechanism
```

This is a pedagogical diagram, **not internal source code**. The runtime has its own parent-locale lookup rules, service configuration, caching, and implementation details. Nevertheless, it reveals two truths:

1. **Order matters:** `SPI,CLDR` and `CLDR,SPI` can produce different results when both sources can satisfy the request.
2. **Fallback matters:** if the first provider lacks the requested service/locale, the runtime can consult subsequent sources. There is no guarantee the leading provider wins every call.

### Distinguish four kinds of fallback

- **Provider fallback:** from SPI to CLDR when SPI lacks suitable data.
- **Locale fallback:** from a specific locale to a parent/generic locale per API rules.
- **ResourceBundle fallback:** resolving application bundles, distinct from the provider property.
- **Font fallback:** renderer searching for fonts/glyphs, completely separate from locale formatting data.

When outputs do not change across configurations, it may be because both sources share the same rule for that locale, the service does not support the tested provider, or fallback leads to the same data. **No visible change does not mean the property was ignored.**

### Default provider order by JDK

For **Oracle/OpenJDK 17**, the documented default corresponds to `CLDR,COMPAT`. Starting in **JDK 23**, legacy COMPAT is gone, and the default on Oracle JDK 23 corresponds to `CLDR`. Other vendors/JDKs should be checked against their implementation docs.

`System.getProperty("java.locale.providers")` returning `null` does not mean there are no providers. It merely indicates no explicit value was set in system properties at the time you read it.

## 5. Starting the JVM properly

### 5.1. System property syntax

`-Djava.locale.providers=...` is a **JVM option**. It must appear before the main class or before `-jar`:

```bash
java -Djava.locale.providers=CLDR,SPI -cp app.jar com.example.Main
java -Djava.locale.providers=CLDR,SPI -jar app.jar
```

Incorrect example:

```text
java com.example.Main -Djava.locale.providers=SPI,CLDR
```

In the incorrect command, `-D...` usually goes into the application's `args[]` rather than becoming a JVM system property. Inspect the JVM options of the actual running process, not just build tool configuration files.

### 5.2. The property is read at startup

Per Java 17 documentation, the provider order is read when the Java runtime starts up; in newer JDK docs, the value is also read/cached during service initialization. Therefore:

```java
System.setProperty("java.locale.providers", "SPI,CLDR");
```

**is not a safe way to switch providers after locale services have initialized.** Do not create a formatter first, set the property afterward, and assume a new formatter will use the new order. **Compare using two separate JVM processes** with different command-line options.

`Locale.setDefault(Locale.US)` also does not solve this: it only adjusts the default locale, not provider order, and it is JVM-wide shared state.

### 5.3. Common pitfalls in build systems

IDEs, Maven, Gradle, application servers, test forks, containers, and CLIs may run in **different Java processes**. Setting a system property on the Gradle daemon does not guarantee the test JVM or application JVM receives it. In CI, explicitly record:

- Command line of the process running the app or tests.
- JDK vendor + version (not only compiler version).
- Actual `java.locale.providers` inside the process.
- Locale, timezone, currency, and style/pattern at formatting sites.
- Pre/post-upgrade test suite results.

In containers, pass the property in the container entrypoint's JVM options; do not try changing it on a thread once services have started.

## 6. Standalone Java 17+ example: checking numbers, dates, and Unicode code points

Create the file **`LocaleProvidersDemo.java`** below. The program needs no external data files, does not mutate the JVM default locale, and uses `Locale.FRANCE` and `UTC` explicitly. It prints the current property configuration, the JDK feature version number, and the code points of the number string to reveal near-identical whitespace characters.

```java
import java.text.DateFormat;
import java.text.NumberFormat;
import java.time.Instant;
import java.util.Date;
import java.util.Locale;
import java.util.StringJoiner;
import java.util.TimeZone;

public class LocaleProvidersDemo {

    private static String codePoints(String text) {
        StringJoiner out = new StringJoiner(" ");
        text.codePoints().forEach(cp ->
                out.add(String.format(
                        Locale.ROOT, "U+%04X", cp)));
        return out.toString();
    }

    public static void main(String[] args) {
        Locale fr = Locale.FRANCE;
        Date fixed = Date.from(
                Instant.parse("2024-01-02T12:00:00Z"));

        DateFormat date = DateFormat.getDateInstance(
                DateFormat.LONG, fr);
        date.setTimeZone(TimeZone.getTimeZone("UTC"));

        String number = NumberFormat
                .getNumberInstance(fr)
                .format(12345.67);

        System.out.println("javaFeature="
                + Runtime.version().feature());
        System.out.println("configured="
                + System.getProperty(
                        "java.locale.providers", "<default>"));
        System.out.println("frDate=" + date.format(fixed));
        System.out.println("frNumberCodepoints="
                + codePoints(number));
        System.out.println("frNumberLength=" + number.length());
    }
}
```

Compile with JDK 17 or later:

```bash
javac -encoding UTF-8 LocaleProvidersDemo.java
```

Run **each line in a separate process**:

```bash
java LocaleProvidersDemo
java -Djava.locale.providers=CLDR LocaleProvidersDemo
java -Djava.locale.providers=SPI,CLDR LocaleProvidersDemo
```

If you are on **JDK 17–22** and want to inspect legacy data:

```bash
java -Djava.locale.providers=COMPAT,CLDR LocaleProvidersDemo
java -Djava.locale.providers=CLDR,COMPAT LocaleProvidersDemo
```

From JDK 23 onward, COMPAT is no longer an effective option. **Do not use test results on JDK 24 to infer how JDK 17's COMPAT behaves.**

**Observed stdout on a Zulu OpenJDK 24 test machine, default configuration:**

```text
javaFeature=24
configured=<default>
frDate=2 janvier 2024
frNumberCodepoints=U+0031 U+0032 U+202F U+0033 U+0034 U+0035 U+002C U+0036 U+0037
frNumberLength=9
```

This is a **specific verified output**, not a promise that every Java 17+ runtime returns every line identically. On JDK 17 `javaFeature` will be 17; when `-D` is passed, `configured` will show the configured value. Dates/numbers can vary when providers, CLDR version, JDK vendor, or locale data change.

### Reading the output lines

1. `javaFeature` confirms the actual process's feature version.
2. `configured=<default>` means no explicit property was seen; the runtime still uses its default provider order.
3. `frDate` illustrates the French month name thanks to `Locale.FRANCE` being passed explicitly.
4. `frNumberCodepoints` in the tested environment uses `U+202F` as the thousands grouping separator and `U+002C` as the decimal comma.
5. `frNumberLength=9` counts **UTF-16 code units**, not UTF-8 bytes.
6. You cannot deduce the actual provider name used from a single output string; multiple providers may produce identical output.

### Why inspect using code points?

ASCII space `U+0020`, no-break space `U+00A0`, and narrow no-break space `U+202F` can look nearly identical in the UI, yet **`String.equals`, parsers, and snapshot tests distinguish them**. Printing code points helps pinpoint the root cause after a JDK upgrade instead of blindly "fixing" strings by stripping all whitespace without checking formatting rules.

## 7. SPI: packaging an application-supplied provider

### 7.1. Registration mechanism

`java.util.spi.LocaleServiceProvider` is the abstract base class for locale-sensitive SPIs. An implementation can be packaged on the classpath with a **service configuration file**:

```text
META-INF/services/java.text.spi.NumberFormatProvider
```

If the implementation is named `demo.CustomNumberProvider`, the file contents are:

```text
demo.CustomNumberProvider
```

The service configuration file must be UTF-8 encoded. With Java modules, you can declare `provides ... with ...` in `module-info.java` per the Java module/service loader contract. Do not simply create a class and expect the runtime to scan every class on the classpath automatically.

### 7.2. Sample provider structure

Below is an example **illustrating how to extend the API**, not a production-ready formatter suite:

```java
package demo;

import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.NumberFormat;
import java.text.spi.NumberFormatProvider;
import java.util.Locale;

public final class CustomNumberProvider
        extends NumberFormatProvider {

    private static final Locale TEST =
            Locale.forLanguageTag("en-XA");

    @Override
    public Locale[] getAvailableLocales() {
        return new Locale[] { TEST };
    }

    private NumberFormat make(String pattern) {
        // Use US symbols here to avoid recursively calling
        // the NumberFormat factory for the TEST locale itself.
        return new DecimalFormat(pattern,
                DecimalFormatSymbols.getInstance(Locale.US));
    }

    @Override
    public NumberFormat getNumberInstance(Locale locale) {
        return make("'[custom] '#,##0.00");
    }

    @Override
    public NumberFormat getIntegerInstance(Locale locale) {
        NumberFormat f = make("'[custom] '#,##0");
        f.setParseIntegerOnly(true);
        return f;
    }

    @Override
    public NumberFormat getCurrencyInstance(Locale locale) {
        return make("'[custom currency] '¤#,##0.00");
    }

    @Override
    public NumberFormat getPercentInstance(Locale locale) {
        return make("'[custom percent] '0.0%");
    }
}
```

In the code above, you must add **locale parameter validation**, integer rounding/parsing policy, currency metadata, locale fallback, Unicode extensions, and contract tests before production use. `NumberFormatProvider` requires each method to honor the semantics of its formatter type; for instance, percent must multiply inputs by 100 when displaying rather than merely appending a literal `%` sign. This example focuses solely on the SPI skeleton.

A real provider must declare exactly the locales it supports. Declaring locales that are not properly implemented can break formatting across many areas. Never create an infinite recursion loop by calling `NumberFormat.getNumberInstance(locale)` for the very locale the provider is serving.

### 7.3. SPI order and classpath

Put the provider JAR on the **application process's** classpath/module path and run with:

```bash
java -Djava.locale.providers=SPI,CLDR -cp "app.jar;provider.jar" demo.Main
```

The classpath line above illustrates **Windows** with `;`. On Linux/macOS, the classpath separator is typically `:`. The JARs and main class are illustrative names; they must exist after your build step with properly registered providers.

When a service/locale is already supported by CLDR, `CLDR,SPI` may prioritize CLDR, whereas `SPI,CLDR` gives SPI the chance to be selected first. Without an actual SPI artifact, adding `SPI` to the order creates no new data.

## 8. Diagnostics: the property does not prove which provider won

`System.getProperty("java.locale.providers")` only tells you **the requested order**, not the exact history of every lookup. There is no single simple standard API for every formatter to return the actual provider name used.

To diagnose issues, collect:

- Full Java version and JDK distribution/vendor.
- Actual JVM arguments/launcher flags (not just compile options).
- The value of `java.locale.providers`.
- Locale, style/pattern, timezone/currency, and format/parse APIs.
- Unicode code points of formatted results when punctuation/whitespace differs.
- Outputs from running **two fresh JVM processes**.
- For custom SPIs, log directly inside provider methods and verify service registration.

`NumberFormat.getAvailableLocales()` or `DateFormat.getAvailableLocales()` shows locales that may be supported, **not a map of "which provider serves each locale."** The same locale can be backed by multiple sources.

### Do not equate the provider chain with ResourceBundle

`ResourceBundle.getBundle(...)` has its own mechanism for resolving and falling back across application bundles. It does not turn `messages_vi.properties` translation files into CLDR or SPI sources. Likewise, ICU4J has its own mechanisms/data; changing `java.locale.providers` does not implicitly change formatting in ICU4J or browsers.

## 9. Upgrading the JDK: changes that must be tested

When upgrading from JDK 8 to 17 or from JDK 17/21 to 23+, audit code paths using locale-sensitive services:

| Area | Common APIs | What can change |
| --- | --- | --- |
| Date/time | `DateFormat`, `SimpleDateFormat`, localized `DateTimeFormatter` | Month/weekday names, punctuation, AM/PM, styles. |
| Numbers | `NumberFormat`, `DecimalFormatSymbols` | Grouping/decimal separators, digits, spacing. |
| Currency | `NumberFormat.getCurrencyInstance`, `Currency` | Symbols, placement, whitespace, fractional digits. |
| Display names | `Locale.getDisplayName` and locale-name services | Language/region names. |
| Timezone text | `TimeZone.getDisplayName` | Timezone names/abbreviations. |
| Sorting/segmentation | `Collator`, `BreakIterator` | Specific data and implementations, not completely uniform with CLDR. |

### A short test matrix to maintain

- Use the locales actually supported by the product, not only `en-US`.
- Fix `Instant`, timezone, currency, and input numbers when comparing.
- Print formatted text and code points/hex to spot whitespace differences.
- Test parsing after formatting where the domain requires it; verify the parser consumes the whole input.
- For dates, test two-digit years, month names, invalid dates, and day/month order.
- For numbers, test grouping, fractions, negative numbers, percentages, and currencies.
- Test real inputs previously saved from the older JDK.
- Run on each target JDK/vendor and the exact `java.locale.providers` planned for deployment.
- When SPI is present, test both locales supported by the provider and locales that must fall back.

### Why is COMPAT not a long-term solution?

A legacy system may have relied on `COMPAT` to defer formatting changes since JDK 9. However, **starting with JDK 23, legacy data no longer exists**. When applications communicate machine-to-machine, use schemas, ISO formatters, or stable decimal formats instead of serialized display strings. If invoices or forms must follow fixed rules, explicitly configure formats and version the contract rather than expecting legacy data to remain in the runtime forever.

## 10. Common mistakes

| Mistake | Consequence | Correct approach |
| --- | --- | --- |
| Thinking the property picks the user's language | CLDR/SPI is not `Locale.FRANCE`. | Choose Locale explicitly; providers are data sources. |
| Writing `-D` after the main class | Treated only as an application argument. | Place options before the class/`-jar`. |
| Calling `System.setProperty` after init | Order may already be read/cached. | Restart the process with JVM options. |
| Using `COMPAT` across all Java 17+ versions | JDK 23 removed legacy data. | Migrate to CLDR or a dedicated provider/format. |
| Thinking `JRE` is a completely distinct provider from `COMPAT` | Historical alias name. | Understand the timeline and JDK 23 removal. |
| Having an SPI JAR without enabling `SPI` | Custom provider might not be consulted. | Register the service and declare order. |
| Setting `CLDR,SPI` and expecting SPI always wins | Earlier provider may support the locale. | Use `SPI,CLDR` if custom overrides must take precedence. |
| Trusting HOST always works in containers | HOST depends on OS/vendor. | Have fallbacks and test on target OS. |
| Treating formatted output as a stable protocol | CLDR/JDK data can change. | Store typed data, format in the UI. |
| Ignoring U+202F/U+00A0 in snapshots | Strings look alike but differ in code points. | Log Unicode code points when diagnosing. |
| Thinking every service pulls data from CLDR | Exceptions exist by API/JDK. | Check per-service documentation. |
| Treating `System.getProperty` as actual provider used | It is only the requested configuration. | Compare empirically and log inside SPI. |
| Changing `Locale.setDefault` per user | Affects concurrent requests. | Pass user Locale into factories. |

## 11. Hands-on exercises

**Exercise 1 — Ordering:** On JDK 17, run `CLDR,COMPAT` and `COMPAT,CLDR` in two separate JVM processes. Record `LocaleProvidersDemo` stdout and explain: why does seeing no difference for one locale not prove the ordering was ignored?

**Exercise 2 — Version comparison:** Run the same code on JDK 17 and JDK 23+, trying the COMPAT configuration in a test environment. Verify how legacy support differs across versions and draft a migration plan.

**Exercise 3 — SPI provider:** Create a `NumberFormatProvider` for a test locale, package `META-INF/services`, and run with `SPI,CLDR`. Test one locale supported by the SPI and one unsupported locale; document where fallback occurs.

**Exercise 4 — Unicode whitespace:** Compare `Locale.FRANCE` number strings across two JDKs; print code points and distinguish `U+0020`, `U+00A0`, and `U+202F`. Never blindly strip all spaces without understanding the contract.

**Exercise 5 — Property timing:** Create a formatter, then call `System.setProperty`, and create another formatter. Compare against a fresh process launched with `-D`. Explain why testing inside the same JVM is insufficient.

**Exercise 6 — API architecture:** A REST API currently outputs `"1 234,50 €"` as transaction data. Redesign it with separate amount and currency code fields, formatting in the UI by locale. Explain why this design is resilient to provider changes.

**Exercise 7 — Upgrade failure analysis:** After a JDK upgrade, a date is rendered with different punctuation or AM/PM markers. List the JDK version, provider property, API, Locale, timezone, and code points to gather; separate display changes from parsing/protocol bugs.

### Checklist

- [ ] Distinguish `Locale`, locale providers, and locale-sensitive services.
- [ ] Know `-Djava.locale.providers` syntax and priority-by-order semantics.
- [ ] Explain `CLDR`, `SPI`, `HOST`, `COMPAT/JRE` and platform/version limits.
- [ ] Know CLDR became default in JDK 9 and COMPAT was removed in JDK 23.
- [ ] Understand per-service/locale fallback without inferring the real source from the property alone.
- [ ] Set the system property when launching the JVM, not relying on runtime mutation.
- [ ] Know `META-INF/services` files and the role of `SPI`.
- [ ] Test exact Unicode code points when outputs look alike yet differ.
- [ ] Pass Locale/zone/currency explicitly and avoid display strings as protocols.
- [ ] Maintain a migration testing plan for JDK/CLDR upgrades.

## 12. Official references

- JDK 17 `LocaleServiceProvider`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/spi/LocaleServiceProvider.html
- Oracle JDK 17 supported locales: https://www.oracle.com/java/technologies/javase/jdk17-suported-locales.html
- JDK 23 removed legacy locale data: https://docs.oracle.com/en/java/javase/23/migrate/removed-tools-and-components.html
- JDK 17 `NumberFormatProvider`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/spi/NumberFormatProvider.html

**Conclusion:** `java.locale.providers` specifies the **prioritized lookup order of locale data sources**, without changing the user's language on its own. CLDR is the primary source on modern JDKs; SPI enables extensibility; HOST is system-dependent; COMPAT/JRE belongs to the pre-23 past. Set the order at Java startup, pass explicit locales into APIs, test on real runtimes, and never turn localized strings into canonical data identifiers.
