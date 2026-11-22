# `Locale.LanguageRange` and Priority Weights

## 1. Why Negotiate Languages?

In a multilingual application, a user may accept multiple languages with different levels of preference. For example, a browser sends:

```http
Accept-Language: fr-CA, fr;q=0.8, en-US;q=0.6, en;q=0.4
```

The user prefers Canadian French (`fr-CA`); if that cannot be served, next is French in general (`fr`), US English (`en-US`), and English (`en`). The application must match that list against **the translations that are actually available**, then select a valid option or configured fallback.

Java provides `java.util.Locale.LanguageRange` and the methods `Locale.filter`, `Locale.filterTags`, `Locale.lookup`, and `Locale.lookupTag` to perform an important part of this process according to RFC 4647. This mechanism has existed since Java 8 and works well on Java 17+.

Distinguish three concepts:

- **Language tag**: a BCP 47 code identifying a language or variant, such as `en`, `en-US`, `zh-Hant-TW`.
- **Language range**: an expression matching one or more tags, such as `en`, `fr-CA`, `*`, `zh-Hant-*`.
- **Language Priority List**: a list of `Locale.LanguageRange` in priority order, where each entry has a `weight`.

A `LanguageRange` is **not** a selected `Locale` object, nor does it represent a translation file. It is a **criterion and priority level** for selecting from the languages the system has.

## 2. Structure and API of `Locale.LanguageRange`

| API | Effect |
| --- | --- |
| `new Locale.LanguageRange("fr-CA")` | Creates a range with default weight `1.0` |
| `new Locale.LanguageRange("en-US", 0.6)` | Creates a range with weight `0.6` |
| `getRange()` | Returns the range, e.g. `"en-us"` |
| `getWeight()` | Returns the priority level as a `double` |
| `MIN_WEIGHT` | `0.0` |
| `MAX_WEIGHT` | `1.0` |
| `Locale.LanguageRange.parse(text)` | Parses a priority list from a string |
| `parse(text, map)` | Parses and then customizes using an equivalence mapping |
| `mapEquivalents(list, map)` | Creates a list customized according to equivalent ranges |

The constructor validates the language range syntax and the weight range `0.0` to `1.0`. A `null` range causes `NullPointerException`; invalid syntax or an out-of-bounds weight causes `IllegalArgumentException`. Syntax validation does not mean verifying that a subtag is registered in IANA, and does not prove the application has translations for the corresponding language.

RFC 4647 distinguishes:

- **Basic language range**: `en`, `ja-JP`, `fr-CA`, or `*` (full wildcard).
- **Extended language range**: `*-CH`, `es-*`, `zh-Hant-*`. A wildcard can appear in a component of the range.

This distinction matters when choosing the filtering mode. Letter case of a language tag does not affect matching results; the API performs case-insensitive matching.

## 3. How Does the `q` Weight Work?

In an `Accept-Language` list, `q` is the *quality value*, representing preference level:

```text
fr-CA, fr;q=0.8, en-US;q=0.6, en;q=0.4
```

| Range | q | Meaning in the Example |
| --- | ---: | --- |
| `fr-CA` | `1.0` | Highest priority; if q is not declared, it defaults to 1.0 |
| `fr` | `0.8` | Next priority |
| `en-US` | `0.6` | Acceptable with lower priority |
| `en` | `0.4` | Last option in this list |

Weights are **not probabilities** and do not need to sum to 1.0. They are relative priority levels. If the highest-priority range does not match any supported content, the application continues evaluating the remaining choices.

- Valid weights range from `0.0` to `1.0`; omitting `q` yields `1.0`.
- `q=0` indicates the corresponding range is not acceptable in HTTP. When Java filters over basic ranges, a range with weight 0 is excluded from selection.
- For a list without `q`, order of appearance is the priority order.
- When parsing a list with `q`, Java sorts by descending weight. It does not re-sort by language tag name.
- When a range appears multiple times in the input string, Java keeps **the first occurrence**, rather than adding or averaging weights.

Because preference differs from availability, the application needs a separate list of supported languages.

## 4. Parsing a Priority List

`Locale.LanguageRange.parse(String)` accepts a comma-separated string as well as forms prefixed with `Accept-Language:`. It validates syntax, reads `q`, sorts the list by priority, and can add equivalent language codes according to IANA.

Standalone Java 17+ example:

```java
import java.util.List;
import java.util.Locale;

public class LanguageRangeParseDemo {
    public static void main(String[] args) {
        String header = "fr-CA, fr;q=0.8, en-US;q=0.6, en;q=0.4";
        List<Locale.LanguageRange> preferences =
                Locale.LanguageRange.parse(header);

        for (Locale.LanguageRange preference : preferences) {
            System.out.printf(Locale.ROOT, "%s -> %.1f%n",
                    preference.getRange(),
                    preference.getWeight());
        }
    }
}
```

Save `LanguageRangeParseDemo.java` as UTF-8; run with JDK 17+:

```bash
javac -encoding UTF-8 LanguageRangeParseDemo.java
java LanguageRangeParseDemo
```

Stdout:

```text
fr-ca -> 1.0
fr -> 0.8
en-us -> 0.6
en -> 0.4
```

`getRange()` returns the range in lowercase, `getWeight()` returns the number. Using `Locale.ROOT` in `printf` fixes the example's decimal separator formatting, independent of the machine's default locale.

**Note on aliases:** `parse` may add equivalent codes from the IANA Language Subtag Registry. For example, the legacy Hebrew code `iw` may be accompanied by `he` with the same weight. Therefore, the number of elements after parsing can exceed the number of original ranges. Do not write code assuming the first element is the first range in the header and that every header produces that exact number of elements.

## 5. Filtering and Lookup: Find All or Pick One?

Java supports two families of matching methods:

| API Family | Available Input | Result |
| --- | --- | --- |
| `Locale.filter(...)` | `Collection<Locale>` | Multiple matching `Locale`s, ordered |
| `Locale.filterTags(...)` | `Collection<String>` containing BCP 47 tags | Multiple matching tag strings, ordered |
| `Locale.lookup(...)` | `Collection<Locale>` | One best `Locale`, or `null` |
| `Locale.lookupTag(...)` | `Collection<String>` | One best tag string, or `null` |

**Filtering** asks “which tags match the user's preferences?”. With basic range `fr`, both `fr-FR` and `fr-CA` can match.

**Lookup** asks “which specific tag is the closest choice?”. According to RFC 4647, it tries from the highest-priority range and progressively strips subtags to find a candidate. For example, `zh-Hant-TW` can drop down to `zh-Hant`, then `zh`. Lookup is not an algorithm that measures semantic proximity across all languages.

Runnable example on JDK 17+:

```java
import java.util.List;
import java.util.Locale;

public class LanguageMatchingDemo {
    public static void main(String[] args) {
        List<String> supported = List.of(
                "en-US", "fr-FR", "fr-CA", "vi-VN");
        List<Locale.LanguageRange> preferences =
                Locale.LanguageRange.parse(
                        "fr-CA, en-US;q=0.8, fr;q=0.5");

        System.out.println(Locale.filterTags(preferences, supported));
        System.out.println(Locale.lookupTag(preferences, supported));

        var chinese =
                Locale.LanguageRange.parse("zh-Hant-TW, en-US;q=0.8");
        System.out.println(Locale.lookupTag(
                chinese,
                List.of("zh-Hant", "en-US", "zh-Hans-CN")));
    }
}
```

Save `LanguageMatchingDemo.java`, then:

```bash
javac -encoding UTF-8 LanguageMatchingDemo.java
java LanguageMatchingDemo
```

Stdout:

```text
[fr-CA, en-US, fr-FR]
fr-CA
zh-Hant
```

The first line returns **all** matching tags in priority order; the second line selects only `fr-CA`; the third line proves `lookupTag` can find `zh-Hant` when `zh-Hant-TW` is absent.

When there is no matching candidate, `lookupTag` and `lookup` return `null`. The application must check the result before using it and decide on a specific fallback.

## 6. Wildcards and Filtering Modes

Basic range `*` represents a full wildcard and can allow filtering to return multiple tags. However, for lookup, **a range consisting solely of `*` is ignored**, so `*` must not be treated as a guarantee that lookup will pick an arbitrary tag.

For extended ranges like `zh-Hant-*` or `*-CH`, you can call:

```java
Locale.filterTags(preferences, supportedTags,
        Locale.FilteringMode.EXTENDED_FILTERING)
```

Values in `Locale.FilteringMode`:

- `AUTOSELECT_FILTERING`: default behavior, automatically selects filtering mode based on the ranges.
- `EXTENDED_FILTERING`: uses extended filtering.
- `IGNORE_EXTENDED_RANGES`: ignores extended ranges.
- `MAP_EXTENDED_RANGES`: maps extended ranges to basic form for filtering.
- `REJECT_EXTENDED_RANGES`: throws `IllegalArgumentException` if the list contains an extended range.

Do not handle wildcards yourself using `startsWith` or ad-hoc regexes because it is easy to break subtag boundaries and RFC rules. Choose a filtering mode based on the ranges the product wants to accept.

Short example proving `q=0` is not selected during filtering:

```java
import java.util.List;
import java.util.Locale;

public class ZeroWeightDemo {
    public static void main(String[] args) {
        var ranges = Locale.LanguageRange.parse("en;q=0, fr;q=1");
        var supported = List.of("en-US", "fr-FR");
        System.out.println(Locale.filterTags(ranges, supported));
    }
}
```

Save `ZeroWeightDemo.java`, run:

```bash
javac -encoding UTF-8 ZeroWeightDemo.java
java ZeroWeightDemo
```

Stdout:

```text
[fr-FR]
```

Even though `en-US` is in the supported list, `en` has `q=0` so it is not returned. In a full HTTP protocol implementation, you must continue considering HTTP requirements such as overlapping ranges. Do not replace all HTTP negotiation rules with a simple custom sort function.

## 7. Language Selection Example with Fallback

Suppose an application has resources only for `vi-VN`, `en-US`, and `fr-FR`. Do not use `Locale.getAvailableLocales()` as the supported languages list: the JDK may know how to format data for a language for which the application does not yet have UI translations.

A clear workflow is to receive a priority list, parse it, look it up in the supported set, and then fall back according to product policy:

```java
import java.util.List;
import java.util.Locale;

public class SelectLanguageDemo {
    private static final List<String> SUPPORTED =
            List.of("vi-VN", "en-US", "fr-FR");
    private static final String DEFAULT_TAG = "vi-VN";

    static String selectLanguage(String headerValue) {
        if (headerValue == null || headerValue.isBlank()) {
            return DEFAULT_TAG;
        }

        List<Locale.LanguageRange> ranges =
                Locale.LanguageRange.parse(headerValue);
        String chosen = Locale.lookupTag(ranges, SUPPORTED);

        return chosen == null ? DEFAULT_TAG : chosen;
    }

    public static void main(String[] args) {
        System.out.println(selectLanguage("fr-FR, en-US;q=0.5"));
        System.out.println(selectLanguage("ja-JP"));
        System.out.println(selectLanguage(null));
    }
}
```

Save `SelectLanguageDemo.java`, run:

```bash
javac -encoding UTF-8 SelectLanguageDemo.java
java SelectLanguageDemo
```

Stdout:

```text
fr-FR
vi-VN
vi-VN
```

In the example, `Locale.LanguageRange.parse` throws `IllegalArgumentException` if the header is syntactically invalid. The function lets the exception propagate to separate language selection from HTTP handling policy. At the request boundary of a real application, you must limit header length, decide whether to return an error or fall back, and validate input before producing a response.

If a user explicitly picks a language in account settings, the product can apply that choice before `Accept-Language`. The header reflects client-sent preferences, not necessarily the final choice the user configured in the application.

After selecting a tag, the application can construct `Locale.forLanguageTag(chosen)` for locale-sensitive formatting APIs. When using `ResourceBundle` or a UI translation framework, verify its separate resource lookup and fallback rules; a successful match does not automatically create missing translations.

## 8. Equivalent Ranges and `mapEquivalents`

In language data, there are legacy codes replaced by current codes. `parse` can add equivalent ranges per IANA to help find matching tags. For specialized requirements, there are also:

```java
Locale.LanguageRange.parse(
        String ranges,
        Map<String, List<String>> map)

Locale.LanguageRange.mapEquivalents(
        List<Locale.LanguageRange> priorityList,
        Map<String, List<String>> map)
```

The parse overload taking a map is equivalent to `mapEquivalents(parse(ranges), map)`. Mapped ranges inherit the weight of the original range. However, custom mappings **can replace** or **expand** depending on how the map is declared; if you want to keep the original range as well, you must include that option in the equivalents list. This is a policy that impacts negotiation results and requires clear business justification.

In particular, `zh-Hans` and `zh-Hant` represent different writing systems; do not automatically treat all Chinese variants as interchangeable. Suitability depends on the application's actual resources.

## 9. Common Pitfalls

1. **Thinking q is a percentage/probability.** Weights only rank priority and do not need to sum to 1.
2. **Splitting manually and sorting alphabetically.** Order and q must be handled by the parser; aliases also need consideration.
3. **Confusing a language range with a specific language tag.** Range `fr` can match multiple tags when filtering.
4. **Assuming filter and lookup are equivalent.** One method returns multiple candidates; the other picks just one and has subtag fallback rules.
5. **Not handling lookup returning `null`.** The requested list might not match any translation.
6. **Treating `*` as an automatic fallback for lookup.** A range of only `*` is ignored in lookup; fallback must be decided by the application.
7. **Ignoring extended ranges.** `*-CH` and `zh-Hant-*` require an explicit mode selection.
8. **Assuming the item count after parsing equals the header item count.** The parser can expand IANA aliases and drop duplicate ranges.
9. **Using all JDK locales as the source of UI translations.** The set of locales the JDK knows and the set of content the product provides are two different things.
10. **Blindly trusting external headers.** Headers may be empty, malformed, or unusually long; handling rules are needed at the request boundary.
11. **Relying on unstable `Set` order.** When multiple candidates are tied, collection iteration order can affect selection. Use a list with deterministic order when stable results are required.
12. **Thinking tag negotiation is the entire i18n system.** Loading resources, formatting numbers/dates, and translation fallbacks require separate policies.

## 10. Testing a Locale Selector

A valuable test suite should check:

- Lists with multiple q values, default q of `1.0`, q equal to `0`, and out-of-range q values.
- Basic and extended ranges, wildcard `*`, and the filtering modes to be supported.
- `filterTags` results potentially containing multiple candidates; `lookupTag` picking one or returning `null`.
- Cases like `zh-Hant-TW` truncating to `zh-Hant`; cases with no candidates.
- Historical codes with aliases, duplicate ranges, and invalid ranges.
- Empty headers, `null`, malformed data, and excessive lengths.
- Product fallback differing from the server's default locale.
- Consistent output when the supported languages list maintains a stable order.

You can write tests for `selectLanguage` using deterministic inputs without modifying `Locale.setDefault`; negotiation should not depend on the host machine's default locale.

## 11. Takeaways

`Locale.LanguageRange` expresses **which languages the user wants and their priority levels**. `parse` turns a string with `q` into a structured list. `filterTags` returns matching tags; `lookupTag` finds a single best candidate. The final decision must still rely on the list of actually available translations, fallback policies, input handling, and resource loading.

Official documentation for further reference:

- [Oracle Java 21 — Locale.LanguageRange](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.LanguageRange.html)
- [Oracle Java 21 — Locale Matching](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.html)
- [RFC 4647 — Matching of Language Tags](https://www.rfc-editor.org/rfc/rfc4647)
- [RFC 9110 — HTTP Accept-Language](https://www.rfc-editor.org/rfc/rfc9110#name-accept-language)
