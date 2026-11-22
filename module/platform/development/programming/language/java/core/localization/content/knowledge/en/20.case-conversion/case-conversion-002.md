# The Turkish I Difference: Unicode, Locale, and Case Conversion in Java

## 1. How can a single letter I break a multilingual application?

Java developers commonly know:

```java
"I".toLowerCase(Locale.ENGLISH) // "i"
"i".toUpperCase(Locale.ENGLISH) // "I"
```

However, the rule above **does not hold for all languages**. Turkish (`tr`/`tr-TR`) distinguishes two pairs of letters:

- **I ↔ ı**: uppercase **dotless** I (U+0049) ↔ lowercase **dotless** ı (U+0131).
- **İ ↔ i**: uppercase **dotted** İ (U+0130) ↔ lowercase **dotted** i (U+0069).

Consequently, the result of `String.toLowerCase(locale)` and `String.toUpperCase(locale)` can vary by `Locale`. This bug is commonly known as the **Turkish I problem** in software internationalization.

Practical example: a technical key name `"TITLE"` in a Java program is converted to lowercase. If `"TITLE".toLowerCase()` is used while the server has a Turkish default locale, the result is `"tıtle"`, containing the letter **ı** U+0131, which is **different** from `"title"` containing **i** U+0069.

A `map.get("title")` lookup or `equals` comparison can fail even though the difference is hard to spot visually in a font. The issue is not that Java "mistranslated": we applied **user linguistic rules to a technical identifier that must be language-independent**.

### Lesson objectives

After this lesson, you can:

1. Identify the four Unicode code points `I`, `i`, `İ`, `ı` and the two uppercase/lowercase pairs in Turkish.
2. Distinguish `String.toLowerCase()` (using default locale), `String.toLowerCase(Locale)`, and `Locale.ROOT`.
3. Determine when to convert case **by display language** and when to handle **machine identifiers** independently of locale.
4. Understand the limits of `Character.toLowerCase`, `equalsIgnoreCase`, `Collator`, Unicode normalization, and regex.
5. Write Java 17 tests to reproduce the bug and prevent production incidents.

## 2. Four letters, two pairs: visually similar but different Unicode codes

| Letter | Unicode name | Code point | Role in Turkish |
| --- | --- | --- | --- |
| `I` | LATIN CAPITAL LETTER I | U+0049 | **Dotless uppercase** letter |
| `ı` | LATIN SMALL LETTER DOTLESS I | U+0131 | **Dotless lowercase** letter |
| `İ` | LATIN CAPITAL LETTER I WITH DOT ABOVE | U+0130 | **Dotted uppercase** letter |
| `i` | LATIN SMALL LETTER I | U+0069 | **Dotted lowercase** letter |

These are **four distinct code points**, not four ways of rendering the same character. In poorly supported fonts or hard-to-read consoles, `I` and `İ` may differ by a tiny dot; `i` and `ı` differ by having or lacking a dot.

Diagram of the two pairs:

```text
Turkish:
    UPPER       lowercase
     I    <-->     ı       (dotless)
     İ    <-->     i       (dotted)

Common English rule:
     I    <-->     i

The English pair cannot replace both Turkish pairs.
```

**Do not confuse with Vietnamese diacritics**: Unicode `İ` is not simply an ASCII `I` rendered with a dot by a different font. Both `İ` and `ı` have their own dedicated code points.

### Correct table for Turkish case mapping

With `Locale.forLanguageTag("tr-TR")`:

| Input | `toLowerCase(tr)` | `toUpperCase(tr)` |
| --- | --- | --- |
| `I` (U+0049) | `ı` (U+0131) | `I` (U+0049) |
| `ı` (U+0131) | `ı` (U+0131) | `I` (U+0049) |
| `İ` (U+0130) | `i` (U+0069) | `İ` (U+0130) |
| `i` (U+0069) | `i` (U+0069) | `İ` (U+0130) |

With a language-independent locale like `Locale.ROOT`, `I → i` and `i → I` follow default Unicode rules. However, `İ` when lowercased with `Locale.ROOT` typically becomes **two code points**: `i` (U+0069) followed by **COMBINING DOT ABOVE** (U+0307). This is an example proving that Unicode case conversion is not always a **one code point → one code point** mapping.

## 3. Distinguishing the three ways to call in Java

### 3.1. Without passing a Locale

```java
String lower = "TITLE".toLowerCase();
String upper = "title".toUpperCase();
```

Both zero-argument overloads use the **JVM's default locale** (equivalent to `toLowerCase(Locale.getDefault())` and `toUpperCase(Locale.getDefault())`). Results can depend on the server, CI machine, container, or OS configuration.

This is a problem when the string is not user text, but rather a **variable name, identifier, protocol key, constant, enum name, HTTP header name, database field name**, or a machine code that must remain stable across all machines.

### 3.2. Passing the locale of an actual language

```java
Locale turkish = Locale.forLanguageTag("tr-TR");

String label = "İSTANBUL";
String lower = label.toLowerCase(turkish);
```

For Turkish, `lower` becomes `istanbul` as expected for dotted letters. This is reasonable when processing **natural text of Turkish users**, such as display labels, search, or linguistic matching.

### 3.3. Using `Locale.ROOT` for locale-independent identifiers

```java
String key = "TITLE".toLowerCase(Locale.ROOT);
```

`key` becomes `title` and is not altered by a Turkish, Vietnamese, or English JVM default locale.

**Design principle:** technical identifiers must follow an **invariant canonicalization contract**. For ASCII-only protocols and tokens, `Locale.ROOT` is typically suitable for locale-independent case mapping. For unrestricted Unicode identifiers, `Locale.ROOT` is **not sufficient** as a complete "safe case-folding" system: you also need to specify Unicode normalization, case folding, Unicode version, allowed character lists, and anti-collision/anti-spoofing rules.

## 4. Complete Java 17 program: observing the two letter pairs

Create the file `TurkishIDemo.java`:

```java
import java.util.Locale;
import java.util.stream.Collectors;

public class TurkishIDemo {
    private static final Locale TR =
            Locale.forLanguageTag("tr-TR");

    private static String points(String text) {
        return text.codePoints()
                .mapToObj(cp -> String.format(
                        Locale.ROOT, "U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    public static void main(String[] args) {
        String[] inputs = {
                "I", "i", "\u0130", "\u0131"
        };

        for (String input : inputs) {
            System.out.println(
                    points(input)
                    + " lowerTR=" + points(input.toLowerCase(TR))
                    + " upperTR=" + points(input.toUpperCase(TR)));
        }

        System.out.println("TITLE root=" +
                points("TITLE".toLowerCase(Locale.ROOT)));
        System.out.println("TITLE tr=" +
                points("TITLE".toLowerCase(TR)));
        System.out.println("title tr upper=" +
                points("title".toUpperCase(TR)));
    }
}
```

Save source as UTF-8 and run with JDK 17+:

```bash
javac -encoding UTF-8 TurkishIDemo.java
java TurkishIDemo
```

**Deterministic stdout**, using U+ codes to avoid font or terminal encoding dependencies:

```text
U+0049 lowerTR=U+0131 upperTR=U+0049
U+0069 lowerTR=U+0069 upperTR=U+0130
U+0130 lowerTR=U+0069 upperTR=U+0130
U+0131 lowerTR=U+0131 upperTR=U+0049
TITLE root=U+0074 U+0069 U+0074 U+006C U+0065
TITLE tr=U+0074 U+0131 U+0074 U+006C U+0065
title tr upper=U+0054 U+0130 U+0054 U+004C U+0045
```

Explanation:

- `I` (U+0049) converts to `ı` (U+0131) when using `TR`.
- `i` (U+0069) converts to `İ` (U+0130) when using `TR`.
- `"TITLE".toLowerCase(Locale.ROOT)` has second code point U+0069.
- `"TITLE".toLowerCase(TR)` has second code point U+0131.
- `"title".toUpperCase(TR)` has second code point U+0130 instead of ASCII `I`.

Because `String.equals` compares sequences of code units, `"title".equals("tıtle")` is `false`. These are **two different strings**, even though small UI fonts may make readers think they look the same.

## 5. Production bug: technical identifier altered by JVM default

Suppose an application uses a `Map` to look up an attribute named `"title"`:

```java
Map<String, String> attributes = Map.of(
        "title", "Java Guide");
String rawKey = "TITLE";
String normalized = rawKey.toLowerCase();
String title = attributes.get(normalized);
```

This is an illustrative snippet inside a method. If the JVM default locale is Turkish, `normalized` is `tıtle`, so `Map.get` returns `null`. When running in an environment with a different default locale, it may turn into `title` and work.

### 5.1. Standalone Java program reproducing the bug

File `TurkishMapBugDemo.java`:

```java
import java.util.Locale;
import java.util.Map;

public class TurkishMapBugDemo {
    public static void main(String[] args) {
        Locale original = Locale.getDefault();
        try {
            // Simulation only in a single-threaded demo program.
            Locale.setDefault(Locale.forLanguageTag("tr-TR"));

            Map<String, String> data = Map.of(
                    "title", "FOUND");

            String input = "TITLE";

            String unsafeKey = input.toLowerCase();
            String stableKey = input.toLowerCase(Locale.ROOT);

            System.out.println("unsafeFound=" +
                    (data.get(unsafeKey) != null));
            System.out.println("stableFound=" +
                    (data.get(stableKey) != null));
            System.out.println("unsafeEqualsTitle=" +
                    unsafeKey.equals("title"));
            System.out.println("stableEqualsTitle=" +
                    stableKey.equals("title"));
        } finally {
            Locale.setDefault(original);
        }
    }
}
```

Run with JDK 17+:

```bash
javac -encoding UTF-8 TurkishMapBugDemo.java
java TurkishMapBugDemo
```

Stdout:

```text
unsafeFound=false
stableFound=true
unsafeEqualsTitle=false
stableEqualsTitle=true
```

**Why restore the default locale?** `Locale.setDefault` mutates **JVM-wide** state. The demo uses `try/finally` to return to the original environment, but this **does not make the operation thread-safe**. Never change `Locale.setDefault(...)` per request in a web server: concurrent users may observe different results and third-party libraries are affected too.

In real applications, the proper fix is `toLowerCase(Locale.ROOT)` where technical keys are defined, rather than forcing the server's default locale to English to hide the bug.

### 5.2. Areas commonly affected

- Normalizing keys from input/JSON config before `Map` lookups.
- Converting enum names, status codes, parser tokens, protocol field names.
- Matching key names when importing/exporting CSV, configuration, or metadata.
- Path/filename checking logic using lowercased strings; you must know the OS and filesystem rules.
- Comparing strings used as identifiers stored across multiple JVMs with different locales.
- Generating column names, parameters, or lookup keys by concatenating an English word containing I/i.

**Do not fix this by forcing all user text to use `Locale.ROOT`.** For Turkish sentences, that itself is a localization bug. The fix is to identify **scope**: machine identifiers need locale-independent stability, whereas natural-language text needs the appropriate locale.

## 6. Locale-sensitive vs. locale-independent case conversion: when to use which?

| Context | Approach | Reason |
| --- | --- | --- |
| Turkish UI labels | `toUpperCase(trLocale)` / `toLowerCase(trLocale)` | Respects I/İ/ı/i rules |
| Turkish natural text search | Locale-sensitive collation/matching per requirements | Linguistically meaningful comparison |
| Internal ASCII key `TITLE` | `toLowerCase(Locale.ROOT)` or canonical key policy | Consistent across environments |
| Enum codes, statuses, protocol tokens | Per protocol spec; typically ASCII/ROOT | User locale must not affect machine contracts |
| Personal names and place names | Do not alter original spelling when storing; transform only display copies when needed | Case may carry linguistic meaning |
| Case-insensitive usernames | Explicit Unicode/case folding/normalization policy | `Locale.ROOT` alone does not guarantee collision prevention |
| Passwords or secret tokens | Do not auto-lowercase | Can alter credentials and weaken uniqueness |
| HTML/XML/URL/schema identifiers | Follow each format's exact spec | Do not apply user locale to syntax codes |

**Boundary example:** Displaying the Turkish heading `"İSTANBUL"` as `"istanbul"` is a linguistic matter. Converting the JSON key `"TITLE"` to `"title"` is a technical contract matter. Two actions that look identical in code must **choose different locales**.

## 7. The story of İ: one code point can become two

This is a subtle issue even when not using a Turkish locale.

`İ` is U+0130, Latin capital letter I with dot above. Under Unicode default case conversion rules, when lowercased in a locale-independent manner, it can produce the sequence:

```text
U+0130 LATIN CAPITAL LETTER I WITH DOT ABOVE
            |
            | lower-case default (Locale.ROOT)
            v
U+0069 LATIN SMALL LETTER I
U+0307 COMBINING DOT ABOVE
```

In Turkish, however, the result is a single code point `i` U+0069, because the dot is already a dedicated component of the `İ ↔ i` pair. Thus, case conversion can **change the number of Unicode code points** and the `String` length.

### Java 17 example checking length and code points

File `DottedIExpansionDemo.java`:

```java
import java.util.Locale;

public class DottedIExpansionDemo {
    public static void main(String[] args) {
        String capitalDottedI = "\u0130";

        String root =
                capitalDottedI.toLowerCase(Locale.ROOT);
        String turkish =
                capitalDottedI.toLowerCase(
                        Locale.forLanguageTag("tr-TR"));

        System.out.println("originalUnits=" +
                capitalDottedI.length());
        System.out.println("rootUnits=" + root.length());
        System.out.println("turkishUnits=" +
                turkish.length());

        System.out.println("rootCodePoints=" +
                root.codePointCount(0, root.length()));
        System.out.println("turkishCodePoints=" +
                turkish.codePointCount(0, turkish.length()));

        System.out.println("rootIsPlainI=" +
                root.equals("i"));
        System.out.println("turkishIsPlainI=" +
                turkish.equals("i"));
    }
}
```

```bash
javac -encoding UTF-8 DottedIExpansionDemo.java
java DottedIExpansionDemo
```

Stdout per Unicode/Java 17 rules:

```text
originalUnits=1
rootUnits=2
turkishUnits=1
rootCodePoints=2
turkishCodePoints=1
rootIsPlainI=false
turkishIsPlainI=true
```

The result `rootIsPlainI=false` is not because Java failed; it preserves the dot information as a combining mark per default case mapping.

**Consequence:** Do not assume `s.toLowerCase(locale).length() == s.length()`. Do not use original UTF-16 indices to point directly into the string after case conversion. When analyzing Unicode, distinguish code units, code points, and grapheme clusters.

## 8. `Character.toLowerCase` differs from `String.toLowerCase(Locale)`

Java has methods on `Character`:

```java
int lowercaseCodePoint = Character.toLowerCase(0x0049);
int uppercaseCodePoint = Character.toUpperCase(0x0069);
```

The `Character.toLowerCase(int)` and `toUpperCase(int)` APIs perform **simple Unicode case mapping** for a single code point and **do not accept a `Locale` parameter**. They do not perform all context/language-dependent string transformations and cannot directly represent mappings from one code point to **two** code points.

Meanwhile, `String.toLowerCase(Locale)` / `String.toUpperCase(Locale)` can:

- Use locale-specific rules such as `tr-TR` and `az`.
- Depend on context within the string for certain languages.
- Expand one character into multiple characters (for example, specific Unicode uppercase/lowercase rules).

**Do not** use a `Character.toLowerCase(s.charAt(i))` loop to "optimize" `String.toLowerCase(trLocale)`. It both omits the locale and can mishandle code points outside the BMP when iterating char by char. Use the string API with a locale or an appropriate Unicode library as required.

### Example not to write

```java
StringBuilder lower = new StringBuilder();
for (int i = 0; i < text.length(); i++) {
    lower.append(Character.toLowerCase(text.charAt(i)));
}
```

This is an illustrative snippet inside a method with a `text` variable. It does not follow Turkish I rules and does not handle multi-code-point mappings fully. When lowercasing user text, call `text.toLowerCase(selectedLocale)`.

## 9. Does `equalsIgnoreCase` really "understand Turkish"?

`String.equalsIgnoreCase` **does not accept a `Locale`**. Per the Java specification, it performs case-insensitive comparison based on `Character`/Unicode per code point, **not following Turkish's specific letter-pair system**.

Therefore, you must not use the result:

```java
boolean same = a.equalsIgnoreCase(b);
```

as confirmation that two Turkish words are the same under linguistic rules. Similarly, `String.CASE_INSENSITIVE_ORDER` and `compareToIgnoreCase` are not per-locale collation algorithms.

Note two types of questions with different meanings:

1. **Are these the same machine key after canonicalization per contract?** Use a clearly defined canonicalization, such as ASCII-only keys + `Locale.ROOT`.
2. **Are these the same word when a Turkish user searches regardless of case?** This requires **locale-aware** matching, potentially using `Collator` or a search engine configured with Turkish collation.

A system handling Turkish personal names, lists, or dictionaries must consider distinguishing **I/ı** and **İ/i**; do not lump them all into one group just because they look like the letter I.

## 10. `Collator`: comparing strings by language

`java.text.Collator` applies locale-based text comparison rules. It does not completely replace a search engine, but is suited for sorting and comparing words when local cultural rules are required.

Initializing for Turkish:

```java
Collator collator = Collator.getInstance(
        Locale.forLanguageTag("tr-TR"));
collator.setStrength(Collator.PRIMARY);
```

`PRIMARY` can ignore secondary-level differences such as case within the context of the locale's collation rules. For Turkish, dotless I and dotted i belong to **two separate letter pairs**, so using `Collator` has different semantics from forcing all characters to lowercase with `Locale.ROOT`.

### Standalone Java 17 example

File `TurkishCollationDemo.java`:

```java
import java.text.Collator;
import java.util.Locale;

public class TurkishCollationDemo {
    public static void main(String[] args) {
        Locale turkish = Locale.forLanguageTag("tr-TR");
        Collator collator = Collator.getInstance(turkish);
        collator.setStrength(Collator.PRIMARY);

        System.out.println("I-dotlessI=" +
                (collator.compare("I", "\u0131") == 0));
        System.out.println("dottedI-i=" +
                (collator.compare("\u0130", "i") == 0));
        System.out.println("I-i=" +
                (collator.compare("I", "i") == 0));
        System.out.println("i-dotlessI=" +
                (collator.compare("i", "\u0131") == 0));
    }
}
```

```bash
javac -encoding UTF-8 TurkishCollationDemo.java
java TurkishCollationDemo
```

With JDK 17's common Turkish collation rules (provider supporting Turkish), the **expected relationships** are:

```text
I-dotlessI=true
dottedI-i=true
I-i=false
i-dotlessI=false
```

`Collator` results depend on the provider and locale data; if the application supports multiple JDK/CLDR/providers, you must **test directly on the deployment runtime**. This expectation table illustrates the two-pair principle, not a guarantee across every Java configuration with custom providers.

**Do not share a mutable `Collator` and concurrently change its strength/locale across requests**. Create separate instances, clone when appropriate, or use a safe caching strategy; use `CollationKey` when optimizing comparisons across many strings.

### Comparison is not synonymous with search

`Collator` handles locale-based comparison/sorting. Full-text search may also need tokenizers, language analyzers, Unicode normalization, prefix matching design, and alignment with database collation. Do not assume `Collator.PRIMARY` is a complete Turkish search engine for every data domain.

## 11. Unicode normalization: the dot also has a combining form

Some Unicode text has **composed** and **decomposed** representations. For the letter İ U+0130, the canonical decomposed form is:

```text
composed:   U+0130            (İ)
decomposed: U+0049 U+0307     (I + COMBINING DOT ABOVE)
```

These two strings can look identical, yet `String.equals` will differ before normalization. `java.text.Normalizer` lets you apply NFC/NFD.

Example:

```java
String composed = "\u0130";
String decomposed = "I\u0307";
boolean before = composed.equals(decomposed); // false

String normalized = Normalizer.normalize(
        decomposed, Normalizer.Form.NFC);
boolean after = composed.equals(normalized);   // true
```

This is an illustrative snippet inside a method, requiring `import java.text.Normalizer`.

**Normalization and case conversion are two different tasks:**

- **Normalization** handles equivalent/compatibly related Unicode representations according to the chosen form.
- **Case conversion** applies uppercase/lowercase rules, which may depend on locale.
- **Collation** determines linguistic sorting/comparison relationships and does not necessarily produce a single canonical string.
- **Case folding** is a Unicode mechanism for caseless matching; full folding rules differ from simple lowercasing and are not synonymous with Turkish-specific casing.

In a search system, **the order of normalization/case-conversion can affect results** with combining marks. Build and test a fixed pipeline for each data type. Do not manually strip U+0307 just to "fix Turkish I bugs" because that can change the meaning of characters in other languages.

### 11.1. Code points and grapheme clusters

`"i\u0307"` contains two Unicode code points yet typically renders as a single dotted i. `String.length()` returns the number of UTF-16 code units; `String.codePointCount` returns the number of code points; neither necessarily reflects the number of user-perceived characters.

When highlighting search results or using start/end indices of a string after case conversion, remember that **length can change** due to mappings like `İ → i + combining dot`. Do not use indices computed on the pre-conversion string to slice the post-conversion string.

## 12. Regex does not automatically know the user's locale

Java has flags such as:

- `Pattern.CASE_INSENSITIVE`: enables case-insensitive matching (by default mainly applies to ASCII in Java regex).
- `Pattern.UNICODE_CASE`: combined with `CASE_INSENSITIVE`, enables Unicode-aware case-insensitive matching.
- `Pattern.UNICODE_CHARACTER_CLASS`: changes the meaning of certain predefined character classes according to Unicode.

These flags **do not accept a `Locale`**, so they are not a way to specify `tr-TR` rules for every I/i letter. For Turkish search patterns, you must test the `I/ı` and `İ/i` pairs, and consider libraries/engines that perform locale-aware case-insensitive matching.

Another mistake is running `regex.matcher(text.toLowerCase(Locale.ROOT))` and assuming you can use the UTF-16 offsets on the original text: lowercasing can alter length, especially with `İ`. For highlighting, design an offset mapping or avoid transforming input text in a way that breaks positions.

Regex does not replace collation, tokenization, or normalization policies.

## 13. Production design: separating text and identifiers

### 13.1. Domain layer: preserve original data

- Personal names, place names, user content: store the exact original casing per contract; do not auto-uppercase/lowercase on write.
- If a search index is needed, create a **separate** canonical field with the algorithm version; do not overwrite the original.
- If uniqueness checks are needed, align rules between the Java application and database collation to avoid one side treating `I` and `i` as equal while the other treats them as distinct.

### 13.2. UI layer: pass `Locale` explicitly

```java
Locale displayLocale = Locale.forLanguageTag("tr-TR");
String shown = source.toUpperCase(displayLocale);
```

The locale can come from user preferences, profiles, or negotiation with supported locales and fallbacks. Do not use a single global JVM default for all users in a multi-locale web server.

### 13.3. Protocol layer: locale-independent machine contract

For ASCII-only technical keys:

```java
String canonicalKey(String input) {
    return input.toLowerCase(Locale.ROOT);
}
```

This snippet illustrates a method in a class. It does not automatically validate ASCII or prevent spoofing; check the allowed character set if the protocol requires restrictions. If used for security-sensitive identifiers, add validation, normalization, and an explicit uniqueness policy; do not rely on `toLowerCase(Locale.ROOT)` alone as a security guarantee.

**Do not "fix" by setting the entire JVM's default locale to `Locale.US`**. That only masks API calls missing a locale, and can cause Turkish translations or user date/number formatters to behave incorrectly.

### 13.4. Data layer: database and search engine

A system may simultaneously process:

- Java `String.equalsIgnoreCase` using simple locale-neutral rules;
- Database `tr-TR` collation using Turkish semantics;
- Search engine using Unicode case folding;
- Frontend JavaScript `toLocaleLowerCase("tr-TR")`.

These components **do not necessarily produce identical results**. Choose a contract for each data type, especially login identifiers, emails, display names, and lookup keys. Do not assume the same letter I definitely maps identically across all layers.

For user data, case-insensitive handling of names typically must follow a specific locale and consider normalized forms; for technical IDs, use strict canonicalization and character sets.

## 14. Reproducible tests to prevent regressions

### 14.1. Matrix of required values

| Input | Locale | Expected behavior |
| --- | --- | --- |
| `"I"` | `tr-TR` lowercase | `"ı"` (U+0131) |
| `"i"` | `tr-TR` uppercase | `"İ"` (U+0130) |
| `"İ"` | `tr-TR` lowercase | `"i"` (U+0069) |
| `"ı"` | `tr-TR` uppercase | `"I"` (U+0049) |
| `"TITLE"` | `Locale.ROOT` lowercase | `"title"` |
| `"TITLE"` | `tr-TR` lowercase | `"tıtle"` |
| `"İ"` | `Locale.ROOT` lowercase | `"i\u0307"` (2 code points) |
| `"İ"` | `tr-TR` lowercase | `"i"` (1 code point) |
| `"I"` and `"i"` | `equalsIgnoreCase` | Do not conclude this is Turkish comparison |
| `"I"` and `"ı"` | `Collator tr-TR` | Verify per locale/provider collation |

### 14.2. Runnable Java 17: assertions independent of default locale

File `TurkishIAssertions.java`:

```java
import java.util.Locale;

public class TurkishIAssertions {
    private static final Locale TR =
            Locale.forLanguageTag("tr-TR");

    private static void check(boolean ok, String label) {
        if (!ok) {
            throw new AssertionError(label);
        }
        System.out.println("PASS " + label);
    }

    public static void main(String[] args) {
        check("I".toLowerCase(TR).equals("\u0131"),
                "I-to-dotless-i");
        check("i".toUpperCase(TR).equals("\u0130"),
                "i-to-dotted-I");
        check("\u0130".toLowerCase(TR).equals("i"),
                "dotted-I-to-i");
        check("\u0131".toUpperCase(TR).equals("I"),
                "dotless-i-to-I");

        check("TITLE".toLowerCase(Locale.ROOT).equals("title"),
                "machine-key");
        check("\u0130".toLowerCase(Locale.ROOT)
                        .equals("i\u0307"),
                "unicode-expansion");
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 TurkishIAssertions.java
java TurkishIAssertions
```

Stdout:

```text
PASS I-to-dotless-i
PASS i-to-dotted-I
PASS dotted-I-to-i
PASS dotless-i-to-I
PASS machine-key
PASS unicode-expansion
```

If an assertion fails, it is a signal to review the runtime, source code, expected rules, or API used. When running tests across environments, specify JDK 17+ and the locale/provider set; do not test only on a developer machine with an English default.

### 14.3. Testing the JVM default locale in isolation

Test in a separate program (not running concurrently with tests depending on the JVM default) to demonstrate that `"TITLE".toLowerCase()` is sensitive to the default locale. Do not change `Locale.setDefault` inside a server request or an unisolated parallel unit test suite.

For web apps, test the full path: HTTP header/profile locale → locale resolver → display case mapping. Also test that machine keys/codes still canonicalize with `Locale.ROOT` even when the user selects Turkish.

### 14.4. When handling diverse Unicode text

Check the following forms:

- `İ` (U+0130) vs. `I + U+0307` (decomposed);
- `i + U+0307` after default case mapping;
- `ı` (U+0131) vs. `i` (U+0069);
- words containing multiple I/i letters at the beginning, middle, and end;
- supplementary characters and combining marks if the pipeline works across all of Unicode;
- text displayed under fonts/terminals lacking full support.

Tests comparing results by code point (e.g., printing `U+0131`) are usually more reliable than merely inspecting characters in a terminal.

## 15. Frequently asked questions

**Question 1.** Why does `"TITLE".toLowerCase()` sometimes not become `"title"`?

**Answer:** The locale-less overload uses the JVM default locale. In Turkish, `I` lowercases to dotless `ı`, producing `tıtle`.

**Question 2.** If we need to lowercase variable names, protocol keys, or machine identifiers, what should we do?

**Answer:** Use a locale-independent contract; typically `toLowerCase(Locale.ROOT)` for ASCII identifiers, plus protocol validation. Do not use the viewer's locale.

**Question 3.** If a username is Turkish, should we always use `Locale.ROOT`?

**Answer:** No. For linguistic display/casing operations, use an appropriate locale like `tr-TR`. For login/uniqueness, define a dedicated canonicalization rule consistent across all systems.

**Question 4.** Does `Character.toLowerCase('I')` understand Turkish ı?

**Answer:** It has no locale parameter and thus cannot apply all language-specific case mappings. Use `String.toLowerCase(trLocale)` when converting a whole string in Turkish.

**Question 5.** Can `equalsIgnoreCase` replace `Collator`?

**Answer:** No. `equalsIgnoreCase` does not accept a locale, whereas `Collator` relies on linguistic comparison rules. They serve different goals.

**Question 6.** Why can `İ` become two code points under default lowercasing?

**Answer:** Unicode default mapping preserves `i` plus combining dot above `U+0307`. Under Turkish rules, `İ` converts to a single `i`.

**Question 7.** Should we apply `Normalizer.NFC` and consider Turkish I solved?

**Answer:** No. Normalization handles Unicode representations, not choosing the right language case rules. You still need to decide on locale and case comparison/collation.

**Question 8.** Why not call `Locale.setDefault(tr)` for each HTTP request?

**Answer:** Default locale is shared JVM state. Other requests can be affected; pass `Locale` explicitly into text processing instead.

**Question 9.** Does regex with `CASE_INSENSITIVE | UNICODE_CASE` guarantee Turkish matching?

**Answer:** No. These flags take no locale parameter; explicitly test the I/ı and İ/i pairs or use an appropriate locale-aware matching mechanism.

**Question 10.** Can `String.toLowerCase(Locale.ROOT)` serve as a security guarantee for all Unicode usernames?

**Answer:** No. It is not a comprehensive Unicode full case folding/normalization/security profile; you must also design allowed-character, collision, and anti-spoofing rules.

## 16. Takeaways

- Turkish has **two letter pairs**: **I ↔ ı** and **İ ↔ i**. Do not treat every letter resembling I/i as a single pair.
- Zero-argument `String.toLowerCase()` and `toUpperCase()` use the **JVM default locale**, which can corrupt technical keys in `tr-TR` environments.
- For **Turkish natural text**, use `toLowerCase(trLocale)` or `toUpperCase(trLocale)` when business logic genuinely requires case conversion.
- For **language-independent identifiers**, design a stable canonicalization (typically `Locale.ROOT` for ASCII) with validation; do not use the user's locale.
- `String` supports locale-dependent mappings and can change length; `Character` only offers simple per-code-point mapping, insufficient for all cases.
- `equalsIgnoreCase`/regex Unicode flags do not automatically replace **locale-aware collation**; use `Collator` or a suitably configured search mechanism when handling Turkish words.
- `Normalizer`, case conversion, case folding, and collation are distinct operations. Clearly define the pipeline and test with Unicode code points.
- Do not change the JVM-wide default locale per request. **Pass locale explicitly**, and test both English/ROOT and Turkish in Java 17.

### Java 17 and Unicode references

- [Oracle Java 17 — String: toLowerCase, toUpperCase, equalsIgnoreCase](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [Oracle Java 17 — Locale](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html)
- [Oracle Java 17 — Collator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Collator.html)
- [Oracle Java 17 — Character](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html)
- [Oracle Java 17 — Normalizer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html)
- [Unicode Standard — Special Casing](https://www.unicode.org/Public/UCD/latest/ucd/SpecialCasing.txt)
