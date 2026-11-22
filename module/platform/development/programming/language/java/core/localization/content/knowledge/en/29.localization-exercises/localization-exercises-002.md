# Choosing a Locale from a Priority List and Supported Locales in Java

## 1. Practical Problem: The User Wants French, the Server Has Vietnamese, German, and English

A multilingual Java application may ship multiple translation bundles, yet **it does not support every locale in the world**. Meanwhile, a browser or user account typically sends **multiple languages in priority order**, rather than a single language.

For example, an HTTP request carries the header:

```http
Accept-Language: fr-CA,fr;q=0.9,de-DE;q=0.8,en-US;q=0.6
```

This expresses that the user prefers:

1. `fr-CA` — Canadian French, with default weight `q=1.0`.
2. `fr` — French in general, `q=0.9`.
3. `de-DE` — German in Germany, `q=0.8`.
4. `en-US` — US English, `q=0.6`.

If the product actually has translations only for `vi-VN`, `de-DE`, and `en-US`, which locale should be chosen? **`de-DE`**, because it is the highest-ranked entry in the priority list that can be satisfied under the chosen matching policy.

However, if the system has `fr-FR` but **not** `fr-CA`, the problem becomes subtler: should French in France be considered an acceptable substitute for `fr-CA`? Standard RFC 4647 **lookup** rules do not automatically pick an arbitrary "same-language locale"; **filtering** and product fallback policies can yield different behavior.

In Java 17, the core APIs are:

- `Locale.LanguageRange.parse(headerValue)`: parses a list of **language ranges** with weights.
- `Locale.lookup(priorityList, supportedLocales)`: finds **one** best-matching locale using RFC 4647 lookup.
- `Locale.filter(priorityList, supportedLocales)`: retrieves a list of matching locales using filtering.
- `Locale.lookupTag(...)` / `Locale.filterTags(...)`: variants that operate on BCP 47 `String` tags.
- `Locale.forLanguageTag("vi-VN")`: creates a `Locale` from a BCP 47 tag.
- `ResourceBundle.getBundle(baseName, locale)`: loads translations **after deciding the locale**, using its own bundle-selection/fallback mechanism.

**Goal:** select a locale **from the set the product truly supports**, respecting the user's priority order and defined fallback policy; do not confuse "a locale for which Java has formatting data" with "a locale the application has translations for", and do not use the JVM default locale to decide on the user's behalf.

## 2. Distinguishing Four Concepts

| Concept | Example | Who Decides? |
| --- | --- | --- |
| **User language preferences** | `fr-CA,fr;q=0.9,en-US;q=0.5` | User/browser/header |
| **Language range** | `fr-CA`, `fr`, `en-US`, `*` | Matching request expression per RFC 4647 |
| **Supported locales** | `vi-VN`, `en-US`, `de-DE` | Product/deployment with translations and QA |
| **Application default/fallback** | `en-US` or `vi-VN` | Explicit product policy |

A `LanguageRange` is a **preference pattern**; it is not necessarily a `Locale` object populated with full language, script, and region attributes. `"fr"` is a range asking simply for French, whereas `"fr-CA"` also specifies Canada; `"*"` is a wildcard.

A `Locale` such as `Locale.forLanguageTag("fr-FR")`, by contrast, is a concrete choice usable for formatting and language selection.

The **supported list** must reflect the actual product—for instance, the `messages` sets that have genuinely been translated and tested:

```text
SUPPORTED = [vi-VN, en-US, de-DE, fr-FR]
DEFAULT   = en-US
```

**Do not use `Locale.getAvailableLocales()` as your list of supported translations.** That API describes the Java runtime's locale data (numbers, dates, region names, etc.), and makes no guarantee that the product has `messages_vi.properties`, `messages_fr.properties`, or complete UI translations.

### Locale Is Distinct from Time Zone, Currency, and UI Direction

Selecting `fr-FR` does not automatically convert USD amounts into EUR; selecting `ja-JP` does not mandate using the Japanese imperial calendar. Time zones are chosen via `ZoneId`, calendar systems via `Chronology`, and currencies via `Currency`/business contracts. A `Locale` is primarily a **language and formatting context**.

## 3. Structure of a BCP 47 Language Tag

A language tag can express:

```text
language  - script - region - variants - extensions
zh        - Hant   - TW
sr        - Latn   - RS
pt                 - BR
en                 - US
```

| Part | Examples | Meaning |
| --- | --- | --- |
| Language | `vi`, `en`, `de`, `tr` | Language |
| Script | `Hans`, `Hant`, `Latn`, `Cyrl` | Writing script |
| Region | `VN`, `US`, `BR` | Region |
| Variant | A registered subtag | Specific dialect/variant |
| Unicode extension | `u-ca-buddhist`, `u-nu-latn` | Calendar/numbering preferences when supported by APIs |

`zh-Hant-TW` (Traditional Chinese in Taiwan) differs from `zh-Hans-CN` (Simplified Chinese in China). Therefore, **do not compare only the first two letters of a language tag** and assume one translation can substitute for another.

Java's `Locale.forLanguageTag` understands BCP 47 syntax, yet **does not verify that every tag corresponds to a locale with product resources**. A syntactically valid tag may still lack a translation bundle. If input requires strict syntax validation, you can use `new Locale.Builder().setLanguageTag(tag).build()` and catch `IllformedLocaleException`; even then, valid syntax does not prove the tag is registered, translated, or QA-approved.

### Do Not Use toString() as a Protocol Language Tag

`Locale.toString()` uses legacy formatting such as `en_US`, whereas BCP 47 uses `en-US`. For HTTP headers and API profile exchange, store `locale.toLanguageTag()` and parse with `Locale.forLanguageTag(...)`.

## 4. The Accept-Language Header and q-Weights

In HTTP, `Accept-Language` is a prioritized list of choices. For example:

```http
Accept-Language: de-DE,de;q=0.9,en-US;q=0.6,en;q=0.4
```

- Missing `q` → default weight of 1.0.
- `q=0.9` → lower priority than an entry with `q=1.0`.
- `q=0` in HTTP means **not acceptable** for that range.
- `*` means accepting an unspecified language tag according to appropriate matching rules.
- Order/weight need not match left-to-right order: the application must parse and match using the actual priority list.

Java provides:

```java
List<Locale.LanguageRange> priorities =
        Locale.LanguageRange.parse(
                "de-DE,de;q=0.9,en-US;q=0.6,en;q=0.4");
```

This snippet resides inside a method with `import java.util.*;`.

`LanguageRange.parse`:

- Accepts a comma-separated list with `;q=...` weights.
- Sorts the resulting list in descending order of priority/weight.
- May add **equivalent** language ranges from the registry (such as legacy and modern language codes), so the returned list size may differ from the number of ranges written by the client.
- Deduplicates repeated occurrences of the same range according to API rules.
- Validates syntax, **without validating translation content or whether every code exists in the registry**.
- May throw `IllegalArgumentException` when a language range or weight is invalid.

**Do not parse `Accept-Language` manually with `split(",")` and pick the first item** if the product intends to honor `q`, aliases, and matching rules. Likewise, do not pass the entire multi-range header directly to `Locale.forLanguageTag(header)`; that API does not parse priority lists.

### 4.1. q=0 and HTTP Acceptability

HTTP RFCs define `q=0` as an unacceptable language. However, `Locale.LanguageRange.parse` and `Locale.lookup/filter` are **RFC 4647 matching APIs**, not a complete HTTP content negotiation engine.

If a header contains `en;q=0, *;q=0.5`, you must explicitly decide how to **exclude rejected languages** when a wildcard could match multiple entries. Do not simply drop `q=0` ranges and let `*` re-select the very language that was forbidden. Full HTTP negotiation must apply appropriate product or framework acceptability/exclusion rules. Do not claim `Locale.lookup` enforces all `q=0` rules of RFC 9110 on its own.

In academic Java examples, positive `q` values are used to illustrate deterministic results; the production design sections explain how to guard against unusual headers.

## 5. Two RFC 4647 Mechanisms: Lookup and Filtering

### 5.1. Lookup — Finding the Single Closest Locale by Priority Order

`Locale.lookup(...)` returns **one `Locale` or `null`**:

```java
Locale chosen = Locale.lookup(priorities, supported);
```

The RFC 4647 **progressive truncation** algorithm works as follows: for a range such as `zh-Hant-TW`, it tries `zh-Hant-TW`, then `zh-Hant`, then `zh`; if none matches, it moves to the next range in priority order. This **does not mean** it selects any tag sharing the same language prefix.

Important example:

```text
User priority: en-GB
Supported:     en-US

Locale.lookup(...) → null
```

Because `en-GB` is tried specifically and then truncated to `en`, while the supported list contains only `en-US` and **not the tag `en`**. Lookup does not silently convert `en-GB` into `en-US` via an implicit "nearest region."

Similarly, given priorities `fr-CA,fr;q=0.9,en-US;q=0.6` and supported locales `fr-FR`, `en-US`, lookup can choose **en-US** because the `fr` range during lookup does not exactly match the tag `fr-FR`. This is not a Java bug; it is **a specific matching algorithm**.

In particular, the wildcard `*` is **ignored in lookup**. If the priority list contains only `*`, lookup can return `null` even when `supported` is non-empty. The caller must define an explicit default/fallback.

### 5.2. Filtering — Retrieving Locales Covered by Ranges

`Locale.filter(...)` returns a list:

```java
List<Locale> matches = Locale.filter(
        priorities, supported);
```

Unlike lookup, a language range **`fr`** during filtering can match `fr-FR`, `fr-CA`, and various `fr-...` variants. `Locale.filter` returns matching locales in priority order with duplicates removed.

Why do both APIs exist?

| Need | Suggested API | Result |
| --- | --- | --- |
| Pick a single locale via RFC 4647 lookup | `Locale.lookup` | `Locale` or `null` |
| Get a list of locales matching each language range | `Locale.filter` | `List<Locale>` |
| Populate a dropdown suggesting suitable languages | `Locale.filter` | Multiple choices |
| Return BCP 47 tags instead of `Locale` objects | `lookupTag` / `filterTags` | `String` or list of strings |
| Pick a business fallback close to the requested language | App policy using lookup/filter output and explicit mapping | A locale in the allowed set |

**Never call `filter(...).get(0)` when the list might be empty.** Check `isEmpty()` and maintain a fallback inside `supportedLocales`.

### 5.3. Clear Comparison Table

| Header/Preference | Supported | `lookup` | `filter` |
| --- | --- | --- | --- |
| `de-DE,de;q=0.9` | `de-DE, en-US` | `de-DE` | Includes `de-DE` |
| `en-GB` | `en-US` | `null` | Excludes `en-US` if only range `en-GB` |
| `en` | `en-US` | `null` | Includes `en-US` |
| `fr-CA,fr;q=0.9,en-US;q=0.7` | `fr-FR, en-US` | `en-US` | `fr-FR` then `en-US` |
| `*` | `de-DE, en-US` | `null` | May select from all supported under filtering |

This table uses simple cases to highlight differences. If a language involves aliases, extended wildcards, or custom provider data, test the exact list with the real API on your target JDK.

## 6. Standalone Java 17 Example: Comparing Lookup and Filter

Create the file `LookupVsFilterDemo.java`:

```java
import java.util.List;
import java.util.Locale;
import java.util.stream.Collectors;

public class LookupVsFilterDemo {

    static String tags(List<Locale> locales) {
        return locales.stream()
                .map(Locale::toLanguageTag)
                .collect(Collectors.joining(", "));
    }

    static void inspect(String preference, List<Locale> supported) {
        List<Locale.LanguageRange> ranges =
                Locale.LanguageRange.parse(preference);

        Locale match = Locale.lookup(ranges, supported);
        List<Locale> matches = Locale.filter(ranges, supported);

        System.out.println("preference=" + preference);
        System.out.println("lookup=" +
                (match == null ? "null" : match.toLanguageTag()));
        System.out.println("filter=" + tags(matches));
    }

    public static void main(String[] args) {
        List<Locale> supported = List.of(
                Locale.forLanguageTag("fr-FR"),
                Locale.forLanguageTag("en-US"));

        inspect("fr-CA,fr;q=0.9,en-US;q=0.7", supported);
        inspect("en", supported);
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 LookupVsFilterDemo.java
java LookupVsFilterDemo
```

Deterministic stdout on Java 17 for the language ranges above:

```text
preference=fr-CA,fr;q=0.9,en-US;q=0.7
lookup=en-US
filter=fr-FR, en-US
preference=en
lookup=null
filter=en-US
```

**Explanation:**

- `fr-CA` is not in `supported`; the range `fr` lets **filtering** find `fr-FR`, whereas **lookup** requires an exact `fr` tag after truncation.
- The `en-US` range appears later in the priority list, and lookup selects `en-US` because that specific tag is supported.
- The `en` range alone does not cause lookup to select `en-US`, whereas filtering returns `en-US`.

Do not decide which API is "more correct" merely because one result feels more intuitive. Both mechanisms are correct under **two different criteria**; product architecture must explicitly define how "same language, different region" should be handled.

## 7. Defining a Locale Selection Policy in Your Product

Before writing code, a product typically needs to answer:

1. **Which locales are actually translated and supported?** From the release catalog, not `Locale.getAvailableLocales()`.
2. **What is the default locale?** It must belong to the supported set.
3. **Which source takes higher precedence?** Manual language selection in UI? Account settings? URL `/vi/`? Browser header?
4. **Is cross-region fallback within the same language allowed?** E.g., `pt-AO → pt-PT` or `pt-BR`, which must be approved by product/linguists.
5. **Are script variants supported?** `zh-Hant` and `zh-Hans` cannot be swapped arbitrarily.
6. **What happens when nothing matches?** Published default, language prompt, or rejecting negotiation if required by an API contract.
7. **Should `q=0` and `*` be honored per HTTP semantics?** If so, use an RFC-compliant negotiator library/framework or implement and thoroughly test exclusion logic.
8. **Are header length and language-range count bounded?** Client headers are untrusted input.
9. **Does caching depend on the selected locale?** Prevent serving the wrong translation to another user.

### 7.1. Reference Precedence Order

A commonly sensible policy (though product-specific) is:

```text
Explicit user language selection in UI
          ↓ if not present
Account language setting
          ↓ if not present
Language info in URL/route when available
          ↓ if not present
Browser Accept-Language header
          ↓ if no match
Product-supported DEFAULT_LOCALE
```

In other products, the URL may outrank profile settings so shared links stay language-stable. What matters is that **the order is defined and tested**, not that one universal order fits every application.

Do not use IP geolocation as definitive proof of language. A Vietnamese speaker living in Germany may prefer `vi-VN`; a machine located in Vietnam may still use an `en-US` interface.

## 8. Runnable Java 17 Example: Selecting a Locale from a Supported List

At a basic level, you can combine `Locale.lookup` with an explicit product fallback.

File `LocaleNegotiatorDemo.java`:

```java
import java.util.List;
import java.util.Locale;

public class LocaleNegotiatorDemo {
    private static final Locale DEFAULT_LOCALE =
            Locale.forLanguageTag("vi-VN");

    private static final List<Locale> SUPPORTED = List.of(
            Locale.forLanguageTag("vi-VN"),
            Locale.forLanguageTag("en-US"),
            Locale.forLanguageTag("de-DE"),
            Locale.forLanguageTag("fr-FR"));

    static Locale choose(String acceptLanguage) {
        if (acceptLanguage == null || acceptLanguage.isBlank()) {
            return DEFAULT_LOCALE;
        }

        try {
            List<Locale.LanguageRange> priorities =
                    Locale.LanguageRange.parse(acceptLanguage);

            Locale matched = Locale.lookup(priorities, SUPPORTED);
            return matched != null ? matched : DEFAULT_LOCALE;
        } catch (IllegalArgumentException ex) {
            // Demo policy: fall back to default on malformed input.
            return DEFAULT_LOCALE;
        }
    }

    public static void main(String[] args) {
        String[] examples = {
                "de-DE,de;q=0.9,en-US;q=0.8",
                "fr-CA,fr;q=0.9,en-US;q=0.7",
                "en-GB",
                "vi-VN,en-US;q=0.7",
                "*",
                "es-MX,es;q=0.8"
        };

        for (String header : examples) {
            System.out.println(
                    choose(header).toLanguageTag());
        }
    }
}
```

```bash
javac -encoding UTF-8 LocaleNegotiatorDemo.java
java LocaleNegotiatorDemo
```

Stdout:

```text
de-DE
en-US
vi-VN
vi-VN
vi-VN
vi-VN
```

This is a **demo of an RFC 4647 lookup + application default policy**:

- `de-DE` matches directly.
- `fr-CA` and `fr` do not match `fr-FR` under lookup; `en-US` is the next valid range and gets selected.
- `en-GB` does not match the `en-US` tag: falls back to `vi-VN`.
- `vi-VN` matches directly.
- Wildcard `*` is ignored in lookup: falls back to `vi-VN`.
- Neither `es-MX` nor `es` is in `SUPPORTED`: falls back to `vi-VN`.

**Do not use this code as a complete production HTTP negotiator:** it lacks header size limits, `q=0`/HTTP exclusion handling, same-language fallback rules, and only catches syntax errors at the API level. That is why you must add explicit contracts and integration tests rather than copy-pasting a basic example into a gateway.

## 9. Handling "Same Language, Different Region" Intentionally

The user requests `fr-CA` and the product only has `fr-FR`. There are at least three valid policies depending on the product:

### Policy A: Strict Lookup, No Implicit Region Substitution

Use `Locale.lookup` only. If no match, try the next range, then fall back to the default. For `fr-CA,fr;q=0.9,en-US;q=0.7`, this may select `en-US` even though `fr-FR` is supported.

Pros: follows RFC 4647 lookup strictly without silently swapping one region for another.

Cons: some users may prefer `fr-FR` over `en-US`. The policy must be documented.

### Policy B: Filtering Broad Language Ranges

If the user explicitly lists `fr` in the priority list, `Locale.filter` can return `fr-FR`. A product may pick the **first element** when its contract permits "any locale of a language accepted by the user."

Example:

```java
List<Locale> filtered = Locale.filter(
        Locale.LanguageRange.parse("fr-CA,fr;q=0.9,en-US;q=0.7"),
        List.of(Locale.forLanguageTag("fr-FR"),
                Locale.forLanguageTag("en-US")));

Locale selected = filtered.isEmpty()
        ? Locale.forLanguageTag("en-US")
        : filtered.get(0);
```

This is an in-method illustration. `selected` is `fr-FR` under filtering, differing from strict lookup.

**Note:** filtered ranges may be wildcard or extended ranges. Picking the first element is valid only if the product contract permits relying on API order, the supported list has controlled ordering, and HTTP `q=0`/exclusions have already been resolved.

### Policy C: Approved Fallback Mapping

A product can maintain an explicit mapping table:

| User Preference | Allowed Fallback |
| --- | --- |
| `fr-CA` | `fr-FR` if approved by the localization team |
| `en-AU` | `en-GB` or `en-US` depending on content style |
| `pt-AO` | `pt-PT` or specific regional strategy |
| `zh-HK` | Prefer `zh-Hant`; do **not** automatically switch to `zh-Hans` |
| `sr-Latn` | Do not automatically switch to `sr-Cyrl` if Latin script resources are required |

Such a mapping is a **business policy**, not something `Locale.lookup` infers on its own. It must be versioned, reviewed linguistically, tested for non-equivalent regions, and guaranteed to stay within the supported set.

## 10. Advanced Filtering and Wildcard Language Ranges

RFC 4647 defines two kinds of language ranges:

- **Basic ranges**, e.g. `en`, `ja-JP`, `*`.
- **Extended ranges**, e.g. `zh-Hant-*`, `*-CH`.

Java provides `Locale.FilteringMode` to control filtering behavior:

| Mode | General Meaning |
| --- | --- |
| `AUTOSELECT_FILTERING` | Java automatically picks the filtering mode matching the range types |
| `EXTENDED_FILTERING` | Uses extended filtering |
| `IGNORE_EXTENDED_RANGES` | Skips extended ranges |
| `MAP_EXTENDED_RANGES` | Maps extended ranges to appropriate basic forms |
| `REJECT_EXTENDED_RANGES` | Throws an exception when extended ranges are present |

Explicit mode example:

```java
List<Locale.LanguageRange> priorities =
        Locale.LanguageRange.parse("zh-Hant-*");

List<Locale> filtered = Locale.filter(
        priorities,
        supportedLocales,
        Locale.FilteringMode.EXTENDED_FILTERING);
```

This is an in-method illustration assuming `supportedLocales` is defined and `java.util.Locale`/`java.util.List` are imported.

### When Are Extended Ranges Useful?

Suppose a product supports multiple regions for **Traditional Chinese**: `zh-Hant-TW`, `zh-Hant-HK`. A range `zh-Hant-*` expresses preference for Traditional script without specifying a particular region. Meanwhile, `zh-Hans-CN` is Simplified Chinese and should not be treated as a substitute match merely because both share `zh`.

**Be explicit:** wildcards in locale ranges and HTTP `*` can behave differently between lookup and filtering. In lookup, a standalone `*` is ignored; in filtering, wildcards can match multiple supported tags. Do not apply filter-result assumptions to lookup.

### Ordering of the Supported List

Do not use `HashSet` or unordered collections if your policy requires deterministic results when multiple candidates tie. For `lookup`/`filterTags`, if multiple tags match a wildcard or differ only by letter case, input ordering can affect the returned tag. Define a controlled list and an explicit product tie-breaker.

## 11. From Selected Locale to ResourceBundle

Once `selectedLocale` is chosen, the application typically uses it to load the translation family:

```java
ResourceBundle bundle = ResourceBundle.getBundle(
        "i18n.Messages", selectedLocale);

String greeting = bundle.getString("greeting");
```

This code illustrates usage inside a method and requires `import java.util.ResourceBundle;`. Here, `selectedLocale` has already been chosen by the application from `SUPPORTED`.

**Two distinct mechanisms:**

1. **Locale negotiation:** picks **one locale the product intends to use** from the user's priority list and supported locales.
2. **ResourceBundle lookup:** resolves the **actual bundle and each key** using candidate locales, root/default fallback, classloader/module scope, and `ResourceBundle` caching.

If `de-DE` is selected without `Messages_de_DE.properties` or `Messages_de.properties`, `ResourceBundle` may fall back to another bundle according to its default policy. That does not mean negotiation properly selected a `de-DE` translation. **The supported list must reflect actually released resources and translations**, rather than relying on `getBundle` not throwing an error.

### ResourceBundle.getLocale() Helps Diagnose Fallback

After loading a bundle, you can call `bundle.getLocale()` to inspect the locale bound to the resulting bundle. If the application requested a specific locale and the returned bundle came from the root, that signals missing translation coverage. However, because `ResourceBundle` also uses parent inheritance per key, inspecting only the bundle's locale is still insufficient to verify **full key coverage**.

### Runnable Java 17 Example: Negotiate Then Load Translation

Prepare the directory structure:

```text
project/
  src/demo/NegotiatedBundleDemo.java
  resources/demo/Messages.properties
  resources/demo/Messages_de.properties
  resources/demo/Messages_vi.properties
```

Contents of `resources/demo/Messages.properties`:

```properties
hello=Hello
```

Contents of `resources/demo/Messages_de.properties`:

```properties
hello=Hallo
```

Contents of `resources/demo/Messages_vi.properties` (UTF-8):

```properties
hello=Xin chào
```

Save `src/demo/NegotiatedBundleDemo.java`:

```java
package demo;

import java.util.List;
import java.util.Locale;
import java.util.ResourceBundle;

public class NegotiatedBundleDemo {
    private static final Locale FALLBACK =
            Locale.forLanguageTag("vi-VN");
    private static final List<Locale> SUPPORTED =
            List.of(FALLBACK,
                    Locale.forLanguageTag("en-US"),
                    Locale.forLanguageTag("de-DE"));

    static Locale choose(String header) {
        Locale match = Locale.lookup(
                Locale.LanguageRange.parse(header),
                SUPPORTED);
        return match != null ? match : FALLBACK;
    }

    public static void main(String[] args) {
        Locale selected = choose(
                "de-DE,de;q=0.8,en-US;q=0.5");

        ClassLoader loader =
                NegotiatedBundleDemo.class.getClassLoader();

        ResourceBundle.Control control =
                ResourceBundle.Control.getNoFallbackControl(
                        ResourceBundle.Control.FORMAT_PROPERTIES);

        ResourceBundle messages = ResourceBundle.getBundle(
                "demo.Messages", selected, loader, control);

        System.out.println("selected=" +
                selected.toLanguageTag());
        System.out.println("bundleLocale=" +
                messages.getLocale().toLanguageTag());
        System.out.println("hello=" +
                messages.getString("hello"));
    }
}
```

Bash inside the `project` directory:

```bash
mkdir -p out/demo
javac -encoding UTF-8 -d out src/demo/NegotiatedBundleDemo.java
cp resources/demo/Messages*.properties out/demo/
java -cp out demo.NegotiatedBundleDemo
```

Stdout:

```text
selected=de-DE
bundleLocale=de
hello=Hallo
```

Why is `bundleLocale=de` instead of `de-DE`? Because the demo only has `Messages_de.properties`, not `Messages_de_DE.properties`. `getBundle` resolves candidate `de` when searching the family, while the selected UI locale remains `de-DE`.

**Practical takeaway:** having a single `_de` bundle serve multiple German-speaking regions is a valid resource policy **if the translations are semantically appropriate**. Do not equate "bundle filename lacks a region" with an error; evaluate translation coverage against the product contract.

`ResourceBundle.Control` is intended primarily for the classpath/unnamed module. In JPMS named modules, overloads and `Control` usage are restricted; module-aware lookups or `ResourceBundleProvider` may be needed. This demo intentionally uses the classpath.

## 12. Selecting a Locale Does Not Solve Everything

After choosing `selectedLocale`, various APIs consume it:

```java
NumberFormat numberFormat =
        NumberFormat.getNumberInstance(selectedLocale);

DateTimeFormatter dateFormat =
        DateTimeFormatter.ofLocalizedDate(FormatStyle.MEDIUM)
                .withLocale(selectedLocale);

Collator collator =
        Collator.getInstance(selectedLocale);
```

This snippet is inside a method and requires importing `java.text.NumberFormat`, `java.time.format.DateTimeFormatter`, `java.time.format.FormatStyle`, and `java.text.Collator`.

However:

- `Locale` does not determine the `ZoneId` for timestamps.
- `Locale` does not convert USD to EUR.
- `Locale` does not necessarily select a non-ISO `Chronology`.
- `Locale` does not guarantee active fonts render Arabic, Hebrew, or emojis properly.
- `Locale` does not automatically handle all HTML/CSS `dir` attributes or Java Swing component orientation.
- `Locale` does not automatically load translation files from external plugin loaders/modules.
- `Locale` does not guarantee that every `ResourceBundle` contains all keys.

A well-engineered multilingual application performs **explicit locale negotiation** while keeping formatting, translation, data, and layout concerns separate.

## 13. Bugs Caused by Mixing Preferred Locale with JVM Default

Avoid doing:

```java
Locale.setDefault(chosenLocale);
```

when `chosenLocale` comes from an HTTP request. `Locale.setDefault` mutates **global JVM state**, affecting formatting, casing, and bundle lookups in unrelated requests.

Famous failure case:

```java
String key = "TITLE".toLowerCase();
```

If the JVM default locale is Turkish, uppercase `I` turns into dotless `ı`, corrupting the key when code expects ASCII `"title"`. Machine identifiers should use `toLowerCase(Locale.ROOT)` per contract; user-facing text should pass `selectedLocale` explicitly to formatting/casing APIs.

**Do not use the user's locale to parse JSON date/time wire formats** unless the protocol explicitly mandates it. Machine APIs typically use ISO-8601; locale-aware UI presentation belongs to a separate layer.

## 14. Input Validation and Handling Untrusted Headers

`Accept-Language` arrives from the client as untrusted input. Never trust it blindly.

### 14.1. Length and Entry Count

- Cap the maximum header length accepted by the system according to operational requirements.
- Limit the number of parsed language ranges/strings if needed to prevent excessive processing cost.
- Do not store unbounded raw headers verbatim in logs or cache keys.
- When the header is empty or missing, use the default or another verified preference.
- `LanguageRange.parse` can throw `IllegalArgumentException` on invalid input: define a clear policy instead of returning an unhandled 500 error.

### 14.2. q=0, Wildcards, and Consistency

- `en;q=0` requests **not accepting English** under HTTP semantics.
- `*` can match other tags, but you must ensure it does not re-enable an explicitly rejected language.
- With `Locale.lookup`, `*` is ignored; therefore, you need an explicit fallback.
- `Locale.filter` can return multiple items and follows a different policy than lookup.
- If the product implements full HTTP `Accept-Language` negotiation, use an implementation tested against RFC 9110 and RFC 4647, or write custom logic with tests for exclusions, ties, and weights.

### 14.3. Language Rejection and Default Fallback

A paradox to resolve in requirements: if all supported locales are rejected (`q=0`), should you still return the default `en-US`? It depends on the product:

- For a typical website, falling back to a UI default keeps the page usable, though you must recognize this **does not strictly obey client acceptability**.
- For an API with a strict content-negotiation contract, returning `406 Not Acceptable` may be appropriate when no acceptable representation exists.
- When a user configures language in their profile, you can prompt them to re-select or fall back to the published default.

Not every website is required to return 406; HTTP RFCs allow servers discretion in serving a representation. Document your choice, test the all-rejected case, and prevent user-facing UIs from switching abruptly due to an odd header.

### 14.4. Privacy

Very long or hyper-specific `Accept-Language` lists can reveal personal language preferences or increase browser fingerprinting surface. Collect and retain only what the product needs. Do not log unused header contents, and never infer nationality, identity, or exact physical location solely from a language tag.

## 15. Caching and Content-Language Considerations

If the same URL returns different translations based on `Accept-Language`, HTTP/CDN caches can serve the wrong version unless language is factored into the caching strategy.

- Return `Content-Language` when the response genuinely reflects the corresponding language.
- Consider `Vary: Accept-Language` when responses vary by that header.
- If the locale is chosen from a user profile, cookie, or URL instead of the header, cache keys and privacy policies must match; `Vary: Accept-Language` **does not solve** every scenario automatically.
- For private content, verify `Cache-Control` and per-user cache partitioning per policy.
- Do not use an unbounded raw `Accept-Language` string as a cache key if cardinality explosion is a risk; consider keying on the normalized selected locale where architecture allows.

**Key takeaway:** the input header may list many preferences, whereas the response body is usually generated under **one concrete selected locale**. Caches should bind to the exact content/language variant rather than arbitrary client-supplied header strings.

## 16. Comprehensive Edge-Case Testing

### 16.1. Lookup/Filter Test Matrix

| Preference | Supported | What to Verify |
| --- | --- | --- |
| `de-DE,de;q=0.9,en-US;q=0.6` | `de-DE, en-US` | Lookup selects `de-DE` |
| `fr-CA,fr;q=0.9,en-US;q=0.7` | `fr-FR, en-US` | Lookup selects `en-US`; filtering prioritizes `fr-FR` |
| `en-GB` | `en-US` | Lookup returns `null`, does not auto-select `en-US` |
| `en` | `en-US` | Lookup returns `null`; filter includes `en-US` |
| `*` | `vi-VN, en-US` | Lookup returns `null`; defined fallback policy applies |
| `es-MX,es;q=0.8` | `vi-VN, en-US` | No match; uses default |
| `zh-Hant-TW` | `zh-Hant, zh-Hans-CN` | Lookup truncates to `zh-Hant`; does not pick `Hans` just for sharing `zh` |
| `tr-TR` | `tr-TR, en-US` | Case mapping/`tr-TR` works properly after selection |
| `ar-EG` | `ar-EG, en-US` | RTL UI handled outside locale lookup logic |
| Empty/missing header | Any non-empty supported list | Default is used |
| Malformed header | Fixed list | No unhandled 500 error |
| `en;q=0,*;q=0.5` | `en-US, de-DE` | Rejected language is not re-selected via wildcard under strict HTTP contract |
| Equal `q` | Both tags supported | Tie-breaking/priority follows deterministic policy |
| Duplicates/aliases | Tag set with aliases | Does not silently drop or duplicate locales improperly |
| Supported list change | A locale removed in a new release | No longer selects a locale without translation resources |

### 16.2. Post-Negotiation Testing

Even after selecting a locale, verify:

- `ResourceBundle.getBundle` resolves the family and required keys properly.
- Placeholders and `MessageFormat` have no ordering or escaping errors.
- Number/date/currency formatters match the locale and handle parse round-trips.
- `Collator` sorts words according to language rules, especially Turkish `I`.
- Font rendering, line breaking, and RTL layout work for Arabic/Hebrew.
- Long translations do not overflow buttons/menus, and screen readers read them properly.
- Canonical/API data formats do not mutate simply because the UI uses another locale.
- Changing an account's locale between requests updates bundles/formatters without leaking into other requests.

## 17. Java 17 Test: Assertions for an Explicit Policy

File `LocaleNegotiationAssertions.java`:

```java
import java.util.List;
import java.util.Locale;

public class LocaleNegotiationAssertions {
    static final Locale DEFAULT =
            Locale.forLanguageTag("vi-VN");
    static final List<Locale> SUPPORTED = List.of(
            DEFAULT,
            Locale.forLanguageTag("en-US"),
            Locale.forLanguageTag("de-DE"),
            Locale.forLanguageTag("fr-FR"));

    static Locale choose(String header) {
        if (header == null || header.isBlank()) {
            return DEFAULT;
        }
        Locale matched = Locale.lookup(
                Locale.LanguageRange.parse(header),
                SUPPORTED);
        return matched == null ? DEFAULT : matched;
    }

    static void check(String title, boolean condition) {
        if (!condition) {
            throw new AssertionError(title);
        }
        System.out.println("PASS " + title);
    }

    public static void main(String[] args) {
        check("exact-de", choose("de-DE").equals(
                Locale.forLanguageTag("de-DE")));

        check("next-preference",
                choose("fr-CA,fr;q=0.9,en-US;q=0.7")
                        .equals(Locale.forLanguageTag("en-US")));

        check("no-sibling-match",
                choose("en-GB").equals(DEFAULT));

        check("wildcard-default",
                choose("*").equals(DEFAULT));

        check("empty-default",
                choose("").equals(DEFAULT));

        check("supported-only",
                SUPPORTED.contains(
                        choose("es-MX,fr-FR;q=0.7")));
    }
}
```

```bash
javac -encoding UTF-8 LocaleNegotiationAssertions.java
java LocaleNegotiationAssertions
```

Stdout:

```text
PASS exact-de
PASS next-preference
PASS no-sibling-match
PASS wildcard-default
PASS empty-default
PASS supported-only
```

This test uses `main` to run standalone without requiring JUnit. It does not include malformed-header tests (the demo `choose` in the assertion file does not catch exceptions) because it focuses on **valid lookup behavior**. In production, add `try/catch`, input limits, `q=0`/HTTP acceptability, and alias/extended-range coverage.

## 18. Common Design Mistakes

| Mistake | Why It Is Wrong | Fix |
| --- | --- | --- |
| Always picking the first entry of `Accept-Language` | Might be unsupported; ignores `q` | Parse `LanguageRange` and match against supported locales |
| Using `Locale.getAvailableLocales()` as supported | JDK locale data differs from translation coverage | Maintain product's own supported list |
| Calling `Locale.forLanguageTag(wholeHeader)` | Header has multiple ranges and `q`, not a single tag | Use `LanguageRange.parse` |
| Assuming `Locale.lookup` picks `en-US` for `en-GB` | Lookup does not auto-select sibling regions | Define explicit same-language fallback policy |
| Assuming `lookup("en")` matches `en-US` | Lookup truncates ranges, not prefix-filtering | Use `filter` when that semantics is desired |
| Calling `filter(...).get(0)` when empty | Throws `IndexOutOfBoundsException` | Check empty and return default |
| Treating wildcard `*` as a real locale | Not a concrete BCP 47 language tag | Handle via negotiation policy |
| Treating `q=0` as low priority yet acceptable | In HTTP, `q=0` means unacceptable | Enforce exclusions per HTTP RFC |
| Using unordered `HashSet` for tied candidates | Non-deterministic selection | Use an ordered supported list and tie-breaker |
| Calling `Locale.setDefault` per request | Causes race conditions in multi-user JVMs | Pass `Locale` explicitly |
| Treating `ResourceBundle` fallback as proof of "supported" | May fall back to root or another translation | Verify catalog/translation coverage |
| Ignoring script in tags like `zh-Hant` | Can select the wrong writing system | Define explicit script policy |
| Using IP address as proof of language | Does not reflect personal preference | Prioritize explicit user settings |
| Leaving user-controlled headers unbounded | Risks CPU cost/DoS or cache cardinality blowup | Limit header length and range count |
| Assuming selecting a locale changes time zone/currency | Independent dimensions | Manage `ZoneId`/`Currency`/`Chronology` separately |
| Letting cache reuse the previous request's locale | Serves the wrong language | Configure cache keys, `Content-Language`, and `Vary` properly |
| Testing only `en-US` | Misses regional differences, RTL, and Turkish casing | Run a multi-locale and UI test matrix |
| Blocking requests when the header is absent | Header is not guaranteed to be present | Define missing-header default policy |

## 19. Exercises and Answers

**Exercise 1.** The user sends `de-DE,de;q=0.8,en-US;q=0.5`. The app supports `vi-VN`, `en-US`, and `de-DE`. What does strict lookup select?

**Answer:** `de-DE`, because the first range matches a supported locale directly.

**Exercise 2.** The user sends `en-GB`, and the app only supports `en-US`. Why does `Locale.lookup` return `null`?

**Answer:** Lookup truncates `en-GB → en`, but `supported` does not contain the tag `en`; `en-US` is not an exact match for `en` in lookup. To fall back within the same language, you need a custom policy or filtering on an appropriate range.

**Exercise 3.** The user sends `en`, and the app supports `en-US`. What do `Locale.filter` and `Locale.lookup` return?

**Answer:** Filtering can return `en-US`; lookup returns `null` if there is no `en` locale in `supported`.

**Exercise 4.** The browser sends `fr-CA,fr;q=0.9,en-US;q=0.7`; supported locales are `fr-FR,en-US`. Why do lookup and filter differ?

**Answer:** Under filtering, `fr` covers `fr-FR`, whereas lookup requires an exact match for the full or truncated tag; `en-US` is the next matching range. Product policy determines whether to enforce strict lookup or preferred-language fallback.

**Exercise 5.** Why can `LanguageRange.parse` return more elements than the number of ranges in the header?

**Answer:** Java may append equivalent language ranges from the IANA Language Subtag Registry, such as legacy and modern language codes.

**Exercise 6.** What does `q=0` mean in `Accept-Language`?

**Answer:** In HTTP, it means that range is unacceptable; do not treat it merely as a very low-weight choice or let a wildcard accidentally re-select it.

**Exercise 7.** Why shouldn't `Locale.getAvailableLocales()` be used to determine display locales?

**Answer:** It reports the JDK's built-in locale data, not whether the product has translations and UI QA for each locale.

**Exercise 8.** `zh-Hant-TW` and `zh-Hans-CN` share the language `zh`. Should you swap them automatically?

**Answer:** No. Their scripts differ; only use fallbacks approved by localization owners.

**Exercise 9.** After selecting `de-DE`, `ResourceBundle.getBundle` loads `Messages_de.properties`. Is that an error?

**Answer:** Not necessarily. The `de` bundle candidate can serve `de-DE`; verify coverage and content against the product contract.

**Exercise 10.** Two users hit the same endpoint with different `Accept-Language` headers. What bug can happen if a CDN caches the page solely by URL?

**Answer:** It may serve one user's language version to the next user. Design appropriate cache keys, `Vary`, and `Content-Language` headers, and verify private data handling.

**Exercise 11.** An app calls `Locale.setDefault(chosen)` on every incoming request. What is the risk?

**Answer:** It mutates the global JVM default, causing cross-request interference across formatters, casing operations, and bundles that do not pass an explicit `Locale`.

**Exercise 12.** There is no `fr-FR` translation, yet `Locale.getAvailableLocales()` includes `fr-FR`. Should it be added to `SUPPORTED`?

**Answer:** No, unless the product officially supports that locale with translations and QA. Having a JDK formatter does not mean translations exist.

**Exercise 13.** When a client omits `Accept-Language`, should the system immediately guess from the IP address?

**Answer:** IP should not be treated as definitive evidence. Use other explicit user preferences or the defined product fallback.

**Exercise 14.** Why shouldn't you hardcode number/month/year formatting per region once a locale is selected?

**Answer:** Java provides locale formatting data via CLDR/providers; obtain the matching formatter for presentation. Do not mix it with fixed machine-readable API formats.

## 20. Production Deployment Checklist

- [ ] `SUPPORTED_LOCALES` is verified by the product from actual translations + QA, not from JDK available locales.
- [ ] `DEFAULT_LOCALE` is present inside the supported list.
- [ ] Priority order across sources (UI, profile, URL, header) has an explicit contract and tests.
- [ ] `Accept-Language` header is parsed with appropriate APIs and enforces validation/size limits.
- [ ] `q`, wildcards, and `q=0` are handled according to the chosen HTTP policy.
- [ ] It is explicit whether **lookup** or **filtering** is used, with tests covering `en-GB/en-US` differences.
- [ ] Language/script/region fallback rules are reviewed rather than assuming sibling regions are interchangeable.
- [ ] Every selected result belongs to the supported set (except when explicitly rejecting negotiation).
- [ ] Unmatched behavior (default / 406 / user prompt) is defined.
- [ ] `Locale` is passed explicitly without mutating JVM default per request.
- [ ] Bundles load in the proper scope, with key coverage and fallback tested.
- [ ] `ZoneId`, `Chronology`, and `Currency` are managed separately.
- [ ] Caching, `Content-Language`, and `Vary` match the actual selection inputs.
- [ ] Turkish `I`, RTL, fonts, and number/date formatting are tested for every truly supported locale.
- [ ] Outcomes are tracked via metrics without leaking raw headers or unnecessary PII.

## 21. Summary

**Locale selection is a problem of matching user preferences against actual product support.** Users may send multiple language ranges with `q` weights; the application must select only from the **catalog of locales that actually have translations** and define an unambiguous default policy.

Java 17 provides `Locale.LanguageRange.parse`, `Locale.lookup`/`lookupTag`, and `Locale.filter`/`filterTags`. **Lookup** selects a single tag under RFC 4647 using progressive truncation, without automatically choosing sibling regions of the same language. **Filtering** finds all tags covered by the ranges, fitting broader acceptance policies.

Do not use `Locale.getAvailableLocales()` as a translation list; do not confuse negotiation with `ResourceBundle` fallback; do not call `Locale.setDefault` per request. For production HTTP services, add `q=0`/wildcard handling, input limits, user preferences, caching, and testing for special languages.

A solid selector does not merely "return a `Locale`"—it **returns a genuinely supported locale**, makes fallback behavior explicit, and avoids corrupting language, data, or caches.

### Official References

- [Locale — BCP 47, RFC 4647 matching, lookup, and filtering (Oracle Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html)
- [Locale.LanguageRange — parsing, weight, and language priority list (Oracle Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.LanguageRange.html)
- [Locale.FilteringMode — filtering modes for language ranges (Oracle Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.FilteringMode.html)
- [ResourceBundle — bundles, fallback, and modules (Oracle Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html)
- [RFC 4647 — Matching of Language Tags](https://www.rfc-editor.org/rfc/rfc4647.html)
- [RFC 9110 — HTTP Semantics, Accept-Language](https://www.rfc-editor.org/rfc/rfc9110.html)
