# Application-Supported Locales List

A multilingual application must clearly declare **the locales that the application itself supports**. This list differs from the list of locales that Java/JDK can handle. For example, the JDK can format numbers for `fr-FR`, but if the product has not translated its screens and messages into French, `fr-FR` should not automatically be added to the application's language selector.

In the context of **locale selection**, “supported” is a **product commitment**: the application knows how to serve users in the corresponding language, display conventions, and resources at a defined level. `java.util.Locale` only describes a language/region; that object does not by itself prove the completeness of the application.

## 1. Three Concepts to Distinguish

| Concept | Meaning | Who Decides? |
| --- | --- | --- |
| Representable locale | A valid language/region code described by `Locale`, such as `vi-VN`, `en-US`, or `zh-Hant-TW` | Language tag syntax and the `Locale` API |
| Locale with JDK/provider data | A locale that has formatting data for services supported by the runtime; for example, numbers, dates, month names, or symbols | The JDK, locale service providers, and CLDR/other data |
| **Application-supported locale** | The set of locales the product has chosen to release, with appropriate selection/fallback rules, translations, and testing | **The application/development team itself** |

For example: a website that only releases Vietnamese and US English interfaces can declare `vi-VN` and `en-US` as its two supported locales, even though `Locale.getAvailableLocales()` returns many other locales. The fact that the runtime knows how to format French dates **does not create translations** for “Sign in”, error messages, or emails in French for the website.

A product can clearly define different levels of support, such as full UI and formatting support, or formatting-only support. When referring to the “supported locales list” for a language selector, choose a **consistent contract**, avoiding listing locales that only have partial features without informing the user.

## 2. `Locale.getAvailableLocales()` Is Not the Application's Selection List

Java provides:

~~~java
Locale[] runtimeLocales = Locale.getAvailableLocales();
~~~

This method returns the locales for which the runtime environment has data for **Java's locale-sensitive services**. The result depends on the JDK version and locale provider configuration; it is not the application's catalog of “translated languages”.

Specialized APIs, such as `NumberFormat.getAvailableLocales()` or `DateFormat.getAvailableLocales()`, indicate the scope of locales supported by those services. They also **do not prove** that every screen or business content of the application has translations.

Avoid building a menu like this:

~~~java
// Do NOT use as the sole source for a product's language menu.
Locale[] choices = Locale.getAvailableLocales();
~~~

If you do that, users could select a locale where number formatting works, yet the UI falls back to the default language because no translations exist. The list can also change when upgrading the runtime, even though the product's support commitment has not changed.

**Principle:** the runtime may support **more** than the application; the application must also control the locales it publishes itself, even when some formatting is handled by libraries other than the JDK.

## 3. Declaring an Explicit Support List

For a small system, supported locales can be configured directly in code or read from deployment configuration. Use **BCP 47 language tags** as stable identifiers, such as `vi-VN`, `en-US`, and `en-GB`. Do not use display names like “English” or “Tiếng Việt” as keys: display names can be translated or vary by locale.

Create the file `SupportedLocalesDemo.java`:

~~~java
import java.util.List;
import java.util.Locale;
import java.util.Set;

public class SupportedLocalesDemo {
    private static final Locale DEFAULT_LOCALE =
            Locale.forLanguageTag("vi-VN");

    private static final List<Locale> SUPPORTED_LOCALES = List.of(
            Locale.forLanguageTag("vi-VN"),
            Locale.forLanguageTag("en-US"),
            Locale.forLanguageTag("en-GB")
    );

    private static final Set<Locale> SUPPORTED_LOOKUP =
            Set.copyOf(SUPPORTED_LOCALES);

    public static void main(String[] args) {
        System.out.println("Supported locales:");
        for (Locale locale : SUPPORTED_LOCALES) {
            System.out.println("- " + locale.toLanguageTag());
        }

        System.out.println("Default: " + DEFAULT_LOCALE.toLanguageTag());
        System.out.println("fr-FR supported: " +
                SUPPORTED_LOOKUP.contains(Locale.forLanguageTag("fr-FR")));
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac SupportedLocalesDemo.java
java SupportedLocalesDemo
~~~

Exact output:

~~~text
Supported locales:
- vi-VN
- en-US
- en-GB
Default: vi-VN
fr-FR supported: false
~~~

Here, `List` preserves **display order** in the menu, while `Set` supports membership lookup. Do not iterate over `Set.copyOf(...)` expecting a stable order; the iteration order of this set is not guaranteed. `DEFAULT_LOCALE` must be in the supported list, and that can be verified at application startup.

The list can live in configuration instead of source code, for example:

~~~yaml
# Application configuration example; not automatic JDK configuration syntax.
localization:
  default-locale: vi-VN
  supported-locales:
    - vi-VN
    - en-US
    - en-GB
~~~

The application must read, validate, and convert these strings into `Locale` instances itself. Java does not automatically detect the product's supported list merely from a `supported-locales` key in YAML. At deployment, you should verify there are no duplicate locales after normalization, that every locale has the required data, and that the default locale is part of the supported set.

### Why Use Both `List` and `Set`?

- `List<Locale>`: used when a specific order is needed (for example, Vietnamese first, US English second).
- `Set<Locale>`: used when checking whether an exact choice belongs to the list.
- `Map<String, Locale>`: useful if data comes from language tags in configuration/APIs; keys can use the normalized form from `toLanguageTag()`.

If a menu needs display names, you can use `locale.getDisplayName(displayLocale)`, though this is a name provided by runtime data. To achieve a consistent product tone, the application can still declare editorially curated labels like “Tiếng Việt” or “English (US)”. Do not use labels as identifiers or replacements for language tags.

## 4. Validating a User-Selected Locale

Applications often receive a locale from user profiles, URLs, cookies, queries, or UI selectors. You should not blindly treat every received string as “supported”.

Two concerns must be separated:

1. **Syntax:** is the input a well-formed language tag?
2. **Policy:** is that valid locale in the list published by the application?

`Locale.forLanguageTag(...)` handles some malformed inputs leniently: it may ignore invalid parts instead of always throwing an error. When strict validation is needed, use `Locale.Builder.setLanguageTag(...)` and catch `IllformedLocaleException`.

Create `LocaleSelectionDemo.java`:

~~~java
import java.util.IllformedLocaleException;
import java.util.List;
import java.util.Locale;

public class LocaleSelectionDemo {
    private static final Locale DEFAULT_LOCALE =
            Locale.forLanguageTag("vi-VN");

    private static final List<Locale> SUPPORTED = List.of(
            DEFAULT_LOCALE,
            Locale.forLanguageTag("en-US"),
            Locale.forLanguageTag("en-GB")
    );

    static Locale selectExact(String languageTag) {
        if (languageTag == null || languageTag.isBlank()) {
            return DEFAULT_LOCALE;
        }

        try {
            Locale candidate = new Locale.Builder()
                    .setLanguageTag(languageTag.trim())
                    .build();

            return SUPPORTED.contains(candidate)
                    ? candidate
                    : DEFAULT_LOCALE;
        } catch (IllformedLocaleException e) {
            return DEFAULT_LOCALE;
        }
    }

    public static void main(String[] args) {
        System.out.println(selectExact("en-US").toLanguageTag());
        System.out.println(selectExact("fr-FR").toLanguageTag());
        System.out.println(selectExact("en_US").toLanguageTag());
    }
}
~~~

~~~bash
javac LocaleSelectionDemo.java
java LocaleSelectionDemo
~~~

Exact output:

~~~text
en-US
vi-VN
vi-VN
~~~

- `en-US` is valid and declared supported, so it is kept as is.
- `fr-FR` is a representable locale but not yet supported by the product; the example policy chooses `vi-VN`.
- `en_US` uses an underscore that does not match the BCP 47 format accepted by the example; the builder reports an error and the application falls back.

This is an **exact match policy**. It is suitable for explicit selections from a menu. It does not perform advanced language negotiation and does not automatically treat `en`, `en-US`, and `en-GB` as equivalent choices.

For an API to clearly distinguish “invalid input” from “valid but unsupported locale”, a real-world application can return a result type with status or a dedicated validation error, rather than always falling back silently. This choice depends on the API contract and user experience.

## 5. Tag Normalization, Region, Script, and Extensions

`Locale` includes language, region, script, variant, and Unicode extensions. A few examples:

| Tag | Meaning |
| --- | --- |
| `en` | English, no region specified |
| `en-US` | English in a US context |
| `en-GB` | English in a UK context |
| `zh-Hans-CN` | Chinese, Simplified script, China region |
| `zh-Hant-TW` | Chinese, Traditional script, Taiwan region |
| `sr-Latn-RS` | Serbian, Latin script, Serbia region |
| `en-US-u-nu-arab` | English/US with an extension requesting the Arabic-Indic numbering system |

**Avoid two extremes:** requiring every request to match the configured tag identically in all cases, or automatically merging all tags with the same language. For an application that needs to distinguish `zh-Hans` and `zh-Hant`, dropping the script can select the wrong writing system. For English, users may expect different date patterns between `en-GB` and `en-US`.

`Locale.equals(...)` compares all relevant components, including extensions. Therefore, `en-US-u-nu-arab` is not necessarily equal to `en-US` in a `Set<Locale>`. If the product wants to allow “UI language en-US with a different numbering system”, separate the **supported content locale** from **formatting preferences**, validate permitted extensions, and configure the formatter separately. Do not blindly strip all extensions or claim to support all preferences.

Store tags in the canonical form produced by `toLanguageTag()`; use `Locale.Builder` to validate input syntax when strict checks are required. If you need to restrict to the exact published list, compare against the normalized set of tags/`Locale` objects, not directly against display names.

## 6. Selecting a Locale from HTTP `Accept-Language`

Browsers can send a header such as:

~~~http
Accept-Language: fr-CA, en-GB;q=0.9, en-US;q=0.8
~~~

This is a **priority list** with quality weights `q` (defaulting to `1.0`), not a single locale. Java provides `Locale.LanguageRange.parse(...)` and `Locale.lookup(...)` based on the RFC 4647 language range/lookup mechanism to select a matching candidate from the supported set.

Create `LocaleNegotiationDemo.java`:

~~~java
import java.util.List;
import java.util.Locale;

public class LocaleNegotiationDemo {
    private static final Locale DEFAULT_LOCALE =
            Locale.forLanguageTag("vi-VN");

    private static final List<Locale> SUPPORTED = List.of(
            DEFAULT_LOCALE,
            Locale.forLanguageTag("en-US"),
            Locale.forLanguageTag("en-GB")
    );

    static Locale negotiate(String header) {
        if (header == null || header.isBlank()) {
            return DEFAULT_LOCALE;
        }

        try {
            List<Locale.LanguageRange> preferences =
                    Locale.LanguageRange.parse(header);

            Locale match = Locale.lookup(preferences, SUPPORTED);
            return match != null ? match : DEFAULT_LOCALE;
        } catch (IllegalArgumentException e) {
            return DEFAULT_LOCALE;
        }
    }

    public static void main(String[] args) {
        System.out.println(negotiate(
                "fr-CA, en-GB;q=0.9, en-US;q=0.8").toLanguageTag());
        System.out.println(negotiate(
                "fr-CA, fr;q=0.9").toLanguageTag());
    }
}
~~~

~~~bash
javac LocaleNegotiationDemo.java
java LocaleNegotiationDemo
~~~

Exact output:

~~~text
en-GB
vi-VN
~~~

In the first request, `fr-CA` has the highest priority but is not in the supported set; `en-GB` is the next matching choice. In the second request there is no matching candidate, so `Locale.lookup(...)` returns `null` and the application applies `DEFAULT_LOCALE`.

### `lookup` Does Not Pick Any Arbitrary “Closest” Locale

The lookup mechanism searches by language range and the RFC 4647 language range truncation rules. Do not assume that when only `en-GB` is supported, a request for `en-US` will definitely be switched to `en-GB` automatically. If the product wants explicit fallback within the same language, you must design a specific policy and write tests for it.

Java also has `Locale.filter(...)` to retrieve **multiple** locales matching language ranges. When an application needs **one** locale for a request, `lookup` is usually closer to the goal. The difference between filtering a list and picking a single item is a product decision, not two different names for the same operation.

Headers are client-supplied data; production systems should limit length, entry count, and handle malformed cases. The sample snippet focuses on demonstrating the lookup API and does not implement those input limits or resource-protection policies.

## 7. Application Priority Order and Fallback Policy

A practical selection policy can be described as follows:

1. **Current explicit choice** from the user, if valid and in the supported set.
2. **Language saved in the profile**, if the user is logged in and it is still supported.
3. **Negotiation from `Accept-Language`** when no explicit choice exists.
4. **Declared application default locale**, such as `vi-VN`.

This order is only an example: an application may choose a different order depending on the product contract, but it must be consistent. Do not use the JVM's `Locale.getDefault()` as the language choice for all visitors on a shared server; the JVM default reflects the runtime environment and can change, and does not necessarily reflect each user's preference.

A suitable logic diagram:

~~~text
Request / user configuration
    |
    +-- Valid, supported explicit choice? -----------> Use that choice
    |
    +-- Supported saved choice? ---------------------> Use saved choice
    |
    +-- Accept-Language has a matching candidate? ---> Use looked-up locale
    |
    +-- No ------------------------------------------> Product default locale
    |
    v
Use the selected locale to fetch translations and format output
~~~

**Do not conflate** the application's fallback with the internal fallback of `ResourceBundle` or a formatter's locale provider. Without control, a screen could display translations in one language while formatting dates in another locale. Decide the effective locale in a clear policy layer and pass it through the relevant components.

For example, do you need a special fallback `fr-CA → fr-FR` if Canadian translations are missing? Declare an intentional rule and evaluate its impact on language, dates, and currency. You should not infer from the prefix `fr` that all regional conventions of France are appropriate for Canada. A separate **UI locale** for translation language and a separate **formatting locale** based on user region/preferences can be used when the product needs to distinguish them.

## 8. Supported List and `ResourceBundle`: Verifying Translations

If a product publishes `vi-VN`, `en-US`, and `en-GB`, bundles might be organized like this:

~~~text
src/main/resources/
  Messages.properties
  Messages_vi.properties
  Messages_en.properties
  Messages_en_GB.properties
~~~

These bundle names are an **example of resource organization**, and do not mean every tag combination requires an exact matching file. `ResourceBundle` searches for candidates based on the locale and has a fallback mechanism. For instance, a request for `en-GB` can retrieve keys from `Messages_en_GB.properties`, from `Messages_en.properties`, or from the base bundle if there is no region-specific translation.

This is convenient for reusing translations, but it can also **hide omissions**. If `Messages_en_GB.properties` has few keys, the application can still return strings from a higher-level bundle. If the product requires all British English content to be reviewed, `ResourceBundle.getBundle(...)` returning successfully is not enough to prove quality.

When verifying release readiness for each locale, there should be clear criteria:

- UI messages, errors, forms, emails, and critical flows have approved translations or fallbacks.
- Message keys, placeholders (such as `{0}`), and plural/gender expressions if any are verified against the i18n mechanism in use.
- Formatting of dates, numbers, currency, proper names, and business content renders appropriately for the user's context.
- The UI accommodates varying string lengths; layout testing is performed when the language changes.
- The language selector and URLs/routes store the selection using stable tags.
- If a translation is not ready, that locale is not advertised as fully supported.

**Note:** `Locale`, `ResourceBundle`, and `NumberFormat` address different needs. Having UI translations does not mean every currency or business phrasing is automatically handled; conversely, having locale-based number formatting does not mean UI translations exist.

## 9. Maintaining the Supported List in Production Systems

### Configuration Data and API Interfaces

If both frontend and backend participate in locale selection, there should be a single clear source of product configuration: for example, an endpoint publishing the supported locales list, default locale, display labels, and support status. It can be represented as data:

~~~json
{
  "defaultLocale": "vi-VN",
  "supportedLocales": [
    {"tag": "vi-VN", "label": "Tiếng Việt"},
    {"tag": "en-US", "label": "English (US)"},
    {"tag": "en-GB", "label": "English (UK)"}
  ]
}
~~~

This is an **API design example**, not a built-in JDK return format. If using a list from configuration, both backend and frontend should apply the same effective-locale policy to avoid the UI selecting one value while the server uses another.

For web applications that cache translations or HTML output, the effective locale usually must be part of the cache key; if a public cache varies content by `Accept-Language`, consider the `Vary: Accept-Language` header according to the service's HTTP design. User language choices via cookies/profiles may require a separate caching strategy to avoid serving the wrong content between users.

### Testing the List and Selection

A minimal test matrix for the example supporting `vi-VN`, `en-US`, and `en-GB`:

| Scenario | Expected Result |
| --- | --- |
| Exact selection `en-US` | Keep `en-US` |
| Exact selection `en-GB` | Keep `en-GB` |
| Select `fr-FR` when unsupported | Fallback or validation error per contract, never silently claim as supported |
| Malformed tag `en_US` | Handle as invalid input |
| No selection and no header | Use default `vi-VN` |
| Header `fr-CA, en-GB;q=0.9` | With the example set, lookup selects `en-GB` |
| Header contains only unsupported languages | Apply fallback policy |
| Change JDK version | Product list does not automatically expand with the runtime |
| Resources for a locale are missing keys | Tests detect it or apply approved fallback |

You can add tests to ensure locales are not duplicated after normalization, the default locale is always in the supported list, all tags are valid BCP 47, and key pages have appropriate translations.

### Changing the List Over Time

When adding a new locale, release translations and run tests before enabling the option in the UI; when removing a locale, handle user profiles that previously saved that tag. Choose an intentional fallback and explain it in the UX if needed, instead of letting the application randomly display translations based on the JVM default.

If a language is supported at a limited level (beta, single region, read-only pages), clearly represent the published scope so the supported list does not promise beyond actual capability.

## 10. Common Pitfalls

1. **Putting all of `Locale.getAvailableLocales()` into a menu.** Runtime data does not prove the application has corresponding translations and testing.
2. **Counting bundles and treating that as the number of supported locales.** A language-level bundle can serve multiple region tags; some bundles may only be partially translated.
3. **Comparing input strings directly with display names.** The name “English (United States)” can change depending on the display language; use canonical language tags.
4. **Assuming `en` and `en-US` are always equal.** They differ in specificity; only merge them when the support policy permits.
5. **Dropping the script when matching locales.** This can select the wrong writing system, especially for languages with multiple scripts.
6. **Treating `Locale.lookup(...)` as an algorithm that converts every language to the closest same-language locale.** It follows language range/lookup rules, and can return `null`.
7. **Calling `Locale.setDefault(...)` per request.** That is shared default state within the JVM, unsuitable for controlling individual languages across multiple concurrent users.
8. **Assuming fallback translations are complete.** The base bundle may prevent errors while mixing languages; a quality policy and testing are required.
9. **Treating `Accept-Language` as stronger than an explicit choice.** The header may just be a default browser setting and not reflect the user's latest choice.
10. **Frontend/backend mismatch.** The user sees one locale in the menu, but API responses or error messages use a different locale.

## 11. Step-by-Step Application in a Java Project

When building a language selection feature, you can follow this process:

1. **Define product support scope**: UI language, formatting, email notifications, help content, and required flows.
2. **Declare an ordered list and default locale**: use BCP 47 language tags; do not generate directly from JDK available locales.
3. **Validate configuration at startup**: valid tags, no duplicates, default locale present in the list, and essential resources ready.
4. **Build a testable locale selection function**: prioritize explicit and profile choices, use header negotiation when needed, and fall back clearly.
5. **Pass the effective locale to the presentation layer**: formatters receive the specific locale; message translations come from the i18n source; time zones and currencies are handled per separate requirements.
6. **Test at release and upon JDK upgrades**: pay attention to separators, Unicode whitespace, date patterns, missing translations, and UI/API consistency.

**Self-check:**

- Why shouldn't an application that only has Vietnamese and English put every locale from `Locale.getAvailableLocales()` into its menu? — Because the runtime's formatting capability does not prove the application supports that UI language.
- When a user selects `fr-FR` but the list only contains `vi-VN` and `en-US`, what should the application do? — Apply a clear policy: report unsupported or choose a published fallback.
- What does `Locale.lookup(...)` returning `null` indicate? — No candidate was found in the list matching the language ranges; the application must decide the next step.
- Why does `ResourceBundle.getBundle(...)` succeeding still not prove translations are complete? — Because fallback can fetch keys from a parent or base bundle.
- Why should you maintain a dedicated supported locales set instead of relying on the JDK version? — So the product commitment, menu, and tests do not fluctuate unexpectedly when the runtime changes.

**Remember:** **The application's supported locales list is an intentional product decision.** Use `Locale` to represent tags, use the declared list to validate choices, use lookup when language negotiation is needed, and verify that translations/formatting truly meet the promised scope of support.
