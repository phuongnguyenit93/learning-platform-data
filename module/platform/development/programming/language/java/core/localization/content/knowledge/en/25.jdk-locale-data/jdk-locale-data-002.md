# Locale.getAvailableLocales vs. Per-Service Supported Locales in Java

When building multilingual Java software, developers may call **Locale.getAvailableLocales()**, receive hundreds of Locale objects, and assume every internationalization feature of the JVM fully supports all of those locales. That conclusion is inaccurate. **The runtime-level locale list** is not equivalent to **each individual service's locale list**, and even less equivalent to **the list of languages the product has translated and tested**.

For example, **NumberFormat**, **DateFormat**, **Collator**, **BreakIterator**, **DateFormatSymbols**, and **DecimalFormatSymbols** each have specialized APIs or data. A locale may be advertised by the Java environment without having the same data depth across all services. Conversely, if a factory can construct an object for an uncommon locale, that may be the result of **fallback**, not proof of dedicated region-specific data.

This lesson explains how to distinguish **locale identifier**, **JDK-advertised locales**, **per-service advertised locales**, and **application-committed supported locales**; how to inspect them with Java 17+, manage CLDR/providers, choose fallbacks, and build a safe language-selection mechanism.

## 1. Four layers of the term "locale support"

| Layer | Question to answer | Tool |
| --- | --- | --- |
| Locale identifier | Can a Locale object carrying this language/region tag be created? | Locale.forLanguageTag, Locale.Builder |
| General JDK capability | Which locales does the current JVM list? | Locale.getAvailableLocales() |
| Per-service capability | Which locales does the number/date/collation/segmentation service advertise? | The service classes and their own getAvailableLocales() |
| Product capability | Are there UI translations, content, fonts, QA, and a fallback policy? | The project's appSupportedLocales list |

**These four lists must never automatically be treated as equal.** An application might only support Vietnamese and English UIs, while the Java runtime holds formatting data for many more locales. Presence in the general list also does not prove every service has specialized tailoring for it.

The problem must start with specific questions: "Does the app support Vietnamese in the UI?" differs from "Does the JDK know how to format numbers for vi-VN?" and differs from "Does Collator vi-VN sort directories like a Vietnamese dictionary?"

## 2. Locale is an identifier, not a resource bundle

**java.util.Locale** carries language, script, country/region, variant, and certain extension components represented via language tags. It does not itself contain all translated strings, date/time patterns, or sorting rules.

**File LocaleIdentity.java**

~~~java
import java.util.Locale;

public class LocaleIdentity {
    public static void main(String[] args) {
        Locale vi = Locale.forLanguageTag("vi-VN");
        Locale ca = Locale.forLanguageTag("fr-CA");

        System.out.println(vi.toLanguageTag());
        System.out.println(vi.getLanguage());
        System.out.println(vi.getCountry());
        System.out.println(ca.toLanguageTag());
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 LocaleIdentity.java
java LocaleIdentity
~~~

Stdout:

~~~text
vi-VN
vi
VN
fr-CA
~~~

**The program only confirms that the identifiers are properly represented.** It cannot query the application's translation list, does not confirm that fr-CA has specialized collation rules, and does not prove the transaction's Currency is CAD.

Locale.forLanguageTag accepts a language tag and builds a Locale according to API rules; successful construction is not equivalent to checking service support. If strict tag validation is needed, study **Locale.Builder** rules, handle invalid tags, and restrict inputs to the list accepted by the application.

## 3. What does Locale.getAvailableLocales actually say?

**Locale.getAvailableLocales()** returns a **Locale[]** array of locales installed/advertised in the current Java runtime. The set of locales can come from data sources supported by the Java environment and providers. This is **information about the environment**, not a certificate that every service has high-quality rules for each one.

~~~java
Locale[] all = Locale.getAvailableLocales();
~~~

The illustrative snippet above belongs inside a method and requires `import java.util.Locale`.

Points to understand:

1. The count of locales can vary by **JDK version, JDK vendor, providers, and configuration**. Do not hardcode a universal number.
2. The returned array is not the list of languages the application has translated.
3. Do not rely on **element ordering** to build menus.
4. The presence of a locale does not prove specialized data exists in every service.
5. A Locale can carry an extension such as requesting a numbering system; exact membership checking in the list is not enough to know whether that extension is fully handled.
6. When a specific capability is needed, ask the right service and verify behavior on the target deployment runtime.

**In short:** Locale.getAvailableLocales is a starting overview of internationalization capabilities in the JDK, not a guarantee of complete product functionality.

## 4. Each service has its own set of locales

Java provides static **getAvailableLocales()** APIs on formatting and text-processing classes:

| API | Advertised capability |
| --- | --- |
| **NumberFormat.getAvailableLocales()** | Number formatting service and number/currency/percent variants |
| **DateFormat.getAvailableLocales()** | java.text-style date/time formatting service |
| **Collator.getAvailableLocales()** | Locale-sensitive text comparison/sorting service |
| **BreakIterator.getAvailableLocales()** | Text boundary detection service |
| **DateFormatSymbols.getAvailableLocales()** | Date/time symbols and names |
| **DecimalFormatSymbols.getAvailableLocales()** | Number symbols, decimal separator, grouping separator |
| **Locale.getAvailableLocales()** | General runtime-level list |

**A service's list is not a simple projection of the general list.** Each service returns the locales it advertises under its API contract and corresponding provider sources. Do not infer from NumberFormat that Collator also has a specialized locale; do not infer from DateFormatSymbols that DateFormat meets every display requirement.

A few cases to distinguish:

- **Currency.getAvailableCurrencies()** returns **Set<Currency>**, a set of currencies, not Locale[].
- **DateTimeFormatter** in java.time does not have a static **getAvailableLocales()** method analogous to DateFormat.
- An application's **ResourceBundle** has its own resources; there is no single universal ResourceBundle.getAvailableLocales API for all translation sets.
- Third-party i18n libraries maintain their own support lists, which do not automatically match the JDK.

## 5. Java 17+: program to inspect each service properly

This example prints the number of distinct locales on the **currently running JVM**. The numbers are runtime data and should not be hardcoded as fixed stdout across all environments.

**File LocaleServiceCatalog.java**

~~~java
import java.text.BreakIterator;
import java.text.Collator;
import java.text.DateFormat;
import java.text.DateFormatSymbols;
import java.text.DecimalFormatSymbols;
import java.text.NumberFormat;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Locale;
import java.util.Set;

public class LocaleServiceCatalog {
    private static Set<Locale> asSet(Locale[] locales) {
        return new HashSet<>(Arrays.asList(locales));
    }

    private static void report(String name, Locale[] locales) {
        System.out.printf(Locale.ROOT, "%s: %d%n",
                name, asSet(locales).size());
    }

    public static void main(String[] args) {
        report("Locale", Locale.getAvailableLocales());
        report("NumberFormat",
                NumberFormat.getAvailableLocales());
        report("DateFormat",
                DateFormat.getAvailableLocales());
        report("Collator",
                Collator.getAvailableLocales());
        report("BreakIterator",
                BreakIterator.getAvailableLocales());
        report("DateFormatSymbols",
                DateFormatSymbols.getAvailableLocales());
        report("DecimalFormatSymbols",
                DecimalFormatSymbols.getAvailableLocales());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 LocaleServiceCatalog.java
java LocaleServiceCatalog
~~~

The program prints exactly **seven lines**, in the label order **Locale**, **NumberFormat**, **DateFormat**, **Collator**, **BreakIterator**, **DateFormatSymbols**, **DecimalFormatSymbols**; after each colon is a non-negative integer returned by the current environment.

**Do not assert a fixed set of stdout counts**: those numbers are precisely what is being inspected. If two classes both report N locales, you cannot conclude their sets are identical without comparing members. If counts differ, that is not automatically a bug nor proof of data quality for any individual locale.

Use **Set<Locale>** to count distinct members rather than assuming arrays are pre-sorted or have meaningful order. Locale.ROOT in printf merely standardizes technical report formatting; it does not alter the data inside each array.

## 6. Checking membership of a target locale

To compare three sets, use Set and contains with the same Locale object:

**File LocaleMembership.java**

~~~java
import java.text.Collator;
import java.text.NumberFormat;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Locale;
import java.util.Set;

public class LocaleMembership {
    private static Set<Locale> set(Locale[] values) {
        return new HashSet<>(Arrays.asList(values));
    }

    public static void main(String[] args) {
        Locale target = Locale.forLanguageTag("vi-VN");

        System.out.println("locale=" + target.toLanguageTag());
        System.out.println("general="
                + set(Locale.getAvailableLocales())
                        .contains(target));
        System.out.println("number="
                + set(NumberFormat.getAvailableLocales())
                        .contains(target));
        System.out.println("collation="
                + set(Collator.getAvailableLocales())
                        .contains(target));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 LocaleMembership.java
java LocaleMembership
~~~

The first line is always:

~~~text
locale=vi-VN
~~~

The next three lines have the labels **general=**, **number=**, **collation=** and a true/false value determined by the current JDK. Do not guess the booleans before running.

**Meaning:** to evaluate number formatting quality, check NumberFormat and run numeric examples; to evaluate dictionary ordering, check Collator and test real name lists. Do not use a single contains check on Locale.getAvailableLocales to conclude all capabilities.

### 6.1. Why is exact membership not enough for locale extensions?

A Locale can carry a Unicode extension such as **en-US-u-nu-arab**. It requests a digit representation style but might not appear as a verbatim element in every getAvailableLocales result. This **does not automatically prove** NumberFormat cannot handle that extension, nor guarantee full support.

Distinguish between **a locale being listed** and **a locale feature executing properly according to an extension**. Test the actual formatter, runtime documentation, and output.

## 7. Being in the list does not mean full functionality

Suppose **fr-CA** appears in a list. The product still needs to verify:

- **NumberFormat**: decimal separator, grouping separator, and fractional digits when formatting currency.
- **DateFormat**: component order, month/day names, and punctuation.
- **Collator**: ordering of accented words and character variants.
- **BreakIterator**: word, sentence, or grapheme cluster boundaries.
- **DateFormatSymbols** and **DecimalFormatSymbols**: actual symbols.
- **UI translations**: text and error messages genuinely in fr-CA, not falling back to another language.
- **Font/RTL/accessibility**: suitability of UI rendering for the language.
- **Business policies**: actual transaction currency, timezone, legal content, and required compliance formats.

**"Supported" metadata does not replace functional tests.** A service may provide an API-valid fallback that still fails product quality standards.

## 8. Absence from the list does not mean a factory will definitely fail

Consider a call:

~~~java
Locale requested = Locale.forLanguageTag("fr-CA");
NumberFormat format =
        NumberFormat.getNumberInstance(requested);
String result = format.format(1234.5);
~~~

This illustrative snippet requires imports **java.util.Locale** and **java.text.NumberFormat** inside a method. The factory may fetch matching data or apply a fallback mechanism depending on the runtime. **Do not take formatting success as absolute proof that dedicated fr-CA data exists.**

Similarly, if a Locale does not appear in a service array, do not write an error message saying "Java cannot format this Locale." The runtime might still produce a fallback result. However, if the product requires specialized formatting, you can **explicitly disallow untested fallbacks** per your product contract.

### 8.1. Signs of fallback and consequences

Fallback can cause:

- Month names appearing in generic form instead of region-specific form.
- Unexpected ordering or language.
- Number or currency symbols unfamiliar to the user.
- Parts of a UI sentence appearing in another language.
- Different JDK builds returning different results.

There is no uniform method across every formatter to query the exact **effective locale after fallback**. Therefore, log the requested locale, selected app locale, service type, and runtime version, alongside key output tests.

## 9. CLDR, SPI, and the LocaleServiceProvider system

Java uses localization data sources and the locale provider mechanism. In modern runtimes, **CLDR** is a primary data source; you may also encounter **SPI** (registered providers), some **HOST** capabilities depending on runtime/OS, and compatibility providers in JDKs that still support them. The set and order of providers can be configured depending on the version, such as via the JVM property **java.locale.providers** in supported releases.

**Do not assume every JDK 17+ release has the exact same list of configurable provider values.** Legacy providers can be changed or removed in newer Java versions.

Some SPI types:

| Provider API | Function |
| --- | --- |
| **java.text.spi.NumberFormatProvider** | Creates number formats |
| **java.text.spi.DateFormatProvider** | Creates legacy date/time formats |
| **java.text.spi.CollatorProvider** | Language-sensitive comparison |
| **java.text.spi.BreakIteratorProvider** | Text segmentation |
| **java.text.spi.DecimalFormatSymbolsProvider** | Number symbols |
| **java.text.spi.DateFormatSymbolsProvider** | Date/month symbols |
| **java.util.spi.CurrencyNameProvider** | Currency names and symbols |
| **java.util.spi.LocaleNameProvider** | Language and region names |
| **java.util.spi.TimeZoneNameProvider** | Time zone names |
| **java.util.spi.CalendarDataProvider** | Local calendar data |

They relate to **java.util.spi.LocaleServiceProvider**, though each type has its own data and capabilities.

**Why can identical code yield different outputs?** Because the JDK version, CLDR data, provider options, HOST environment, or installed SPI libraries may differ. Do not automatically treat such differences as bugs; cross-check against the product contract and supported runtime matrix.

### 9.1. Changing providers can change lists and outputs

A JDK upgrade test plan should record runtime version, provider configuration, and critical outputs. Do not claim that merely having **vi-VN** in Locale.getAvailableLocales guarantees all patterns and Vietnamese name sorting remain identical across every release.

## 10. NumberFormat, DecimalFormatSymbols, and currency

A locale may require several types of number formats:

~~~java
NumberFormat number =
        NumberFormat.getNumberInstance(locale);
NumberFormat currency =
        NumberFormat.getCurrencyInstance(locale);
NumberFormat percent =
        NumberFormat.getPercentInstance(locale);
~~~

Illustrative snippet inside a method, requiring imports NumberFormat/Locale and a `locale` variable. **NumberFormat.getAvailableLocales()** is useful for surveying the service, though actual results also depend on formatter type and policy.

**DecimalFormatSymbols.getAvailableLocales()** advertises locales with decimal, grouping, digit, and other symbols for the symbols service. It does not perform exchange rate calculations.

If the transaction is in EUR, you may need:

~~~java
currency.setCurrency(
        Currency.getInstance("EUR"));
~~~

Illustrative snippet requiring `import java.util.Currency`. **setCurrency does not convert an amount from VND to EUR**; it only configures the unit being displayed. Currency.getAvailableCurrencies returns the set of currency units and does not prove a locale supports a UI language.

Do not equate a region's default currency with a transaction's currency. In many applications, **amount + Currency** is business data, while **Locale** is a display choice.

## 11. DateFormat and DateTimeFormatter do not share the same locale discovery API

**DateFormat.getAvailableLocales()** belongs to the **java.text**-style date/time formatting service:

~~~java
DateFormat legacy =
        DateFormat.getDateInstance(
                DateFormat.FULL, locale);
~~~

Meanwhile, Java 17 recommends **java.time**:

~~~java
DateTimeFormatter modern =
        DateTimeFormatter.ofLocalizedDate(
                FormatStyle.FULL)
                .withLocale(locale);
~~~

These are two illustrative snippets inside a method, requiring imports DateFormat, DateTimeFormatter, FormatStyle, Locale, and a `locale` variable.

**DateTimeFormatter does not expose a static DateTimeFormatter.getAvailableLocales() like DateFormat.** To confirm a localized date formatter meets requirements for a locale, test the actual formatter, date/calendar type, and FormatStyle used by the product. Verify month/day names, field ordering, and punctuation rather than only consulting a general list.

In particular, **Locale is not ZoneId**: a LocalDate differs from an Instant, and the user's local time at a location must be determined with a timezone when needed. An available locale does not prove the application picked the right time zone.

## 12. Collator: locale for dictionary comparison

**Collator.getAvailableLocales()** is the list for the language-sensitive string comparison service. If the product sorts Vietnamese names, obtain the explicit locale:

~~~java
Collator collator =
        Collator.getInstance(
                Locale.forLanguageTag("vi-VN"));
collator.setStrength(Collator.TERTIARY);
~~~

Illustrative snippet using imports Collator and Locale. However, having vi-VN in the list does not prove the default rule set meets every standard of a specialized dictionary.

You should test:

- Letters **ă, â, đ, ê, ô, ơ, ư**.
- Tone marks, uppercase, and lowercase.
- Precomposed Unicode pairs and combining marks.
- Strength and decomposition settings.
- Mixed scripts and punctuation.
- Differences across JDK/providers during upgrades.

**String.compareTo** only compares UTF-16 char units; it does not replace Collator when users expect dictionary order.

## 13. BreakIterator: locale for text segmentation

**BreakIterator.getAvailableLocales()** indicates the locales advertised by the service. Its factories:

~~~java
BreakIterator words =
        BreakIterator.getWordInstance(locale);
BreakIterator sentences =
        BreakIterator.getSentenceInstance(locale);
BreakIterator characters =
        BreakIterator.getCharacterInstance(locale);
~~~

Illustrative snippet requiring BreakIterator, Locale imports, and a `locale` variable.

An advertised locale does not guarantee every word/sentence boundary on real product data matches intent. In particular, some scripts have complex segmentation rules; **String.split(" ")** cannot substitute for word boundaries across all languages.

If the application uses double-click word selection, finds sentence break points, or analyzes segments containing emojis/combining marks, test those exact operations. Do not use NumberFormat's success to infer BreakIterator meets an editor's needs.

## 14. ResourceBundle: JDK having a locale does not mean the app has translations

Suppose a product has the files:

~~~text
messages.properties
messages_en.properties
messages_vi.properties
~~~

This is an example of files managed by the **application**. **ResourceBundle** has a locale-based lookup and fallback mechanism. If fr-CA is requested when the app only has a base bundle, calling getBundle can **return the base bundle**. That is not proof the product has translated Canadian French.

A product-level supported locale requires:

1. Complete core UI strings, error messages, emails, and accessibility labels.
2. A translation and review workflow.
3. Testing of screens, forms, dates/times, and monetary amounts.
4. Fonts, RTL rendering (if needed), and localized content.
5. A clearly documented fallback policy.
6. Separately modeled currency units, time zones, and business values.
7. Quality testing on target devices and environments.

**Do not build a language dropdown from Locale.getAvailableLocales.** That list can be far larger than the languages the app actually provides.

## 15. Product-declared list of supported locales

Declare an explicit **appSupportedLocales** collection. Java 17 example:

**File AppSupportedLocales.java**

~~~java
import java.util.List;
import java.util.Locale;

public class AppSupportedLocales {
    private static final List<Locale> SUPPORTED = List.of(
            Locale.forLanguageTag("vi-VN"),
            Locale.US,
            Locale.FRANCE);

    public static boolean isSupported(Locale locale) {
        return SUPPORTED.contains(locale);
    }

    public static void main(String[] args) {
        System.out.println(isSupported(
                Locale.forLanguageTag("vi-VN")));
        System.out.println(isSupported(
                Locale.forLanguageTag("ja-JP")));
        System.out.println(SUPPORTED.size());
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 AppSupportedLocales.java
java AppSupportedLocales
~~~

Exact stdout:

~~~text
true
false
3
~~~

The program illustrates **a hypothetical application's policy**, not that these three languages are automatically supported by every product. When releasing a new translation, update the product's configuration and test suite rather than letting dropdowns expand automatically with the JDK.

### 15.1. Locale extensions and exact equality

A locale such as **en-US-u-nu-arab** carries a Unicode extension related to numbering systems. **SUPPORTED.contains(locale)** uses Locale object equality; a tag with extensions may not equal Locale.US. That is a decision about checking the selected list, **not a conclusion that formatters cannot apply the extension**.

The application must explicitly decide whether to accept extensions, preserve/strip them, or require an exact locale. Do not accidentally discard calendar/numbering system preferences meaningful to users if the product has committed to supporting them.

## 16. Locale.LanguageRange and Locale.lookup for language negotiation

Many web clients send a prioritized string with quality weights, for example:

~~~text
vi-VN, en-US;q=0.8, fr-FR;q=0.5
~~~

Java provides **Locale.LanguageRange.parse** and **Locale.lookup** to find a suitable match from **the list passed by the application**.

**File LocaleNegotiation.java**

~~~java
import java.util.List;
import java.util.Locale;

public class LocaleNegotiation {
    public static void main(String[] args) {
        List<Locale> supported = List.of(
                Locale.forLanguageTag("vi-VN"),
                Locale.US,
                Locale.FRANCE);

        List<Locale.LanguageRange> preferred =
                Locale.LanguageRange.parse(
                        "vi-VN, en-US;q=0.8, fr-FR;q=0.5");

        Locale selected =
                Locale.lookup(preferred, supported);

        if (selected == null) {
            selected = Locale.US;
        }

        System.out.println(selected.toLanguageTag());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 LocaleNegotiation.java
java LocaleNegotiation
~~~

Stdout:

~~~text
vi-VN
~~~

**Locale.lookup** selects from **supported**, without substituting the JDK's advertised locales. If no candidate matches, it can return **null**, so the application must have a fallback. For invalid input or overly long headers, enforce error handling and length limits rather than assuming every client-sent string is safe/valid.

**Locale.filter** is better suited when you want multiple matching candidates instead of a single choice. Whether using lookup or filter, the supported set must be defined by the app based on translations and QA.

## 17. Requested, selected, and formatting locales need not be identical

An illustrative model:

~~~text
requestedLocale   = fr-CA
selectedUiLocale  = fr-FR
formattingLocale  = fr-CA
currency          = CAD
timeZone          = America/Toronto
~~~

These are example values, not Java's default fallback output.

- **requestedLocale:** the value requested by the user.
- **selectedUiLocale:** chosen by the app from translated languages.
- **formattingLocale:** the locale used to format dates/numbers where needed.
- **currency:** the actual currency unit of the transaction.
- **timeZone:** the timezone used to express an Instant as regional date and time.

Do not collapse these dimensions simply because they all relate to internationalization. A user on a Vietnamese UI may still view numbers in en-US and pay in EUR; Locale does not convert exchange rates or determine time zones automatically.

### 17.1. Do not guess the effective locale

When a formatter falls back, not every service offers a simple method to read back exactly which locale's data was applied. Therefore logs should include the JDK/provider runtime, requested locale, app configuration, and relevant sample data; avoid logging an inferred "resolved locale" without an API proving it.

## 18. Default DISPLAY and FORMAT locales

Java provides two important default Locale categories:

~~~java
Locale display =
        Locale.getDefault(Locale.Category.DISPLAY);
Locale format =
        Locale.getDefault(Locale.Category.FORMAT);
~~~

Illustrative snippet inside a method, requiring `import java.util.Locale`.

**DISPLAY** governs how language/region names are presented, while **FORMAT** governs contextual formatting. The two values may differ depending on the environment.

If code constructs NumberFormat/DateFormat or calls Collator without passing a locale, results may depend on the JVM default. **Do not mutate Locale.setDefault per request** on a multi-user server: it is a JVM-wide setting and readily causes cross-request interference. Pass Locale explicitly to all user-serving operations.

## 19. Testing quality instead of testing counts

An assertion like the following is unreliable over time:

~~~java
// Illustrative code NOT to use:
assert Locale.getAvailableLocales().length == 500;
~~~

The count is arbitrary; runtime updates can alter the list. Better tests divide into:

| Test | Expectation |
| --- | --- |
| App supported locales | Matches exact product-approved list |
| Locale.lookup | Picks preferred locale or app fallback |
| NumberFormat | Decimal, grouping, currency per contract |
| DateFormat/DateTimeFormatter | Desired date/month styles and localized names |
| Collator | Sorts realistic name sets accurately |
| BreakIterator | Segments critical cases properly |
| ResourceBundle | Complete translations, fallback does not leak wrong language |
| Unicode extensions | Numbering/calendar settings work as expected |
| JDK/provider upgrades | Detect meaningful data changes |
| RTL/font/accessibility | No broken layout or loss of readability |
| Currency/TimeZone | Not mechanically inferred from locale |

If the product requires exact strings down to every code point, control the runtime/provider and formatting policy. If CLDR updates are accepted, test behavior at the appropriate level instead of forcing every JDK build to return an identical verbatim snapshot.

## 20. Diagnostic workflow when locale support does not behave as expected

If vi-VN appears in Locale.getAvailableLocales yet a list of Vietnamese names sorts unnaturally:

1. Identify the **relevant service**: Collator, not NumberFormat.
2. Check **Collator.getAvailableLocales** and provider configuration on the real runtime.
3. Verify the code passes **Locale.forLanguageTag("vi-VN")**, not an accidental default.
4. Inspect **strength/decomposition** and any custom comparator.
5. Run a test set of words with **ă, â, đ, ê, ô, ơ, ư**, uppercase letters, and tone marks.
6. Compare results against the dictionary standard required by the product.
7. If the domain requires differences from the default rule set, define dedicated collation tailoring/versioning.
8. Evaluate JDK upgrades or provider changes if environments differ.

If currencies display incorrectly, switch to checking NumberFormat, DecimalFormatSymbols, and Currency. If words break incorrectly, inspect BreakIterator. **Investigate per service, not by a vague general support flag.**

## 21. Common mistakes

### Mistake 1: Treating Locale.getAvailableLocales as the app language menu

Incorrect. It reflects runtime data; the product must maintain its own supportedLocales list based on translations and QA.

### Mistake 2: Assuming all getAvailableLocales return the same set

Do not assume this. Service classes have their own data types and providers, so query the right API.

### Mistake 3: Treating Locale.forLanguageTag as proof a locale is supported

No. A valid identifier does not mean dedicated formatters or translations exist.

### Mistake 4: Assuming factory success means dedicated data exists

Not necessarily. Fallback can yield an API-valid result that falls short of product needs.

### Mistake 5: Comparing counts instead of comparing elements

Two sets of equal size can hold different locales. Use Set membership, intersections/unions, and functional tests.

### Mistake 6: Using NumberFormat's locale list to validate Collator

Number formatting and dictionary ordering are separate services. Use Collator.getAvailableLocales and test actual names.

### Mistake 7: Assuming java.time has a list like legacy DateFormat

DateTimeFormatter has no static getAvailableLocales. Test modern formatters with real APIs and real data.

### Mistake 8: Confusing Currency with language

Currency.getAvailableCurrencies gives currency units, not UI locales. Do not convert money using setCurrency.

### Mistake 9: Treating ResourceBundle fallback as having a translation

A base bundle can make lookup succeed while returning another language. The app's list must govern translated content.

### Mistake 10: Hardcoding locale counts in tests

Provider/JDK data changes. Measuring counts is for diagnostics only, not a Java 17+ contract.

### Mistake 11: Using exact contains to reject all locale extensions

An extended tag might not appear in the list even though a formatter honors certain extensions. Verify feature behavior directly.

### Mistake 12: Mutating Locale.setDefault per request

JVM-wide configuration affects other requests; pass Locale explicitly.

### Mistake 13: Treating JDK/CLDR as immutable

Locale data can be updated. Test on supported runtimes and design an upgrade strategy.

### Mistake 14: Claiming "Language X is supported" just because one formatter has data

An application also needs translations, rendering, fonts, validation, UX, and language-specific content policies.

## 22. Exercises

1. Run LocaleServiceCatalog on JDK 17 and another Java runtime used in your system; compare counts without treating them as immutable standards.
2. Run LocaleMembership with vi-VN, fr-CA, and your project's real locales; compare the general/number/collation lists.
3. Build a dedicated language dropdown for an app with two translations; demonstrate that the count does not grow automatically when switching JDKs.
4. For a Locale with a Unicode numbering extension, compare NumberFormat output against the unextended locale on the target runtime.
5. Compare Vietnamese name ordering using String.compareTo vs. Collator vi-VN; explain why they differ.
6. Run BreakIterator on a passage with punctuation and proper names; compare with `String.split(" ")`.
7. Test ResourceBundle with only base and English bundles; verify how a fr-CA request falls back.
8. Test Locale.lookup with preferences outside the app's list; verify fallback per policy.
9. When upgrading the JDK, re-run the test suite for currency, date/time, collation, and segmentation; document acceptable changes.
10. Write documentation explaining your application's requestedLocale, selectedUiLocale, formattingLocale, currency, and timeZone.

## 23. Checklist

- [ ] Understand Locale as an **identifier**, not automatic translation.
- [ ] Distinguish **Locale.getAvailableLocales** from per-service lists.
- [ ] Know that NumberFormat, DateFormat, Collator, and BreakIterator have their own methods.
- [ ] Distinguish DateFormatSymbols and DecimalFormatSymbols from the formatters that use them.
- [ ] Do not confuse Currency.getAvailableCurrencies with locale lists.
- [ ] Do not assume DateTimeFormatter has a static getAvailableLocales.
- [ ] Understand CLDR, SPI sources, and the LocaleServiceProvider mechanism.
- [ ] Do not assert identical locale counts across all JDKs.
- [ ] Verify functional outputs, not just exact membership.
- [ ] Maintain an appSupportedLocales list committed to by the product.
- [ ] Verify ResourceBundle translations do not fall back to the wrong language.
- [ ] Use Locale.lookup/LanguageRange over the app's allowed list.
- [ ] Define a fallback when no candidate matches.
- [ ] Separate requested, UI, and formatting locales.
- [ ] Separate Currency and ZoneId from Locale.
- [ ] Never mutate Locale.setDefault during concurrent requests.
- [ ] Test extensions if the product supports them.
- [ ] Check JDK/provider/CLDR when upgrading the runtime.
- [ ] Verify RTL, fonts, and accessibility where applicable.
- [ ] Do not use getAvailableLocales as a certificate for the entire UX.

## 24. Conclusion

**Locale.getAvailableLocales() is not synonymous with locales supported across all services.** It gives a general list for the Java environment. Services such as **NumberFormat, DateFormat, Collator, BreakIterator, DateFormatSymbols, and DecimalFormatSymbols** have their own advertised lists and data/providers; appearing in a list or succeeding in a factory call also does not replace output testing, because fallback can occur.

In Java 17+, use **the exact API of the service you are querying**, test functionality on the real JDK/provider, and manage **appSupportedLocales** as an independent product decision. Use Locale.LanguageRange and Locale.lookup to select languages from your app's translated list; separate Locale from Currency/TimeZone; control fallbacks and avoid mutating the JVM-wide default Locale during requests. This approach lets your application leverage the JDK's rich locale data without falsely claiming untested translations or features.
