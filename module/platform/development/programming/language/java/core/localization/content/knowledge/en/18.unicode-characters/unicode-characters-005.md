# Combining Marks, Vietnamese, and Equivalent Unicode Representations in Java

## Objectives

Vietnamese text contains many accented characters: `á`, `à`, `ả`, `ã`, `ạ`, `ắ`, `ằ`, `ẫ`, `ậ`, `ế`, `ệ`, etc. Users see a single accented letter, yet Unicode can store that letter using **one precomposed code point** or **a base letter plus combining marks**.

Two strings that look identical do not necessarily have the same code point sequence, the same number of elements in `String`, or compare equal under `String.equals(...)`. That directly affects comparison, search, data storage, filename handling, input validation, and localization.

After this lesson, you will be able to:

- Distinguish **UTF-16 code unit**, **Unicode code point**, **combining mark**, and **grapheme cluster** (a cluster of characters users typically perceive as one letter).
- Describe why `ắ` can be `U+1EAF` or the sequence `U+0061 U+0306 U+0301`, and why these two forms are considered **canonically equivalent**.
- Use `java.text.Normalizer` with `NFC` and `NFD` to normalize before comparing or processing according to a data contract.
- Distinguish `NFC/NFD` from `NFKC/NFKD` and understand why compatibility normalization can alter meaningful distinctions.
- Recognize Vietnamese-specific pitfalls: reversed mark order, stripping accents for comparison, treating `đ` and `d` as Unicode-equivalent, slicing strings by `char`, or inconsistent normalization across systems.
- Write runnable Java 17+ examples and design test suites that preserve the meaning of Vietnamese letters.

**Focus:** Unicode representation and combining marks. This lesson does not aim to teach all Vietnamese orthography rules or full natural language processing algorithms.

## 1. One Visible Letter Is Not Always One Code Point

Unicode assigns numeric identifiers called **code points** to many characters and marks. Codes are written as `U+XXXX`; for example:

- `a`: `U+0061` (LATIN SMALL LETTER A).
- `á`: `U+00E1` (LATIN SMALL LETTER A WITH ACUTE).
- `ắ`: `U+1EAF` (LATIN SMALL LETTER A WITH BREVE AND ACUTE).
- `◌̆`: `U+0306` (COMBINING BREVE).
- `◌́`: `U+0301` (COMBINING ACUTE ACCENT).

The dotted circle `◌` in combining mark illustrations only helps show where the mark attaches; it is **not** a required part of the stored text string.

The letter `ắ` has at least two important representations:

```text
Approach A — precomposed form:
U+1EAF
  ắ

Approach B — decomposed form:
U+0061 U+0306 U+0301
  a       ◌̆       ◌́
       (when rendered together: ắ)
```

Approach A has **one code point**; Approach B has **three code points**, yet both strings can render to an identical character image. By Unicode rules, the precomposed form above and the properly ordered decomposed form are **canonically equivalent**: they represent the same character sequence under canonical equivalence.

Key takeaway:

> **Looking identical is not enough to infer identical bytes, identical code points, or that `String.equals(...)` returns `true`.**

This is not a font bug or a quirk unique to Vietnamese; it is an intentional feature of Unicode to support multiple text representations, maintaining compatibility with data produced across diverse systems and input methods.

## 2. Terminology: Code Unit, Code Point, Combining Mark, Grapheme Cluster

In Java, `String` stores text as **UTF-16 code units**. Many code points in the BMP, including the Vietnamese letters mentioned above and the combining mark `U+0301`, are represented by one code unit. Code points outside the BMP typically require **two code units (a surrogate pair)**.

| Concept | Unit counted | Illustrative Java API |
| --- | --- | --- |
| **UTF-16 code unit** | 16-bit `char` unit | `String.length()`, `charAt(i)` |
| **Unicode code point** | Unicode scalar value (excluding lone surrogates) | `codePointCount(...)`, `codePoints()` |
| **Combining mark** | Code point acting as a combining accent/symbol | Unicode category inspectable via `Character.getType(cp)` |
| **Grapheme cluster** | Group of code points typically perceived by users as one character | Regex `\X` in Java 17+ supports extended grapheme clusters |

For instance, the decomposed form `a + ◌̆ + ◌́` has:

- `String.length() == 3` (three UTF-16 code units).
- `codePointCount(...) == 3` (three code points).
- One grapheme cluster under the corresponding Unicode segmentation rules.

Meanwhile, the precomposed form `ắ` has `length() == 1` and one code point, and is still typically **one grapheme cluster**.

Do not describe `String.length()` as "the number of visible letters". For some languages or emojis, the difference is even more pronounced because a cluster can contain many code points, sometimes including surrogate pairs.

### Why Does This Matter When Slicing and Limiting Input?

A form limiting to 20 "visible characters" is different from limiting to 20 UTF-16 code units. If a user enters Vietnamese in NFD form, counting with `length()` can register more units even though the number of letters they see has not changed.

Conversely, if a system has a **byte** limit when writing to a protocol or database, the UTF-8 byte count is yet another measurement. You should separate three needs:

1. **Memory/protocol limit:** can be based on byte count or UTF-16 code units per schema.
2. **Code point limit:** can be based on `String.codePointCount(...)`.
3. **User-perceived letter limit:** can be based on grapheme clusters using an appropriate segmentation tool.

You cannot take a single `length()` number and claim it simultaneously satisfies all three requirements.

## 3. Precomposed Characters and Combining Mark Sequences in Vietnamese

Many Vietnamese letters already have precomposed code points:

| Visible letter | Precomposed form | A canonically decomposed form |
| --- | --- | --- |
| `á` | `U+00E1` | `U+0061 U+0301` |
| `ắ` | `U+1EAF` | `U+0061 U+0306 U+0301` |
| `ế` | `U+1EBF` | `U+0065 U+0302 U+0301` |
| `Á` | `U+00C1` | `U+0041 U+0301` |

Components of the letter `ắ`:

- `U+0061`: base letter `a`.
- `U+0306`: breve mark, contributing to forming the letter `ă`.
- `U+0301`: acute accent, representing the *sắc* tone.

For `ế`, the base letter `e` is combined with a circumflex (`U+0302`) and an acute accent (`U+0301`).

Some systems store precomposed strings; some pipelines can produce strings containing combining marks. Even when a user types the exact same word, data arriving from keyboards, editors, files, browsers, or external services may carry different code point sequences.

**Do not predict the normalization form solely from the operating system or input method.** Check and normalize intentionally when business logic requires it.

### Vietnamese Has More Than Just "Tone Marks"

Vietnamese combines different kinds of features:

- **Tone marks:** *sắc* (acute), *huyền* (grave), *hỏi* (hook above), *ngã* (tilde), *nặng* (dot below).
- **Letter-forming diacritics:** circumflex in `â`/`ê`/`ô`; breve in `ă`; horn in `ơ`/`ư`.
- **Distinct letter:** `đ`/`Đ`.

If you process all these marks simply by "removing every code point in the mark category", the system can wipe out both letter distinctions and tone marks, directly altering Vietnamese meaning.

## 4. Canonical Equivalence Does Not Mean Java Strings Are Equal

`String.equals` compares content by code units. It does not automatically normalize Unicode before comparing:

```java
String precomposed = "\u1EAF";
String decomposed = "a\u0306\u0301";

System.out.println(precomposed.equals(decomposed));
```

This is an illustrative snippet inside a method. Stdout:

```text
false
```

The two literals above at runtime represent the same letter `ắ` canonically, yet have different code sequences:

```text
precomposed: U+1EAF
decomposed:  U+0061 U+0306 U+0301
```

If used directly as map keys:

```java
Map<String, Integer> counts = new HashMap<>();
counts.put(precomposed, 1);
System.out.println(counts.containsKey(decomposed));
```

Inside a method with `import java.util.Map;` and `import java.util.HashMap;`, the result is `false`. The reason: `HashMap` uses `String.equals/hashCode` on the code unit sequence; it does not automatically treat two canonically equivalent Unicode representations as the same key.

This can cause:

- Two "visually identical" accounts/labels/identifiers creating two distinct keys.
- Name lookups failing even though the displayed text matches.
- Result sets containing visually duplicate records.
- Content comparisons across systems returning different results when one side normalizes and the other leaves the string untouched.

The solution is not defaulting to `equalsIgnoreCase`: case folding is a separate issue from normalizing combining marks.

## 5. NFC and NFD: Two Canonical Normalization Forms

`java.text.Normalizer` provides Unicode normalization forms:

| Form | General meaning | Main effect |
| --- | --- | --- |
| `Normalizer.Form.NFD` | Canonical Decomposition | Splits precomposed combinations into canonically decomposed code point sequences, and orders marks canonically where applicable |
| `Normalizer.Form.NFC` | Canonical Decomposition + Composition | Performs canonical decomposition then recomposes where Unicode allows, yielding appropriate precomposed representations |
| `Normalizer.Form.NFKD` | Compatibility Decomposition | Also decomposes compatibility forms, which can lose formatting/symbol distinctions |
| `Normalizer.Form.NFKC` | Compatibility Decomposition + Composition | Performs compatibility decomposition then recomposes, stronger than NFC and does not preserve all original distinctions |

For problems that **treat canonically equivalent Unicode representations as the same string**, `NFC` or `NFD` are the two foundational choices. In many general text storage and exchange scenarios, `NFC` is chosen because it uses precomposed code points when appropriate. However, the system's contract must be consistent with this choice.

Example:

```java
import java.text.Normalizer;

String precomposed = "\u1EAF";
String decomposed = "a\u0306\u0301";

String left = Normalizer.normalize(
        precomposed, Normalizer.Form.NFC);
String right = Normalizer.normalize(
        decomposed, Normalizer.Form.NFC);

System.out.println(left.equals(right));
```

Stdout:

```text
true
```

A system can choose NFD instead of NFC if its character-processing pipeline requires separated marks, yet it must be consistent at every data creation and comparison point. **Do not normalize only one side** and compare against an unnormalized side, and do not mix NFC and NFD arbitrarily across modules.

### `Normalizer.isNormalized`

`Normalizer.isNormalized(text, Normalizer.Form.NFC)` checks whether a string **is already in NFC** without having to interpret Unicode codes manually. However, an "is NFC" result only confirms the representation form; **it does not prove the text is spelled properly, safe, or compliant with business rules**.

For example, `"ma"` and `"má"` can both be in NFC while still being two strings with different meanings.

## 6. Complete Java 17+ Example: Comparison, Unicode Codes, and Grapheme Clusters

The following example constructs strings using Unicode escapes in Java source. This prevents compilation from depending on whether the terminal displays Vietnamese accents properly.

Create the file `VietnameseNormalizationDemo.java`:

```java
import java.text.Normalizer;
import java.util.Locale;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

public class VietnameseNormalizationDemo {
    private static String points(String text) {
        return text.codePoints()
                .mapToObj(cp -> String.format(
                        Locale.ROOT, "U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    public static void main(String[] args) {
        String composed = "\u1EAF";           // ắ
        String decomposed = "a\u0306\u0301";   // a + breve + acute

        System.out.println("raw equals: "
                + composed.equals(decomposed));

        System.out.println("length: "
                + composed.length() + "/" + decomposed.length());

        System.out.println("code points: "
                + composed.codePointCount(0, composed.length())
                + "/" + decomposed.codePointCount(0, decomposed.length()));

        System.out.println("composed: " + points(composed));
        System.out.println("decomposed: " + points(decomposed));

        String nfc = Normalizer.normalize(
                decomposed, Normalizer.Form.NFC);
        String nfd = Normalizer.normalize(
                composed, Normalizer.Form.NFD);

        System.out.println("NFC equal: " + nfc.equals(composed));
        System.out.println("NFD equal: " + nfd.equals(decomposed));

        long clusters = Pattern.compile("\\X")
                .matcher(decomposed)
                .results()
                .count();

        System.out.println("grapheme clusters: " + clusters);

        String reversedMarks = "a\u0301\u0306";
        System.out.println("reversed equal: "
                + Normalizer.normalize(
                    reversedMarks, Normalizer.Form.NFC)
                  .equals(composed));

        String dStroke = "\u0111"; // đ
        System.out.println("d-stroke equals d after NFD: "
                + Normalizer.normalize(
                    dStroke, Normalizer.Form.NFD)
                  .equals("d"));

        String circledOne = "\u2460"; // ①
        System.out.println("NFKC circled one: "
                + Normalizer.normalize(
                    circledOne, Normalizer.Form.NFKC));
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 VietnameseNormalizationDemo.java
java VietnameseNormalizationDemo
```

Deterministic stdout for the program:

```text
raw equals: false
length: 1/3
code points: 1/3
composed: U+1EAF
decomposed: U+0061 U+0306 U+0301
NFC equal: true
NFD equal: true
grapheme clusters: 1
reversed equal: false
d-stroke equals d after NFD: false
NFKC circled one: 1
```

**Explanation of key lines:**

1. Direct `equals` returns `false` because the UTF-16 code unit sequences differ.
2. `length` and `codePointCount` return 1/3 in this example: all code points involved are inside the BMP, so each code point uses one UTF-16 code unit.
3. The two `points` lines clearly show `U+1EAF` versus `U+0061 U+0306 U+0301`.
4. After proper NFC or NFD, canonically equivalent strings are brought to the same representation, so the result is `true`.
5. Regex `\X` recognizes the decomposed string above as **one extended grapheme cluster**, even though it contains three code points.
6. Reversing the marks to `a + acute + breve` is **not** automatically equated by Unicode with the canonical sequence `a + breve + acute` in this test.
7. `đ` does not turn into `d` via NFD: the two letters have a real distinction and do not form such a canonical equivalence pair.
8. `NFKC` turns `①` into the digit `1` because they have a compatibility relationship, showing that NFKC can merge representations that are not canonically equivalent.

When applying this to real data, do not rely solely on viewing output glyphs on a console; some terminals or fonts render combining marks differently even when the code point sequence is identical. Printing code points provides far more reliable diagnostics.

## 7. Combining Mark Order and Canonical Ordering

Unicode does not treat **every permutation of combining marks** as equivalent. Where appropriate, normalization can reorder marks based on *Canonical Combining Class* (CCC); however, the order of marks sharing the same combining class can still be significant and is not arbitrarily reordered.

In the tested example:

```text
a + U+0306 + U+0301  -> NFC: U+1EAF (ắ)
a + U+0301 + U+0306  -> does not produce the same NFC as U+1EAF
```

Do not write a "Vietnamese normalization" algorithm by arbitrarily sorting all marks by name, by code point, or by "tone mark first, letter diacritic second". Unicode's canonical ordering rules are more complex than an arbitrary sort, and mark order can affect character composition.

Likewise, do not treat a string after NFC as **valid Vietnamese spelling**. Unicode normalization handles representation equivalence; it does not check whether tone marks are placed on the right syllable or whether a word is linguistically valid.

If you need to fix IME errors or position tone marks per Vietnamese orthography, that is a separate linguistic feature requiring dedicated rules and tests, not something replaceable by `Normalizer.normalize(..., NFC)` alone.

## 8. Distinguishing Unicode Normalization from Vietnamese Accent Stripping

Examples:

```text
ma
má
mà
mả
mã
mạ
```

These words/spellings **are not merely different Unicode representations of the same string**. Tone marks create linguistic distinctions. NFC does not—and must not—turn them into the same value.

A commonly seen "accent-stripping" snippet:

```java
String noMarks = Normalizer.normalize(
        text, Normalizer.Form.NFD)
        .replaceAll("\\p{M}+", "");
```

This is an illustrative snippet inside a method with variable `text`. `\p{M}` in Java regular expressions represents the Unicode Mark character category. This approach **intentionally deletes information**; it is not canonical normalization that preserves meaning. It can collapse `"ma"`, `"má"`, `"mà"`, `"mã"`… into the same string `"ma"`.

In particular, `đ` has no canonical decomposition into `d` + mark, so stripping `\p{M}` after NFD **does not automatically convert `đ` to `d`**. Some custom "Vietnamese accent-stripping" pipelines also map `đ → d`, yet that is an additional search/text-processing policy, not canonical Unicode normalization.

### When Is Accent Stripping Reasonable?

A search-suggestion feature might want a user typing `"ca phe"` to still find `"cà phê"`. In that case, you can build an approximate **secondary search key** using product-defined accent-stripping rules.

However, you should not use the accent-stripped search key to:

- Overwrite the user's original name.
- Check identity or absolute uniqueness without a clear policy.
- Replace legal/personal values that must be preserved accurately.
- Decide that two strings definitely have the same meaning.

A solid architecture **keeps the original text** and adds a normalized field for search when needed, along with duplicate/confusion checks. When displaying to users, always use the original value or the Unicode-normalized value per the storage contract, never text with marks stripped.

## 9. NFC Differs from NFKC: Do Not Apply Compatibility Normalization Unthinkingly

Two strings can be *compatibility equivalent* without being *canonically equivalent*. For example, the character `①` (CIRCLED DIGIT ONE) and the digit `1`:

```java
String circledOne = "\u2460";
String nfc = Normalizer.normalize(
        circledOne, Normalizer.Form.NFC);
String nfkc = Normalizer.normalize(
        circledOne, Normalizer.Form.NFKC);
```

Inside a method importing `Normalizer`:

- `nfc` still represents the circled digit symbol `①`.
- `nfkc` becomes the digit character `1`.

NFKC/NFKD can alter presentation or structural distinctions that carry meaning in a given domain. Therefore:

- **Display names and original Vietnamese text:** typically consider NFC to unify canonical representations, rather than automatically using NFKC.
- **Identifiers with custom normalization rules:** use compatibility normalization only if the schema, security requirements, and compatibility rules specify it.
- **Broad compatibility search:** may require a separate transformation step for search indices, accepting the risk of merging distinct strings.

NFKC is not a "better version of NFC". It solves a different problem; in certain security contexts, NFKC plays a role in specialized profiles, yet it does not automatically eliminate all visually confusable characters.

## 10. Input, Storage, and Comparison at System Boundaries

A common real-world bug:

```text
Service A stores: "ắ"                -> U+1EAF
Service B sends:  "a\u0306\u0301"      -> U+0061 U+0306 U+0301

Screen: looks identical
String.equals: false
HashMap/cache lookup: may miss
```

If business logic treats two canonical representations as equivalent, you need a **consistent normalization policy**. A simple approach:

1. Accept valid Unicode from input sources (forms, files, APIs).
2. Validate length/character-group requirements and other business rules.
3. Normalize to `NFC` at a defined boundary, **before building comparison/storage keys if that is the chosen contract**.
4. Use the same normalized form to construct queries, cache keys, indices, and application-level unique constraints.
5. Retain the original version separately if needed for auditing or reproducing the exact user-entered text.
6. When changing normalization policy on a running system, plan migrations, resolve post-normalization collisions, and synchronize across services.

Illustrative normalization helper:

```java
import java.text.Normalizer;
import java.util.Objects;

public final class UnicodeKeys {
    private UnicodeKeys() {}

    public static String canonicalKey(String input) {
        Objects.requireNonNull(input, "input");
        return Normalizer.normalize(input, Normalizer.Form.NFC);
    }
}
```

This class compiles as `UnicodeKeys.java`, though it has no `main` to run standalone. It handles only canonical equivalence. If requirements also include case-insensitive comparison, whitespace handling, forbidden characters, or Unicode confusables, build **separate policies** rather than quietly stuffing them into normalization.

### Databases and Unique Constraints

A database may use different collations: some treat equivalent forms as the same string, while others may distinguish them or apply their own normalization rules. **Do not assume** the database, Java `HashMap`, and search service use identical text comparison.

If a system requires uniqueness based on "same string after NFC", define how normalized keys are generated, set up appropriate indices/constraints, and verify consistency across all write paths. When adding normalization to legacy data, two existing records may collide onto the same key after normalization; have a collision-handling policy rather than silently deleting data.

### APIs and Byte Serialization

JSON, UTF-8, and Unicode protocols can carry both NFC and NFD forms. Two strings having identical visual appearance **does not force their UTF-8 bytes to match**. If a system computes digital signatures, hashes, ETags, or uses strings as cache keys, byte differences can yield different results.

Normalize **before signing/hashing** only if both sender and receiver share the same normalization contract; do not arbitrarily modify signed messages or JSON and expect signatures to remain valid. Canonicalizing JSON for signing also has its own rules (field ordering, escapes, number formatting…) that cannot be solved by `Normalizer` alone.

## 11. Linguistic Comparison with `Collator` Is a Separate Problem

`String.equals` is based on code unit content; `Normalizer` handles Unicode representation; `java.text.Collator` handles **comparison/sorting according to linguistic conventions**.

Example:

```java
import java.text.Collator;
import java.util.Locale;

Collator collator = Collator.getInstance(
        Locale.forLanguageTag("vi-VN"));
collator.setDecomposition(Collator.CANONICAL_DECOMPOSITION);
```

This is an illustrative snippet inside a method. `Collator` has strength levels that determine whether letter and accent differences are considered during comparison/sorting. Depending on strength and collation data, two strings **differing in tone marks** may compare closer together, or follow a specific order.

Distinguish clearly:

- **NFC/NFD:** the same string under canonical equivalence, without altering tone-mark meaning.
- **Collation:** linguistic comparison/ordering with a chosen strength.
- **Accent-insensitive search:** an approximate search requirement, which can use collation/search keys or a dedicated search engine.
- **Exact equality for identifiers:** requires a clear contract; usually does not unthinkingly use a comparator that ignores accents.

If you merely want `"ắ"` and `"a\u0306\u0301"` to be treated as the same data under canonical equivalence, normalizing to NFC first and then using `equals` is transparent. If you want to sort Vietnamese words in proper lexical order, use a locale-aware collation tool and test with user data.

## 12. Checking User-Perceived Characters

Many UI bugs occur when code iterates by `char`:

```java
for (int i = 0; i < text.length(); i++) {
    char part = text.charAt(i);
    // Do not assume part is a complete user-perceived letter.
}
```

This is an illustrative snippet inside a method. For `"a\u0306\u0301"`, the loop receives three separate `char`s: the letter `a` and two combining marks. If you use `substring(0, 1)`, you keep only `a` and lose the accents; if you slice in the middle of a cluster, the trailing part can start with an orphaned combining mark without a base letter.

`String.codePoints()` solves iterating by **code point** (avoiding splitting surrogate pairs), yet still **does not** group combining marks with their base letter. If you need to slice by user-perceived letter clusters, you can use Java regex supporting extended grapheme clusters:

```java
import java.util.regex.Pattern;

String text = "a\u0306\u0301";
long clusterCount = Pattern.compile("\\X")
        .matcher(text)
        .results()
        .count();
```

This is an illustrative snippet inside a method; `clusterCount` equals 1 in the example. For complex UIs (emojis, multi-script combinations), consider Unicode/JDK versions and an appropriate segmentation library; a grapheme cluster still does not always equal "one semantic character" in every context.

### Do Not Restrict Every Field with an ASCII Regex

Checks like `^[A-Za-z]+$` reject accented Vietnamese and the letter `đ`. Even a regex allowing only certain precomposed letter ranges can reject NFD strings containing combining marks. If the goal is "allow Vietnamese names", build rules that properly support letters and combining marks, consider normalization, and clearly document the allowed character policy.

Do not mechanically use `\\w` or `Character.isLetter` to claim every name string is valid: there are also combining marks, spaces, hyphens, apostrophes, multiple scripts, security considerations, and business context.

## 13. Testing Vietnamese Unicode with the Right Scope

An appropriate test suite should include:

| Group | Illustrative test | Expectation |
| --- | --- | --- |
| Canonical equivalence | `"\u1EAF"` and `"a\u0306\u0301"` | Raw `equals` differs; equal after NFC |
| NFD decomposition | `"\u1EAF"` | Sequence `U+0061 U+0306 U+0301` |
| Mark order | `"a\u0306\u0301"` vs `"a\u0301\u0306"` | Do not assume arbitrary permutations are equivalent |
| Distinct letter | `"đ"` and `"d"` | NFD does not make them equal |
| Different tone marks | `"ma"` and `"má"` | NFC does not merge them |
| Character counting | `"\u1EAF"` vs `"a\u0306\u0301"` | `length` differs; grapheme count remains 1 in the example |
| Compatibility characters | `"\u2460"` and `"1"` | NFKC can merge, NFC does not |
| Hash/map | Keys from NFC vs NFD | Lookup with unnormalized key can miss |
| Filenames/DB | Visually identical names with different bytes | Requires explicit boundary policy |
| Accent-stripped search | `ma/má/mà` | Can match under search policy without altering original data |

When testing, intentionally compare code point sequences or bytes; screenshots or visual inspection are insufficient to detect normalization differences.

### Checking Consistency Across Layers

For an API storing usernames, create two requests with the same Vietnamese content, one using NFC and one using NFD. Clarify:

1. Does the system accept both?
2. Does it normalize on write, on lookup, or both?
3. Is there any requirement to store the exact original code point sequence?
4. Does it create two records or two distinct cache keys?
5. Do unique constraints operate by canonical equivalence or by another collation?
6. Do displayed results preserve Vietnamese accents and word order?

These questions should be resolved **before** adding normalization to an existing data system, because changing normalized keys can cause collisions between previously distinct records.

## 14. Common Misconceptions

| Misconception | Problem | Correct understanding |
| --- | --- | --- |
| "If the user sees one letter, `length()` must be 1" | A UTF-16 code unit is not a grapheme cluster | Distinguish `length`, `codePointCount`, and graphemes |
| "Two visually identical letters are equal under `String.equals`" | Strings may differ in NFC/NFD form | Normalize to the same form before comparing if required by contract |
| "Every Vietnamese accented letter is one precomposed code point" | Unicode also represents accents via combining marks | Recognize mark sequences and normalization |
| "Reordering combining marks in any way is equivalent" | Canonical ordering does not equate arbitrary permutations | Use `Normalizer`, do not sort marks manually |
| "NFD turns `đ` into `d`" | `đ` has no such canonical decomposition | Mapping `đ/d` requires a separate policy |
| "NFC strips Vietnamese accents" | NFC preserves letter and accent distinctions | Do not confuse normalization with accent stripping |
| "NFKC is always a better choice" | Can merge compatibility characters that must remain distinct | Choose NFC/NFKC per data contract |
| "Just use `equalsIgnoreCase`" | Case-insensitivity does not solve canonical equivalence | Normalize independently of case handling |
| "`codePoints()` iterates one user-perceived letter at a time" | One grapheme can contain multiple code points | Use a grapheme segmenter if needed |
| "Use accent-stripped text as the primary name" | Loses meaning and can create many collisions | Keep original name, create a secondary search key if needed |
| "NFC validates Vietnamese spelling" | `Normalizer` knows nothing of grammar/orthography | Language validation is a separate step |
| "UTF-8 automatically converts to NFC" | Encoding is not Unicode normalization | Normalize per policy, then encode |
| "Databases and Java always compare letters the same way" | Collation, normalization, and byte comparison differ | Test end-to-end from API to DB/cache/index |

## 15. Practice Exercises

**Exercise 1 — Representing the same letter.** Write a string `"\u1EAF"` and a string `"a\u0306\u0301"`. Compare with `equals`, print `length` and `codePointCount`. Explain why those results differ even though both render as `ắ`.

**Exercise 2 — NFC/NFD normalization.** Run `Normalizer.normalize(..., NFC)` and `NFD` on the two strings above. Print all code points in `U+XXXX` format and verify the results after normalization.

**Exercise 3 — Mark ordering.** Compare `a + U+0306 + U+0301` with `a + U+0301 + U+0306`. Are they equal after NFC? Explain why you should not sort marks manually as desired.

**Exercise 4 — Distinguishing different letters.** Try normalizing `"đ"` and `"d"`, `"má"` and `"ma"`. Why does normalization preserve these differences? When might an approximate search feature want to merge them?

**Exercise 5 — Input field limit.** A form limits to 10 "visible characters", yet the code checks `String.length() <= 10`. Show a scenario where a user entering decomposed Vietnamese gets counted as more characters. Design tests based on grapheme clusters.

**Exercise 6 — Identifiers.** Two requests create visually identical display names, one in NFC and one in NFD. When used as `HashMap` keys and in a database unique constraint, how can results differ? Propose a normalization policy at system boundaries, legacy data handling, and collision checking.

**Exercise 7 — NFKC.** Run `Normalizer.normalize("\u2460", NFKC)`. Why does getting `1` not make this a canonical equivalence case like `ắ` and its decomposed sequence?

**Exercise 8 — Search.** Design a Vietnamese name search feature that does not require entering accents. State what must be stored in the original field, what can go into a secondary search index, and how to avoid using accent-stripped results as absolute identifiers.

## 16. Takeaways

**Combining marks are real Unicode code points.** A Vietnamese letter like `ắ` can be stored as one precomposed code point or as a sequence of base letter + combining marks. Two strings can look identical yet differ in code unit count, code point count, and byte count, causing `String.equals`, `HashMap`, or storage systems not to treat them as duplicates automatically.

**`Normalizer.Form.NFC` and `NFD` handle canonical equivalence; they do not strip accents and do not fix spelling.** Distinguish them from `NFKC`/`NFKD` (compatibility equivalence), linguistic collation, and accent-stripped search rules. `đ` does not become `d` via NFD, and changing the order of combining marks does not always preserve the string under Unicode.

In Java, use `Normalizer` to normalize according to a published policy, use `codePoints()` when you need to iterate code points, and use a grapheme segmenter when you need to count or slice user-perceived letters. Store the original text when business rules require preservation, control normalized data consistently across API/database/cache, and thoroughly test Vietnamese Unicode in both NFC and NFD forms.

**Core principle:** *Normalize representation for consistent comparison — do not equate Unicode normalization with removing linguistic distinctions.*

### References

- [`java.text.Normalizer` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html)
- [`java.lang.String` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [`java.util.regex.Pattern` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html)
- [Unicode Normalization Forms (UAX #15)](https://unicode.org/reports/tr15/)
- [Unicode Text Segmentation (UAX #29)](https://unicode.org/reports/tr29/)
