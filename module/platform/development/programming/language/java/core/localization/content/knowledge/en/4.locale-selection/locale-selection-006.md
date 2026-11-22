# Distinguishing Filtering Multiple Results from Looking Up One Matching Result

## 1. The Locale Selection Problem in a Java Application

Suppose an application has localizations for `fr-FR`, `fr-CA`, `en-US`, `en-GB`, and `vi-VN`. A user sends the preference order:

```text
fr-CA, fr;q=0.9, en;q=0.6
```

The application needs to answer **two different questions**:

1. **Which locales satisfy the languages the user accepts?** The result is *a list*, which can be used to display options or narrow down a list of content.
2. **Which single locale should be used for the session or the resource to return?** The result is *one best candidate under lookup mechanics*, or no candidate.

Java supports two mechanisms in RFC 4647 — **filtering** and **lookup** — via `java.util.Locale`. The easy-to-miss trap is that “filter” and “lookup” sound similar, yet **their matching conditions, result counts, fallback behavior, and how the application processes the results** are not the same.

## 2. Two Core Methods and Data Types

| Criterion | Filtering — `Locale.filter(...)` | Lookup — `Locale.lookup(...)` |
| --- | --- | --- |
| Goal | Find **all** locales matching the priority list | Find **one** best-matching locale per the lookup algorithm |
| Primary inputs | `List<Locale.LanguageRange>` and `Collection<Locale>` | Same two input types |
| Return type | `List<Locale>` | `Locale` |
| When no results | Empty list | `null` |
| Range matching | Allows a general language `fr` to match more specific tags like `fr-FR`, `fr-CA` | Tries specific ranges in priority order and progressively trims subtags to find a **tag matching per lookup rules** |
| Use when | Lists of options, filtering multiple translations/languages | Deciding one locale to serve a request |
| String variant | `Locale.filterTags(...)` returns `List<String>` | `Locale.lookupTag(...)` returns `String` or `null` |

**Never think of `lookup` simply as `filter(...).get(0)`.** RFC 4647 defines two different matching mechanisms. Therefore, there are cases where filtering returns one or more locales while lookup returns `null` — an example is demonstrated in section 5.

The fact that `filter` returns multiple choices does not mean all translations or application features are actually ready. The candidate set must be the locales **supported by the product**, never arbitrarily replaced with the entire `Locale.getAvailableLocales()` from the JDK.

## 3. Inputs: Language Range, Priority List, and Weights

`Locale.LanguageRange` represents **a language range to match**. `Locale.LanguageRange.parse(...)` reads a priority list in the form commonly seen in the HTTP `Accept-Language` header value:

```java
List<Locale.LanguageRange> priority =
        Locale.LanguageRange.parse("fr-CA, fr;q=0.9, en;q=0.6");
```

Where:

- `fr-CA` is a request for French in Canada, defaulting to weight `q=1.0`.
- `fr;q=0.9` is French in general, with lower priority.
- `en;q=0.6` is English, with even lower priority.
- Weights follow `q` syntax in `[0,1]`; higher values are processed first. If you need to construct a range manually: `new Locale.LanguageRange("fr", 0.9)`.

In the example above, the evaluation order by priority is `fr-CA` → `fr` → `en`. Both methods take a **list of ranges**, but interpret matching differently.

**Distinguishing a language range from a language tag:**

- `fr`, `fr-CA`, `en` in the priority list are **query criteria**.
- `fr-FR`, `fr-CA`, `en-GB` in the supported set are **actual candidates**.
- `fr` under filtering can match multiple tags starting with `fr-`; under lookup, do not assume the tag `fr` will automatically select an arbitrary variant like `fr-FR`.

A **basic language range** can be `en`, `en-US`, or `*`. Patterns containing a wildcard in the middle such as `zh-*-TW` are **extended language ranges**; filtering mode choices are discussed in section 7.

## 4. Java 17+ Example: Comparing Filtering and Lookup on the Same Data

Create the file **`LocaleSelectionDemo.java`**:

```java
import java.util.List;
import java.util.Locale;
import java.util.stream.Collectors;

public class LocaleSelectionDemo {
    private static String tags(List<Locale> locales) {
        return locales.stream()
                .map(Locale::toLanguageTag)
                .collect(Collectors.joining(", "));
    }

    public static void main(String[] args) {
        List<Locale> supported = List.of(
                Locale.forLanguageTag("fr-FR"),
                Locale.forLanguageTag("en-GB"),
                Locale.forLanguageTag("fr-CA"),
                Locale.forLanguageTag("vi-VN"),
                Locale.forLanguageTag("en-US"));

        List<Locale.LanguageRange> priorities =
                Locale.LanguageRange.parse("fr-CA, fr;q=0.9, en;q=0.6");

        List<Locale> matches = Locale.filter(priorities, supported);
        Locale selected = Locale.lookup(priorities, supported);

        System.out.println("filter: " + tags(matches));
        System.out.println("lookup: " +
                (selected == null ? "(none)" : selected.toLanguageTag()));
    }
}
```

Run with JDK 17 or later in the directory containing the file:

```bash
javac -encoding UTF-8 LocaleSelectionDemo.java
java -cp . LocaleSelectionDemo
```

Output:

```text
filter: fr-CA, fr-FR, en-GB, en-US
lookup: fr-CA
```

**Why does filtering return four results?**

1. Range `fr-CA` matches `fr-CA`.
2. Range `fr` matches `fr-FR` and `fr-CA`; locale `fr-CA` is already included, so it is not duplicated.
3. Range `en` matches `en-GB` and `en-US`.
4. `vi-VN` matches no range and is excluded. Results order groups by weight/range and preserve the order of matching candidates within each group; **they are not sorted alphabetically**.

`Locale.filter` returns the list of matching locales and ensures matching locales do not appear twice. It **does not decide on its own** which locale the application must use.

**Why does lookup return only `fr-CA`?**

Range `fr-CA` has the highest priority and an exact matching candidate `fr-CA` exists. `Locale.lookup` stops after finding the first suitable result per the algorithm, without listing `fr-FR`, `en-GB`, `en-US`.

### How to Use the Results

For an “Available Languages” page, use the filtering list to show all compatible choices:

```java
List<Locale> choices = Locale.filter(priorities, supported);
```

For deciding the UI language of a request, pick one locale and handle the no-match case:

```java
Locale selected = Locale.lookup(priorities, supported);
if (selected == null) {
    selected = Locale.forLanguageTag("en-US"); // product default
}
```

The two snippets above are **only excerpts** using the `priorities` and `supported` variables already created in the complete program; they are not two standalone Java files.

## 5. Important Counterexample: Filter Has Results While Lookup Has None

A common mistake is thinking `Locale.lookup` will always pick some regional variant if the user only requests a general language.

Suppose the application only has `fr-FR`, `en-GB`, and `en-US`, and the user specifically requests `fr`. With **basic filtering**, `fr` matches `fr-FR` because the candidate tag is a more specific form of the same language. However, **lookup** searches for a matching tag via exact matching / trimming subtags of the *range*; `fr` does not expand into `fr-FR`, so if there is no candidate tag `fr`, lookup can return `null`.

Create **`FilteringVsLookupDemo.java`**:

```java
import java.util.List;
import java.util.Locale;

public class FilteringVsLookupDemo {
    public static void main(String[] args) {
        List<Locale> supported = List.of(
                Locale.forLanguageTag("fr-FR"),
                Locale.forLanguageTag("en-GB"),
                Locale.forLanguageTag("en-US"));

        List<Locale.LanguageRange> french =
                Locale.LanguageRange.parse("fr");

        System.out.println("filter(fr): " + Locale.filter(
                french, supported).stream()
                .map(Locale::toLanguageTag).toList());

        System.out.println("lookup(fr): " +
                Locale.lookup(french, supported));

        List<Locale.LanguageRange> preferences =
                Locale.LanguageRange.parse("fr-CA, en-US;q=0.7");

        Locale best = Locale.lookup(preferences, supported);
        System.out.println("lookup(fr-CA, en-US): " +
                (best == null ? "(none)" : best.toLanguageTag()));
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 FilteringVsLookupDemo.java
java -cp . FilteringVsLookupDemo
```

Output:

```text
filter(fr): [fr-FR]
lookup(fr): null
lookup(fr-CA, en-US): en-US
```

**Analysis of the last line:** `fr-CA` is not in the supported set. Lookup can shorten the range to `fr`, yet there is no `fr` tag to match under lookup rules either. It then examines the next range `en-US` and finds candidate `en-US`. The algorithm does not automatically switch `fr-CA` to locale `fr-FR` just because both are French.

Therefore:

- **Filtering:** `fr` can list all French localizations such as `fr-FR`, `fr-CA`.
- **Lookup:** `fr` does not implicitly pick a specific region that was not requested. To pick `fr-FR` as the default localization for French, **the application must define that selection policy** (or include a corresponding tag in the priority list/candidates).
- If you need a locale even when lookup returns `null`, pick an **intentional fallback** from the deployed supported set.

This is a difference in **matching mechanism**, not a Java bug.

## 6. Lookup Does Not Automatically Produce a Valid Product Locale

`Locale.lookup(...)` can return `null`. If the application immediately calls `selected.toLanguageTag()`, a `NullPointerException` will occur. Empty results must be handled explicitly.

One way to implement locale selection for a request:

```java
import java.util.List;
import java.util.Locale;

public class ChooseLocaleDemo {
    private static final List<Locale> SUPPORTED = List.of(
            Locale.forLanguageTag("vi-VN"),
            Locale.forLanguageTag("en-US"));

    public static Locale choose(String acceptLanguage) {
        if (acceptLanguage == null || acceptLanguage.isBlank()) {
            return Locale.forLanguageTag("en-US");
        }

        try {
            List<Locale.LanguageRange> ranges =
                    Locale.LanguageRange.parse(acceptLanguage);
            Locale found = Locale.lookup(ranges, SUPPORTED);
            return found != null ? found : Locale.forLanguageTag("en-US");
        } catch (IllegalArgumentException invalidHeader) {
            return Locale.forLanguageTag("en-US");
        }
    }

    public static void main(String[] args) {
        System.out.println(choose("vi-VN, en-US;q=0.7").toLanguageTag());
        System.out.println(choose("ja-JP").toLanguageTag());
        System.out.println(choose(null).toLanguageTag());
    }
}
```

Run:

```bash
javac -encoding UTF-8 ChooseLocaleDemo.java
java -cp . ChooseLocaleDemo
```

Output:

```text
vi-VN
en-US
en-US
```

**Scope of the example:** this is simple negotiation for two **specific** locales. `Locale.lookup` does not translate messages itself and does not guarantee that a corresponding `ResourceBundle` exists. The `SUPPORTED` list must reflect the translations and features the application genuinely commits to. In a web application, beyond handling `Accept-Language`, you usually also need to prioritize the user's saved language choice per product policy, limit header size, and handle invalid input.

For a “Vietnamese” request in the form `vi`, if the supported set only has `vi-VN`, lookup will not necessarily pick `vi-VN`. Consider mapping `vi → vi-VN`, adding a neutral `vi` locale, or using a clearly defined selection rule. **Never implicitly assume** lookup always expands a language-only tag into a region-qualified locale.

## 7. Filtering Modes, Wildcards, and API Variants

### 7.1. Basic Filtering and Extended Filtering

With **basic filtering**, range `en` matches `en-US` and `en-GB`; range `en-US` matches `en-US` and tags with appropriate trailing subtags, but does not match `en-GB`. Matching is case-insensitive and must respect **subtag boundaries**, rather than simply using `String.startsWith` on arbitrary strings.

With **extended filtering**, a range can contain a wildcard in a position between subtags, such as `zh-*-TW`. Java lets you specify `Locale.FilteringMode`:

- `AUTOSELECT_FILTERING`: default for the overload without `mode`; automatically chooses the filtering method appropriate to the supplied range types.
- `EXTENDED_FILTERING`: uses extended filtering rules.
- `IGNORE_EXTENDED_RANGES`: ignores extended ranges to process the remaining basic ranges.
- `MAP_EXTENDED_RANGES`: converts extended ranges to basic form according to mapping rules.
- `REJECT_EXTENDED_RANGES`: throws an error when the list contains an extended range.

These modes affect **filtering**, and are not parameters of `Locale.lookup`. Do not change modes trying to make lookup behave like filtering.

### 7.2. The Asterisk `*`

Range `*` in filtering can match candidates regardless of language when filtering rules allow. **Lookup ignores a range consisting solely of `*`**, so `Locale.lookup(Locale.LanguageRange.parse("*"), supported)` does not automatically select the first locale; if no other range matches, the result is `null`.

This matters when the `Accept-Language` header merely states that the user accepts any language: the application needs a **default policy**, and cannot expect lookup to always return a value.

### 7.3. Overloads Working on String Language Tags

If the candidate set is stored as BCP 47 strings:

```java
List<String> tags = List.of("fr-CA", "fr-FR", "en-US");
List<Locale.LanguageRange> ranges =
        Locale.LanguageRange.parse("fr, en;q=0.5");

List<String> all = Locale.filterTags(ranges, tags);
String one = Locale.lookupTag(ranges, tags);
```

This is an illustrative **snippet** using `List` and `Locale`; `import java.util.List` and `import java.util.Locale` are required in a Java class when using it. `filterTags` returns multiple tags; `lookupTag` returns one tag or `null`. They still follow two different RFC 4647 mechanisms. Use the `Locale` APIs when downstream parts of the program need `Locale`; the tag forms are useful when input/output data is strings.

## 8. Choosing the Approach Based on Business Requirements

| Scenario | Appropriate Approach | Reason |
| --- | --- | --- |
| Listing UI languages the user can choose from | `Locale.filter` on the supported list | Need **multiple** candidates |
| Filtering a list of documents with translations by preferences | `Locale.filter` or `filterTags` | May return multiple documents/languages |
| Choosing **one** language to return a web page | `Locale.lookup` then apply fallback policy | Need one result |
| Choosing **one** email translation | `Locale.lookup`/`lookupTag` and verify template existence | Cannot assume a template exists after matching |
| User requests `fr` but only `fr-FR`, `fr-CA` exist | Need a product rule deciding the default region or asking the user | Filtering gives multiple candidates; lookup may return no result |
| No range matches | Fallback explicitly defined in configuration | `filter` returns `[]`, `lookup` returns `null` |

**Recommended workflow for real applications:**

1. Maintain a `supportedLocales` set containing only deployed and tested locales, with a stable order. Never use all JVM locales as the “application-supported” list.
2. Define priority source order: the user's explicit choice, account settings, permitted parameters, `Accept-Language`, application default.
3. Parse into a `LanguageRange` list when the input consists of weighted ranges; validate input length/format if received from HTTP.
4. Use **filter** if business logic needs multiple choices returned; use **lookup** if a single choice must be decided.
5. If lookup returns `null`, apply an intentional fallback rule; if filter returns empty, display an appropriate list or message.
6. Once a locale is chosen, continue verifying **actual resources** (`ResourceBundle`, translations, display templates) and appropriate number/date formatting; tag matching does not replace the localization step.
7. Test cases: exact match, multiple regions of the same language, weight ordering, no match, `*` only, invalid ranges, and saved user preferences.

## 9. Common Pitfalls

**Pitfall 1 — Taking the first element of a filtering result and calling it lookup.** The two mechanisms have different matching definitions. With range `fr` and sole candidate `fr-FR`, filtering yields `[fr-FR]` whereas lookup can return `null`. Never treat the two as equivalent.

**Pitfall 2 — Using a single `Locale` to stand in for an entire priority list.** A user might accept `fr-CA`, then `fr`, then `en` with weights. If you only grab the first string, the application discards the fallback options the user declared.

**Pitfall 3 — Handling language ranges with ad-hoc string comparisons.** `en` and `en-US` have a subtag relationship, yet `startsWith("en")` does not implement the RFC 4647 standard, region control, wildcards, or priorities. Use the matching APIs.

**Pitfall 4 — Assuming `Locale.lookup` always finds a result.** A valid result can be `null`; every call site must have a branch handling this case.

**Pitfall 5 — Using a candidate set of all locales known to the JDK.** That only describes the runtime's locale capabilities, and does not prove the product's language files and content exist.

**Pitfall 6 — Confusing locale selection with resource loading.** `Locale.filter` and `Locale.lookup` only solve **matching**; `ResourceBundle` and the i18n system have their own fallback rules that must be tested.

**Pitfall 7 — Not handling preferences containing only `*`.** Filtering and lookup handle wildcards differently; never rely on lookup picking an arbitrary locale.

## 10. Takeaways

- `Locale.filter` returns **a list of all matching locales**, suitable for filters or option lists.
- `Locale.lookup` returns **one best-matching locale** per lookup mechanics, or **`null`**. It is not equivalent to taking the first element of filtering.
- `Locale.LanguageRange.parse` helps represent priority lists and weights (typically from `Accept-Language`).
- **A general language range `fr` can filter `fr-FR`, yet lookup still will not pick `fr-FR` if a lookup-matching tag is missing.** To default to a region, the product needs an explicit policy.
- Pass **only the locales the application genuinely supports**, handle empty results, and test content after selection. Matching is the locale selection step; localization quality is the next responsibility.
