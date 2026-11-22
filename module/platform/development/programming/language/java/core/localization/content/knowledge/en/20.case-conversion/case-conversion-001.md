# String.toLowerCase and toUpperCase with Explicit Locale in Java

## 1. Why does case conversion relate to localization?

A seemingly harmless piece of code:

```java
String key = "TITLE".toLowerCase();
```

On many machines, `key` will be `"title"`. However, with a **Turkish default locale** (`tr-TR`), the result can be `"tıtle"`: the letter `ı` (`U+0131`, LATIN SMALL LETTER DOTLESS I) is **not** `i` (`U+0069`). If the string is used as a field name, status code, configuration key, or path specified in ASCII, the application may fail to find data or behave differently when running on another server.

For a user interface, the Turkish result **may actually be the exact result needed**. There is no single case conversion suitable for every purpose: you must determine whether the string being processed is **natural language text** or a **machine identifier**.

Java provides four methods:

```java
String toLowerCase();
String toLowerCase(Locale locale);

String toUpperCase();
String toUpperCase(Locale locale);
```

The two **parameterless** overloads use the JVM's default locale. The two **parameterized** overloads use the case transformation rules for the specified locale. This lesson clarifies choosing a `Locale`, special Unicode cases, length changes after conversion, pitfalls of case-insensitive comparison, and how to write easily verifiable Java 17+ code.

## 2. Basic rules of the two methods

`String.toLowerCase(Locale)` converts letters in a string to lowercase according to the Unicode rules applicable to the locale. `String.toUpperCase(Locale)` does the same toward uppercase.

```java
import java.util.Locale;

String source = "Java Localization";
String lower = source.toLowerCase(Locale.ENGLISH);
String upper = source.toUpperCase(Locale.ENGLISH);
```

Here `lower` is `"java localization"` and `upper` is `"JAVA LOCALIZATION"`. But that is only the easy case; for international text, the rule is not always "change each letter to exactly one other letter".

| API | Locale used | Situation |
| --- | --- | --- |
| `s.toLowerCase()` | `Locale.getDefault()` at call time | When the application genuinely wants to depend on the default locale, though prone to subtle bugs |
| `s.toUpperCase()` | `Locale.getDefault()` at call time | Same as above |
| `s.toLowerCase(locale)` | Passed-in locale | Intentional case conversion; easy to test, independent of machine configuration |
| `s.toUpperCase(locale)` | Passed-in locale | Intentional case conversion; easy to test, independent of machine configuration |

These methods return a `String` and do not modify the original string because `String` is immutable. Do not assume the resulting string always has the same `length()` as the input string or always replaces one `char` at a time: Unicode casing supports **one-to-many code point** mappings and **context-dependent rules**.

### Locale does not mean timezone or encoding

- `Locale` here controls **case conversion rules**; it does not convert UTF-8 to UTF-16 and does not perform translation on its own.
- Choosing `Locale.forLanguageTag("tr-TR")` does not change the language of all other strings in the application: it only affects the call using that locale.
- `Locale.ROOT` is a language/region-neutral locale for performing case conversions independent of the default locale; it is **not** a complete Unicode comparison/semantic ruleset for every application.

## 3. The classic case: I, İ, ı, and i in Turkish

Turkish has two distinct uppercase/lowercase letter pairs:

| Uppercase | Unicode | Lowercase | Unicode | Meaning |
| --- | --- | --- | --- | --- |
| `I` | `U+0049` | `ı` | `U+0131` | **Dotless** letter i |
| `İ` | `U+0130` | `i` | `U+0069` | **Dotted** letter i |

In non-Turkish-specific rules, `I` normally becomes `i` and `i` becomes `I`. But in `tr-TR`, `I` must become `ı`, and `i` must become `İ`.

```java
Locale turkish = Locale.forLanguageTag("tr-TR");

String a = "TITLE".toLowerCase(Locale.ROOT);  // title
String b = "TITLE".toLowerCase(turkish);      // tıtle

String c = "title".toUpperCase(Locale.ROOT);  // TITLE
String d = "title".toUpperCase(turkish);      // TİTLE
```

This is a **snippet** requiring `import java.util.Locale;`. The difference is not in the font: `i` and `ı` are **two different Unicode code points**. A key named `"title"` will not match `"tıtle"` when using exact `String.equals` comparison.

### Not just Turkish

Azerbaijani has similar `I`/`İ` letter rules. Greek has final sigma and context-based lowercasing. Some case conversions in Lithuanian involve combining marks. Therefore, you should not build Unicode casing rules by manually adding/subtracting ASCII codes or iterating over each `char`.

**Conclusion:** data displayed to users should be converted according to a locale meaningful for **that text**. Culture-independent machine identifiers should use rules defined by the **technical contract**, typically `Locale.ROOT` or ASCII-only handling if the protocol restricts to ASCII.

## 4. Standalone Java 17+ program: comparing Locale.ROOT and tr-TR

Create the file **`LocaleCaseDemo.java`** with the following content:

```java
import java.util.Locale;
import java.util.stream.Collectors;

public class LocaleCaseDemo {
    private static String points(String input) {
        return input.codePoints()
                .mapToObj(cp -> String.format(
                        Locale.ROOT, "U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    public static void main(String[] args) {
        Locale turkish = Locale.forLanguageTag("tr-TR");

        System.out.println("TITLE ROOT: "
                + points("TITLE".toLowerCase(Locale.ROOT)));
        System.out.println("TITLE TR: "
                + points("TITLE".toLowerCase(turkish)));

        System.out.println("title ROOT upper: "
                + points("title".toUpperCase(Locale.ROOT)));
        System.out.println("title TR upper: "
                + points("title".toUpperCase(turkish)));

        System.out.println("TITLE TR equals title: "
                + "title".equals("TITLE".toLowerCase(turkish)));

        String dottedUpperI = "\u0130";
        System.out.println("Dotted I ROOT lowercase: "
                + points(dottedUpperI.toLowerCase(Locale.ROOT)));
        System.out.println("Dotted I TR lowercase: "
                + points(dottedUpperI.toLowerCase(turkish)));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 LocaleCaseDemo.java
java LocaleCaseDemo
```

**Stdout:**

```text
TITLE ROOT: U+0074 U+0069 U+0074 U+006C U+0065
TITLE TR: U+0074 U+0131 U+0074 U+006C U+0065
title ROOT upper: U+0054 U+0049 U+0054 U+004C U+0045
title TR upper: U+0054 U+0130 U+0054 U+004C U+0045
TITLE TR equals title: false
Dotted I ROOT lowercase: U+0069 U+0307
Dotted I TR lowercase: U+0069
```

The program intentionally prints code points using `U+XXXX` notation to avoid depending on whether the terminal renders `ı`, `İ`, and combining marks properly. The lines show:

1. `"TITLE"` has the letter `I` `U+0049` at the second position.
2. `Locale.ROOT` turns it into `i` `U+0069`, while `tr-TR` turns it into `ı` `U+0131`.
3. `"title"` uppercased with `tr-TR` yields `İ` `U+0130`.
4. `"İ".toLowerCase(Locale.ROOT)` produces **two code points** (`i + COMBINING DOT ABOVE`), whereas with `tr-TR` it produces a single `i`. Even the **number of UTF-16 characters** can change after case conversion.

Do not compare two outputs visually or rely on fonts to judge whether they have the same Unicode values.

## 5. String.toUpperCase can make strings longer: ß → SS

A common German example is `ß` (LATIN SMALL LETTER SHARP S). Under the uppercase conversion rules applied by `String.toUpperCase(Locale)`, a single `ß` can expand to **`SS`**:

```java
String original = "straße";
String upper = original.toUpperCase(Locale.GERMAN);

System.out.println(upper);            // STRASSE
System.out.println(original.length()); // 6
System.out.println(upper.length());    // 7
```

Because `ß` is one code point while `SS` is **two**, do not assume:

```text
input.length() == input.toUpperCase(locale).length()
```

Also do not replace `String.toUpperCase(Locale)` by looping over each `char` and calling `Character.toUpperCase(char)`. The single-character method cannot directly produce two characters to represent one-to-many mappings, and may ignore context conditions.

### Note on "lowercasing after uppercasing to round-trip"

If `"straße".toUpperCase(Locale.GERMAN)` becomes `"STRASSE"`, converting back:

```java
"STRASSE".toLowerCase(Locale.GERMAN)
```

will give `"strasse"`, **not `"straße"`**. Case conversion is a text processing operation, **not a reversible two-way encoding**. Do not use the converted result to replace the original identifier value when the exact original spelling must be preserved.

## 6. Context-dependent case mapping: sigma in Greek

Greek has two lowercase forms of sigma:

- `σ` (`U+03C3`) when not at the end of a word.
- `ς` (`U+03C2`) when at the end of a word by context.

When converting `"ΟΣ"` (capital omicron + capital sigma) to lowercase, the result is `"ος"`, with the final code point `U+03C2`:

```java
String greek = "\u039F\u03A3";
String lower = greek.toLowerCase(Locale.ROOT);

System.out.println(
        lower.codePoints()
             .mapToObj(cp -> String.format(
                     Locale.ROOT, "U+%04X", cp))
             .toList());
// [U+03BF, U+03C2]
```

This is a **snippet** requiring `import java.util.Locale;`. A per-code-point conversion alone will not necessarily preserve the context of the whole string. Therefore, use the `String.toLowerCase(Locale)` API on the entire piece of text rather than manually processing each `char` or each code point with a simplistic mapping.

Casing in various languages can also depend on Unicode marks, word boundaries, and the Unicode data version supported by the JDK. If there are specialized linguistic requirements (such as title case or standard case folding), use the appropriate API rather than replacing everything with `toUpperCase`.

## 7. Standalone Java 17+ example: length and sigma

Create the file **`CaseExpansionDemo.java`**:

```java
import java.util.Locale;

public class CaseExpansionDemo {
    public static void main(String[] args) {
        String german = "stra\u00DFe";
        String upper = german.toUpperCase(Locale.GERMAN);

        System.out.println("German upper: " + upper);
        System.out.println("German lengths: "
                + german.length() + " -> " + upper.length());
        System.out.println("Round trip: "
                + german.equals(upper.toLowerCase(Locale.GERMAN)));

        String greek = "\u039F\u03A3";
        String greekLower = greek.toLowerCase(Locale.ROOT);
        System.out.println("Greek lower code points: "
                + greekLower.codePoints()
                    .mapToObj(cp -> String.format(
                            Locale.ROOT, "U+%04X", cp))
                    .toList());
    }
}
```

Run:

```bash
javac -encoding UTF-8 CaseExpansionDemo.java
java CaseExpansionDemo
```

Result:

```text
German upper: STRASSE
German lengths: 6 -> 7
Round trip: false
Greek lower code points: [U+03BF, U+03C2]
```

The lesson is not "every locale expands `ß` equally in every tool", but rather: **String casing can change length and must be treated as a Unicode transformation per Java's contract**, without assuming one-to-one replacement. The results above reflect `String` mappings on modern JDKs.

## 8. How do Locale.ROOT, Locale.ENGLISH, and default locale differ?

Three common usages:

```java
String a = input.toLowerCase(Locale.ROOT);
String b = input.toLowerCase(Locale.ENGLISH);
String c = input.toLowerCase();
```

This is a snippet, with `input` already defined.

- **`Locale.ROOT`**: the language/region-neutral locale, suited for **string conversions defined to be independent of the user's language**. This is the explicit recommendation in the `String.toLowerCase()` documentation when handling programming language identifiers, protocol keys, HTML tags, etc. However, the protocol contract remains the final authority: if the protocol specifies ASCII only, you may need to accept only ASCII and use a specific ASCII algorithm.
- **`Locale.ENGLISH`**: carries the English language, suitable when the text is actually English. It is not equivalent in **intent** to `Locale.ROOT`, even though many ASCII letters produce the same result.
- **Not passing a locale**: `toLowerCase()` and `toUpperCase()` use **`Locale.getDefault()`**. This easily causes bugs on multi-region server deployments or when the JVM default locale changes.

### Choosing by purpose

| Data | Usually appropriate locale/approach | Example |
| --- | --- | --- |
| Turkish UI labels | `Locale.forLanguageTag("tr-TR")` | Changing case in a Turkish sentence |
| English text | `Locale.ENGLISH` or appropriate regional English locale | English button or heading |
| Technical keys independent of user locale | `Locale.ROOT`, per the key's contract | `"CONTENT-TYPE"`, internal identifiers |
| Multilingual user text | Locale tied to the text, not arbitrarily relying on machine locale | UI search/formatting |
| Data requiring linguistically case-insensitive matching | Locale-aware comparator like `Collator`, if appropriate | Name lists, local search |
| Username, ID, token, security code | Normalization/comparison rules **separately specified**; do not guess | Authentication systems |

**Do not use `Locale.setDefault(...)` per request.** The default locale is JVM-wide state; changing it in a multi-threaded server can cause other requests' results to change unexpectedly. Pass an explicit locale in every call that needs localization.

## 9. Do not confuse case conversion with case-insensitive comparison

### 9.1. equalsIgnoreCase does not accept a Locale

`String.equalsIgnoreCase(String)` has no `Locale` parameter. It compares characters using Java's rules that ignore uppercase/lowercase differences, **not creating a comparison following every linguistic rule**. Java documentation notes that this approach may not produce appropriate results for some locales; `Collator` supports locale-dependent comparison.

```java
boolean equal = "Hello".equalsIgnoreCase("HELLO");
```

For ordinary ASCII words, `equal` is `true`. But one should not infer that `equalsIgnoreCase` can replace `Collator` or Unicode full case folding in all languages.

In particular, there is no guarantee that:

```text
a.equalsIgnoreCase(b)
==
a.toLowerCase(locale).equals(b.toLowerCase(locale))
```

The two sides can differ because one does not take a locale, one takes a locale, and there are also one-to-many Unicode mappings. If business logic relies on comparison, define a separate **comparison contract** rather than treating any single case conversion as a universal solution.

### 9.2. Collator serves language-specific ordering and comparison

`java.text.Collator` allows comparing strings according to locale rules:

```java
import java.text.Collator;
import java.util.Locale;

Collator collator = Collator.getInstance(
        Locale.forLanguageTag("tr-TR"));
collator.setStrength(Collator.SECONDARY);
int result = collator.compare("text1", "text2");
```

This is a **snippet** illustrating configuration. `Collator.SECONDARY` typically distinguishes different accents/diacritics while ignoring uppercase/lowercase differences in common collation rules; exact results depend on locale/provider. `Collator` should not be viewed as a solution for **exact byte comparison** or security token validation. For large multilingual text search, consider search/collation engines supporting Unicode and product requirements.

### 9.3. Locale.ROOT is not Unicode full case folding

Unicode **case folding** is a concept used to produce a case-insensitive comparison form under specific rules. `String.toLowerCase(Locale.ROOT)` is a lowercasing operation, not specified as **full Unicode case folding**, especially when multi-code-point expansions, combining structures, and security/ID rules are involved.

If specialized matching is required such as case-insensitive Unicode usernames, you must clearly specify: normalization form (NFC/NFKC per standard), Unicode case-folding, character policy, Unicode version, confusable character checks, and stability across versions. Standard `String` APIs do not provide all of these policies by themselves.

## 10. toLowerCase/toUpperCase do not solve normalization

Two strings can look identical while containing different sequences of code points:

```java
String composed = "\u00E9";   // é: single code point
String decomposed = "e\u0301"; // e + combining acute accent
```

`equals` usually returns `false` because the UTF-16 sequences differ. Lowercasing both does not necessarily make them identical. If the application needs comparison by **canonical equivalence**, you can normalize with `java.text.Normalizer`:

```java
import java.text.Normalizer;
import java.util.Locale;

String a = Normalizer.normalize(
        composed.toLowerCase(Locale.ROOT), Normalizer.Form.NFC);
String b = Normalizer.normalize(
        decomposed.toLowerCase(Locale.ROOT), Normalizer.Form.NFC);
boolean equivalent = a.equals(b); // true for the two sample strings
```

This is a snippet requiring the declared `composed` and `decomposed` variables. There is no single normalization/casing order suitable for all protocols: follow application domain requirements. Normalization does not automatically handle all capitalization differences, linguistic sorting, Unicode confusables, or user-perceived equivalent characters.

Especially with strings containing `İ`, `toLowerCase(Locale.ROOT)` can generate an extra `COMBINING DOT ABOVE` mark, increasing the number of code points. Consequently, after case conversion you may need to **recheck length, normalization, and validation** if data constraints exist.

## 11. Practical applications: configuration keys and UI content

### 11.1. Stable technical keys

Suppose a system allows users to enter field names in ASCII, and wants to treat uppercase and lowercase letters the same:

```java
import java.util.Locale;
import java.util.regex.Pattern;

static String normalizeAsciiKey(String key) {
    if (!Pattern.matches("[A-Za-z0-9_.-]+", key)) {
        throw new IllegalArgumentException("Invalid ASCII key");
    }
    return key.toLowerCase(Locale.ROOT);
}
```

This is a **snippet of a method inside a class**. It separates two steps:

1. **Validation:** the key contains only characters allowed by the contract `[A-Za-z0-9_.-]+`.
2. **Canonicalization:** lowercase ASCII letters using `Locale.ROOT`, independent of user/machine locale.

This approach fits when **the system's own specification genuinely restricts to ASCII**. If the protocol allows Unicode, the validation step must use a different policy; do not arbitrarily apply an ASCII regex to personal names, display labels, or Vietnamese content.

### 11.2. Displaying names/titles by language

```java
Locale displayLocale = Locale.forLanguageTag("tr-TR");
String heading = "istanbul";
String upperHeading = heading.toUpperCase(displayLocale);
```

In `tr-TR`, the leading `i` can turn into `İ`. This is right when the text has a Turkish linguistic context. However, `toUpperCase` only converts to uppercase; it **does not translate** `heading` into another language and **does not perform title case**. Capitalizing the first letter of each word per grammar/typography is also not simply calling `toUpperCase` on the entire string.

### 11.3. Original data and display data

Do not overwrite the original value with a `toLowerCase` version solely for display or search, unless the business logic defines that as the stored canonical form. A common strategy is keeping the original value while creating a **separate** normalized key for search indexing per contract. This avoids losing information such as `ß → SS` and helps reconstruct the user's display formatting.

## 12. Required testing for internationalized systems

At a minimum, test the following groups:

| Scenario | Test values | What to verify |
| --- | --- | --- |
| Explicit locale | `Locale.ROOT`, `tr-TR` | Results stay stable even if JVM default locale differs |
| Letter I | `TITLE`, `title`, `I`, `İ`, `ı` | Dotted/dotless mappings are accurate |
| One-to-many Unicode | `straße` | `toUpperCase` can increase length |
| Context-sensitive characters | `ΟΣ` | Final sigma is handled across the string |
| Length | Before/after casing | Do not assume length stays unchanged |
| Combining marks | `é` and `e + U+0301` | Distinguish casing from normalization |
| Technical keys | `TITLE` across all locales | Canonicalization per contract, not using default |
| User text | Vietnamese, Turkish, Greek, German | Choose language-appropriate locale and review visually |
| Comparison | `equalsIgnoreCase`/`Collator` | Do not confuse case conversion with collation |
| Security data | Username/token/ID | Clear mapping, normalization, and validation rules |
| Running across JDK versions | Diverse Unicode character sets | Note differences across Unicode data versions if any |

### Why not test English only?

A test with `"HELLO"` and `"hello"` often passes through `Locale.ROOT`, `Locale.ENGLISH`, and `tr-TR` paths without revealing differences in the letter `I`. Conversely, `"TITLE"` or `"IDENTIFIER"` exposes bugs immediately during lowercasing. Testing multi-code-point cases such as `İ` and `ß` will catch the invalid assumption that the output is always the same length as the input.

### Why not use Locale.setDefault in multi-threaded tests?

`Locale.setDefault(...)` mutates JVM-wide state and easily interferes with concurrently running tests. When testing production behavior, pass an explicit `Locale` to each function. If you must test parameterless overloads, isolate the test, restore the default in `finally`, and avoid running concurrently with other tests relying on the default locale.

## 13. Common mistakes

| Mistake | Cause | Fix |
| --- | --- | --- |
| `"TITLE".toLowerCase()` produces a different key on Turkish machines | Parameterless overload uses default locale | For language-independent keys, use `Locale.ROOT` |
| `"title".toUpperCase()` has letter `İ` | Turkish casing | Pass the right locale for the purpose |
| Using `Locale.ENGLISH` for all text | Assuming English is the global default rule | For other-language text, use the text's locale; for technical keys, `ROOT` |
| Looping `charAt(i)` then `Character.toUpperCase(...)` | Does not handle 1:N and full context | Convert the whole `String` with a Locale-taking API |
| Assuming output preserves length | `ß` can become `SS`, `İ` can become `i + mark` | Do not index by old positions if the string changed |
| Using `equalsIgnoreCase` instead of Collator | Not locale-sensitive comparison | Choose the API matching the search/sort contract |
| Using lowercase as Unicode full case folding | Casing differs from case folding | Design an explicit Unicode profile rule |
| Believing two visually identical strings are equal | Different Unicode normalization | Use Normalizer if the contract requires it |
| Saving uppercase/lowercase version and discarding original | Loses ability to recover original spelling | Keep source string and processing key separate |
| Using `Locale.setDefault` per request | Mutates JVM shared state | Pass locale into every operation |
| Transforming username/token without a spec | Can cause collisions or logic bypass | Define whitelist, normalization, and safe comparison |
| Using casing to translate content | Only transforms case, does not translate | Use ResourceBundle/i18n to localize messages |

## 14. Review questions

**Question 1.** How does `"TITLE".toLowerCase(Locale.ROOT)` differ from `"TITLE".toLowerCase(Locale.forLanguageTag("tr-TR"))`?

**Answer:** With `ROOT`, the letter `I` becomes `i` (`U+0069`). With Turkish, `I` becomes `ı` (`U+0131`). The strings `"title"` and `"tıtle"` differ under exact comparison.

**Question 2.** Should you use the parameterless `String.toLowerCase()` to normalize protocol keys?

**Answer:** No, because it depends on the JVM default locale. Use `Locale.ROOT` or the canonicalization algorithm specified by the protocol, along with validation.

**Question 3.** Why can `"straße".toUpperCase(Locale.GERMAN)` be longer than the original string?

**Answer:** `ß` expands to `SS`; that is a one-to-many Unicode mapping. The length increases from 6 to 7.

**Question 4.** Does `"STRASSE".toLowerCase(Locale.GERMAN)` return `"straße"`?

**Answer:** No. The result is `"strasse"`; case conversion does not guarantee round-tripping.

**Question 5.** Does `equalsIgnoreCase` take a `Locale` parameter? Does it replace `Collator` in all cases?

**Answer:** It has no locale parameter, and it is not a full language-specific collation tool. Use a comparator matching the requirements.

**Question 6.** Is `"İ".toLowerCase(Locale.ROOT)` guaranteed to be one code point long?

**Answer:** No. The result consists of `i` `U+0069` and combining dot `U+0307`, two code points. In `tr-TR`, it becomes a single `i`.

**Question 7.** If strings have Vietnamese letters with the same visual appearance but different combining mark code points, is lowercasing alone enough for `equals`?

**Answer:** Not necessarily. Normalization to an agreed form, such as NFC, may be required; casing does not automatically normalize all of Unicode.

## 15. Takeaways

- `String.toLowerCase(Locale)` and `toUpperCase(Locale)` can use **language/region** rules; pass an explicit locale when the intent is clear.
- Overloads **without `Locale`** rely on `Locale.getDefault()` and easily make technical identifiers depend on the host machine.
- `Locale.ROOT` is usually the appropriate choice for **locale-independent** case conversion, but does not replace a system's specialized Unicode processing/comparison contract.
- Unicode mappings can be **one-to-many** and **context-dependent**: Turkish `I/İ`, German `ß`, and Greek sigma are key examples.
- Case conversion **does not guarantee length preservation**, **is not reversible**, **does not replace normalization**, and **is not synonymous with collation/case folding**.
- Choose the right `Locale` for user text; test at least Turkish, Greek, and German scenarios before shipping multilingual products to production.

**Official documentation:**

- [Java SE 21 — String, toLowerCase/toUpperCase](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html)
- [Java SE 21 — Locale](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.html)
- [Java SE 21 — Collator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/Collator.html)
- [Java SE 21 — Normalizer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/Normalizer.html)
- [Unicode Standard — Default Case Algorithms](https://www.unicode.org/versions/latest/core-spec/chapter-3/)
