# Case Conversion Can Change String Length in Java

## 1. Core issue: uppercase/lowercase is not a 1:1 per-char replacement

In a Java application supporting multiple languages, `String.toUpperCase(Locale)` and `String.toLowerCase(Locale)` can produce a string of **different length** from the source string. The reason is that Unicode has case conversion rules where **a single Unicode character can map to multiple code points**, or the mapping changes depending on the language and surrounding context before/after the character.

Classic example:

~~~text
Input          : straße
ROOT uppercase : STRASSE
Java length    : 6 -> 7 (UTF-16 code units)
Code points    : 6 -> 7
~~~

The character `ß` (U+00DF, German small sharp s) when uppercased across the whole string in Java typically turns into **two S letters**. Therefore, the idea of "converting each `char` to uppercase without changing the number of characters" is **wrong** for Unicode string processing.

An example in the reverse direction:

~~~text
Input                 : İ (U+0130, Latin capital I with dot above)
toLowerCase(ROOT)     : i + U+0307 (combining dot above)
UTF-16 length         : 1 -> 2
Code points           : 1 -> 2
toLowerCase(tr-TR)    : i (U+0069), length = 1
~~~

Thus, the result depends both on **Unicode data** and potentially on **Locale**. Programmers should not assume `uppercase.length() == original.length()`, even when the code calls a seemingly simple case-conversion method.

This lesson focuses on **case conversion and its impact on length**: Unicode full case mapping, locale, `String.length()`, code points, string positions, data limits, and common mistakes in localization applications.

## 2. Two processing levels: single char vs. whole String

Java provides multiple case-conversion APIs, but their contracts differ.

| API | Input/output | Can it produce multiple code points? |
| --- | --- | --- |
| `Character.toUpperCase(char)` | One `char` → one `char` | **No** |
| `Character.toUpperCase(int)` | One code point → one code point | **No** |
| `Character.toLowerCase(int)` | One code point → one code point | **No** |
| `String.toUpperCase(Locale)` | Whole `String` → new `String` | **Yes** |
| `String.toLowerCase(Locale)` | Whole `String` → new `String` | **Yes** |
| `String.toUpperCase()` / `toLowerCase()` | Whole string, based on default Locale | **Yes** |

### 2.1. Why is Character insufficient for all text?

Methods like `Character.toUpperCase(int)` can only return **a single `int` value**. They cannot represent cases where one code point becomes **two code points**, such as `ß` uppercased in a whole string. The same applies to mappings requiring **context** from the whole string, such as sigma in Greek.

Illustrative example, placed inside a method:

~~~java
String whole = "\u00DF".toUpperCase(Locale.ROOT); // "SS"
int simple = Character.toUpperCase(0x00DF);      // U+00DF in example
~~~

This snippet requires `import java.util.Locale;`. Do not conclude that `Character.toUpperCase` and `String.toUpperCase(Locale)` share the same behavior just because both names are "toUpperCase".

**Dangerous pattern:** iterating with a `char` loop and writing:

~~~java
for (int i = 0; i < source.length(); i++) {
    out.append(Character.toUpperCase(source.charAt(i)));
}
~~~

This is only an **illustrative snippet**, assuming `source` is a `String` and `out` is a `StringBuilder`. This approach can skip full mappings, mishandle supplementary characters if surrogates are split, ignore linguistic context, and is not equivalent to `source.toUpperCase(locale)`.

**In most text processing scenarios**, call `String.toUpperCase(locale)` / `String.toLowerCase(locale)` on the **entire string**.

### 2.2. String is immutable and does not mutate the source value

~~~java
String original = "Java";
String upper = original.toUpperCase(Locale.ROOT);
~~~

`original` remains `"Java"`; `upper` is `"JAVA"`. The method returns a resulting string without modifying the original `String`. When comparing lengths, compare between two **different variables**, rather than expecting `original.length()` to change by itself.

## 3. Why does ß make uppercase longer?

For `straße` (German):

~~~text
Original code points:
U+0073 U+0074 U+0072 U+0061 U+00DF U+0065

ROOT uppercase code points:
U+0053 U+0054 U+0052 U+0041 U+0053 U+0053 U+0045
~~~

The input has 6 code points, and the output has 7. Because all code points in these two strings belong to the BMP and require no surrogate pairs:

~~~java
String original = "stra\u00DFe";
String upper = original.toUpperCase(Locale.ROOT);
System.out.println(original.length()); // 6
System.out.println(upper.length());    // 7
~~~

This example is inside a method and requires importing `Locale`. German typography also includes capital `ẞ` (U+1E9E), but **do not assume every full-string uppercase operation in Java must choose `ẞ`**. In programs verified on current JDKs, `String.toUpperCase(Locale.ROOT)` maps `ß` to `SS`.

This also shows that conversion is not always **reversible**:

~~~text
straße -> STRASSE -> strasse
~~~

The final string `strasse` is **different** from `straße`, even though the two strings may be related in pronunciation and spelling. Therefore, do not uppercase/lowercase and expect to restore the exact original.

### 3.1. Character.toUpperCase does not perform this expansion

~~~java
Character.toUpperCase(0x00DF)
~~~

In tested Java environments, the return value is `U+00DF`, because the simple mapping API cannot return two code points `U+0053 U+0053`. If an application converts one `char` at a time, the result may differ from the Unicode full mapping performed by `String`.

## 4. İ and i: results also depend on Locale

A well-known case involves the letters I in Turkish and Azerbaijani. Unicode contains at least these values to distinguish:

| Character | Code point | Notes |
| --- | --- | --- |
| `I` | U+0049 | Latin capital I |
| `i` | U+0069 | Latin small i |
| `İ` | U+0130 | Latin capital I with dot above |
| `ı` | U+0131 | Latin small dotless i |
| Combining dot above | U+0307 | Combining dot above |

For `U+0130`:

- `"\u0130".toLowerCase(Locale.ROOT)` produces **`U+0069 U+0307`** (two code points). The conversion increases `length()` from 1 to 2.
- `"\u0130".toLowerCase(Locale.forLanguageTag("tr-TR"))` produces **`U+0069`** (one code point).
- `"i".toUpperCase(Locale.ROOT)` produces **`U+0049`**.
- `"i".toUpperCase(Locale.forLanguageTag("tr-TR"))` produces **`U+0130`**.

This is not a Java bug; it reflects **localization rules and full case mapping**. If you change case **without passing a `Locale`**, the parameterless method uses the JVM default locale. A server set to `tr-TR` can produce different results from one set to `en-US`.

Risky example:

~~~java
String normalized = userInput.toLowerCase();
~~~

In this illustrative code, relying on the default locale can be inappropriate for a data key needing stable rules. You should choose:

- For **user-displayed text**: pass the appropriate locale, such as `toLowerCase(userLocale)`.
- For **fixed identifier rules**: define the system's normalization/canonicalization policy, often starting with `Locale.ROOT` if language-neutral casing is needed, though **do not treat it as a complete solution for Unicode case folding and identifier security**.
- For **values that must remain unchanged** (passwords, signatures, case-sensitive tokens, IDs with a case-sensitive contract): do not alter case automatically.

`Locale.ROOT` removes dependence on the *default locale*, but does not mean every character maps 1:1 or every language gets culturally appropriate results.

## 5. Character context also affects the result

Unicode has case mappings that depend on position within a word. One example is the Greek capital sigma:

~~~text
Input code points  : U+039F U+03A3   (ΟΣ)
ROOT lowercase     : U+03BF U+03C2   (ος)
~~~

At the end of a word, sigma typically converts to **final sigma** `U+03C2` instead of regular sigma `U+03C3`. Converting case on each code point in isolation lacks the **context** to always pick the right rule.

In this example the number of code points and UTF-16 code units **does not change**, yet the key takeaway remains: **full case conversion can depend on the whole string**, not an independent per-character operation.

Other locales such as Lithuanian also have combining-mark rules during case conversion; in particular, characters with accents above/below can cause the output string to gain combining marks. Thus, one must not extrapolate the behavior of all Unicode from ASCII A–Z alone.

## 6. length, codePointCount, and visual length differ

Java's `String.length()` counts **UTF-16 code units**, not user-visible characters. `String.codePointCount(0, s.length())` counts **Unicode code points** in the selected UTF-16 index range. A **grapheme cluster** is a user-perceived character unit, which may consist of multiple code points.

When changing case, all three measurements can change in different ways:

| Case | `length()` before → after | `codePointCount` before → after | Explanation |
| --- | --- | --- | --- |
| `straße` → `STRASSE` | 6 → 7 | 6 → 7 | `ß` becomes `SS` |
| `İ` → `i` + U+0307 with ROOT | 1 → 2 | 1 → 2 | One code point becomes two |
| `İ` → `i` with `tr-TR` | 1 → 1 | 1 → 1 | Locale has a different rule |
| `i` → `İ` with `tr-TR` | 1 → 1 | 1 → 1 | Code point changes, length stays |
| `ΟΣ` → `ος` | 2 → 2 | 2 → 2 | Code point changes by context |

**Note on supplementary Unicode:** a code point outside the BMP takes **two `char`s** in UTF-16. If a case conversion replaces a code point with one having a different number of UTF-16 code units, `length()` can change **by a different amount** than the code point count. These two metrics are not identical.

**Note on combining marks:** `i` + `U+0307` has two code points yet may be perceived by users as a single dotted letter; `codePointCount` is not a grapheme cluster counter. For emoji sequences with ZWJ/variation selectors or accented characters, a dedicated grapheme segmentation policy is needed if the application genuinely limits by visible character count.

### 6.1. Byte length cannot be inferred from length() either

When storing or transmitting over UTF-8, byte counts are computed separately:

~~~java
int bytes = value.getBytes(
        java.nio.charset.StandardCharsets.UTF_8).length;
~~~

This is an illustrative snippet, where `value` is a declared `String`. For `straße`:

- There are **6** UTF-16 code units.
- In UTF-8, five ASCII letters and one `ß` (two bytes) yield **7 bytes**.
- `STRASSE` has **7** UTF-16 code units and **7 UTF-8 bytes**.

This example nicely illustrates that **Java length increases while UTF-8 byte count stays unchanged**. With `U+0130` turning into `i` + `U+0307`, Java length increases from 1 to 2, while UTF-8 increases from 2 bytes to 3 bytes.

Do not treat byte count, code unit count, code point count, or grapheme count as equivalent metrics. If data contains lone surrogates or the output encoding has a character replacement policy, byte calculation also depends on how the encoder is configured.

## 7. Complete Java 17 program: measuring output accurately

To avoid depending on how a terminal types German, Turkish, and Greek characters, the program uses **Unicode escapes in Java source** and prints **code points in `U+...` format**. This example runs on JDK 17 or later without external libraries.

**File `CaseLengthDemo.java`:**

~~~java
import java.util.Locale;
import java.util.stream.Collectors;

public class CaseLengthDemo {
    static String points(String value) {
        return value.codePoints()
                .mapToObj(cp -> String.format(Locale.ROOT, "U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    static void show(String label, String value) {
        System.out.println(label + ": length=" + value.length()
                + ", codePoints=" + value.codePointCount(0, value.length())
                + ", hex=" + points(value));
    }

    public static void main(String[] args) {
        Locale turkish = Locale.forLanguageTag("tr-TR");

        String german = "stra\u00DFe";
        show("german original", german);
        show("german upper ROOT", german.toUpperCase(Locale.ROOT));

        String dottedI = "\u0130";
        show("dotted I original", dottedI);
        show("dotted I lower ROOT", dottedI.toLowerCase(Locale.ROOT));
        show("dotted I lower Turkish", dottedI.toLowerCase(turkish));

        show("i upper ROOT", "i".toUpperCase(Locale.ROOT));
        show("i upper Turkish", "i".toUpperCase(turkish));

        String greek = "\u039F\u03A3";
        show("greek lower ROOT", greek.toLowerCase(Locale.ROOT));
        System.out.println("sharp s vs SS equalsIgnoreCase: "
                + "\u00DF".equalsIgnoreCase("SS"));
        System.out.println("Character.toUpperCase(sharp s): "
                + points(new String(Character.toChars(
                        Character.toUpperCase(0x00DF)))));
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 CaseLengthDemo.java
java CaseLengthDemo
~~~

**Verified stdout** with the tested JDK's Unicode data:

~~~text
german original: length=6, codePoints=6, hex=U+0073 U+0074 U+0072 U+0061 U+00DF U+0065
german upper ROOT: length=7, codePoints=7, hex=U+0053 U+0054 U+0052 U+0041 U+0053 U+0053 U+0045
dotted I original: length=1, codePoints=1, hex=U+0130
dotted I lower ROOT: length=2, codePoints=2, hex=U+0069 U+0307
dotted I lower Turkish: length=1, codePoints=1, hex=U+0069
i upper ROOT: length=1, codePoints=1, hex=U+0049
i upper Turkish: length=1, codePoints=1, hex=U+0130
greek lower ROOT: length=2, codePoints=2, hex=U+03BF U+03C2
sharp s vs SS equalsIgnoreCase: false
Character.toUpperCase(sharp s): U+00DF
~~~

**Explanation by group:**

1. **German:** 6-code-point string, `ß` becomes `SS`, resulting in 7 code points. `Character.toUpperCase(0x00DF)` does not perform the `SS` expansion.
2. **Dotted I:** `U+0130` becomes `U+0069 U+0307` when lowercased with ROOT, growing from 1 to 2. The same input lowercased in Turkish outputs only `U+0069`.
3. **i:** uppercased with ROOT outputs `U+0049`, with Turkish outputs `U+0130`. Both have length 1 but **different code points**.
4. **Greek:** `U+039F U+03A3` converts to `U+03BF U+03C2`, demonstrating word-final context dependency.
5. **equalsIgnoreCase:** `"ß".equalsIgnoreCase("SS")` is `false` in Java because `equalsIgnoreCase` is not a full Unicode case-folding normalization that matches one code point to two letters.
6. **Hex output:** uses `Locale.ROOT` when formatting hex codes and prints explicit code points, avoiding confusion from terminal fonts or language settings.

This is an example testing **Unicode case mapping**, not an exhaustive catalog of all Unicode rules. Unicode mappings can be updated across JDK versions; pin the runtime version in snapshot tests if the application depends on exact output for every character.

## 8. Why can case conversion cause bugs when slicing and highlighting text?

Many `String` APIs take **UTF-16 indices**, including:

- `substring(begin, end)`
- `charAt(index)`
- `codePointAt(index)` (parameter is still a UTF-16 index)
- `indexOf(...)` (return value is still a UTF-16 index)

Suppose you search for a keyword in `straße`, then transform the whole string to `STRASSE`:

~~~text
Original:  s t r a ß e
UTF-16:    0 1 2 3 4 5
Uppercase: S T R A S S E
UTF-16:    0 1 2 3 4 5 6
~~~

The position of `e` shifted from **index 5 to index 6**. If an application keeps offsets/selections/annotations from the old string and applies them to the new string, the highlighted region can be wrong.

### 8.1. Use indices only on the string they were computed on

Safe options:

1. Search and display only on the same **version of the text** on which indices were generated.
2. If you must display case-converted text, recompute indices on the result **or** maintain an offset mapping table from original to transformed text; do not guess offsets by fixed addition.
3. When receiving offsets from a UI or another library, identify whether they are **UTF-16 offsets**, **code point indices**, **grapheme indices**, or **byte offsets**.
4. For highlighting based on case-insensitive matching, use appropriate search/collation tools and source-tracking mechanisms; do not simply uppercase two strings and treat resulting indices as original indices.

**Even when code point count stays unchanged**, non-BMP scripts or Unicode normalization can shift UTF-16 offsets. Any text transformation must be treated as potentially invalidating stored indices.

### 8.2. Do not arbitrarily split a string before case-converting

If you split a string right before a context-sensitive character (such as sigma), the case mapping result of each fragment may differ from processing the full sentence. Splitting text into individual `char`s, code points, or arbitrary chunks before changing case can make context **incomplete**.

Especially in multilingual UIs, decide the order clearly: normalize per policy, convert case with the appropriate locale, search/mark, and then compute position bounds after transformation if targeting the resulting string. Do not rely on per-`char` operations by default.

## 9. Maximum length, storage, and validation

### 9.1. Should length limits apply before or after case conversion?

This depends on **which data is stored and used as the canonical value**.

For example, an account display name capped at `6` code points before case conversion:

~~~text
Input       : straße   -> 6 code points
Upper ROOT  : STRASSE  -> 7 code points
~~~

If the system stores the **uppercase version** in a column/field limited to 6 UTF-16 units, validating the input before case conversion is insufficient: the 7-unit result will exceed the limit. Conversely, if the system stores the original text and uppercases only for **display**, there is no need to force the user to rename just because the display string grew.

Practical rules:

- **If storing the normalized form:** validate **after** normalization/case mapping, in the exact unit of the storage/contract limit.
- **If storing the original:** validate the original against input limits; the display form is a derivative that needs appropriate rendering/layout.
- **If there is a UTF-8 byte limit:** measure bytes of the exact string to be stored/exchanged.
- **If the UI limits by user-perceived characters:** apply Unicode grapheme segmentation, not `length()` as a proxy.
- **If valid Unicode scalar values are required:** check for lone surrogates before converting/encoding; case conversion does not validate malformed data by itself.

Do not truncate the uppercase version to 6 `char`s just to "make it fit": besides losing data, with supplementary characters there is a risk of splitting a surrogate pair in half.

### 9.2. Apply Unicode normalization before or after?

Different Unicode representations can look identical yet have different code point and byte counts. `java.text.Normalizer` supports NFC, NFD, and other normalization forms. When designing canonicalization:

1. Define the **normalization policy** (if any), such as NFC, for the specific data type.
2. Choose an explicit **Locale** or case-folding rule.
3. Specify the transformation order and test accented/combining/locale-specific characters.
4. Validate the final result against the **exact metric** and storage limit.
5. Keep the original if business logic requires verbatim display or auditing.

Do not claim that "running NFC first and then toLowerCase guarantees all inputs with the same spelling will be equal". Unicode normalization and Unicode **full case folding** are two distinct processes; Java's `String.toLowerCase(Locale)` does not implement full case folding for every identifier requirement.

## 10. Case-insensitive comparison does not automatically solve everything

Java has `String.equalsIgnoreCase(String)`, `compareToIgnoreCase`, and `String.CASE_INSENSITIVE_ORDER`. They are useful for certain case-insensitive comparisons, yet **are not a complete linguistic comparison**.

Verified example:

~~~java
System.out.println("\u00DF".equalsIgnoreCase("SS")); // false
~~~

Reason: `equalsIgnoreCase` uses character comparison rules per Java's contract and does not perform multi-code-point full case folding like `ß` → `SS`.

Therefore:

- `a.toUpperCase(locale).equals(b.toUpperCase(locale))` is not a universal substitute for **Unicode collation/case folding**: there remain issues of normalization, diacritics, character equivalence, versions, and linguistic policies.
- `String.equalsIgnoreCase` does not take a locale parameter and does not represent all lookup, sorting, or personal-name matching rules.
- For **linguistic sorting/lookup of words**, look into `java.text.Collator` with an appropriate locale and strength. `Collator` solves collation, while database ID uniqueness/integrity policies still must be defined explicitly.
- For **usernames, emails, domains, URLs, tokens, paths, and protocol keys**, each domain has its own normalization rules. Do not blindly apply `toLowerCase(Locale.ROOT)` to all of them; doing so can cause collisions, security bugs, or break compatibility.
- For **passwords, signatures, and case-sensitive identifiers**, preserve the exact original value per contract with no implicit transformation.

That a case-ignoring comparison returns `true` also **does not mean** every Unicode version or locale will interpret the two strings identically for every task. System uniqueness standards should be defined and tested with expansions, accented characters, and tricky characters.

## 11. Default locale, concurrency, and stability

`String.toUpperCase()` and `String.toLowerCase()` without arguments use the JVM's **default locale**. Across dev machines, CI, containers, or multilingual servers, the default locale may differ and can be mutated by other code.

~~~java
String key = raw.toLowerCase(Locale.ROOT);
String display = raw.toUpperCase(userLocale);
~~~

This is an illustrative snippet where `raw` is a `String`, `userLocale` is a `Locale`, and `Locale` must be imported. For technical keys with a specific case-insensitive policy, using an explicit locale (typically `ROOT`) prevents discrepancies across host machines. For UI text, a user-specific locale may be necessary.

**Do not call `Locale.setDefault(...)` per request** to change display language: the default locale is shared JVM state and can cause other requests to process text inconsistently. Pass an explicit locale and keep a consistent canonicalization policy.

`String` is immutable and thread-safe to read; creating a new uppercase/lowercase string does not mutate source data. However, if **caching a canonicalized key**, maintain the same algorithm/locale/Unicode version per contract; when upgrading the JDK, retesting normalized data may be required.

## 12. Common mistakes and how to avoid them

| Mistake | Why it is wrong | Right approach |
| --- | --- | --- |
| Assuming uppercase always preserves `length()` | `ß` can become `SS` | Check length of the **result** |
| Assuming lower always preserves code point count | `İ` under ROOT becomes `i` + combining dot | Consider locale and full mapping |
| Converting each `char` via `Character.toUpperCase` and comparing to `String.toUpperCase` | Simple mapping cannot expand 1→N | Use whole-string APIs |
| Using default locale for technical keys | `I`/`i` behave differently in `tr-TR` | Choose explicit locale/canonicalization |
| Slicing or reusing indices from before case change | UTF-16 positions can shift | Recompute offsets / mapping table |
| Using `String.length()` to count graphemes | One visible letter can have multiple code points | Use appropriate grapheme segmentation |
| Checking length before saving an uppercased string | Result may be longer | Validate the actual string being saved |
| Thinking uppercase then lowercase restores original text | `straße` → `STRASSE` → `strasse` | Preserve original if needed |
| Treating `equalsIgnoreCase` as Unicode full folding | `ß` and `SS` are not treated as equal | Choose comparison strategy per domain |
| Arbitrarily using `toLowerCase` on passwords/tokens | Breaks case-sensitive semantics | Follow contract, usually keep unchanged |
| Equating code units with UTF-8 bytes | Byte size and Java length differ | Measure with actual charset |
| Lacking Unicode/locale tests after JDK upgrade | Unicode mappings can change | Test behavior on supported runtimes |

## 13. Testing and practical exercises

A useful test suite should cover:

1. **German sharp s:** `straße` → `STRASSE`, verifying `length` 6 → 7 and `codePointCount` 6 → 7.
2. **Turkish dotted I:** `U+0130` lowercased with ROOT yields two code points `U+0069 U+0307`, with `tr-TR` yields one `U+0069`.
3. **Turkish small i:** uppercased with ROOT yields `U+0049`, with `tr-TR` yields `U+0130`.
4. **Greek final sigma:** an all-uppercase string ending with sigma; verify context-sensitive lowercasing differs from single-character operations.
5. **Simple vs full mapping:** `Character.toUpperCase(0x00DF)` does not produce `SS`, whereas `String.toUpperCase(Locale.ROOT)` does.
6. **Immutability:** source string stays unchanged after case conversion.
7. **Byte limit:** compare `getBytes(UTF_8).length` on strings before/after.
8. **Index drift:** record the index of `e` in `straße`; after uppercasing, check the new index.
9. **Grapheme:** `İ` lowercased with ROOT produces `i` + combining mark; test the chosen grapheme segmenter.
10. **Locale default:** verify logic using explicit locales does not depend on dev or CI machine config.
11. **Storage:** verify stored string limits **after** canonicalization, not only before.
12. **Case insensitive semantics:** compare `equalsIgnoreCase`, uppercase normalization, and collation on tricky inputs.
13. **Normalization:** create accented strings in NFC/NFD; test the system's normalization/casing strategy.
14. **Unicode version:** if product data depends on exact mappings, retest when upgrading Java.

### Exercise 1 — shifted index

Given `String s = "stra\u00DFe";`:

~~~java
int oldIndex = s.indexOf('e');                     // 5
String changed = s.toUpperCase(Locale.ROOT);       // "STRASSE"
int newIndex = changed.indexOf('E');               // 6
~~~

This is an illustrative snippet requiring `Locale` to be imported. Explain why using `oldIndex` on `changed` points to the second `S` rather than `E`.

### Exercise 2 — asymmetric transformation

Create three strings:

~~~java
String a = "stra\u00DFe";
String b = a.toUpperCase(Locale.ROOT);
String c = b.toLowerCase(Locale.ROOT);
~~~

Compare `a.equals(c)`, `a.length()`, `b.length()`, `c.length()`. The results show that the transformation direction does not guarantee recovering the original Unicode code points.

### Exercise 3 — data store limit

Build a function accepting a display name up to 6 code points long, but storing the uppercase version. Prove why `straße` exceeds the storage limit if the column only permits 6 code units. Propose a new rule: store the original, or validate the string after normalization, and specify a clear message for the user.

### Exercise 4 — fixed locale vs. user locale

Use `Locale.ROOT` and `Locale.forLanguageTag("tr-TR")` to change case for `I`, `i`, `İ`, `ı`. Compare code points/lengths; do not compare characters merely by eye. Write a test where locale is passed as an **explicit parameter** instead of mutating the JVM default.

## 14. Conclusion

**Unicode case conversion is not necessarily a one-to-one replacement.** `String.toUpperCase(Locale)` and `String.toLowerCase(Locale)` can **expand a single code point into multiple code points**, and some rules depend on locale or whole-string context. Because Java's `String.length()` counts UTF-16 code units, length can change after case conversion; code point count, grapheme count, and byte count are also distinct concepts.

In multilingual code, pass `Locale` explicitly, use `String`-level APIs instead of converting individual `char`s, do not reuse old indices after transformation, and validate limits on the **actual string to be stored**. For identifiers, queries, matching, or security, choose the right canonicalization/collation policy for the domain rather than assuming `toLowerCase` or `equalsIgnoreCase` is a universal Unicode solution.

**References:**

- Java SE 17, `String`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html
- Java SE 17, `Character`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html
- Java SE 17, `Locale`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html
- Java SE 17, `Normalizer`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html
- Java SE 17, `Collator`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Collator.html
- Unicode Standard, Default Case Algorithms: https://www.unicode.org/versions/latest/core-spec/chapter-3/#G34078
