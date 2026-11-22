# Why Being Able to Create a `Locale` Does Not Mean Every Service Supports It

## 1. Core issue: `Locale` is a request, not a certificate of support

In Java, you can construct a `Locale` object simply from a structurally valid language tag:

```java
Locale locale = Locale.forLanguageTag("zz-ZZ");
```

`zz-ZZ` here is an illustrative code for an uncommon language/region choice, not representing any market deployed by the application. Java can still create and store this tag. Yet from that **you cannot conclude** that Java, UI libraries, messaging systems, currency data, or the application itself have resources for that choice.

This is a key distinction in the `Locale` model:

- **Representing a request:** creating `Locale`, calling `getLanguage()`, `getCountry()`, `toLanguageTag()`, and passing it to APIs.
- **Having implementations/data:** each service (number formatting, date formatting, string collation, word breaking, resource bundles, etc.) has its own dataset and locale providers.
- **Working via fallback:** a service may return results using generic rules or another locale, even when no dedicated data exists for the requested locale.
- **Fit for market and users:** translations, grammar, symbols, local conventions, and UI cases have been verified. This is a higher bar than an API call succeeding.

**Conclusion of this phenomenon:** `new Locale(...)` (legacy), `Locale.forLanguageTag(...)`, or `Locale.Builder` only creates a **locale descriptor object**; they do not load translations, check all services, or force the application to support that locale.

## 2. Why does Java allow creating an unsupported locale?

### 2.1. The `Locale` object stores an identifier, not all local data

A `Locale` can carry:

| Component | Example | Meaning |
| --- | --- | --- |
| Language | `vi` | Language |
| Script | `Latn`, `Hant` | Writing system when disambiguation is needed |
| Region | `VN`, `US` | Country/region |
| Variant | A valid variant | Additional variant information |
| Extension | E.g. `u-nu-latn` | Additional BCP 47 request; support varies by service |

`Locale.forLanguageTag("vi-VN")` creates a description of Vietnamese in Vietnam; `Locale.forLanguageTag("zz-ZZ")` can still create a syntactically valid description. Neither operation guarantees the existence of translation files, collation rules, regional data, or corresponding UI design.

`Locale.Builder` can catch **syntax errors** via `IllformedLocaleException`, yet still does not prove **service support exists**. `Locale.forLanguageTag` handles malformed parts according to language tag parsing rules; therefore do not use the absence of an exception as a test for "this locale is supported".

Example:

```java
Locale requested = Locale.forLanguageTag("zz-ZZ");
System.out.println(requested.toLanguageTag()); // zz-ZZ
```

The output shows that Java preserved the requested identifier. It does not prove `zz` translations exist.

### 2.2. "Support" depends on the service and dataset

Locale-sensitive services in Java are not required to share the same list of locales. For example:

| Service/API | What does it provide? | Why can it differ from other services? |
| --- | --- | --- |
| `NumberFormat` | Formatting/parsing numbers, percentages, currency | Needs symbol data and number formatting patterns |
| `DateFormat` / `DateTimeFormatter` | Patterns, month names, weekday names, date/time display rules | Needs date/time data and has its own fallback mechanism |
| `Collator` | Linguistically appropriate string comparison order | Needs character sorting rules |
| `BreakIterator` | Character, word, sentence, and line boundaries | Needs text segmentation rules |
| `ResourceBundle` | Messages supplied by the application/libraries | Depends on available bundles on classpath/modules and their fallback |
| `Currency` | Currency code/unit info associated with a region, when determinable | Depends on currency and region data, not a translation repository |

A locale may have number formatting capability yet **lack application translations**; or have translation bundles yet remain untested for word sorting or calendar display. Even within Java, data can come from different locale-data providers, including the JDK's CLDR data and providers extended via SPI, depending on version/configuration/runtime.

Do not interpret "method ran without error" as "the service has dedicated accurate data for that exact locale". In particular, an API silently applying fallback rules can mask missing data.

## 3. Checking advertised capability per API

Many APIs provide `getAvailableLocales()`, such as `NumberFormat`, `DateFormat`, `Collator`, and `BreakIterator`. Ask **the specific service** your application is about to use rather than only inspecting the JVM-wide locale list.

Create the file **`LocaleAvailabilityDemo.java`**:

```java
import java.text.BreakIterator;
import java.text.Collator;
import java.text.DateFormat;
import java.text.NumberFormat;
import java.util.Arrays;
import java.util.Locale;

public class LocaleAvailabilityDemo {
    private static boolean advertised(Locale[] locales, Locale requested) {
        return Arrays.asList(locales).contains(requested);
    }

    public static void main(String[] args) {
        Locale requested = Locale.forLanguageTag("zz-ZZ");
        System.out.println("requested: " + requested.toLanguageTag());

        System.out.println("number: " + advertised(
                NumberFormat.getAvailableLocales(), requested));
        System.out.println("date: " + advertised(
                DateFormat.getAvailableLocales(), requested));
        System.out.println("collation: " + advertised(
                Collator.getAvailableLocales(), requested));
        System.out.println("word-boundary: " + advertised(
                BreakIterator.getAvailableLocales(), requested));

        NumberFormat formatter = NumberFormat.getNumberInstance(requested);
        System.out.println("formatted: " + formatter.format(1234567.5));
    }
}
```

Run with JDK 17+:

```bash
javac -encoding UTF-8 LocaleAvailabilityDemo.java
java -cp . LocaleAvailabilityDemo
```

The first line has deterministic output:

```text
requested: zz-ZZ
```

The remaining lines depend on the JDK version, locale provider configuration, and providers installed in the runtime, so **there is no single fixed stdout across all machines**. In a runtime that does not advertise support for `zz-ZZ`, you may see `false` on the check lines, while `getNumberInstance(requested).format(...)` can still produce a formatted number string using fallback data.

### How to interpret the results properly

- `true` means the service **advertises** that locale in the set returned by the API. It does not prove your UI translations exist or that all cultural rules are accurate.
- `false` means that locale **is not in that API's advertised list**. It does not necessarily mean every formatting call with that locale will fail; the service may fall back.
- Results from `NumberFormat` **cannot be inferred** from `DateFormat` or `Collator`.
- `Locale.getAvailableLocales()` returns the list of locales installed/provided at the runtime level; it is **not the list of translations your application has**, nor is it sufficient testing for every business feature.

A check like `Arrays.asList(...).contains(requested)` above performs an **exact locale object match**, which is useful for inspecting APIs. In real applications, choosing `vi` when `vi-VN` is requested is a separate **matching/fallback policy** and cannot rely solely on this `contains` check.

## 4. `ResourceBundle`: can return a message while still lacking a translation for the right locale

`ResourceBundle` reads resources packaged by the application/libraries, separate from the available locale sets of `NumberFormat` or `Collator`.

Suppose a project only provides:

**`labels.properties`** (root bundle):

```properties
welcome=Hello
```

**`labels_vi.properties`**:

```properties
welcome=Xin chào
```

And the program **`BundleFallbackDemo.java`**:

```java
import java.util.Locale;
import java.util.ResourceBundle;

public class BundleFallbackDemo {
    public static void main(String[] args) {
        show("vi-VN");
        show("fr-FR");
    }

    private static void show(String languageTag) {
        Locale requested = Locale.forLanguageTag(languageTag);
        ResourceBundle.Control control =
                ResourceBundle.Control.getNoFallbackControl(
                        ResourceBundle.Control.FORMAT_PROPERTIES);
        ResourceBundle bundle =
                ResourceBundle.getBundle("labels", requested, control);

        System.out.printf("%s -> %s (bundle: %s)%n",
                requested.toLanguageTag(),
                bundle.getString("welcome"),
                bundle.getLocale().toLanguageTag());
    }
}
```

Save all three files in the same directory and run on the classpath with JDK 17+:

```bash
javac -encoding UTF-8 BundleFallbackDemo.java
java -cp . BundleFallbackDemo
```

With the exact three files in the example, output:

```text
vi-VN -> Xin chào (bundle: vi)
fr-FR -> Hello (bundle: und)
```

**Detailed explanation:**

- The user requested `vi-VN`; `labels_vi_VN.properties` does not exist, but `labels_vi.properties` does, so the Vietnamese greeting is selected. `getLocale()` returns `vi`: the locale of the bundle actually loaded, not necessarily the requested locale.
- The user requested `fr-FR`; no French bundle exists, so the root `labels.properties` with `Locale.ROOT` is loaded. `Locale.ROOT.toLanguageTag()` is `und` ("undetermined"). The call succeeds, yet the message **is still English**.
- `getNoFallbackControl(...)` in the example disables the branch that tries the **JVM default locale** to keep results clear; it still allows falling back to the **root bundle**. With the default `getBundle` behavior, the candidate set may also check the default locale according to `ResourceBundle`'s algorithm.
- On JDK 17, `.properties` resource bundles are read as UTF-8 under current rules (with legacy compatibility mechanisms). Thus Vietnamese diacritics can be saved directly as in the example; ensure build/packaging tools preserve content and encoding.

The same applies when a bundle has some keys but is missing others: `getString` may pull values from a parent bundle. If the key is not found anywhere in the resolution chain, Java throws `MissingResourceException`. Therefore, check **key coverage and translation quality**, not just whether `getBundle` returns an object.

A program can have `labels_vi.properties` even if a third-party service lacks dedicated rules for `vi-VN`. Conversely, the runtime may format French numbers while the application has no French messages at all.

## 5. Fallback is a helpful feature, yet easily leads to wrong conclusions

There are multiple independent fallback layers:

```text
User-requested tag: vi-VN / fr-FR / ...
           |
           +--> Matching a locale the product commits to support
           |       -> e.g., supports vi, en; picks fallback en
           |
           +--> ResourceBundle
           |       -> variant/region translation -> language -> root bundle
           |       -> may try default locale depending on Control
           |
           +--> NumberFormat / DateFormat / Collator / ...
                   -> each service's data provider
                   -> runtime's own fallback rules
```

The diagram shows **independent branches**, not a single unified execution order in Java. A `ResourceBundle` returning an English sentence and a `NumberFormat` producing a number string **do not prove** that the product fully supports `fr-FR`.

Some APIs may also fail to resolve region-specific data or throw errors for unsuitable input. Do not assume every API falls back, or falls back to the same locale. Specifically:

- `NumberFormat.getCurrencyInstance(locale)` uses locale formatting rules; it **does not change the currency unit or exchange rate** of transaction data.
- `Currency.getInstance(locale)` requires valid region information and currency code data; merely creating a `Locale` does not guarantee a currency can be derived.
- `DateTimeFormatter.ofLocalizedDate(...).withLocale(locale)` requires pattern formatting data. Choosing a locale **does not** choose a time zone; time zone must be specified separately with `ZoneId`.
- `Collator` may use generic rules when specialized data is missing. Producing a sort order without errors is not enough to conclude it meets the language's dictionary requirements.
- Unicode extensions in BCP 47 (such as selecting a numbering system) only take effect in APIs/providers that actually understand and apply them.

## 6. Explicitly defining the application's own "supported locales"

For a product, "supported locale" should be a **concrete commitment** per feature, rather than simply "Java accepts the language tag".

For example, an application ships only Vietnamese and English UIs:

```java
import java.util.Locale;
import java.util.Set;

public class SupportedLocaleDemo {
    private static final Set<String> SUPPORTED =
            Set.of("vi", "en");

    public static void main(String[] args) {
        Locale requested = Locale.forLanguageTag("fr-FR");
        String language = requested.getLanguage();

        Locale selected = SUPPORTED.contains(language)
                ? requested
                : Locale.forLanguageTag("en");

        System.out.println("requested: " + requested.toLanguageTag());
        System.out.println("selected: " + selected.toLanguageTag());
    }
}
```

Run:

```bash
javac -encoding UTF-8 SupportedLocaleDemo.java
java -cp . SupportedLocaleDemo
```

Output:

```text
requested: fr-FR
selected: en
```

The example only illustrates a support policy **by language**. In real products, `en-US` and `en-GB`, or `zh-Hans` and `zh-Hant`, may need to be treated as distinct locales; collapsing to `getLanguage()` is not always appropriate. Use an actual list of supported locales with a well-defined matching policy; `Locale.LanguageRange` with `Locale.lookup`/`Locale.filter` can be used when negotiating BCP 47 language tags and HTTP `Accept-Language`.

A reliable support list should answer:

1. **Messages:** are all keys translated, reviewed, and backed by transparent fallback?
2. **Numbers/dates/times:** which provider data is used, and for which locales and runtime versions is formatting tested?
3. **Sorting, searching, and word segmentation:** does the feature genuinely require language-specific rules, and has it been tested?
4. **Currency, time zone, measurement units:** which parts are hinted by locale, and which must be explicit choices or business data?
5. **UI:** have long strings, Vietnamese diacritics, right-to-left scripts where applicable, fonts, screen readers, and error messages been tested?

| Status | What can actually be asserted |
| --- | --- |
| `Locale.forLanguageTag(tag)` returns an object | Java can represent/parse the identifier within that API's capabilities |
| `SomeService.getAvailableLocales()` contains the locale | That service advertises the locale in the current runtime |
| A formatting call throws no error | Output was produced; fallback may have been used |
| `ResourceBundle.getBundle` returns a bundle | A bundle was found by resolution rules; not necessarily the requested locale |
| Translation and formatting QA for the locale passes | The feature has been verified within the specific test scope |
| The application advertises support for the locale | Should be a commitment backed by checks and documented limits |

## 7. How to test so fallback does not mask bugs

For each locale the application plans to support, check the following test groups:

- **Correct translations:** critical keys appear in the expected language; they do not fall back to the root bundle outside allowed policy. Inspect `bundle.getLocale()` when needed to detect whole-bundle fallback; for individual missing keys, test content/value coverage directly.
- **Untranslated keys:** the system displays controlled fallback content or flags missing translations during testing/build; never expose raw key names or unintended mixed-language messages.
- **Locale formatting:** verify number, date, percentage/currency patterns, and month/weekday names on the chosen JDK/locale provider. Avoid pinning exact snapshots across all JDKs if CLDR data may be updated.
- **Boundary values:** negative numbers, very large numbers, decimals, year transitions, dates/times near DST/timezone shifts, languages with diacritics or different scripts.
- **Independent services:** successful number formatting does not replace testing `Collator` and `BreakIterator` if the application uses them.
- **Unsupported locales:** request `zz-ZZ` or a valid tag outside the product list; verify the application selects the expected fallback and does not falsely indicate that the locale is fully supported.
- **Environment:** pin or record JDK version, locale provider configuration, timezone, resource set, and dependencies. Data across JDK/CLDR versions can change.

### Common pitfalls

| Mistake | Why is it wrong? | Correct practice |
| --- | --- | --- |
| "Creating `Locale` without error means this language is supported" | `Locale` only stores an identifier | Verify each service's capability and product coverage |
| "Being in `Locale.getAvailableLocales()` means translations exist" | Runtime data is separate from application resources | Verify bundles, translation keys, and QA |
| "`format()` outputs text so the locale is right" | Output may come from fallback | Test actual results and providers |
| "Having `messages_fr.properties` means every service supports `fr-FR`" | Bundles only resolve messages | Test numbers, dates, text, and business rules separately |
| "Every API returns the same list of locales" | Each API/provider has a different scope | Call `getAvailableLocales()` on the specific API |
| "`Locale` also determines time zone/currency unit" | Those are separate facts | Manage `ZoneId`, currency codes, and business data independently |
| "Fallback throws no error so no testing is needed" | Fallback can hide missing translations | Test the actual locales used and define fallback clearly |

## 8. Key takeaways

- **Being able to create a `Locale` only proves you have a request descriptor object.** It does not add data, translate text, or prove every Java service supports that locale.
- **Support belongs to each API/provider and each part of the product.** `NumberFormat`, `DateFormat`, `Collator`, `BreakIterator`, and `ResourceBundle` have distinct scopes.
- **Fallback can make calls succeed despite lacking direct support.** To know which translation is actually in use, observe the resolved locale/resource and test the content.
- **The application must define its own supported locale list, selection/fallback policy, and test suite.** Do not infer a product commitment from `Locale.forLanguageTag` accepting a tag.
