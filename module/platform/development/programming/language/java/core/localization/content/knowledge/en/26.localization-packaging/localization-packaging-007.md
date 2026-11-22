# LocaleServiceProvider and SPIs for Names or Formatting in Java

When a Java application needs to support a locale not fully provided by the JDK or needs to **extend how names and formats are displayed** using custom rules, merely constructing a new `Locale` is not enough. Java provides a **locale-sensitive Service Provider Interface (SPI)** mechanism: an application or library can supply an implementation discovered by the runtime so that standard APIs in `java.text` and `java.util` gain additional locale-handling capabilities.

The root class is **`java.util.spi.LocaleServiceProvider`**. Specific SPIs such as `LocaleNameProvider`, `CurrencyNameProvider`, `NumberFormatProvider`, and `DateFormatProvider` allow adding **display names** or **formatting objects** for applicable locales. This mechanism involves packaging, service discovery, and provider ordering; it is **not** an automatic translation system for all messages in an application.

This lesson belongs to the **Packaging and Extensibility** topic in Java Core localization. It uses Java 17+ to explain the provider mechanism, registration via `META-INF/services` or `module-info.java`, a runnable `NumberFormatProvider` example, a `LocaleNameProvider` example for names, key limitations, common mistakes, and a testing plan.

## 1. From Locale to Locale Data Providers

`Locale` primarily acts as an **identifier**. For example:

~~~java
Locale locale = Locale.forLanguageTag("en-US");
~~~

This snippet expresses a language/region request; it does not itself contain all number patterns, language names, or date formats. When calling:

~~~java
NumberFormat f = NumberFormat.getNumberInstance(locale);
String display = f.format(1234.5);
~~~

Java needs a formatting service implementation and suitable locale data. Most applications rely on **JDK built-in data** (such as CLDR), yet certain services can be augmented by **custom providers**.

A conceptual flow:

~~~text
Application calls NumberFormat.getNumberInstance(locale)
                         |
                         v
           Locale-sensitive service lookup
                         |
         +---------------+---------------+
         |                               |
   JDK Provider (CLDR...)       External Provider (SPI)
         |                               |
         +---------------+---------------+
                         |
                         v
              Matching NumberFormat
                         |
                         v
                 Display string
~~~

The priority order of sources is configured via `java.locale.providers`. The outcome also depends on the service, the locales actually supported by the provider, the running runtime, and fallback rules.

### What Is an SPI in This Lesson?

An **SPI (Service Provider Interface)** is a contract allowing third parties to supply service implementations. For localization, these are **specific abstract classes** sharing the `LocaleServiceProvider` superclass. Developers create a subclass, implement the required methods, and package it so Java can discover it.

The term "provider" is often conflated across two levels:

- **Provider data groups** in the `java.locale.providers` order: `CLDR`, `SPI`, `HOST`, and certain legacy groups depending on version.
- **Concrete application provider classes**: for example, `demo.CustomNumberProvider extends NumberFormatProvider`.

`SPI` in the configuration string is **a provider lookup group**, not the name of a Java class you write.

## 2. What Is the Role of the Base Class LocaleServiceProvider?

`java.util.spi.LocaleServiceProvider` is the abstract parent class of locale-sensitive SPIs. Two key methods:

~~~java
public abstract Locale[] getAvailableLocales();

public boolean isSupportedLocale(Locale locale);
~~~

The snippet above shows **illustrative API signatures**, not a standalone runnable class.

- `getAvailableLocales()` returns the list of locales for which the provider **can genuinely supply** data or objects. Do not advertise every locale while supporting only a few.
- `isSupportedLocale(locale)` determines whether a locale is supported. The default implementation compares against `getAvailableLocales()` after **stripping locale extensions**.
- If a provider needs to distinguish Unicode locale extensions, such as numbering systems in `en-US-u-nu-thai`, **override `isSupportedLocale`** and define clearly which extensions are supported.

Example:

~~~java
Locale requested =
        Locale.forLanguageTag("en-XZ-u-nu-latn");
~~~

For a provider advertising `en-XZ`, the default check may treat a request carrying an extension as supported because it compares locales after stripping extensions. However, that **does not guarantee** your formatter implementation actually honors the `nu` extension. If it accepts it without handling the numbering system, output may differ from user expectations. Restrict the advertised scope or implement the corresponding logic.

**Do not store global request state inside a provider.** Providers may be reused by the runtime and their methods invoked from multiple threads. Each call returning a `NumberFormat` should create an appropriate instance; `NumberFormat`/`DecimalFormat` are stateful mutable objects, not inherently safe for concurrent mutations.

## 3. SPIs for Display Names and Formatting

Do not subclass `LocaleServiceProvider` directly and expect Java to know how to use it for everything. Choose the **specific SPI subclass for the target service**.

| Specific SPI | Package | Primary function |
| --- | --- | --- |
| `LocaleNameProvider` | `java.util.spi` | Display names for languages, regions, variants, scripts, or supported extensions |
| `CurrencyNameProvider` | `java.util.spi` | Locale-specific currency symbols/display names |
| `TimeZoneNameProvider` | `java.util.spi` | Time zone display names |
| `CalendarNameProvider` | `java.util.spi` | Calendar field names such as months, weekdays, and eras in corresponding APIs |
| `CalendarDataProvider` | `java.util.spi` | Calendar info such as first day of week and minimal days in first week |
| `NumberFormatProvider` | `java.text.spi` | Creates number, percent, integer, and currency formatters |
| `DecimalFormatSymbolsProvider` | `java.text.spi` | Decimal separator, grouping separator, and `DecimalFormatSymbols` data |
| `DateFormatProvider` | `java.text.spi` | Creates `DateFormat` by locale/style |
| `DateFormatSymbolsProvider` | `java.text.spi` | Symbols/names used in `DateFormatSymbols` |
| `BreakIteratorProvider` | `java.text.spi` | Creates locale-specific text boundary iterators |
| `CollatorProvider` | `java.text.spi` | Creates locale-specific string comparators/sorters |

These are **subclasses present in the Java SE 17 API**, not a promise that every SPI is used by every runtime for every modern date/time class or every Unicode service.

### Names Are Distinct from Formatters

- `LocaleNameProvider` returns a **localized name `String`**, such as the name of language code `fr` in display locale `en-XZ`.
- `CurrencyNameProvider` returns **currency names/symbols**, without performing exchange-rate conversion.
- `NumberFormatProvider` returns a **`NumberFormat` to format numbers**, not translations of UI labels.
- `DateFormatProvider` is an SPI of the `java.text.DateFormat` family; do not assume it overrides all `java.time.format.DateTimeFormatter` behavior.

If you want to translate `button.save=Save` into `Lưu`, that is application content responsibility, typically handled by `ResourceBundle` or a dedicated l10n system; `LocaleNameProvider` is not a general sentence-translation engine.

## 4. Selection Mechanism: CLDR, SPI, COMPAT, HOST

The JDK prioritizes provider groups via the **`java.locale.providers`** system property. On Java 17, documented values include:

| Value | Meaning |
| --- | --- |
| `CLDR` | Localization data based on Unicode CLDR bundled with the JDK |
| `SPI` | Providers registered by applications/libraries via `LocaleServiceProvider` |
| `COMPAT` | Locale data compatible with many pre-JDK 8 behaviors |
| `JRE` | Legacy alias for `COMPAT` in versions that still support it |
| `HOST` | Certain operating system locale settings, depending on runtime/platform |

**On JDK 17**, the default order is equivalent to `CLDR,COMPAT`. For your classpath provider to be searched, you must **include `SPI` in the property when starting the JVM**, for example:

~~~bash
java -Djava.locale.providers=SPI,CLDR,COMPAT -cp out demo.ProviderDemo
~~~

Here `SPI` is tried before `CLDR` and `COMPAT` for services/locales with a matching provider. If no suitable implementation exists, the runtime checks the next provider group, then locale fallbacks per the API algorithm.

**Important:** `java.locale.providers` is read only at runtime startup. Calling `System.setProperty("java.locale.providers","SPI,CLDR")` after the application has already started **does not change the lookup order**.

### Notes When Upgrading JDK Versions

- Since **JDK 9**, CLDR is prioritized by default (JEP 252).
- **JDK 17** still retains legacy `COMPAT/JRE` data.
- In **JDK 23 and later**, legacy `COMPAT/JRE` locale data was removed. Specifying those names in the property does not restore the old dataset.
- `SPI` providers remain a viable extensibility path when satisfying runtime contracts and packaging rules.

Do not rely on `COMPAT` as a long-term strategy for applications preparing for Java upgrades. If you depend on legacy formats, plan an explicit migration: a specific custom formatter or a designed and tested SPI.

### Does SPI Always Beat CLDR?

**No.** Provider order decides. If configured as `CLDR,SPI`, CLDR data may be picked first for a service/locale it already supports. If you want custom providers tried first, specify `SPI,CLDR` (or the appropriate runtime order).

Even with `SPI` listed first, a provider is invoked only when **the corresponding SPI service is requested**, the locale is supported, and the provider is discovered/registered. If your class is not properly on the classpath/module path or the service descriptor is wrong, Java may silently use a standard formatter without an obvious error.

## 5. Registering a Provider on the Classpath

For **classpath** (non-modular) applications, register using a Java service provider configuration file:

~~~text
META-INF/services/<fully qualified SPI name>
~~~

When implementing `NumberFormatProvider`, the exact resource path must be:

~~~text
META-INF/services/java.text.spi.NumberFormatProvider
~~~

Inside the file (UTF-8), each line is the **fully qualified name of a concrete implementation class**, for example:

~~~text
demo.CustomNumberProvider
~~~

This is the content of the configuration file, **not a shell command**. The file name must be the SPI name, not the implementation class name. The final package must include both `demo.CustomNumberProvider` and the readable descriptor at `META-INF/services/...`.

The implementation class must be accessible to the loader, non-abstract, and have an appropriate constructor so the service mechanism can instantiate it. If the configuration points to a missing, inaccessible, or wrong-subtype class, lookup can trigger a service-loading error.

### Sample Directory Structure

~~~text
project/
  src/
    demo/
      CustomNumberProvider.java
      ProviderDemo.java
  resources/
    META-INF/
      services/
        java.text.spi.NumberFormatProvider
~~~

Do not mistakenly place the descriptor inside `src/demo` or under the name `LocaleServiceProvider`. The API searches for the **specific SPI**, such as `java.text.spi.NumberFormatProvider`.

### What About Java Module (JPMS) Applications?

If the implementation is packaged inside a **named module**, you can declare the provider with `provides ... with ...`:

~~~java
module demo.locale.provider {
    provides java.text.spi.NumberFormatProvider
        with demo.CustomNumberProvider;
}
~~~

This is an **illustrative `module-info.java` snippet**, to be integrated into an appropriate project/module layout. You may need to ensure the provider module is resolved into the module graph at runtime; merely placing a JAR on the module path does not guarantee service selection under every launch mode. On the classpath, `META-INF/services` is the clearest mechanism for the example in the next section.

Do not confuse JPMS `uses`/`provides` with `java.locale.providers`: one configures **service class discovery**, while the other sets **locale provider group precedence** when the JVM performs locale-sensitive lookups.

## 6. Java 17 Example: Writing a Custom NumberFormatProvider

We will create an **illustrative-only** locale `en-XZ` and define a custom number format:

~~~text
Value:            1234.5
Demo format:      1_234~50
~~~

The `_` grouping separator and `~` decimal separator in this example **are not official CLDR conventions for any country**. Their purpose is to make it immediately visible that the provider was used.

### 6.1. File src/demo/CustomNumberProvider.java

~~~java
package demo;

import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.NumberFormat;
import java.text.spi.NumberFormatProvider;
import java.util.Locale;

public final class CustomNumberProvider extends NumberFormatProvider {
    private static final Locale DEMO =
            Locale.forLanguageTag("en-XZ");

    public CustomNumberProvider() {
    }

    @Override
    public Locale[] getAvailableLocales() {
        return new Locale[] { DEMO };
    }

    private static void check(Locale locale) {
        if (!DEMO.equals(locale.stripExtensions())) {
            throw new IllegalArgumentException("Unsupported locale");
        }
    }

    private static DecimalFormat format(String pattern) {
        DecimalFormatSymbols symbols =
                DecimalFormatSymbols.getInstance(Locale.US);
        symbols.setGroupingSeparator('_');
        symbols.setDecimalSeparator('~');
        return new DecimalFormat(pattern, symbols);
    }

    @Override
    public NumberFormat getNumberInstance(Locale locale) {
        check(locale);
        return format("#,##0.00");
    }

    @Override
    public NumberFormat getIntegerInstance(Locale locale) {
        check(locale);
        DecimalFormat formatter = format("#,##0");
        formatter.setParseIntegerOnly(true);
        formatter.setRoundingMode(RoundingMode.HALF_EVEN);
        return formatter;
    }

    @Override
    public NumberFormat getCurrencyInstance(Locale locale) {
        check(locale);
        return format("¤ #,##0.00");
    }

    @Override
    public NumberFormat getPercentInstance(Locale locale) {
        check(locale);
        return format("#,##0%");
    }
}
~~~

**Design explanation:**

1. `getAvailableLocales()` advertises exactly one test locale.
2. `check` rejects out-of-scope locales. It strips extensions like the default check and **does not implement custom numbering systems**; this limitation is intentional and explicit.
3. `format` builds `DecimalFormatSymbols` based on `Locale.US`, then sets custom grouping/decimal characters. It **does not call `NumberFormat.getNumberInstance(DEMO)`** inside the provider itself, avoiding recursive lookup back into this SPI.
4. Each method creates a fresh formatter. Because `DecimalFormat` is stateful, this is safer to control than sharing a single instance that another request might mutate.
5. All four abstract methods of `NumberFormatProvider` are implemented: number, integer, currency, and percent.
6. In Java 17, `getCompactNumberInstance(locale, style)` is not a required abstract method; its default implementation throws `UnsupportedOperationException`. To support compact formatting via this SPI, evaluate/override that method as well.

**Intentional limitation:** the currency formatter in this example only demonstrates formatting mechanics; it does not model per-transaction currency codes/rounding policies, locale-specific currency symbols, strict parsing, or business standards. Do not use this demo provider directly for real payments.

### 6.2. File src/demo/ProviderDemo.java

~~~java
package demo;

import java.text.NumberFormat;
import java.util.Locale;

public final class ProviderDemo {
    public static void main(String[] args) {
        Locale demo = Locale.forLanguageTag("en-XZ");
        CustomNumberProvider direct = new CustomNumberProvider();

        System.out.println("Locale: "
                + direct.getAvailableLocales()[0].toLanguageTag());
        System.out.println("Supported: "
                + direct.isSupportedLocale(demo));
        System.out.println("Unsupported: "
                + direct.isSupportedLocale(Locale.US));

        String directNumber =
                direct.getNumberInstance(demo).format(1234.5);
        System.out.println("Direct number: " + directNumber);

        NumberFormat viaFactory = NumberFormat.getNumberInstance(demo);
        String factoryNumber = viaFactory.format(1234.5);
        System.out.println("Factory used SPI: "
                + directNumber.equals(factoryNumber));
    }
}
~~~

Two things to distinguish:

- `new CustomNumberProvider().getNumberInstance(demo)` **invokes the Java object directly**; it works **even without registering the service**.
- `NumberFormat.getNumberInstance(demo)` **goes through the runtime's locale provider lookup**. It picks the application provider only when properly registered and permitted by provider order/locale rules.

### 6.3. Service Registration Resource File

Create the exact file:

~~~text
resources/META-INF/services/java.text.spi.NumberFormatProvider
~~~

File contents:

~~~text
demo.CustomNumberProvider
~~~

### 6.4. Compile and Run (JDK 17+)

Example for Bash shell on macOS/Linux:

~~~bash
mkdir -p out/META-INF/services
javac --release 17 -encoding UTF-8 -d out \
  src/demo/CustomNumberProvider.java \
  src/demo/ProviderDemo.java
cp resources/META-INF/services/java.text.spi.NumberFormatProvider \
  out/META-INF/services/

java -Djava.locale.providers=SPI,CLDR -cp out demo.ProviderDemo
~~~

In PowerShell on Windows, equivalent directory/copy steps:

~~~powershell
New-Item -ItemType Directory -Force out/META-INF/services | Out-Null
javac --release 17 -encoding UTF-8 -d out src/demo/CustomNumberProvider.java src/demo/ProviderDemo.java
Copy-Item resources/META-INF/services/java.text.spi.NumberFormatProvider out/META-INF/services/
java -Djava.locale.providers=SPI,CLDR -cp out demo.ProviderDemo
~~~

This is a **self-contained example setup guide**, requiring no files or libraries beyond Java 17. `out` is the classpath directory holding compiled classes as well as the service descriptor resource.

### 6.5. Expected Output When SPI Is Registered and Prioritized

~~~text
Locale: en-XZ
Supported: true
Unsupported: false
Direct number: 1_234~50
Factory used SPI: true
~~~

The values of `getAvailableLocales`, `isSupportedLocale`, and the **directly** invoked formatter were tested on a JDK: `en-XZ`, `true`, `false`, and `1_234~50`. The `Factory used SPI: true` line is the expectation of the **`ServiceLoader`/locale lookup** path when the classpath contains the descriptor and the JVM starts with `SPI,CLDR` as instructed; if you get `false`, inspect the descriptor file, classpath, startup property, provider locale, and runtime.

To see the difference, launch without `SPI`:

~~~bash
java -Djava.locale.providers=CLDR -cp out demo.ProviderDemo
~~~

The **direct** call will still produce the demo format, whereas `NumberFormat.getNumberInstance` uses another provider; do not promise exact fallback strings if CLDR/runtime versions change.

### Why Choose a Custom Locale?

An SPI using `Locale.US`, for instance, might not be picked if `CLDR` precedes it. The demo locale `en-XZ` avoids confusion about provider precedence and demonstrates supplemental support. Remember, however, that `en-XZ` **is not a real region/formatting standard for production**; real data must rely on valid, approved locales and requirements.

## 7. SPI Example for Names: LocaleNameProvider

The **name** SPI group returns text strings, unlike formatting SPIs that return formatters.

`LocaleNameProvider` in `java.util.spi` has required methods such as:

~~~java
public String getDisplayLanguage(String languageCode, Locale locale);
public String getDisplayCountry(String countryCode, Locale locale);
public String getDisplayVariant(String variant, Locale locale);
~~~

These are **illustrative signatures**. Other methods such as `getDisplayScript` have default implementations in the API and can be overridden when supporting script names.

**Distinguish the two inputs:**

- `languageCode` / `countryCode` is the **code of the entity to be named**.
- `locale` is the **language/region in which to display that name**.

For example, to obtain the name of French displayed in English, the entity to name is code `fr` while the display locale might be `en-US`. Do not invert the two roles.

An illustrative provider:

~~~java
package demo;

import java.util.Locale;
import java.util.spi.LocaleNameProvider;

public final class CustomLocaleNames extends LocaleNameProvider {
    private static final Locale TARGET =
            Locale.forLanguageTag("en-XZ");

    public CustomLocaleNames() {
    }

    @Override
    public Locale[] getAvailableLocales() {
        return new Locale[] { TARGET };
    }

    @Override
    public String getDisplayLanguage(
            String languageCode, Locale locale) {
        if (!isSupportedLocale(locale)) {
            throw new IllegalArgumentException("Unsupported locale");
        }
        return "fr".equals(languageCode) ? "French (custom)" : null;
    }

    @Override
    public String getDisplayCountry(
            String countryCode, Locale locale) {
        return null;
    }

    @Override
    public String getDisplayVariant(
            String variant, Locale locale) {
        return null;
    }
}
~~~

This is an **illustrative helper class**, not a standalone program with `main`. Calling it directly:

~~~java
CustomLocaleNames names = new CustomLocaleNames();
Locale displayLocale = Locale.forLanguageTag("en-XZ");

System.out.println(names.getDisplayLanguage("fr", displayLocale));
// French (custom)
System.out.println(names.getDisplayLanguage("de", displayLocale) == null);
// true
~~~

Both direct calls above were tested with Java. Returning `null` from a **display name** method signals that no translation exists for that code; the locale service lookup mechanism can keep searching other sources or fall back. Do **not** generalize "formatter providers can also return `null` arbitrarily" to formatter-object SPIs like `NumberFormatProvider`.

To register `CustomLocaleNames` on the classpath, use a **separate service file**:

~~~text
META-INF/services/java.util.spi.LocaleNameProvider
~~~

Contents:

~~~text
demo.CustomLocaleNames
~~~

Then call the standard API such as:

~~~java
String shown = Locale.FRENCH.getDisplayLanguage(
        Locale.forLanguageTag("en-XZ"));
~~~

If `SPI` is registered, prioritized, and the locale is supported by the provider, the API can use the name from the provider before falling back to other sources. Do not predict that direct calls and factory lookups behave identically without checking **descriptor + property + runtime**.

### Other Name SPIs

- `CurrencyNameProvider`: currency names or symbols by locale; does not convert exchange rates.
- `TimeZoneNameProvider`: time zone display names; does not alter `ZoneRules` or infer user location.
- `CalendarNameProvider`: names of calendar components for corresponding APIs; does not translate application text.

Having `LocaleNameProvider` support a name does not mean it automatically populates data into every `ResourceBundle` created by the product.

## 8. Formatting Providers: Which API to Choose?

When extending formatting, pick the right data level:

| Requirement | Choice |
| --- | --- |
| Replace the entire number formatter creation rules | `NumberFormatProvider` |
| Replace only the symbol set of `DecimalFormatSymbols` | `DecimalFormatSymbolsProvider` |
| Provide `DateFormat` for a new locale | `DateFormatProvider` |
| Provide month/weekday/era names in `DateFormatSymbols` | `DateFormatSymbolsProvider` |
| Provide custom currency names | `CurrencyNameProvider` |
| Provide language/country names in the `Locale` API | `LocaleNameProvider` |
| Add collation/sorting rules for a locale | `CollatorProvider` |
| Add text boundary segmentation rules | `BreakIteratorProvider` |

There is no single "universal" `LocaleServiceProvider` that automatically dispatches everything based on `getAvailableLocales`. Each SPI is a separate contract for a specific service group.

### NumberFormatProvider Is Not DecimalFormatSymbolsProvider

These two SPIs have different roles. `DecimalFormatSymbolsProvider` supplies symbols for formatters to use under the appropriate mechanism; `NumberFormatProvider` builds the entire `NumberFormat` and can choose patterns, parsing, and formatting logic itself.

When implementing a number formatter, verify:

- grouping/decimal separators;
- negative numbers, very large numbers, floating-point values, and `BigDecimal`;
- percentages (usually multiplied by 100 on display, depending on the formatter);
- integers and rounding;
- currencies, currency codes, and fraction digits;
- parsing, `ParsePosition`, and partially parsed inputs;
- thread safety of mutable formatters;
- Unicode numbering system extensions if the application claims to support them.

Supplying a formatter that can print a demo string **does not make it production-ready for payment processing or business input parsing**. Canonical numeric data should be stored separately from locale-specific display formatting.

## 9. Fallback and Surprising Edge Cases

The locale lookup mechanism may try less specific candidates when the requested locale lacks a service, such as dropping region/variant/extension down to language or root per runtime rules.

Principles to understand:

1. **Per-service lookup:** a name provider does not automatically act as a format provider.
2. **Provider order:** `SPI,CLDR` differs from `CLDR,SPI` if both groups have data for the same service/locale.
3. **Locale support:** `getAvailableLocales()` and `isSupportedLocale` must reflect genuine support rather than advertising indiscriminately.
4. **Extensions:** the default `isSupportedLocale` implementation ignores extensions; override it to handle them specifically.
5. **Names returning null:** name providers may return `null` so lookup continues; formatter objects must fulfill their method contracts instead of treating `null` as a standard fallback.
6. **Classpath/module path:** the provider class and service registration must exist at runtime; bad packaging causes the factory to fall back to another provider.
7. **Startup:** `java.locale.providers` is read when the JVM starts, not dynamically per request.
8. **JDK data changes:** upgrading the JDK or CLDR can change output or provider availability.

If a project uses `jlink` to build a custom minimal runtime image, inspect locale modules/data and actual service discovery inside the image. A build running fine on a full JDK does not automatically ensure a production image retains the provider.

## 10. SPI Is Not a Full-Application Translation System

Suppose a product has messages:

~~~properties
# messages_vi.properties
button.save=Lưu
cart.empty=Giỏ hàng chưa có sản phẩm.
~~~

Those are **application resources**, typically loaded via `ResourceBundle` or the product's translation framework. Do not write a `LocaleNameProvider` to replace all `button.save` or `cart.empty` keys.

Distinguish:

- **LocaleServiceProvider:** extends specific standard services related to names/formatters.
- **ResourceBundle:** manages per-locale application bundles and specific messages/labels.
- **ResourceBundleProvider / ResourceBundleControlProvider:** separate SPIs governing how resource bundles are located/loaded; not the same as `LocaleServiceProvider`.
- **ICU4J / i18n libraries:** can provide additional capabilities like advanced plural/select rules and library-specific locale data/formatting.
- **CLDR:** a locale data/rules repository; not an automatic paragraph-translation library.

In Java 17, `java.text.MessageFormat` does not automatically understand ICU plural/select syntax merely because the runtime uses CLDR data. If you need grammatical inflections for plurals, gender, or cases across languages, choose an appropriate engine and provide complete translated sentences.

## 11. Avoiding Recursion Inside the Provider Itself

A dangerous bug when implementing `NumberFormatProvider`:

~~~java
@Override
public NumberFormat getNumberInstance(Locale locale) {
    return NumberFormat.getNumberInstance(locale); // May look up this same SPI again!
}
~~~

This is an **anti-pattern**, never to be used in production. If the provider was selected for that locale and calls the corresponding factory again, it can re-enter lookup and select itself again, causing **infinite recursion / `StackOverflowError`**.

In the valid example, `CustomNumberProvider` constructs `DecimalFormat` directly using `Locale.US`'s `DecimalFormatSymbols` and replaces the symbols. If you want to delegate to another provider, pick a path that **does not re-enter your own provider** and controls fallback. Using another locale also requires accounting for other configured providers and potential lookup loops; do not guess.

Another mistake is returning **one shared `NumberFormat`** across all requests. `DecimalFormat` is mutable, exposing setters such as `setGroupingUsed` and `setMaximumFractionDigits`. If a caller mutates the formatter returned by the factory, subsequent requests can be affected if they share the instance. Providers should create a fresh object or apply appropriate defensive copying.

## 12. Systematic SPI Testing

Do not test only `new CustomNumberProvider()`: that **bypasses** the descriptor, classpath, `ServiceLoader`, and runtime provider selection. You need both **direct unit tests** and **integration tests through the standard API**.

| Test layer | Example | Expected verification |
| --- | --- | --- |
| Unit provider | `getAvailableLocales()` | Accurate supported locales, no over-advertising |
| Unit locale support | `isSupportedLocale(en-XZ)` | Returns true |
| Unit locale rejection | `isSupportedLocale(en-US)` | Returns false if unsupported |
| Unit formatter | `getNumberInstance(en-XZ).format(1234.5)` | Returns `1_234~50` |
| Unit metadata | `getIntegerInstance`, `getCurrencyInstance` | Valid objects, correct policies |
| Service discovery | `META-INF/services/...` file | Provider discovered by runtime |
| Integration factory | `NumberFormat.getNumberInstance(en-XZ)` | Uses custom provider when `SPI` is first |
| Provider order | `SPI,CLDR` vs. `CLDR,SPI` | Behavior may differ for supported locales |
| Name provider | `Locale.FRENCH.getDisplayLanguage(en-XZ)` | Picks name from provider when registered |
| Name fallback | Name provider returns `null` | No crash, proper fallback |
| Unicode extensions | `en-XZ-u-nu-thai` | Intentionally accepted or rejected |
| JVM startup | Property set before launch | Effective runtime ordering applied |
| Packaging | JAR, classpath, module path, `jlink` | Service descriptors and classes present |
| Production migration | JDK upgrade, CLDR change | No unintended critical output changes |
| Multithreading | Concurrent formatter calls | No unsafe shared mutable instances |

### Diagnostic Checklist When the Factory Ignores the SPI

1. Was `java -Djava.locale.providers=SPI,CLDR ...` passed at process startup?
2. Does the service file have the **exact SPI name** (not the implementation class name)?
3. Does the UTF-8 descriptor contain the exact **fully qualified class name** of the concrete provider?
4. Is the provider class on the classpath/module graph and accessible to the loader?
5. Does the provider have a public constructor and valid instantiation requirements?
6. Does the provider advertise the requested locale in `getAvailableLocales`?
7. Does `isSupportedLocale` return true per contract?
8. Is another provider ordered earlier already supporting that service/locale?
9. Are you calling the standard API consuming that SPI type rather than only calling the provider directly?
10. Is there a recursive lookup inside the provider causing infinite recursion or loading failure?

When in doubt, record the **JDK vendor/version**, `java.locale.providers` at startup, locale tag, JAR/module path, and integration test output. Do not assume the provider is active merely because the class compiles.

## 13. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Assuming `LocaleServiceProvider` handles all locales automatically | Runtime has no specific service to invoke | Subclass the specific SPI type |
| Creating the class without registering the service | Factory never finds the provider | `META-INF/services` or JPMS `provides` |
| Naming the service file after the concrete class | `ServiceLoader` ignores the descriptor | Use the fully qualified SPI name |
| Forgetting `SPI` in `java.locale.providers` on JDK 17 | Classpath provider is not prioritized/queried | Set the startup property appropriately |
| Setting the property after JVM startup | Does not alter locale lookup order | Pass it in the launch command |
| Thinking `SPI` always beats `CLDR` | Provider order may put CLDR first | Configure and test the exact order |
| Advertising all locales while supporting only one | Incorrect formatting or unexpected errors | Return an accurate supported list |
| Ignoring Unicode extensions | Accepts locales with unsupported numbering systems | Override `isSupportedLocale` when needed |
| Calling the same factory inside the provider itself | Lookup recursion | Build formatter directly or delegate safely |
| Returning a shared mutable `DecimalFormat` | Race conditions / config leaks across requests | Return a new formatter |
| Treating name providers and format providers identically | Violates `String`/`NumberFormat` contracts | Separate each SPI |
| Returning `null` for an unsupported formatter | Violates object contract | Support only real locales, return valid objects |
| Treating a name SPI as product message translation | UI keys remain untranslated | Use `ResourceBundle` or app translation system |
| Assuming `java.text` time SPIs override all `java.time` APIs | No such guarantee | Verify each API/service |
| Relying on `COMPAT` on JDK 23+ | Legacy data has been removed | Migrate to CLDR or a custom provider |
| Testing only direct provider calls | Packaging errors go undetected | Integration-test through JDK APIs |

## 14. Self-Check Questions

**Question 1.** Is `LocaleServiceProvider` a class you simply instantiate with `new` to change all JDK formatting?

**Answer:** No. You must subclass a specific SPI, implement methods per its contract, register the service, and configure lookup properly.

**Question 2.** In the `NumberFormatProvider` example, why not call `NumberFormat.getNumberInstance(demoLocale)` inside `getNumberInstance` itself?

**Answer:** The factory path can pick the same provider again, causing recursion. The example constructs `DecimalFormat` directly with controlled symbols.

**Question 3.** What are the two arguments of `LocaleNameProvider.getDisplayLanguage("fr", locale)` for?

**Answer:** `"fr"` is the language code whose name you want; `locale` is the language/region used to render that display name.

**Question 4.** Why can a unit test calling `new CustomNumberProvider()` pass while `NumberFormat.getNumberInstance(locale)` still does not use the demo formatter?

**Answer:** Direct calls do not test service registration or lookup. You need a valid descriptor, proper classpath/module setup, and matching `java.locale.providers` at launch.

**Question 5.** If a name provider does not have a requested name, may it return `null`?

**Answer:** For providers returning **display names** such as `LocaleNameProvider`, returning `null` for unavailable names is permitted so lookup can fall back. Do not generalize this to formatter-object providers.

**Question 6.** Are `SPI,CLDR` and `CLDR,SPI` equivalent?

**Answer:** No. If both sources have data for a given service/locale, the one prioritized first can determine the result.

**Practice exercise:** Change the test locale and patterns in `CustomNumberProvider`, and add tests for `getIntegerInstance` and `getPercentInstance`. Register the class via a descriptor, run with both `SPI,CLDR` and `CLDR,SPI`, and compare results through the factory API. Write an additional `LocaleNameProvider` returning names for a few language codes; test name lookup with both supported and unsupported locales. Finally, describe how to package both providers into a single JAR while keeping **two separate service descriptors**.

## 15. Official Documentation

- [LocaleServiceProvider — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/spi/LocaleServiceProvider.html): SPI list, `getAvailableLocales`, `isSupportedLocale`, packaging, and `java.locale.providers`.
- [NumberFormatProvider — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/spi/NumberFormatProvider.html): four formatter factory methods and `getCompactNumberInstance`.
- [LocaleNameProvider — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/spi/LocaleNameProvider.html): language, country, variant, and script names.
- [CurrencyNameProvider — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/spi/CurrencyNameProvider.html): SPI for currency names/symbols.
- [DateFormatProvider — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/spi/DateFormatProvider.html): date formatting SPI under `java.text`.
- [ServiceLoader — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): classpath/module service discovery mechanism.
- [JEP 252 — Use CLDR Locale Data by Default](https://openjdk.org/jeps/252): provider configuration and CLDR data.
- [Oracle JDK 17 Supported Locales](https://www.oracle.com/java/technologies/javase/jdk17-suported-locales.html): CLDR, COMPAT, SPI, and HOST in JDK 17.
- [JDK 23 migration — removed COMPAT/JRE](https://docs.oracle.com/en/java/javase/23/migrate/removed-tools-and-components.html): changes when upgrading the JDK.

**Key takeaway:** `LocaleServiceProvider` is the foundation for localization SPIs, but **you must pick the right provider for the right service**, advertise supported locales accurately, register the class, and set `java.locale.providers` order at startup. Name providers like `LocaleNameProvider` return localized strings; format providers like `NumberFormatProvider` return formatters. SPIs extend selected Java Core APIs; **they do not translate application content automatically**, do not replace business currency/grammar rules, and are no substitute for real locale testing.
