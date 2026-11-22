# `Locale.filter`, `filterTags`, `lookup`, and `lookupTag` in Java

## 1. Why Is Locale Selection Needed?

A system may provide translations for Vietnamese (`vi-VN`), US English (`en-US`), British English (`en-GB`), French in France (`fr-FR`), and Canadian French (`fr-CA`). Meanwhile, a user prefers Canadian French, then French in general, and finally English. The program must compare **the languages the user accepts** against **the versions the application actually supports** to decide which translation to display.

Do not compare two locale strings with `equals` and stop there: a request for `fr` can match multiple variants like `fr-FR` and `fr-CA`; a request for `zh-Hant-HK` may need to progressively reduce specificity to find `zh-Hant`.

Java 8+ provides four static methods on `java.util.Locale` implementing the RFC 4647 **language matching** mechanism:

- `Locale.filter`: retrieves a **list of `Locale`s** matching the priority language ranges.
- `Locale.filterTags`: retrieves a **list of language tag strings** matching the priority ranges.
- `Locale.lookup`: finds the **single best-matching `Locale`**, or `null`.
- `Locale.lookupTag`: finds the **single best-matching language tag string**, or `null`.

The two operation families **filtering** and **lookup** do not share the same rules. This lesson focuses on locale selection; once a valid locale is selected, loading `ResourceBundle`, formatting numbers/dates, and translating content remain separate responsibilities.

## 2. Language, Region, and Language Range

BCP 47 language tags commonly contain components such as:

| Tag | Components | Meaning |
| --- | --- | --- |
| `vi` | Language | Vietnamese, no region specified |
| `vi-VN` | Language + region | Vietnamese in the Vietnam context |
| `en-US` | Language + region | English in the US |
| `en-GB` | Language + region | English in the UK |
| `zh-Hant-TW` | Language + script + region | Chinese, Traditional script, Taiwan region |

A **language range** expresses a search criterion from the user's side, not necessarily a complete language tag with a single region. For instance, `en` is a range encompassing multiple English variants when filtering; `en-GB` is more specific; `*` is a wildcard range. In **extended language range** syntax, `*` can also appear in the middle, such as `de-*-DE`.

A prioritized list of language ranges is represented in Java as `List<Locale.LanguageRange>`. This is the first input to all four methods.

### 2.1. Creating a Language Priority List

Use `Locale.LanguageRange.parse(...)` to parse a priority string, such as the value of HTTP `Accept-Language`:

```java
import java.util.List;
import java.util.Locale;

List<Locale.LanguageRange> priorities =
        Locale.LanguageRange.parse("fr-CA,fr;q=0.8,en;q=0.5");
```

Meaning:

| Range | Weight `q` | Intent |
| --- | ---: | --- |
| `fr-CA` | 1.0 (default) | Prefer Canadian French |
| `fr` | 0.8 | If unavailable, consider general French |
| `en` | 0.5 | Finally, English is acceptable |

`q` is the priority weight, between `0.0` and `1.0`; larger values have higher priority. When omitted, `q=1.0`. `parse` returns ranges sorted by descending priority/weight and may add equivalent ranges based on registry data; therefore, do not assume the parsed list always contains only the exact elements written in the input string. If a range repeats, the parser keeps the first occurrence. Invalid range or weight syntax can throw `IllegalArgumentException`.

You can construct it directly when configuration is already structured:

```java
List<Locale.LanguageRange> priorities = List.of(
        new Locale.LanguageRange("fr-CA", 1.0),
        new Locale.LanguageRange("fr", 0.8),
        new Locale.LanguageRange("en", 0.5)
);
```

With manual construction, the program itself must put the `List` in proper priority order; the matcher receives a **sorted priority list** and is not responsible for fixing misordered inputs. In the example, manual construction is unnecessary because `parse` handles it.

Note that `Locale.forLanguageTag("en-US")` creates **one `Locale`**, whereas `Locale.LanguageRange.parse("en-US,en;q=0.7")` creates **a list of selection criteria**. The two types serve different roles.

## 3. The Four APIs and Input/Output Types

| Method | Available List Accepted | Returns | When to Use |
| --- | --- | --- | --- |
| `Locale.filter(priorityList, locales)` | `Collection<Locale>` | `List<Locale>` | Need all matching locales to choose/display |
| `Locale.filterTags(priorityList, tags)` | `Collection<String>` | `List<String>` | Translation catalog is stored as BCP 47 strings |
| `Locale.lookup(priorityList, locales)` | `Collection<Locale>` | `Locale` or `null` | Need one best-matching locale |
| `Locale.lookupTag(priorityList, tags)` | `Collection<String>` | `String` or `null` | Need a single tag to look up resource keys |

All four are **static methods of `Locale`** and have existed since Java 8. Both `filter` and `filterTags` also have overloads accepting `Locale.FilteringMode` to choose how **extended language ranges** are handled. The `lookup`/`lookupTag` methods do not take a `FilteringMode` parameter.

The list of available locales/tags must accurately reflect the translations actually deployed. The fact that the JVM recognizes a locale or `Locale.getAvailableLocales()` lists it does not prove the application has translations for it.

## 4. Filtering: Retrieving All Matching Options

With **basic filtering** (RFC 4647), a range acts as a prefix from the start of a language tag and matches only at **subtag boundaries**. For example:

| Range | Available Tag | Basic Filtering | Explanation |
| --- | --- | --- | --- |
| `en` | `en-US` | Matches | `en` is a whole-subtag prefix |
| `en` | `en-GB` | Matches | Same language |
| `en-US` | `en` | No | Candidate lacks region |
| `en-US` | `en-US-x-demo` | Matches | Candidate is more specific and continues after `-` |
| `en` | `eng` | No | Does not match a complete subtag |
| `fr` | `en-US` | No | Different language |

Thus, given available list `[en-US, en-GB, fr-FR]`, filtering with range `en` returns both `en-US` and `en-GB`, not just the first translation. With multiple ranges, results are ordered by range priority/weight, with duplicate matches removed. **Within the same priority level, the iteration order of available candidates can affect result order**: pass a `List` with stable order when display order matters.

By default, `Locale.filter(priorityList, locales)` is equivalent to using `Locale.FilteringMode.AUTOSELECT_FILTERING`. It uses basic filtering if the list has only basic ranges, or extended filtering if there is an extended range.

### `filter` vs. `filterTags`

The two methods apply the same filtering concept but differ in data types:

```java
List<Locale> locales = List.of(
        Locale.forLanguageTag("en-US"),
        Locale.forLanguageTag("en-GB"),
        Locale.forLanguageTag("fr-FR")
);
List<Locale.LanguageRange> ranges = Locale.LanguageRange.parse("en");

List<Locale> selectedLocales = Locale.filter(ranges, locales);

List<String> tags = List.of("en-US", "en-GB", "fr-FR");
List<String> selectedTags = Locale.filterTags(ranges, tags);
```

`selectedLocales` contains two `Locale` objects; `selectedTags` contains two strings `"en-US"` and `"en-GB"`. `filterTags` preserves the casing of the selected input tag (for instance, tag `"en-us"` can still be returned as `"en-us"`) even though matching is case-insensitive. Tags differing only in letter case are treated as duplicates for result purposes; the earlier occurrence is kept.

**Unmatched result:** filtering returns an empty `List`, not `null`. A list with multiple results also does not mean the system should return multiple translations simultaneously to one user; the result can be used to suggest options or check supportability.

## 5. Lookup: Finding One Best Match

**Lookup is not simply `filter(...).get(0)`.** RFC 4647 treats each language range as the *most specific* wish, then tries **progressively reducing specificity** until an available tag is found.

For example, the priority list has range `zh-Hant-HK`. If the system only has `zh-Hant` and `en-GB`, lookup tries:

```text
zh-Hant-HK  → not available
zh-Hant     → available, select zh-Hant
```

In that case, `Locale.lookup(...)` can pick `zh-Hant`, whereas `Locale.filter(...)` does not return `zh-Hant` for range `zh-Hant-HK` because the candidate is less specific than the requested range; if the priority list also contains `en-GB`, filter returns `en-GB`.

A **very common pitfall**:

```java
List<Locale> supported = List.of(Locale.US, Locale.UK);
List<Locale.LanguageRange> requested = Locale.LanguageRange.parse("en");

System.out.println(Locale.filter(requested, supported)
        .stream().map(Locale::toLanguageTag).toList());
System.out.println(Locale.lookup(requested, supported));
```

Output on JDK 17+:

```text
[en-US, en-GB]
null
```

Because filtering `en` accepts more specific tags like `en-US`/`en-GB`, whereas lookup with range equal to `en` first requires tag `en` (and has no subtags left to truncate). An application needing a fallback from `en` to `en-US` must **explicitly define a business fallback**, add an appropriate range to the priority list, or provide tag `en` if that translation truly exists. Do not assume the two mechanisms are equivalent.

### `lookup` and `lookupTag`

`Locale.lookup` returns a `Locale`; `Locale.lookupTag` returns a `String`, preserving the casing of the selected available tag. If there is no matching candidate, both return `null`. The `*` range **is ignored during lookup**; `Locale.lookup(Locale.LanguageRange.parse("*"), supported)` alone does not automatically pick an arbitrary locale.

If a range contains `*` in a subtag and multiple candidates match equally, the iteration order of candidates can determine the first match; use an available list with stable order and define explicit fallbacks.

## 6. Standalone Java 17+ Example Covering All Four Methods

The example below uses a fixed-order available list and common ranges so results are easy to verify. Create file **`LocaleMatchingDemo.java`** with contents:

```java
import java.util.List;
import java.util.Locale;

public class LocaleMatchingDemo {
    private static List<String> languageTags(List<Locale> locales) {
        return locales.stream().map(Locale::toLanguageTag).toList();
    }

    public static void main(String[] args) {
        List<Locale> available = List.of(
                Locale.forLanguageTag("vi-VN"),
                Locale.forLanguageTag("en-US"),
                Locale.forLanguageTag("en-GB"),
                Locale.forLanguageTag("fr-FR"),
                Locale.forLanguageTag("fr-CA")
        );

        List<String> tags = languageTags(available);
        List<Locale.LanguageRange> preferences =
                Locale.LanguageRange.parse("fr-CA,fr;q=0.8,en;q=0.5");

        List<Locale> filtered = Locale.filter(preferences, available);
        List<String> filteredTags = Locale.filterTags(preferences, tags);
        Locale bestLocale = Locale.lookup(preferences, available);
        String bestTag = Locale.lookupTag(preferences, tags);

        System.out.println("filter: " + languageTags(filtered));
        System.out.println("filterTags: " + filteredTags);
        System.out.println("lookup: " + (
                bestLocale == null ? "null" : bestLocale.toLanguageTag()));
        System.out.println("lookupTag: " + bestTag);

        List<Locale> availableForFallback = List.of(
                Locale.forLanguageTag("zh-Hant"),
                Locale.forLanguageTag("en-GB")
        );
        List<Locale.LanguageRange> fallbackPreferences =
                Locale.LanguageRange.parse("zh-Hant-HK,en-GB;q=0.7");

        System.out.println("fallback filter: "
                + languageTags(Locale.filter(
                        fallbackPreferences, availableForFallback)));

        Locale fallbackBest =
                Locale.lookup(fallbackPreferences, availableForFallback);
        System.out.println("fallback lookup: " + (
                fallbackBest == null ? "null" : fallbackBest.toLanguageTag()));

        System.out.println("wildcard lookup: "
                + Locale.lookup(
                        Locale.LanguageRange.parse("*"), available));
    }
}
```

Compile and run with **JDK 17 or later**:

```bash
javac -encoding UTF-8 LocaleMatchingDemo.java
java LocaleMatchingDemo
```

Stdout:

```text
filter: [fr-CA, fr-FR, en-US, en-GB]
filterTags: [fr-CA, fr-FR, en-US, en-GB]
lookup: fr-CA
lookupTag: fr-CA
fallback filter: [en-GB]
fallback lookup: zh-Hant
wildcard lookup: null
```

Explanation in order:

1. `filter` treats `fr-CA` as highest priority, then `fr` allows including `fr-FR`; next, `en` picks the two English variants. `fr-CA` is not duplicated even though it matches both the specific range `fr-CA` and range `fr`.
2. `filterTags` has the same result set, but as strings instead of `Locale`s.
3. `lookup` and `lookupTag` select `fr-CA` because the catalog supports the exact highest-priority tag.
4. For request `zh-Hant-HK`, `filter` does not treat tag `zh-Hant` as a candidate long enough to match that range; the next priority range `en-GB` matches, so the filter result is `[en-GB]`.
5. `lookup` truncates `zh-Hant-HK` down to `zh-Hant` and selects a matching variant before considering `en-GB`.
6. Lookup with only `*` returns `null`. If the system wants a default translation always available, it must define it explicitly in product policy.

The example uses APIs that have existed since Java 8; `Stream.toList()` is an API from **Java 16**, which is why this file targets **Java 17+**. For Java 8–15, replace `.toList()` with `.collect(java.util.stream.Collectors.toList())` and use the corresponding JDK.

## 7. `FilteringMode`: Basic and Extended Filtering

A basic range such as `de-DE` requires contiguous subtags from the start; it matches `de-DE` and `de-DE-1996`, but does not match `de-Latn-DE`.

Extended filtering allows wildcards in the middle, for example `de-*-DE` can match `de-DE`, `de-Deva-DE`, and `de-Latn-DE`. Even with a basic range, if `EXTENDED_FILTERING` is explicitly chosen, the extended model can additionally return tags that have a script inserted between language and region.

`Locale.FilteringMode` values:

| Mode | Behavior |
| --- | --- |
| `AUTOSELECT_FILTERING` | Default: basic ranges only → basic filtering; at least one extended range → extended filtering |
| `EXTENDED_FILTERING` | Always uses extended filtering |
| `IGNORE_EXTENDED_RANGES` | Ignores extended ranges and then applies basic filtering |
| `MAP_EXTENDED_RANGES` | Converts extended ranges to basic form before filtering; `de-*-DE` becomes `de-DE` |
| `REJECT_EXTENDED_RANGES` | Throws `IllegalArgumentException` when an extended range is encountered |

Standalone snippet (place the following lines inside a method such as `main` in Java 17+):

```java
List<String> tags = List.of(
        "de-DE", "de-Deva-DE", "de-Latn-DE", "en-US"
);
List<Locale.LanguageRange> ranges = List.of(
        new Locale.LanguageRange("de-*-DE")
);

System.out.println(Locale.filterTags(
        ranges, tags, Locale.FilteringMode.EXTENDED_FILTERING));
System.out.println(Locale.filterTags(
        ranges, tags, Locale.FilteringMode.MAP_EXTENDED_RANGES));
System.out.println(Locale.filterTags(
        ranges, tags, Locale.FilteringMode.IGNORE_EXTENDED_RANGES));
```

Output:

```text
[de-DE, de-Deva-DE, de-Latn-DE]
[de-DE]
[]
```

This is a **method-body snippet**, not a standalone Java program; it uses `import java.util.List` and `import java.util.Locale` as in the previous full example. The default `AUTOSELECT_FILTERING` also selects extended filtering in this example because of range `de-*-DE`.

**Important limitation:** `FilteringMode` belongs only to the filtering family; it does not turn `lookup` into filter and does not create the ability to “guess the exact language the user wants” outside RFC 4647 rules.

## 8. Designing an Application Locale Selector

A practical processing flow can consist of:

1. **Define the actual supported catalog**, e.g. `List<String> supportedTags = List.of("vi-VN", "en-US", "fr-FR")`. Use a list with fixed order. The catalog must correspond to bundles/templates with usable content; `Locale.getAvailableLocales()` does not replace the application's catalog.
2. **Define priority sources**: a user-selected locale in the profile should normally take precedence over a language guessed from the browser; if reading `Accept-Language` is needed, parse with `Locale.LanguageRange.parse(...)`. Do not automatically assume the HTTP header is a mandatory requirement overriding all user choices.
3. **Choose the strategy**. Use `filterTags`/`filter` if you need to display an ordered list to the user or identify all matching variants. Use `lookupTag`/`lookup` if you need one choice under RFC 4647 lookup mechanics.
4. **Handle no-match**. After lookup, check `null`; after filter, check `isEmpty()`. Choose a fallback from the **supported catalog** according to product rules, e.g. `"vi-VN"` as the default for a service aimed solely at Vietnamese users. Do not automatically assume `"en-US"` is a universal fallback.
5. **Load the right resources**. Once a locale/tag is selected, pass it to `ResourceBundle` or the corresponding translation/formatting framework. You must still check for missing message keys and the bundle mechanism's own fallback; a matching result does not guarantee every key is translated.
6. **Test special policies**. For instance, an application might need to map `"en"` to `"en-US"` if the catalog only has a US English version. This is a **product decision**, so configure and test it explicitly rather than assuming `lookup("en")` automatically picks `en-US`.

Example function applying `lookupTag` with a validated fallback:

```java
import java.util.List;
import java.util.Locale;
import java.util.Objects;

public class SupportedLanguage {
    public static String select(String request, List<String> supported,
                                String defaultTag) {
        Objects.requireNonNull(request);
        Objects.requireNonNull(supported);
        if (!supported.contains(defaultTag)) {
            throw new IllegalArgumentException("Default locale is unsupported");
        }

        List<Locale.LanguageRange> preferences =
                Locale.LanguageRange.parse(request);
        String choice = Locale.lookupTag(preferences, supported);
        return choice == null ? defaultTag : choice;
    }

    public static void main(String[] args) {
        List<String> supported = List.of("vi-VN", "en-US", "fr-FR");
        System.out.println(select("fr-FR,en-US;q=0.5",
                supported, "vi-VN"));
        System.out.println(select("de-DE",
                supported, "vi-VN"));
    }
}
```

Save as `SupportedLanguage.java`, run with:

```bash
javac -encoding UTF-8 SupportedLanguage.java
java SupportedLanguage
```

Output:

```text
fr-FR
vi-VN
```

Here the catalog is `List<String>`, so selecting with `lookupTag` avoids converting to `Locale` when the target is just a BCP 47 string key. The function checks that `defaultTag` belongs to the list, ensuring fallback does not point to a translation the application itself does not support. In a real system, normalize and validate tags, bound the length/count of client-supplied ranges, unify tag comparison rules, and handle `IllegalArgumentException` from invalid headers before passing the choice into the rendering flow.

### Some Selection Strategy Considerations

**Filter and lookup carry different meanings**. Filter is useful when displaying all valid options; lookup is useful when following RFC 4647 single-tag selection. If you want “pick the first element in the list after filtering”, clearly document that as an **application policy built on filtering**, and do not call it `Locale.lookup`.

**Priority and input ordering**. `LanguageRange.parse` handles `q`, but in cases of equal priority or wildcards, the order of the candidate collection can affect selection. Do not use `HashSet` as input if the product requires stable ordering in tie-breaking scenarios. Also, never treat weight `q` as a probability or translation quality score.

**There is no automatic “approximate translation”**. `fr-FR` and `fr-CA` may share a language while differing in terminology/context; `zh-Hans` and `zh-Hant` even differ in writing script. Lookup follows subtag-stripping rules and is **not an intelligent model that automatically adapts content or evaluates semantics**. The application still needs to decide how far to accept different variants/regions and verify language across content.

**Separate locale from time zone and transactions**. The selected locale is an input for presentation. It does not determine the user's `ZoneId` or the actual currency of an order; business constraints must be handled separately.

## 9. Common Pitfalls

| Mistake | Consequence | How to Handle |
| --- | --- | --- |
| Taking `filter(...).get(0)` and calling it lookup | Violates subtag-reduction rules, may select an unintended variant | Pick the exact right mechanism and test the results |
| Assuming `lookup("en")` finds `en-US` when only `en-US` exists | May receive `null` because lookup does not expand `en` into `en-US` | Define an explicit fallback or add `en` to the catalog |
| Using `Locale.US` when meaning all English | Imposes the US region | Use range `en` for all English; pick a region when specificity is needed |
| Passing `List<String>` to `filter` | Wrong parameter type | Use `filterTags` or convert to `List<Locale>` |
| Receiving `null` from lookup and immediately calling `toLanguageTag()` | `NullPointerException` | Check `null` and fall back in a controlled way |
| Assuming filter is never empty | No matching translation exists yet UI proceeds as if one did | Check `isEmpty()` |
| Forgetting priority order/weights | Result contradicts user intent | Use `LanguageRange.parse` or an explicitly ordered list |
| Using extended ranges with `REJECT_EXTENDED_RANGES` | `IllegalArgumentException` | Choose an appropriate mode, or restrict input syntax |
| Thinking `*` in lookup is an automatic default | Lookup may return `null` | Define a default tag from the application's catalog |
| Mixing language tags with display names or `toString()` | Invalid BCP 47 form during matching | Use `toLanguageTag()`, `forLanguageTag()` |
| Putting `Locale.getAvailableLocales()` into the translation catalog | Exposes languages the application has not translated | Manage the supported content list independently |
| Not bounding client-supplied data | Garbage or huge headers cause parser errors/resource exhaustion | Limit input, catch errors, and fall back per policy |

## 10. Self-Check Exercises

**Exercise 1.** Catalog is `[en-US, en-GB, fr-FR]`; priority list is just `en`. What are the results of `filter` and `lookup`?

**Answer:** `filter` returns `[en-US, en-GB]`; `lookup` returns `null` because there is no `en` tag. Application fallback is required if you want to select an English variant.

**Exercise 2.** Catalog is `[zh-Hant, en-US]`; priority list is `zh-Hant-TW,en-US;q=0.5`. Why does the lookup result differ from filter?

**Answer:** Lookup truncates `zh-Hant-TW` down to `zh-Hant` and selects that tag; filter does not select `zh-Hant` for the longer range `zh-Hant-TW`, so it can select `en-US` from the next range.

**Exercise 3.** When the catalog consists of strings `"vi-VN"`, `"en-US"`, `"fr-FR"`, which method should be used to get a single best tag string?

**Answer:** `Locale.lookupTag(priorityList, tags)`, then check for `null`. If all matching tags are needed, use `Locale.filterTags`.

**Exercise 4.** If a range has the form `de-*-DE`, which mode automatically uses extended filtering?

**Answer:** `AUTOSELECT_FILTERING`. Using `REJECT_EXTENDED_RANGES` throws `IllegalArgumentException`. Using `MAP_EXTENDED_RANGES` converts it to `de-DE` and performs basic filtering.

**Exercise 5.** `Locale.lookupTag(...)` returns `null`. Should it default to `en-US`?

**Answer:** Only when that is a fallback **defined and genuinely supported by the product**. There is no universal fallback locale for every application.

## 11. Takeaways and References

- `filter`/`filterTags` return **all** matching locales/tags under filtering mechanics; when unmatched, they return an empty list.
- `lookup`/`lookupTag` select **one** locale/tag under lookup mechanics and may truncate subtags; when unmatched, they return `null`.
- All four accept `List<Locale.LanguageRange>` as criteria. Use `LanguageRange.parse(...)` to handle priority lists with `q` weights.
- Only `filter`/`filterTags` take `FilteringMode`. The default mode automatically picks basic/extended based on the language range types.
- Provide a truly supported catalog, inputs with stable ordering, explicit fallbacks, and tests for no-match cases or users requesting a generic language.

Official documentation:

- [Java SE 21 — Locale and Locale Matching](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.html)
- [Java SE 21 — Locale.LanguageRange](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.LanguageRange.html)
- [Java SE 21 — Locale.FilteringMode](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.FilteringMode.html)
- [RFC 4647 — Matching of Language Tags](https://www.rfc-editor.org/rfc/rfc4647)
