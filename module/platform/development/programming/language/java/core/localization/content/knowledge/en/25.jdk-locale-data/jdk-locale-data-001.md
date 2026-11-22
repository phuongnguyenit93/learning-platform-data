# CLDR and Its Role in Providing Localization Conventions for the JDK

In a multilingual Java application, changing the `Locale` can change how dates, numbers, currency units, month names, country names, or time expressions are formatted. Most of those differences **are not derived from a language code using a few `if` statements**. They require a data source that is researched, maintained, and updated across many languages and regions. **Unicode CLDR — Common Locale Data Repository** — is one of the most important foundational data sources for that task.

In Java, CLDR is not a `translate()` function or an object you call directly to fetch "the translation of the entire application." It is a **repository of localization data and rules**, used by the JDK through appropriate **locale data providers** and APIs. JDK 9 and later prioritize CLDR data by default; in particular, applications running Java 17 need to understand the provider mechanism, the scope limitations implemented by the JDK, and the possibility that results may change when upgrading the JDK/CLDR.

Lesson objectives: understand what CLDR provides, how Java Core consumes locale data, why the same `Locale` can yield different results across JDKs, when you need self-translated resources or specialized libraries, and how to test applications rather than hardcoding every cultural convention.

## 1. What is CLDR?

**CLDR (Common Locale Data Repository)** is the locale data project of the Unicode Consortium. It provides structured data and rules for **internationalization (i18n)** and **localization (l10n)** across many languages, scripts, and geographic regions.

Typical examples of CLDR data and conventions:

- Formatting patterns for **dates, months, and times**, weekday names, month names, time intervals, and time zone names by language.
- Symbols for **decimal separators**, digit grouping, number display, and currency units.
- Display names of **languages, scripts, countries/regions, and currencies**.
- Information on **first week of the year, first day of the week**, calendar system conventions, and regional preferences.
- **Plural/cardinal/ordinal** rules for many languages, used to select message forms.
- Other data and rules in the CLDR ecosystem for **collation, segmentation, unit formatting, numbering systems**, and language interactions.

This is the **scope list of the CLDR project**, not a guarantee that JDK 17 has exposed all of CLDR's data and algorithms as standard Java APIs. Specific classes or capabilities must be verified against the Java version and active locale provider.

CLDR also has specification documents, notably **UTS #35 / LDML** (Locale Data Markup Language), describing the data structure and usage rules. CLDR data is contributed by the community, linguists, and many organizations, reviewed, and released in versions. For that exact reason, **display conventions are not necessarily immutable over time**.

### A simple example

For the same number `1234.5`, an application typically displays it differently depending on the locale:

~~~text
en-US → 1,234.5
de-DE → 1.234,5
~~~

The thousands separator and decimal separator **swap roles**. That illustrates **presentation conventions**, not a change in numeric value. `1234.5` remains the exact same numerical quantity.

Similarly, the same calendar date `2024-06-16` may be displayed in month/day/year or day/month/year order. Applications should not equate localized strings with source date data meant for machine processing.

## 2. CLDR is not synonymous with Locale, ResourceBundle, or application translation

Four concepts have distinct roles:

| Concept | Primary responsibility | Example |
| --- | --- | --- |
| `Locale` | Identifies language, region, script, and locale options | `Locale.forLanguageTag("vi-VN")` |
| CLDR | Shared localization data/rules for software to apply | Decimal separator, date pattern, month names |
| Java formatting APIs | Consume locale data via providers to format/parse | `NumberFormat`, `DateTimeFormatter` |
| Application `ResourceBundle` | Stores messages, labels, and content translated by the product team | `login.button=Đăng nhập` |

**Having a `Locale` is not enough to have translated content.** The tag `"vi-VN"` only requests a Vietnamese language / Vietnam region context; the JDK does not know how a project's "Checkout now" button should be translated. `ResourceBundle` holds application content; CLDR is primarily a source of shared conventions and data.

**CLDR is not Google Translate or machine translation.** It may contain display names for countries, currencies, months, or certain general data categories, but that does not mean all product descriptions, emails, error messages, and UI copy of a project are automatically translated.

**CLDR is also not the sole timezone database.** Calculating offsets and historical time-shift rules for a region is the separate responsibility of timezone data/`ZoneRules` (typically based on tzdb). CLDR may provide **localized time zone names** or certain time zone presentation conventions; it does not determine the user's current `ZoneId` on its own.

### Three steps when formatting data

~~~text
Business value
        +
User locale
        +
Locale data provided by JDK provider
        ↓
NumberFormat / DateTimeFormatter / ... API
        ↓
Display string for the reader
~~~

For example, `NumberFormat.getNumberInstance(Locale.GERMANY)` obtains a formatter whose behavior suits the locale according to current data/providers, without altering the source value. When displaying a USD amount to a user in Germany, the **transaction currency** must be specified independently of the display locale.

## 3. Since when has the JDK used CLDR?

Key historical milestones to know:

1. **JDK 8** included CLDR data in the runtime, but did not make CLDR the default prioritized source.
2. **Starting with JDK 9**, under **JEP 252 — Use CLDR Locale Data by Default**, CLDR became the default priority for many locale-sensitive services.
3. **JDK 17** uses CLDR by default while still retaining the legacy **`COMPAT`** data provider to support migration from pre-JDK 9 behavior.
4. **Starting with JDK 23**, the legacy `COMPAT`/`JRE` locale data was removed; this configuration can no longer restore older JDK 17-era outputs.

Specifically, according to the **Oracle JDK 17 Supported Locales** documentation, the CLDR provider in Oracle JDK 17 is based on **CLDR release 39**. You cannot assume that just because the Unicode CLDR project has a newer release, a running JDK 17 already has the corresponding newer CLDR data. You must check the actual runtime and update release being used.

When a system is upgraded from Java 8 to Java 17, number/date/currency formatting can change **even if no business logic was modified**. When upgrading from Java 17 to Java 23+, you cannot rely on `COMPAT` as a long-term solution. You need a testing and migration plan rather than expecting all UI strings to remain immutable.

### "Using CLDR by default" does not mean every API uses CLDR

A common point of confusion: the **CLDR project** has many datasets, but the **built-in JDK scope** does not include every kind. According to Oracle JDK 17 documentation, the CLDR data of the JDK 17 provider **is not applied to `BreakIterator` and `Collator`** in the same way it is applied to date/number formatting data.

Therefore, avoid stating that "Java 17 uses CLDR so all word segmentation, language collation, or CLDR plural rules are already available in Java Core." An application requiring specific algorithms or coverage must check its Java APIs, datasets, and specialized libraries.

## 4. What is a locale data provider?

Many locale-sensitive Java services are supplied through the **locale service providers** mechanism. Depending on the runtime, they may come from built-in JDK data, the operating system, or custom implementations.

In **JDK 17**, the key provider labels include:

| Provider | Role in JDK 17 |
| --- | --- |
| `CLDR` | Services using Unicode CLDR data bundled with the JDK |
| `COMPAT` | Dataset compatible with many pre-JDK 9 behaviors |
| `JRE` | Legacy alias for `COMPAT` in supported versions, marked for removal |
| `SPI` | Locale service providers implemented by external applications/libraries |
| `HOST` | References OS locale customizations where supported; not provided on all platforms |

The coverage supported by a provider can vary by **service**, **locale**, runtime, and operating system. Simply having the `fr-FR` locale does not mean every i18n API will find data from the same provider with the same level of completeness.

### java.locale.providers

The JDK supports configuring the locale source lookup order using the **`java.locale.providers`** system property.

Example running **on JDK 17**:

~~~bash
java -Djava.locale.providers=CLDR,COMPAT CldrJdkLocaleDemo
java -Djava.locale.providers=COMPAT,CLDR CldrJdkLocaleDemo
~~~

For applicable locale services, providers are queried in the configured order; when a provider does not supply data for the requested service/locale, the runtime may consult the next provider. In Oracle JDK 17, the default behavioral order documented corresponds to prioritizing `CLDR,COMPAT`.

**Important:**

- Set the property **at JVM startup**; per the Java 17 `LocaleServiceProvider` contract, this order is read at startup. Calling `System.setProperty("java.locale.providers", "...")` after the application has started **does not change the provider order in use**.
- `COMPAT` is only a transitional option suitable for certain older JDKs. **Starting with JDK 23**, `COMPAT/JRE` data was removed; do not recommend it as a permanent compatibility solution.
- For `SPI` to be used, an appropriate provider must be installed/registered and selected via the runtime's provider mechanism. Putting `SPI` in the property **does not automatically generate** translation data for the application.
- `HOST` may be unavailable on an OS/runtime or may only reflect certain OS user settings rather than the locale of every customer in a web application.
- Changing providers can alter patterns, separators, month names, or certain parsing behaviors. Do not rely on an arbitrary output to decide what is "absolutely right" across all JDKs.

### Which provider actually served a call?

`Locale` does not carry an attribute like "this record was served by CLDR version X." Not every standard formatting API gives you a method to directly retrieve the name of the provider chosen for that call.

To debug, verify the **JDK/runtime version**, startup properties, requested locale, packaged locale data modules, and output in that environment. Testing with two provider configurations on the **same supported JDK build** can help pinpoint differences, while avoiding guessing which data was used from a single decimal separator alone.

## 5. How does CLDR help format numbers?

`java.text.NumberFormat` is a Java API for formatting/parsing numbers by locale. A consistent numeric value can be presented with different grouping and decimal separators:

~~~java
NumberFormat us = NumberFormat.getNumberInstance(Locale.US);
NumberFormat de = NumberFormat.getNumberInstance(Locale.GERMANY);

String a = us.format(new BigDecimal("1234.5"));
String b = de.format(new BigDecimal("1234.5"));
~~~

This is an **illustrative snippet** requiring imports `java.text.NumberFormat`, `java.math.BigDecimal`, and `java.util.Locale`. On many common JDKs/providers:

~~~text
en-US: 1,234.5
de-DE: 1.234,5
~~~

However, applications should not treat those two strings as an immutable byte-for-byte contract across every JDK release. CLDR data and providers can be updated. If the data is output exchanged between two machines, use a machine-readable numeric contract with its own rules instead of treating localized strings as computation data.

### Locale-sensitive parsing requires discipline

A string such as `1,234` can be interpreted differently depending on the locale: `,` could be a thousands separator or a decimal separator. Therefore:

- If numbers come from user **UI** input, parse using the selected input locale and verify that the entire string was consumed.
- If numbers come from **machine APIs/CSVs**, define a stable protocol format and avoid automatically parsing with the server's default locale.
- For currency, keep **currency** and **rounding rules** separate: CLDR supplies display conventions, not your system's tax laws, cash rounding increments, or payment precision.

`NumberFormat` also has mutable configuration state; do not arbitrarily share a mutable instance across threads. If formatters are needed in a multi-request application, create separate instances or properly control access and configuration.

## 6. How does CLDR help present dates and times?

`DateTimeFormatter` in `java.time` provides localized factories such as:

~~~java
DateTimeFormatter formatter = DateTimeFormatter
        .ofLocalizedDate(FormatStyle.SHORT)
        .withLocale(Locale.GERMANY);

String shown = LocalDate.of(2024, 6, 16).format(formatter);
~~~

This is a **Java 17 illustrative snippet** requiring imports `java.time.LocalDate`, `java.time.format.DateTimeFormatter`, `java.time.format.FormatStyle`, and `java.util.Locale`.

With `ofLocalizedDate(FormatStyle.SHORT)`, the requested **style** and **locale** determine the specific formatting pattern through runtime data. Do not take one country's date pattern and apply it to everyone.

`DateTimeFormatter.ofPattern("uuuu-MM-dd", locale)` is a different case: the developer **chooses an explicit pattern**, and literals/formatting are determined by that pattern. It may suit a protocol or printout requiring a fixed order, not a way for each country to determine field ordering.

### Date locale is distinct from timezone

CLDR can help with month/weekday names or date presentation, but the timezone must be chosen according to the **event/user**:

~~~java
Instant instant = Instant.parse("2024-06-16T12:00:00Z");
ZonedDateTime event = instant.atZone(
        ZoneId.of("Asia/Ho_Chi_Minh"));
~~~

This is an illustrative snippet requiring `import java.time.*`. `Locale.US` does not imply `America/New_York`; a country can span multiple timezones and users can choose a language different from where they live.

CLDR provides certain **localized time zone name** data, whereas historical offset/DST rules are the concern of the timezone rule provider. When an exact point in time is needed, prefer `Instant` and `ZoneId` according to business semantics.

## 7. Currencies, region names, and language data

Relevant APIs:

- `Currency.getInstance("USD")` gives the currency object by code; `getCurrencyCode()` returns the identifier `USD`.
- `Currency.getSymbol(locale)` and `getDisplayName(locale)` retrieve **display strings** depending on the locale and supported data.
- `Locale.getDisplayCountry(displayLocale)`, `getDisplayLanguage(displayLocale)`, and similar methods display country/language names in the desired locale.
- `NumberFormat.getCurrencyInstance(locale)` creates a currency formatter using locale conventions.

Example:

~~~java
Currency usd = Currency.getInstance("USD");

String code = usd.getCurrencyCode();       // "USD"
String symbol = usd.getSymbol(Locale.US); // depends on locale/runtime
~~~

This is an illustrative snippet with imports `java.util.Currency` and `java.util.Locale`.

**Do not confuse symbol with currency code.** `$` can be the symbol for many currencies, whereas `USD` and `CAD` are distinct codes. Never use symbols to store currency IDs.

**Do not infer an invoice's currency from the UI locale.** A user viewing a Vietnamese UI can still pay in USD. The system must store the actual currency unit; the locale determines how it is displayed, not how it is converted.

**Do not confuse CLDR metadata with financial regulations.** Currency data may include typical decimal digits, but payment rounding rules, taxes, fees, or exchange rates are separate business/legal decisions.

## 8. Standalone runnable Java 17 example

This program demonstrates that **the same numeric and date values** can be presented differently in two locales; changing the locale does not change the underlying value. It intentionally prints **boolean invariants** rather than hardcoding a CLDR/provider-dependent date or number string. Thus the example emphasizes API behavior, is easy to test, and is less sensitive to whitespace character or presentation differences across JDKs.

Create the file **`CldrJdkLocaleDemo.java`**:

~~~java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Currency;
import java.util.Locale;

public class CldrJdkLocaleDemo {
    public static void main(String[] args) {
        Locale us = Locale.US;
        Locale de = Locale.GERMANY;
        BigDecimal number = new BigDecimal("1234.5");

        NumberFormat usNumber = NumberFormat.getNumberInstance(us);
        NumberFormat deNumber = NumberFormat.getNumberInstance(de);
        String usText = usNumber.format(number);
        String deText = deNumber.format(number);

        System.out.println("US locale: " + us.toLanguageTag());
        System.out.println("DE locale: " + de.toLanguageTag());
        System.out.println("Number formats differ: "
                + !usText.equals(deText));

        LocalDate date = LocalDate.of(2024, 6, 16);
        String dateUS = date.format(DateTimeFormatter
                .ofLocalizedDate(FormatStyle.SHORT).withLocale(us));
        String dateDE = date.format(DateTimeFormatter
                .ofLocalizedDate(FormatStyle.SHORT).withLocale(de));

        System.out.println("Date formats differ: "
                + !dateUS.equals(dateDE));

        NumberFormat usdUS = NumberFormat.getCurrencyInstance(us);
        usdUS.setCurrency(Currency.getInstance("USD"));
        NumberFormat usdDE = NumberFormat.getCurrencyInstance(de);
        usdDE.setCurrency(Currency.getInstance("USD"));

        System.out.println("Currency display differs: "
                + !usdUS.format(number).equals(usdDE.format(number)));

        System.out.println("Machine date: "
                + date.format(DateTimeFormatter.ISO_LOCAL_DATE));
        System.out.println("Same underlying number: "
                + (number.compareTo(new BigDecimal("1234.50")) == 0));
        System.out.println("USD code: "
                + Currency.getInstance("USD").getCurrencyCode());
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac --release 17 -encoding UTF-8 CldrJdkLocaleDemo.java
java CldrJdkLocaleDemo
~~~

Observed output in the tested JDK/locale data environment:

~~~text
US locale: en-US
DE locale: de-DE
Number formats differ: true
Date formats differ: true
Currency display differs: true
Machine date: 2024-06-16
Same underlying number: true
USD code: USD
~~~

**Line-by-line explanation:**

1. The two tags `en-US` and `de-DE` identify the requested display contexts.
2. `Number formats differ: true` shows that the same number `1234.5` can be formatted differently by locale.
3. `Date formats differ: true` reflects that the `SHORT` date pattern can change by locale. Actual strings may also be affected by data/provider versions.
4. `Currency display differs: true` illustrates that the same currency code `USD` can be represented differently when the locale differs.
5. `Machine date` is a string in `ISO_LOCAL_DATE` format, suitable for machine-contract date representation (not dates with translated names).
6. `BigDecimal.compareTo` confirms `1234.5` and `1234.50` have the same numeric value; formatting does not modify the value.
7. `Currency.getCurrencyCode()` returns `USD`; the currency code does not change by locale.

**Reproducibility warning:** The boolean comparison lines reflect **actual results from a JDK environment with standard en-US/de-DE data**. They are test examples, not a guarantee that every custom runtime or provider order will always return the same strings or always differ. When running in a `jlink` environment where locale data or specific providers have been stripped, re-verify expectations. To inspect exact outputs, print `usText`, `deText`, `dateUS`, and `dateDE` separately and record the version/runtime.

### Why not print number/date results directly as fixed expected output?

CLDR is versioned data, runtimes supply prioritized providers, and many formats include special whitespace characters or separator updates. Locking tests to **input values and business invariants** is more durable than treating one JDK snapshot as universal truth across all releases.

However, UI snapshots remain useful for catching changes within your own application; when upgrading JDK/CLDR, review snapshot diffs with localization expertise rather than blindly accepting every change.

## 9. CLDR does not automatically solve plurals and complex grammar in Java 17

The CLDR project contains **plural categories** data by language, yet Java 17's `java.text.MessageFormat` **does not directly support** ICU MessageFormat's `plural`/`select` syntax.

Do not write:

~~~text
{count, plural, one{# item} other{# items}}
~~~

and pass that string into Java 17's `new java.text.MessageFormat(...)` expecting it to understand and apply CLDR plural rules automatically. That is an **ICU-syntax pattern**, not a built-in format style in Java 17's `java.text.MessageFormat`.

Java Core has `MessageFormat`, `ChoiceFormat`, and `ResourceBundle` for storing/interpolating messages, but `ChoiceFormat` selects by developer-defined numeric thresholds, not a plural engine for all locales.

If you need CLDR plurals, ordinals, grammatical gender, or nested selects across many languages, consider **ICU4J or an i18n framework** that supports the proper data and syntax, and ensure translators provide complete, grammatically sound sentences.

**Rule:** CLDR having a dataset/rule **does not mean** Java Core exposes all of it as a complete Java 17 API. Check the capabilities of **the class actually being used**, rather than inferring from the data project's name.

## 10. Locale data is not application content translation

Example product-specific resources:

~~~properties
# messages_vi.properties
cart.empty=Giỏ hàng chưa có sản phẩm.
button.checkout=Thanh toán
~~~

~~~properties
# messages_en.properties
cart.empty=Your cart is empty.
button.checkout=Checkout
~~~

These contents must be supplied and tested by the application/translators. CLDR can supply month names or number conventions so placeholders inside messages are presented properly, but it **does not generate translations** for `cart.empty`.

Formatting example:

~~~java
ResourceBundle messages = ResourceBundle.getBundle(
        "messages", userLocale);
String template = messages.getString("cart.total");
String formattedNumber = NumberFormat.getNumberInstance(
        userLocale).format(total);
~~~

This is a **non-standalone illustrative snippet** (assuming variables `userLocale`, `total`, and a bundle file containing `cart.total`). Separate the two responsibilities: message content is managed by the application, while number formatting is handled by Java/locale providers. For messages with placeholders, use `MessageFormat` properly, taking apostrophe escaping and per-language grammar into account.

### ResourceBundle fallback differs from provider fallback

`ResourceBundle.getBundle` resolves bundles by locale/parent and falls back per that API's specific policy. `java.locale.providers`, on the other hand, determines the **data source order for locale-sensitive services**.

These two are not the same:
- missing `messages_vi_VN.properties` does not mean the JDK has run out of Vietnamese number data;
- having CLDR data for `vi-VN` does not mean the application has translated every label;
- changing `java.locale.providers` does not rewrite or change your product's `ResourceBundle` content.

## 11. Commonly confused CLDR boundaries

### Locale does not imply all personal preferences

`Locale.forLanguageTag("en-US")` does not prove the user is in the US or uses USD. A user may prefer an English UI while needing Vietnam time, paying in EUR, or using metric units.

CLDR records **common conventions**, which should not replace **actual user preferences and transaction data**. For critical domains, explicitly track display `Locale`, `ZoneId`, `Currency`, calendar system, numbering system, and user-specific settings.

### Locale names, locale codes, and display data

`Locale.getLanguage()` returns a language code and `getCountry()` returns a region code; they are not localized display names themselves. To get display names, call `getDisplayLanguage(displayLocale)` or `getDisplayCountry(displayLocale)`. Names can change across data and JDK versions.

### Unicode normalization is a separate task

CLDR relates to localization rules and data, whereas Unicode normalization such as `Normalizer.Form.NFC` is an API for handling **character equivalence**; "installing CLDR" does not mean all names are Unicode-normalized. Do not treat CLDR, case conversion, transliteration, translation, and Unicode normalization as a single operation.

### Data and algorithms must go together

A set of plural, collation, or segmentation rules is only useful if the library/API **executes the corresponding rules** with a known dataset/version. Do not use `String.equals` and call it CLDR collation; do not use a regex to strip diacritics and call it Unicode normalization.

## 12. jlink and locale data scope in the runtime

When building a **custom runtime with `jlink`**, the application might not package all of the JDK's locale data. In the modular JDK, part of the additional locale data resides in the `jdk.localedata` module. Therefore:

- An application that works on a full JDK can behave or support locales differently when moved to a custom runtime image.
- Components in `java.base` do not imply all locales remain packaged.
- Inspect the module list and image build options; jlink's `--include-locales` is a mechanism to select locales at image creation time when configured compatibly.
- Do not assume "`Locale.forLanguageTag("xx-YY")` constructs successfully" means formatting services have full `xx-YY` data in that runtime image.

**This is a deployment concern**, distinct from whether Java source code is syntactically valid. For applications running in Docker/minimal JVM images, test formatting/parsing for the actually supported locales on the **final runtime artifact**, not only on a developer workstation.

## 13. JDK upgrades, CLDR changes, and testing strategy

CLDR is updated alongside linguistic data and requirements. The JDK ships its own data versions, and major/minor updates can alter some localized outputs.

Items to include in your testing workflow:

1. **Locale matrix:** the actually supported locales, not just the server default.
2. **Service matrix:** numbers, currencies, percentages, dates, times, month names, region names, and parsing.
3. **Edge cases:** end-of-month/year dates, grouping/decimal separators, negative numbers, large numbers, special Unicode characters.
4. **Provider/version:** record JDK vendor, version, startup properties, and runtime image modules.
5. **Application resources:** test translation keys and placeholders separately from JDK formatting data.
6. **User-facing output:** compare pre/post-upgrade displays and review with people knowledgeable in the locale.
7. **Machine protocols:** ensure API/database data never depends on CLDR-dependent display formats.
8. **Monetary precision:** `BigDecimal`, currency code, and rounding policy must never be replaced by a UI-formatted number string.
9. **Timezones:** test `ZoneId`/DST separately; do not treat a timezone name change as evidence that offsets changed.
10. **Custom runtime:** re-verify actual locales when changing `jlink`/container builds.
11. **Legacy provider:** if still launching with `COMPAT` on Java 17/21/22, plan to migrate to CLDR rather than relying on configuration removed in JDK 23.

### Snapshot tests: using them responsibly

A test expecting exact display strings can catch regressions. However, when JDK/CLDR is upgraded, a pattern change **may be a legitimate linguistic update** rather than a bug. Avoid updating snapshots blindly; analyze:
- whether the data source/provider/version changed;
- whether the UI content remains clear and linguistically accurate;
- whether parsing from legacy strings is broken;
- whether legal/print requirements demand a fixed format outside CLDR.

For inter-system communication, use stable-contract formats such as ISO 8601 for semantically appropriate dates/times, decimal strings, or numbers with explicit units, rather than localized display text as the "source of truth."

## 14. Common mistakes table

| Mistake | Why it is wrong | How to avoid |
| --- | --- | --- |
| Thinking CLDR is an automatic translator | CLDR is shared locale data/rules, not translations of app sentences | Use ResourceBundle + translators/tooling |
| Thinking `Locale` holds all cultural rules inside the object | Locale is primarily an identifier | Use APIs + provider data |
| Thinking JDK 17 has every CLDR API | CLDR spans many areas; JDK integrates only a subset | Check specific JDK APIs |
| Assuming Java 17 `BreakIterator`/`Collator` definitely use CLDR | JDK 17 docs note integration exceptions | Check per-service support |
| Using one fixed date pattern for all locales | Field orders and conventions differ | Use ofLocalizedDate with locale |
| Parsing UI numbers with the server locale | Dots/commas have different meanings | Pass input locale and validate |
| Using currency symbols as storage units | Symbols can collide across currencies | Store ISO codes |
| Inferring timezone from locale | Multiple zones exist, and users may choose otherwise | Store ZoneId separately |
| Setting `java.locale.providers` after startup | Provider order is read at JVM startup | Set at launch time |
| Recommending `COMPAT` as an option for JDK 23+ | Legacy provider has been removed | Migrate to CLDR or an explicit solution |
| Assuming newest CLDR means JDK is already updated | Runtime bundles data per its release | Check vendor/version |
| Not testing the final `jlink` runtime | Locale data modules may be missing | Test the actual runtime image |
| Using localized text as a machine API | Output changes with locale/runtime | Use machine-readable formats |
| Equating CLDR plural rules with Java 17 MessageFormat plurals | Java 17 API does not support ICU plural syntax | Use an appropriate engine when needed |
| Testing only en-US | Hides locale-specific bugs | Test all supported locales |

## 15. Self-assessment exercises

**Q1.** Is CLDR a Java API dedicated to translating UI labels into every language?

**Answer:** No. CLDR is a repository of shared locale data and rules. The application still must supply translations for its own content via ResourceBundle or an equivalent localization system.

**Q2.** Why can the same `BigDecimal("1234.5")` be formatted differently between `Locale.US` and `Locale.GERMANY`?

**Answer:** The two locales have different grouping and decimal separator conventions; `NumberFormat` retrieves appropriate data and behavior from the JDK's providers. The numeric value does not change.

**Q3.** On Java 17, what does `java.locale.providers=COMPAT,CLDR` mean? Should it be used as a permanent strategy on Java 23?

**Answer:** On Java 17, it prioritizes the legacy compatibility dataset before CLDR where supported. COMPAT/JRE data was removed in JDK 23, so do not rely on it as a long-term strategy.

**Q4.** If CLDR has Russian plural rules, why doesn't Java 17 `java.text.MessageFormat` automatically understand `{count, plural, ...}`?

**Answer:** The data project and formatter API capabilities are two separate things. ICU plural syntax is not Java 17's `java.text.MessageFormat` syntax; a supporting library/engine is required.

**Q5.** Does `Locale.forLanguageTag("vi-VN")` automatically determine the user's timezone and the actual transaction currency?

**Answer:** No. Locale helps select how data is displayed, whereas user timezone and transaction currency must be provided by business context.

**Exercise:** Run `CldrJdkLocaleDemo` on JDK 17 with the default startup provider and with `-Djava.locale.providers=COMPAT,CLDR`. Record the actual formatted outputs for en-US, de-DE, fr-FR, and vi-VN, testing dates, numbers, and currencies. Then run on a newer JDK and analyze why the COMPAT option is no longer valid starting in JDK 23. Do not assume every difference is a bug; cross-reference with the runtime's locale data and provider documentation.

## 16. References

- [Unicode CLDR Project](https://cldr.unicode.org/): purpose, scope, locale data, and releases.
- [Unicode Technical Standard #35 — CLDR](https://www.unicode.org/reports/tr35/tr35.html): locale model, LDML, and rules.
- [JEP 252 — Use CLDR Locale Data by Default](https://openjdk.org/jeps/252): mechanism and history of prioritizing CLDR in Java.
- [Oracle JDK 17 Supported Locales](https://www.oracle.com/java/technologies/javase/jdk17-suported-locales.html): Oracle JDK 17 data, CLDR 39, providers, and BreakIterator/Collator exceptions.
- [LocaleServiceProvider — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/spi/LocaleServiceProvider.html): `java.locale.providers` ordering and provider types.
- [DateTimeFormatter — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html): locale-sensitive date/time formatting.
- [NumberFormat — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html): number and currency formatting.
- [JDK 23 migration — Removed legacy locale data](https://docs.oracle.com/en/java/javase/23/migrate/removed-tools-and-components.html): removal of COMPAT/JRE.
- [Locale — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html): language tags and display names.

**Takeaway:** **CLDR provides localization data/rules; the JDK provides APIs and providers that apply the relevant subset of data; the application is responsible for business semantics and its own translated content.** Pass `Locale` explicitly, distinguish human-readable formatting from machine data, test against JDK versions/providers, and never assume every CLDR capability is integrated into Java 17.
