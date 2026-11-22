# Parsing Language Priority Lists with `Locale.LanguageRange.parse` in Java

## 1. What Is a Language Priority List?

Users can accept multiple languages without liking them all equally. In HTTP, the `Accept-Language` header can pass a priority list like this:

```http
Accept-Language: vi-VN,vi;q=0.9,en-US;q=0.7,en;q=0.5
```

In this string, commas separate **language ranges**; `q` (*quality value*) indicates the priority weight of each range. Java provides `java.util.Locale.LanguageRange.parse(String)` to parse the string into a **Language Priority List** of type `List<Locale.LanguageRange>`.

Each `LanguageRange` object allows reading:

- `getRange()`: the normalized language range, such as `"vi-vn"`, `"en-us"`, or `"*"`.
- `getWeight()`: the priority weight as a `double`, from `0.0` to `1.0`.

**Parsing is not selection:** `parse` only builds the list. It does not know which languages the application has, does not load translations, and does not automatically pick the final localization. Only after `parse` does the application apply `Locale.filter`, `Locale.filterTags`, `Locale.lookup`, or `Locale.lookupTag` against the set of actually supported locales.

## 2. Language Range Syntax and `q` Weights

`LanguageRange.parse` supports common input forms:

```text
vi,en;q=0.5
Accept-Language: vi,en;q=0.5
vi,en
```

Language range syntax is described by **RFC 4647**, related to BCP 47 language tags. Two important types of ranges:

| Form | Example | Meaning |
|---|---|---|
| Basic | `vi` | Prefers the Vietnamese language |
| Basic | `en-US` | Prefers English in the United States |
| Basic wildcard | `*` | Wildcard matching anything, depending on the matching algorithm |
| Extended | `zh-Hant-*` | Traditional Chinese, arbitrary trailing subtags |
| Extended | `*-CH` | Pattern with region `CH` when using extended filtering |

A basic range has a group of 1–8 letters, optionally followed by groups of `-` and 1–8 alphanumeric characters; or just `*`. Extended ranges allow `*` in certain subtag positions. The `*` symbol is a **wildcard character**, not the name of a translatable language.

Table of `q` rules:

| Value | Interpretation |
|---|---|
| No `q` | Defaults to `1.0`, corresponding to `MAX_WEIGHT` |
| `q=1.0` | Maximum priority level |
| `q=0.8` | Preferred, but lower than `1.0` |
| `q=0` | Lowest level `MIN_WEIGHT`; in an HTTP context usually means that range is not acceptable |
| `q=1.2` or `q=-0.1` | Invalid because it is outside `[0.0, 1.0]`; `parse` throws `IllegalArgumentException` |

Do not sum weights to equal 1; they are **not probabilities**. `q` is also not a translation quality score. The `;q=` attaches to the range immediately preceding it, while commas separate different ranges.

## 3. Standalone Java 17+ Example

Save the code to `LanguagePriorityDemo.java`:

```java
import java.util.List;
import java.util.Locale;

public class LanguagePriorityDemo {
    public static void main(String[] args) {
        String header =
                "Accept-Language: en-US;q=0.6, vi;q=1.0, fr;q=0.8, en-GB;q=0.3";

        List<Locale.LanguageRange> preferences =
                Locale.LanguageRange.parse(header);

        for (Locale.LanguageRange preference : preferences) {
            System.out.printf(
                    "%s -> %.1f%n",
                    preference.getRange(),
                    preference.getWeight());
        }
    }
}
```

Compile and run:

```bash
javac LanguagePriorityDemo.java
java LanguagePriorityDemo
```

Output:

```text
vi -> 1.0
fr -> 0.8
en-us -> 0.6
en-gb -> 0.3
```

What to observe: `vi` is placed first even though it appeared after `en-US` in the original string; the list is **sorted by descending weight**. Ranges `en-US` and `en-GB` are normalized to lowercase in `getRange()`. `printf("%.1f")` is used only to display the example; do not round `double` values before executing priority logic.

`parse` returns a modifiable `List`. However, when parsing user headers, pass the resulting list to the matching step without accidentally re-sorting or altering weights.

## 4. Priority Order, Duplicates, and Equivalent Ranges

### Without `q`

```java
List<Locale.LanguageRange> ranges =
        Locale.LanguageRange.parse("vi,en-US,fr");
```

All ranges have weight `1.0`. The declared order `vi` → `en-us` → `fr` is preserved according to the original list's priority. For inputs without `q`, earlier items indicate higher priority.

### With `q`

```java
List<Locale.LanguageRange> ranges =
        Locale.LanguageRange.parse("en-US;q=0.4,vi;q=0.9,fr;q=0.6");
```

The result is sorted as `vi (0.9)` → `fr (0.6)` → `en-us (0.4)`. Therefore, you should not process the raw input string order directly when weights are present.

### Duplicate Ranges: Keep the **First Occurrence**

```java
List<Locale.LanguageRange> ranges = Locale.LanguageRange.parse(
        "en-US;q=0.2, fr;q=0.8, en-US;q=0.9");

for (Locale.LanguageRange range : ranges) {
    System.out.printf("%.1f %s%n",
            range.getWeight(), range.getRange());
}
```

Output:

```text
0.8 fr
0.2 en-us
```

The second `en-US` with weight `0.9` **does not replace** the first entry `0.2`. Java keeps only the first occurrence of a duplicate range, then sorts the list by weight.

### IANA Equivalents: Output Can Be Longer Than Input

`parse` automatically adds **equivalent language ranges** found in the IANA Language Subtag Registry data. For example, legacy code `iw` (Hebrew) and current code `he`:

```java
List<Locale.LanguageRange> ranges =
        Locale.LanguageRange.parse("iw,en;q=0.5");
```

On Java 17+, the list contains the following entries:

| Range | Weight |
|---|---:|
| `iw` | 1.0 |
| `he` | 1.0 |
| `en` | 0.5 |

Both Hebrew codes have the same priority level; adding `he` helps the matching step find supported tags that use the newer code. **The number of elements after parsing can be larger than the number of comma-separated items.** Do not write logic assuming one input range produces exactly one object. The list of equivalents can depend on IANA/JDK data by version.

## 5. Distinguishing `Locale.LanguageRange` from `Locale`

A `Locale` like `Locale.forLanguageTag("en-US")` describes a specific locale object. `LanguageRange("en")` describes **a matching criterion**, which can match multiple tags such as `en-US` and `en-GB` under filtering rules.

- `Locale.forLanguageTag("vi-VN")` accepts **one** BCP 47 language tag.
- `Locale.LanguageRange.parse("vi-VN, en;q=0.7")` accepts a **list** of weighted ranges.
- `Locale.filterTags(priorityList, supportedTags)` finds **multiple** matching supported tags.
- `Locale.lookupTag(priorityList, supportedTags)` finds **one** supported tag under lookup rules, or returns `null`.

Do not pass an entire `Accept-Language` header to `Locale.forLanguageTag(...)`: input containing commas and `q` is a list string, not a single tag.

## 6. Matching After `parse`: Filtering vs. Lookup

`parse` does not determine which language to serve. The next step requires knowing the set of locales the service actually provides. For example, three supported languages: `fr-FR`, `en-US`, `vi-VN`.

Create the file `LanguageMatchingDemo.java`:

```java
import java.util.List;
import java.util.Locale;

public class LanguageMatchingDemo {
    public static void main(String[] args) {
        List<Locale.LanguageRange> priorities =
                Locale.LanguageRange.parse(
                        "fr-CA, fr;q=0.8, en-US;q=0.5");

        List<String> supported =
                List.of("fr-FR", "en-US", "vi-VN");

        System.out.println(Locale.filterTags(priorities, supported));
        System.out.println(Locale.lookupTag(priorities, supported));
    }
}
```

Run:

```bash
javac LanguageMatchingDemo.java
java LanguageMatchingDemo
```

Verified output:

```text
[fr-FR, en-US]
en-US
```

**Why are they different?** `filterTags` uses RFC 4647 filtering rules and finds `fr-FR` from the range `fr`. `lookupTag` uses the lookup algorithm, checking ranges by priority and subtag truncation rules; it does not automatically deduce that `fr-CA` should fall back to `fr-FR` as a human might expect. With this candidate set, lookup finds `en-US`.

Do not treat `lookupTag` as culturally aware fuzzy matching. If a product wants a custom rule `fr-CA` → `fr-FR`, it must be explicitly designed via priority sets/mappings or a product fallback mechanism. Use `filterTags` to list compatible choices; use `lookupTag` when a single matching tag per lookup is needed.

When the candidate list is a `Collection<Locale>` instead of `Collection<String>`, choose `Locale.filter(...)` or `Locale.lookup(...)`. The `*Tags` methods operate only on tag strings.

## 7. Wildcards, Extended Ranges, `q=0`, and Filtering Modes

**Wildcard `*`:** `"vi;q=1.0,*;q=0.1"` allows considering other tags when no high-priority choice matches, depending on the matching algorithm. The `*` symbol is not a translation or separate locale code.

**Extended range:** `"zh-Hant-*"` and `"*-CH"` are valid under extended language range syntax. When calling `Locale.filterTags` with these patterns, you must understand `Locale.FilteringMode`, especially `EXTENDED_FILTERING`. Some modes map extended ranges to basic ranges, ignore them, or reject them. Do not assume all modes share the same semantics for `*` in subtags.

**Weight `q=0`:** In HTTP, q=0 indicates not wanting the corresponding language range. `parse` still returns this entry with `getWeight()==0.0`. Filtering/exclusion rules belong to the matching step, which especially needs testing when wildcards and multiple overlapping ranges are present. Do not blindly pick the first element after `parse` or take all ranges with non-negative `q` and assume they are all acceptable.

## 8. Detecting Malformed Input

`LanguageRange.parse` performs **syntactic validation**, not confirming that each code exists in the IANA Language Subtag Registry or has translations on the server.

| Input | Handling |
|---|---|
| `"vi,en;q=0.5"` | Valid |
| `"en;q=0"` | Valid, weight equals 0 |
| `"en;q=1.2"` | `IllegalArgumentException` because weight is greater than 1 |
| `"en;q=-0.1"` | `IllegalArgumentException` because weight is negative |
| `"en--US"` | `IllegalArgumentException` because of an empty subtag |
| `null` | `NullPointerException` |
| Pattern-valid code not in the support table | Can parse successfully; handled at the support/matching step |

Create the file `ParseLanguageRangesSafely.java`:

```java
import java.util.List;
import java.util.Locale;

public class ParseLanguageRangesSafely {
    public static void main(String[] args) {
        String raw = "en;q=1.2";

        try {
            List<Locale.LanguageRange> ranges =
                    Locale.LanguageRange.parse(raw);
            System.out.println("Parsed: " + ranges.size());
        } catch (IllegalArgumentException exception) {
            System.out.println("Invalid language preferences");
        }
    }
}
```

Run `javac ParseLanguageRangesSafely.java` and `java ParseLanguageRangesSafely`. Output:

```text
Invalid language preferences
```

For real header data, check `null`, blank data, and length limits, catch `IllegalArgumentException`, and fall back according to **application policy**. If input is invalid, do not use unvalidated values to build resource paths or change the server-wide default locale.

## 9. Overload `parse(String, Map)`: Custom Equivalence Mappings

Besides `parse(String)`, Java also has:

```java
List<Locale.LanguageRange> result =
        Locale.LanguageRange.parse(raw, equivalents);
```

Here `equivalents` is a `Map<String, List<String>>` defining the ranges the application wants to treat as equivalent. It works identically to:

```java
Locale.LanguageRange.mapEquivalents(
        Locale.LanguageRange.parse(raw),
        equivalents);
```

Illustrative example, assuming variable `raw` and imports `java.util.Map`, `java.util.List`:

```java
Map<String, List<String>> equivalents =
        Map.of("zh", List.of("zh-hans", "zh-hant"));
List<Locale.LanguageRange> preferences =
        Locale.LanguageRange.parse(raw, equivalents);
```

This mapping occurs after adding IANA equivalents and preserves the original weight. However, **this is only an API example**, not a recommendation to merge two Chinese scripts into one; in a real UI, `zh-Hans` and `zh-Hant` may need separate translations. Apply a custom map only when there is a clearly designed business rule, not as a substitute for adding translations on the server.

## 10. A Complete Fallback Policy

Suppose a product supports strictly `vi-VN`, `en-US`, and `fr-FR`. We can pick a tag with `lookupTag`; if none is found or the input string is invalid, return a default locale **supported by the server**.

Create the file `SelectSupportedLocale.java`:

```java
import java.util.List;
import java.util.Locale;

public class SelectSupportedLocale {
    private static final List<String> SUPPORTED =
            List.of("vi-VN", "en-US", "fr-FR");

    public static String select(String acceptLanguage) {
        if (acceptLanguage == null || acceptLanguage.isBlank()) {
            return "en-US";
        }

        try {
            List<Locale.LanguageRange> priorities =
                    Locale.LanguageRange.parse(acceptLanguage);

            String match = Locale.lookupTag(priorities, SUPPORTED);
            return match != null ? match : "en-US";
        } catch (IllegalArgumentException exception) {
            return "en-US";
        }
    }

    public static void main(String[] args) {
        System.out.println(select("fr-FR,vi-VN;q=0.7"));
        System.out.println(select("ja-JP"));
        System.out.println(select("en;q=1.5"));
    }
}
```

Run:

```bash
javac SelectSupportedLocale.java
java SelectSupportedLocale
```

Output:

```text
fr-FR
en-US
en-US
```

This is an illustrative policy: using lookup and fallback `en-US`. It does not guarantee that a short range `vi` will automatically expand to `vi-VN` under every algorithm. If the product wants that behavior, explicit mapping/fallback rules must be implemented and tested.

The real-world flow is usually: receive `Accept-Language` → `parse` → match against the supported locales list → fall back when not found → load translations/formatting with the final locale. `Content-Language` in the HTTP response (if emitted) should reflect **the actual language served**, rather than simply copying the entire input preference header. With `ResourceBundle`, continue testing resource fallback rules because an exact bundle may not exist.

Do not call `Locale.setDefault(...)` per HTTP request: it is process-shared default state and can affect other requests. Pass the selected locale explicitly to formatters, parsers, and resource loaders.

## 11. Common Pitfalls

1. **Using `Locale.forLanguageTag` to parse an entire `Accept-Language`:** this method handles a single tag, not a multi-item list with `q`.
2. **Believing the first input item has the highest priority:** wrong when `q` values are not in descending order; inspect the list returned by `parse`.
3. **Treating weights as probabilities:** `q` values do not need to sum to 1.
4. **Taking the last occurrence of duplicate ranges:** Java keeps **the first occurrence**, regardless of whether a later one has a higher weight.
5. **Assuming one input produces exactly one range:** IANA equivalences can increase the element count.
6. **Ignoring the `q=0` case:** it is a valid value and must be handled properly during matching.
7. **Treating a wildcard as a locale:** `*` is a range expression, not a translation code.
8. **Assuming filtering and lookup are the same:** the two algorithms produce different results as shown in the `fr-CA` example.
9. **Assuming `parse` validates IANA codes:** the API only checks syntax; the application must check the supported list.
10. **Ignoring exceptions/null:** invalid input can disrupt requests; safe fallback is needed.
11. **Using display language names for matching:** compare tags/locales, not localized `getDisplayName()` strings.
12. **Modifying the global default locale per user:** use a request-scoped local locale.

## 12. Self-Check Questions

- For `"en;q=0.4,vi;q=0.9,fr;q=0.7"`, the priority result is **vi → fr → en**.
- For `"en-US;q=0.3,en-US;q=0.8"`, only **en-us with weight 0.3** is retained.
- For `"iw,en;q=0.5"`, Java can add the range **he** via IANA equivalence.
- For `q=0`, `parse` still creates a range and keeps weight **0.0**.
- `parse` **does not guarantee** the server has a bundle for the requested locale.
- After `parse`, use **filter** if you need choices satisfying filtering rules; use **lookup** when you need one candidate under lookup rules, while also handling `null` and fallback.

**References:** [Java SE 17 — Locale.LanguageRange](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.LanguageRange.html) · [Java SE 17 — Locale Matching](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html) · [RFC 4647 — Matching of Language Tags](https://www.rfc-editor.org/rfc/rfc4647).
