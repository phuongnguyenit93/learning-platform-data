# The Turkish I Case in Java

Case conversion might seem as simple as calling `toLowerCase()` or `toUpperCase()`. However, Turkish has special rules for the letter **I**: the capital **I** without a dot above pairs with the lowercase dotless **ı**; the capital dotted **İ** pairs with the lowercase dotted **i**. If the wrong locale is used, an application can misconvert personal names, words, search keys, or identifiers.

In Java, three distinct questions must be kept separate:

1. **Which language's readers is the case conversion for?** Use `String.toLowerCase(Locale)` / `toUpperCase(Locale)` with the appropriate locale.
2. **Normalizing technical strings independently of language?** Use a fixed policy—typically `Locale.ROOT` for Unicode data if the convention permits, or explicit ASCII rules if the protocol specifies ASCII.
3. **Under which rules are two strings equal?** `equals()`, `equalsIgnoreCase()`, and language-specific comparisons have different contracts. In particular, `equalsIgnoreCase()` **does not perform Turkish-specific comparison**.

## 1. Four easily confused I/i letters

| Character | Unicode code point | Unicode name | Visual cue |
| --- | --- | --- | --- |
| `I` | `U+0049` | LATIN CAPITAL LETTER I | Capital **dotless** |
| `i` | `U+0069` | LATIN SMALL LETTER I | Lowercase **dotted** |
| `İ` | `U+0130` | LATIN CAPITAL LETTER I WITH DOT ABOVE | Capital **dotted** |
| `ı` | `U+0131` | LATIN SMALL LETTER DOTLESS I | Lowercase **dotless** |

Turkish letter pairing rules:

~~~text
I  <-->  ı     (dotless)
İ  <-->  i     (dotted)
~~~

In English, many people are accustomed to the pair `I ↔ i`. Applying that habit to every language breaks Turkish text.

For example, `"istanbul"` uppercased with the Turkish locale becomes `"İSTANBUL"`, starting with `İ`. Similarly, the letter `I` in a Turkish word lowercases to `ı`, not `i`. Do not rely on visual appearance alone when reading logs; you can print code points in `U+....` form to verify.

## 2. Java's toLowerCase/toUpperCase are affected by Locale

Java has two main overload groups:

~~~java
text.toLowerCase();
text.toUpperCase();

text.toLowerCase(locale);
text.toUpperCase(locale);
~~~

These are **illustrative calls**, assuming `text` is a `String` and `locale` is a `java.util.Locale`.

- **No arguments:** `toLowerCase()` and `toUpperCase()` use the JVM's **default locale**, namely `Locale.getDefault()`. Results can differ when the application runs on a machine or locale configuration with different settings.
- **Passing an explicit locale:** `toLowerCase(Locale)` and `toUpperCase(Locale)` use the case rules of the specified locale. This is the recommended approach when consistent results are required.
- `Locale.forLanguageTag("tr-TR")` creates the Turkish locale used in the examples. `Locale.ROOT` is the language-neutral locale, useful for many technical string-processing operations.

Example:

~~~java
import java.util.Locale;

// Snippet inside a Java method:
Locale tr = Locale.forLanguageTag("tr-TR");
Locale root = Locale.ROOT;

System.out.println("TITLE".toLowerCase(root)); // title
System.out.println("TITLE".toLowerCase(tr));   // tıtle
System.out.println("istanbul".toUpperCase(root)); // ISTANBUL
System.out.println("istanbul".toUpperCase(tr));   // İSTANBUL
~~~

The four `println` statements produce the illustrative outputs shown in the comments. In `tıtle`, the second character is `ı (U+0131)`. In `İSTANBUL`, the first character is `İ (U+0130)`.

**Do not use no-argument `toLowerCase()` to generate technical keys** when consistent results are needed everywhere. If the JVM uses a Turkish locale, `"TITLE".toLowerCase()` can become `"tıtle"`; in an English environment, it can become `"title"`. The two strings are unequal under `equals()`, and their `hashCode()` values may differ. This can affect key names, routing, authorization, or lookups if the design relies on a fixed lowercasing rule.

### Code point conversion table under the two locales

The following values are verified with Java:

| Input character | `toLowerCase(Locale.ROOT)` | `toLowerCase(tr-TR)` | `toUpperCase(Locale.ROOT)` | `toUpperCase(tr-TR)` |
| --- | --- | --- | --- | --- |
| `I (U+0049)` | `i (U+0069)` | `ı (U+0131)` | `I (U+0049)` | `I (U+0049)` |
| `i (U+0069)` | `i (U+0069)` | `i (U+0069)` | `I (U+0049)` | `İ (U+0130)` |
| `İ (U+0130)` | **`i + U+0307`** (2 code points) | `i (U+0069)` | `İ (U+0130)` | `İ (U+0130)` |
| `ı (U+0131)` | `ı (U+0131)` | `ı (U+0131)` | `I (U+0049)` | `I (U+0049)` |

Subtle detail: `"İ".toLowerCase(Locale.ROOT)` does not yield a single `i`; the result is **`i` followed by the combining dot `U+0307`**. Therefore, `String`-level case conversion can **change the number of code points and `length()`**. Never assume 1 input character always maps to 1 output character.

## 3. Standalone Java 17+ example to inspect exact code points

To avoid depending on console fonts (where `I/i/İ/ı` can be hard to distinguish), this program prints Unicode code points in hex. Save it to **TurkishIDemo.java**:

~~~java
import java.util.Locale;
import java.util.stream.Collectors;

public class TurkishIDemo {
    private static String codePoints(String text) {
        return text.codePoints()
                .mapToObj(cp -> String.format(Locale.ROOT, "U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    public static void main(String[] args) {
        Locale root = Locale.ROOT;
        Locale tr = Locale.forLanguageTag("tr-TR");

        String[] letters = {"I", "i", "\u0130", "\u0131"};
        for (String letter : letters) {
            System.out.printf(
                    "%s | ROOT lower=%s | TR lower=%s | ROOT upper=%s | TR upper=%s%n",
                    codePoints(letter),
                    codePoints(letter.toLowerCase(root)),
                    codePoints(letter.toLowerCase(tr)),
                    codePoints(letter.toUpperCase(root)),
                    codePoints(letter.toUpperCase(tr)));
        }

        System.out.println("TITLE ROOT lower = "
                + codePoints("TITLE".toLowerCase(root)));
        System.out.println("TITLE TR lower = "
                + codePoints("TITLE".toLowerCase(tr)));
        System.out.println("istanbul ROOT upper = "
                + codePoints("istanbul".toUpperCase(root)));
        System.out.println("istanbul TR upper = "
                + codePoints("istanbul".toUpperCase(tr)));

        System.out.println("I ignoreCase i = "
                + "I".equalsIgnoreCase("i"));
        System.out.println("I ignoreCase dotless = "
                + "I".equalsIgnoreCase("\u0131"));
        System.out.println("I ignoreCase dottedCapital = "
                + "I".equalsIgnoreCase("\u0130"));

        System.out.println("TR lower I equals lower i = "
                + "I".toLowerCase(tr).equals("i".toLowerCase(tr)));
        System.out.println("TR lower I equals lower dotless = "
                + "I".toLowerCase(tr).equals("\u0131".toLowerCase(tr)));
        System.out.println("ROOT lower dotted capital length = "
                + "\u0130".toLowerCase(root).length());
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac -encoding UTF-8 TurkishIDemo.java
java TurkishIDemo
~~~

**Stdout:**

~~~text
U+0049 | ROOT lower=U+0069 | TR lower=U+0131 | ROOT upper=U+0049 | TR upper=U+0049
U+0069 | ROOT lower=U+0069 | TR lower=U+0069 | ROOT upper=U+0049 | TR upper=U+0130
U+0130 | ROOT lower=U+0069 U+0307 | TR lower=U+0069 | ROOT upper=U+0130 | TR upper=U+0130
U+0131 | ROOT lower=U+0131 | TR lower=U+0131 | ROOT upper=U+0049 | TR upper=U+0049
TITLE ROOT lower = U+0074 U+0069 U+0074 U+006C U+0065
TITLE TR lower = U+0074 U+0131 U+0074 U+006C U+0065
istanbul ROOT upper = U+0049 U+0053 U+0054 U+0041 U+004E U+0042 U+0055 U+004C
istanbul TR upper = U+0130 U+0053 U+0054 U+0041 U+004E U+0042 U+0055 U+004C
I ignoreCase i = true
I ignoreCase dotless = true
I ignoreCase dottedCapital = true
TR lower I equals lower i = false
TR lower I equals lower dotless = true
ROOT lower dotted capital length = 2
~~~

Key results:

1. The `U+0049` line proves `I` becomes `i` with `ROOT` but `ı` with `tr-TR`.
2. The `U+0069` line proves `i` becomes `I` with `ROOT` but `İ` with `tr-TR`.
3. The `U+0130` line proves lowercasing can produce **two code points** when using `ROOT`.
4. `equalsIgnoreCase()` returns `true` for all three comparisons with `I`, whereas Turkish lowercasing rules distinguish `I` from `i`.
5. Therefore, a feature that needs "Turkish case-insensitive equality" **cannot default to `equalsIgnoreCase()`**.

The source code uses escapes `\u0130` and `\u0131` to represent the two special characters without relying on keyboard input or fonts; the actual values remain the two corresponding Unicode code points.

## 4. Why can equalsIgnoreCase() be surprising?

`String.equalsIgnoreCase()` is a **case-insensitive content comparison according to Java's rules**, takes no `Locale`, and does not apply Turkish rules when comparing. By the API contract, `Character`'s simple case mappings are used to determine whether characters are equivalent ignoring case.

In modern Java, all four values `I`, `i`, `İ`, `ı` can be treated as pairwise equal by `equalsIgnoreCase()`. That **differs** from the true Turkish letter pairs:

~~~text
In Turkish:
    I  ↔  ı
    İ  ↔  i

With String.equalsIgnoreCase:
    I, i, İ, ı can be treated as equivalent,
    so this comparison does not separate the two Turkish pairs.
~~~

Example:

~~~java
Locale tr = Locale.forLanguageTag("tr-TR");

System.out.println("I".equalsIgnoreCase("i")); // true
System.out.println("I".toLowerCase(tr)
        .equals("i".toLowerCase(tr)));         // false
~~~

This is an **illustrative code snippet** and should be placed in a method with `Locale` imported.

There is no contradiction: **each API has a different contract**. `equalsIgnoreCase()` does not promise language-specific full Unicode case folding; `toLowerCase(tr)` is designed for converting case according to the passed locale's rules.

### Further distinction from equals(), compareToIgnoreCase()

- `equals()` compares the UTF-16 code unit sequence **literally**. `"I".equals("i")` returns `false`.
- `equalsIgnoreCase()` ignores case using Java's rules and is **not locale-sensitive**.
- `compareToIgnoreCase()` and `String.CASE_INSENSITIVE_ORDER` use Java's case-insensitive ordering and **do not replace Turkish sorting/matching**.
- `java.text.Collator` provides locale-aware text comparison, including language *collation* rules. However, choosing strength `PRIMARY`, `SECONDARY`, or `TERTIARY` also affects diacritics and other differences; do not assume every `Collator` configuration is an exact equivalent of "ignore case."

If the product requirement is to compare or sort Turkish names, clearly specify whether diacritics are distinguished, how Unicode normalization is handled, and which collation configuration fits, then **test on native text**.

## 5. Case conversion for display content vs. technical keys

### Case A: text for Turkish users

When displaying text, building labels, or transforming data per Turkish spelling rules, choose the locale explicitly:

~~~java
Locale turkish = Locale.forLanguageTag("tr-TR");
String upper = "istanbul".toUpperCase(turkish); // "İSTANBUL"
String lower = "I".toLowerCase(turkish);        // "ı"
~~~

This is an **illustrative code snippet** to place inside a Java method. Set the locale from the real language configuration of the data or user, rather than inferring it solely from the server's physical location.

### Case B: language-independent technical keys, protocol keywords, or field names

Suppose a protocol defines keywords `"TITLE"` and `"title"` as equivalent regardless of user language. If normalized using the JVM's default locale, a machine configured with `tr-TR` could produce `"tıtle"` and fail to match the key `"title"`.

Common solution:

~~~java
Locale root = Locale.ROOT;
String key = "TITLE".toLowerCase(root);
System.out.println(key.equals("title")); // true
~~~

**Important note:** `Locale.ROOT` is a language-independent choice, but it **does not by itself solve all Unicode identifier rules or every form of case folding**. If a standard/protocol accepts only ASCII, it may be better to **validate that the data contains only ASCII** and apply the specified ASCII case rules. For domain names, email addresses, usernames, security identifiers, protocol formats, and validation rules, follow **that domain's specific standard**; do not assume a single `toLowerCase(Locale.ROOT)` is enough to canonicalize arbitrary Unicode data.

### Case C: lookup keys defined as "Turkish case-insensitive"

A straightforward approach when the application rule **genuinely** compares by Turkish lowercasing results: build canonical keys using the **same locale** before inserting and before looking up.

~~~java
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;

// Illustrative snippet inside a method:
Locale tr = Locale.forLanguageTag("tr-TR");
Map<String, String> names = new HashMap<>();

names.put("I".toLowerCase(tr), "dotless pair");
names.put("İ".toLowerCase(tr), "dotted pair");

System.out.println(names.get("ı".toLowerCase(tr))); // dotless pair
System.out.println(names.get("i".toLowerCase(tr))); // dotted pair
System.out.println(names.size());                  // 2
~~~

This approach **matches the defined key-mapping policy**: the two letter pairs are not mixed. It is not a general definition of all Unicode rules or Turkish collation. If requirements also involve different Unicode normalization forms, decide on normalization, multi-code-point characters, and diacritic sensitivity before constructing keys.

Do not mix approaches like **storing with `toLowerCase(tr)` while querying with `toLowerCase(Locale.ROOT)`**: from `I`, that produces two different strings `ı` and `i`, causing failed lookups.

## 6. Length and combining characters: the letter İ is a special case

To illustrate why case conversion is not always a 1 `char` → 1 `char` mapping:

~~~java
String capitalDottedI = "\u0130";
String lowerRoot = capitalDottedI.toLowerCase(Locale.ROOT);
String lowerTurkish = capitalDottedI.toLowerCase(
        Locale.forLanguageTag("tr-TR"));

System.out.println(capitalDottedI.length()); // 1
System.out.println(lowerRoot.length());      // 2
System.out.println(lowerTurkish.length());   // 1
~~~

This is an **illustrative code snippet** inside a Java method. With `ROOT`, the result is `U+0069 U+0307`: the letter `i` followed by a combining dot (*COMBINING DOT ABOVE*). With `tr-TR`, the result is a single letter `i (U+0069)`.

Consequences:

- Do not allocate buffers assuming "case conversion never changes `String.length()`."
- Do not iterate with `charAt(i)` and apply a simple per-`char` case change if you want to replicate all `String.toLowerCase(locale)` rules. Unicode case mapping can depend on context and locale and can produce multiple code points.
- When calculating slice positions after case conversion, do not assume UTF-16 offsets before and after conversion remain identical.
- **Unicode normalization** (e.g., `java.text.Normalizer`) and **locale-sensitive case conversion** are two steps with different purposes. Normalizing composed/decomposed Unicode forms does not alter the Turkish rule that `I` and `i` belong to two separate pairs.

### Character.toLowerCase() cannot replace String.toLowerCase(Locale)

`Character.toLowerCase(char)` / `Character.toLowerCase(int)` perform low-level character mapping, accept no locale, and cannot return a multi-character string like `"i\u0307"` from a call returning `char`/`int`. For words or sentences requiring language-specific case conversion, **prefer `String.toLowerCase(Locale)`**.

## 7. How does the default locale affect an application?

Consider the code:

~~~java
String command = "QUIT".toLowerCase();
~~~

When Java uses a Turkish default locale, the `I` in `QUIT` can turn into `ı`, yielding `"quıt"` (dotless i). If the program then compares literally against `"quit"`, the comparison can fail. This is a bug caused by **environment dependence during case conversion**, not by Unicode or Java corrupting the string.

Avoid mutating the entire application state with `Locale.setDefault(...)` just to fix one case-conversion operation. The default locale is shared JVM state and can affect other components that rely on it. **Passing the locale directly at the call site** makes the contract clearer and avoids side effects.

Key test scenarios to cover:

| Data/context | Expectation | Appropriate handling |
| --- | --- | --- |
| Turkish labels or words | Follow `I ↔ ı`, `İ ↔ i` spelling | `toLowerCase(tr)` / `toUpperCase(tr)` |
| Software keywords specified as language-independent | Consistent results on every machine | Fixed technical policy, using `Locale.ROOT` when appropriate |
| Case-insensitive search in Turkish | Do not merge the two I pairs mistakenly | Locale-aware comparison/normalization rules, or a configured and tested `Collator` |
| Exact literal content comparison | Distinguish exact UTF-16 sequences | `equals()` |
| Environment testing | Catch hidden locale dependencies | Test with `en-US`, `tr-TR`, `Locale.ROOT`, and `I/i/İ/ı` cases |
| Systems with an ASCII-only specification | Strictly obey ASCII set and rules | Validate ASCII, transform per protocol rules, do not arbitrarily Unicode-fold |

## 8. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| `"TITLE".toLowerCase()` to generate stable keys | Output varies with default locale, may produce `tıtle` | Specify an explicit policy/locale |
| Assuming `I` and `i` form a pair in every language | Wrong for Turkish | Understand all four letters `I/i/İ/ı` |
| Using `equalsIgnoreCase()` for Turkish matching | May wrongly merge the two letter pairs | Use a comparison mechanism matching the language policy |
| Assuming `Locale.ROOT` is Turkish | ROOT does not include Turkish locale rules | Use `Locale.forLanguageTag("tr-TR")` for Turkish |
| Assuming `Locale.ROOT` solves all Unicode identifier issues | Full Unicode case folding/normalization has many rules | Follow specific data standards and identifier policies |
| Assuming `String.toLowerCase()` preserves length | `İ` under ROOT lowercases to two code points | Check length and indices after transformation |
| Using `Character.toLowerCase(char)` everywhere instead of `String.toLowerCase(locale)` | Loses language context and multi-code-point mappings | Use `String` APIs with a locale for text |
| Using `==` to compare strings after normalization | `==` compares object identity | Use `equals()` for string values |
| Storing keys with `tr-TR` in one place and looking up with `ROOT` in another | Lookups fail or key rules mix | Normalize and compare **consistently** |
| Using case conversion as a substitute for full Turkish text comparison | May miss collation, normalization, accents, and context | Define clear criteria and test with real text |

## 9. Checklist before changing case or comparing strings

1. **Identify which language the text belongs to** and whether the user's locale applies to the transformation.
2. **Clarify the purpose:** spelling-accurate display, sorting names, case-insensitive lookup, or normalizing machine-readable codes.
3. **Specify the locale explicitly** when calling `toLowerCase()` / `toUpperCase()` as required; avoid depending on the default locale when consistent output is needed.
4. **For Turkish, test all four letters** `I`, `i`, `İ`, and `ı`, both individually and inside real words.
5. **Do not use `equalsIgnoreCase()` as a locale-sensitive comparator.** Explicitly define which equality rule applies.
6. **Do not assume a 1–1 transformation:** `String.toLowerCase(Locale)` can produce multiple code points, affecting indices and length.
7. **For lookup keys**, apply the exact same normalization/comparison pipeline at write time and search time; avoid mixing locales between steps.
8. **Check Unicode policy:** normalization, full case folding, ASCII limits, and confusable handling, per the application specification.
9. **Avoid changing `Locale.setDefault()` just to fix one snippet**, as it can impact other parts of the JVM.

## 10. Self-check

**Question 1.** In Turkish, what lowercase letter does `I` map to? What uppercase letter does `i` map to?

**Answer:** `I → ı (U+0131)`; `i → İ (U+0130)`.

**Question 2.** Are `"TITLE".toLowerCase(Locale.ROOT)` and `"TITLE".toLowerCase(Locale.forLanguageTag("tr-TR"))` the same?

**Answer:** No. ROOT gives `title`, whereas `tr-TR` gives `tıtle`, where the second letter is dotless `ı`.

**Question 3.** `"I".equalsIgnoreCase("i")` returns `true`. Does that prove the two letters are a proper uppercase/lowercase pair in Turkish?

**Answer:** No. `equalsIgnoreCase()` does not use the Turkish locale; in Turkish, `I` pairs with `ı` and `İ` pairs with `i`.

**Question 4.** Why is `"\u0130".toLowerCase(Locale.ROOT).length() == 2`?

**Answer:** The result consists of `i (U+0069)` and the combining dot `U+0307`, which is two UTF-16 code units. Case conversion can increase string length.

**Question 5.** An application needs to normalize protocol keywords such as `"QUIT"` regardless of server language. Should it call `"QUIT".toLowerCase()` without specifying a locale?

**Answer:** No. The default locale could be Turkish, turning `QUIT` into `quıt`. Choose a fixed technical rule and use an explicit locale or an ASCII algorithm per the protocol specification.

**Question 6.** Can all kinds of Turkish text comparison be handled accurately simply by lowercasing and calling `equals()`?

**Answer:** That should not be assumed. Locale-aware lowercasing can fit a **specific key policy**, while collation, normalization, and diacritic-sensitivity levels may require additional tools and rules.

## References

- [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): `toLowerCase(Locale)`, `toUpperCase(Locale)`, `equalsIgnoreCase()`, `compareToIgnoreCase()`.
- [Java SE 17 — Locale](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html): `Locale.ROOT`, `Locale.forLanguageTag()`, default locale.
- [Java SE 17 — Character](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html): character-level case mapping and limitations compared to string mapping.
- [Java SE 17 — Collator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Collator.html): locale-sensitive text comparison.
- [Unicode SpecialCasing.txt](https://www.unicode.org/Public/UCD/latest/ucd/SpecialCasing.txt): special case-mapping data, including locale and context rules.
