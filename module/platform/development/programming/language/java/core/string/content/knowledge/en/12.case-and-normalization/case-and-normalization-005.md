# Normalizer and NFC, NFD, NFKC, NFKD Forms in Java

Two strings that look identical on screen do not necessarily contain the same sequence of Unicode characters. For instance, the letter **é** can be represented by a single code point `U+00E9` or by the letter **e** `U+0065` followed by the combining acute accent `U+0301`. To Java, `String.equals()` compares UTF-16 code unit sequences, so those two strings are **not equal under `equals()`** even though they may render identically.

Unicode defines **normalization forms** to bring text into consistent representations according to equivalence rules. Java provides `java.text.Normalizer` with four forms: **NFC, NFD, NFKC, NFKD**. Understanding these four forms helps you compare, search, store keys, and exchange multilingual data intentionally while avoiding unintended changes to text meaning.

## 1. What is normalization, and what is it not?

*Unicode normalization* transforms a **sequence of code points** according to Unicode rules: decomposing certain characters, reordering combining marks into canonical order, and optionally composing eligible decomposed sequences into precomposed characters. Two distinct data forms that Unicode considers equivalent under the chosen equivalence type will share the same normalized representation within the scope of those rules.

Example of representing the letter é:

```text
Precomposed form:     U+00E9               é
Decomposed form:      U+0065 U+0301         e + ◌́

Before normalization: two different code point sequences
After NFC:            both become U+00E9
After NFD:            both become U+0065 U+0301
```

In the diagram above, the symbol `◌́` only helps visualize the combining acute accent and is not an extra code point to enter into real data.

**Normalization is not synonymous with:**

- Converting uppercase to lowercase; `"Java"` and `"java"` remain two distinct strings after NFC/NFD/NFKC/NFKD.
- Stripping Vietnamese diacritics or transliterating. `"á"` does not turn into `"a"` simply by calling `Normalizer.normalize(...)`.
- Translating, spell-checking, normalizing arbitrary spaces, or removing invisible characters.
- Comparing by language-specific rules (*collation*); for example, dictionary sorting is a separate concern.
- Guaranteeing that any two visually similar strings will be equal. Characters from different scripts can look alike without being Unicode-equivalent; normalization does not solve all *confusables*.

Importantly, normalization changes the **representation sequence**; it does not replace choosing an appropriate comparison policy for each problem.

## 2. Two types of Unicode equivalence

### 2.1. Canonical equivalence

Two code point sequences are *canonically equivalent* if Unicode treats them as different canonical representations of the same abstract text. A common example is:

- `U+00E9`: precomposed é.
- `U+0065 U+0301`: letter e combined with acute accent.

The two sequences differ in length and code values, yet are considered canonically equivalent. **NFC** and **NFD** preserve this type of equivalence. Converting between them can change the number of code points, code units, encoded bytes, or string indices.

### 2.2. Compatibility equivalence

Some Unicode characters represent presentation forms or symbols with historical or functional distinctions, yet have a **compatibility decomposition** to ordinary character sequences. For example:

- `①` (`U+2460`, circled digit one) has the compatibility form `1` (`U+0031`).
- `ﬃ` (`U+FB03`, ligature) has the compatibility form of three letters `f`, `f`, `i`.
- `Ａ` (`U+FF21`, fullwidth letter A) has the compatibility form `A` (`U+0041`).

These pairs are **not necessarily canonically equivalent**. Converting with **NFKC/NFKD** can erase differences in presentation style or symbol role. That is useful when data needs to be compared in ordinary character form, but it can also **lose distinguishing information** that the problem actually needs to preserve.

Do not infer that any two visually similar symbols are compatibility equivalent. Only mappings defined by the corresponding Unicode data and rules are applied.

## 3. The four forms: NFC, NFD, NFKC, NFKD

You can remember the form names along two axes:

- **C** = *Composition*: performs canonical decomposition, orders combining marks canonically, and then **recomposes** eligible sequences.
- **D** = *Decomposition*: **decomposes** per the rules without recomposing afterward.
- **K** = *Compatibility*: in addition to canonical decomposition, also applies **compatibility decomposition**. The letter K is part of the official Unicode names.

| Form | Full name | Conceptual execution | Key characteristics |
|---|---|---|---|
| **NFD** | Normalization Form D | Canonical decomposition + canonical ordering | Preserves non-canonical differences |
| **NFC** | Normalization Form C | Canonical decomposition + ordering + canonical composition | Often convenient as a consistent form for general text |
| **NFKD** | Normalization Form KD | Canonical **and compatibility** decomposition + ordering | Can reduce presentation symbols to base characters |
| **NFKC** | Normalization Form KC | Canonical **and compatibility** decomposition + ordering + canonical composition | Combines composed form with compatibility merging |

Illustrative examples:

| Input | NFC | NFD | NFKC | NFKD |
|---|---|---|---|---|
| `é` (U+00E9) | `é` | `e` + acute accent | `é` | `e` + acute accent |
| `e` + acute accent (U+0065 U+0301) | `é` | `e` + acute accent | `é` | `e` + acute accent |
| `①` (U+2460) | `①` | `①` | `1` | `1` |
| `ﬃ` (U+FB03) | `ﬃ` | `ﬃ` | `ffi` | `ffi` |
| `Ａ` (U+FF21) | `Ａ` | `Ａ` | `A` | `A` |

**There is no rule that "NFC always has fewer characters than NFD."** There are decomposed sequences that Unicode does not allow composing into a single precomposed character. Composition order and rules are also subject to constraints such as *composition exclusions*. Thus C means "attempt to compose according to the rules," not "guarantee one code point per visible character."

All normalization forms are **idempotent**: applying the **same form** again yields the same content:

```text
normalize(normalize(s, NFC), NFC) == normalize(s, NFC)
```

The line above expresses **content equality**, not a guarantee that two Java references are equal with `==`.

## 4. The `java.text.Normalizer` API in Java 17+

The `java.text.Normalizer` class is in the standard Java library; no external dependency is needed. Two static methods to know:

```java
String normalized = Normalizer.normalize(input, Normalizer.Form.NFC);
boolean alreadyNormalized =
        Normalizer.isNormalized(input, Normalizer.Form.NFC);
```

This is an **illustrative snippet**, assuming `input` is declared as a non-null `String`. The four corresponding enum constants are:

```java
Normalizer.Form.NFC
Normalizer.Form.NFD
Normalizer.Form.NFKC
Normalizer.Form.NFKD
```

- `normalize(String source, Normalizer.Form form)` returns a `String` whose content is in the requested form.
- `isNormalized(String source, Normalizer.Form form)` reports whether the content is **already** in that form. This method is especially useful when validating data or avoiding unnecessary normalization steps in an application pipeline.
- `String` is immutable: none of these operations modify the source string. To keep the result, use a new variable or assign `input = Normalizer.normalize(input, form);`.
- A string can satisfy **multiple forms** simultaneously. For example, `"abc"` is already in NFC, NFD, NFKC, and NFKD.
- `Normalizer` processes Unicode data according to the Unicode version supported by the JDK implementation; for newer Unicode characters, check the support level of your target Java runtime.

### Example 1: the letter é under NFC and NFD

Save as **`CanonicalNormalizationDemo.java`**:

```java
import java.text.Normalizer;
import java.util.stream.Collectors;

public class CanonicalNormalizationDemo {
    private static String codePoints(String s) {
        return s.codePoints()
                .mapToObj(cp -> String.format("U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    public static void main(String[] args) {
        String composed = "\u00E9";
        String decomposed = "e\u0301";

        System.out.println("raw equals: " + composed.equals(decomposed));

        String nfcA = Normalizer.normalize(composed, Normalizer.Form.NFC);
        String nfcB = Normalizer.normalize(decomposed, Normalizer.Form.NFC);
        System.out.println("NFC equals: " + nfcA.equals(nfcB));
        System.out.println("NFC points: " + codePoints(nfcB));

        String nfdA = Normalizer.normalize(composed, Normalizer.Form.NFD);
        String nfdB = Normalizer.normalize(decomposed, Normalizer.Form.NFD);
        System.out.println("NFD equals: " + nfdA.equals(nfdB));
        System.out.println("NFD points: " + codePoints(nfdA));

        System.out.println("decomposed already NFC: "
                + Normalizer.isNormalized(decomposed, Normalizer.Form.NFC));
        System.out.println("decomposed already NFD: "
                + Normalizer.isNormalized(decomposed, Normalizer.Form.NFD));

        String nfcTwice = Normalizer.normalize(nfcB, Normalizer.Form.NFC);
        System.out.println("NFC idempotent: " + nfcB.equals(nfcTwice));
    }
}
```

Run in the directory containing the file using JDK 17+:

```bash
javac CanonicalNormalizationDemo.java
java CanonicalNormalizationDemo
```

**Stdout:**

```text
raw equals: false
NFC equals: true
NFC points: U+00E9
NFD equals: true
NFD points: U+0065 U+0301
decomposed already NFC: false
decomposed already NFD: true
NFC idempotent: true
```

`composed.equals(decomposed)` is initially `false` because the UTF-16 code unit sequences differ. After NFC, both contain `U+00E9`; after NFD, both contain `U+0065 U+0301`. `isNormalized` checks the **current normalization form**; it does not check whether a string is valid Vietnamese/English, nor does it strip accents. `NFC idempotent` demonstrates that re-applying an already satisfied form does not change the content.

## 5. Example 2: where do NFKC/NFKD differ from NFC/NFD?

The defining feature of the two forms with **K** is that they also process compatibility mappings. To avoid depending on console fonts for special characters, the example below prints **Unicode code points** instead of printing the resulting glyphs directly.

Save as **`CompatibilityNormalizationDemo.java`**:

```java
import java.text.Normalizer;
import java.util.stream.Collectors;

public class CompatibilityNormalizationDemo {
    private static String points(String s) {
        return s.codePoints()
                .mapToObj(cp -> String.format("U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    private static void show(String name, String input) {
        System.out.println(name + " NFC: " + points(
                Normalizer.normalize(input, Normalizer.Form.NFC)));
        System.out.println(name + " NFD: " + points(
                Normalizer.normalize(input, Normalizer.Form.NFD)));
        System.out.println(name + " NFKC: " + points(
                Normalizer.normalize(input, Normalizer.Form.NFKC)));
        System.out.println(name + " NFKD: " + points(
                Normalizer.normalize(input, Normalizer.Form.NFKD)));
    }

    public static void main(String[] args) {
        show("circled-one", "\u2460");
        show("ligature-ffi", "\uFB03");
        show("fullwidth-A", "\uFF21");
    }
}
```

```bash
javac CompatibilityNormalizationDemo.java
java CompatibilityNormalizationDemo
```

**Stdout:**

```text
circled-one NFC: U+2460
circled-one NFD: U+2460
circled-one NFKC: U+0031
circled-one NFKD: U+0031
ligature-ffi NFC: U+FB03
ligature-ffi NFD: U+FB03
ligature-ffi NFKC: U+0066 U+0066 U+0069
ligature-ffi NFKD: U+0066 U+0066 U+0069
fullwidth-A NFC: U+FF21
fullwidth-A NFD: U+FF21
fullwidth-A NFKC: U+0041
fullwidth-A NFKD: U+0041
```

The results show:

1. NFC/NFD do not convert `①` to `1`, `ﬃ` to `ffi`, or `Ａ` to `A` because those pairs are related only via **compatibility equivalence**.
2. NFKC/NFKD can lose information about symbol type, presentation style, or character width. If distinguishing `①` from `1` matters in your data, **do not default to NFKC**.
3. For example strings that have no sequences needing composition after compatibility decomposition, NFKC and NFKD outputs coincide. That does **not** mean the two forms are always identical: they differ whenever components require canonical composition after decomposition.

## 6. Combining characters, mark ordering, and common misconceptions

A Unicode sequence can consist of a base character and multiple combining marks. Normalization does not merely replace one precomposed character with two characters or vice versa; it also applies **canonical ordering** based on *Canonical Combining Class* where rules allow.

Therefore:

- Sequences that have the same canonical meaning but different combining-mark orders are sometimes brought into the same canonical order. Do not arbitrarily swap diacritics; Unicode has specific rules and exceptions.
- A combining mark does not necessarily have a precomposed character for every base letter. Multiple code points can remain even after NFC.
- "One code point" does not mean "one character perceived by the user." A **grapheme cluster** can contain multiple code points, even after normalization.
- `String.length()` counts UTF-16 code units, `codePointCount(0, length())` counts code points, while the number of displayed character clusters is a different measurement. Normalization can change the first two counts while producing a visually similar representation.

Example:

```text
Before: "e" + U+0301
  UTF-16 code units = 2
  Unicode code points = 2

After NFC: U+00E9
  UTF-16 code units = 1
  Unicode code points = 1

One é character as typically perceived by a user: 1 grapheme cluster
```

If you store cursor offsets, `substring` boundaries, highlight ranges, search indices, or annotation coordinates on the original content, **do not reuse old indices after normalization**. Normalize before computing offsets, or build a source–target position mapping mechanism when original text coordinates must be preserved.

## 7. Normalizing before comparing and searching

`String.equals()`, `indexOf()`, `contains()`, and `String` keys in `HashMap` do not apply Unicode normalization automatically. Therefore, data representing the same word with differently encoded diacritics can compare `false` or fail to match in searches.

A common workflow for **canonical equivalence**:

1. Define the comparison rule: here, treat two *canonically equivalent* strings as the same text.
2. Choose **a single form**, usually NFC.
3. Normalize **both sides** before comparing or when writing/querying keys.
4. Use `equals()`/`Objects.equals()` or search operations on the normalized strings.

### Example 3: `HashMap` keys must use a consistent form

Save as **`NormalizedLookupDemo.java`**:

```java
import java.text.Normalizer;
import java.util.HashMap;
import java.util.Map;

public class NormalizedLookupDemo {
    private static String nfc(String s) {
        return Normalizer.normalize(s, Normalizer.Form.NFC);
    }

    public static void main(String[] args) {
        String stored = "caf\u00E9";
        String queried = "cafe\u0301";

        Map<String, String> labels = new HashMap<>();
        labels.put(stored, "found");

        System.out.println("raw equals: " + stored.equals(queried));
        System.out.println("lookup raw: " + labels.get(queried));
        System.out.println("lookup NFC: " + labels.get(nfc(queried)));

        Map<String, String> canonical = new HashMap<>();
        canonical.put(nfc(stored), "normalized");
        System.out.println("canonical lookup: " + canonical.get(nfc(queried)));
    }
}
```

```bash
javac NormalizedLookupDemo.java
java NormalizedLookupDemo
```

**Stdout:**

```text
raw equals: false
lookup raw: null
lookup NFC: found
canonical lookup: normalized
```

The `lookup NFC` line succeeds because `stored` in the example happened to already be in NFC; **you cannot generalize** that normalizing only the query side is enough. To avoid depending on the storage side happening to be normalized, use the same `nfc(...)` function when **writing keys** and **creating lookup keys**, as shown with `canonical` at the end of the example.

A system with existing data stored in mixed forms needs a **data migration** plan or a suitable lookup strategy. Changing only read-side code can leave older keys unfindable if stored key normalization forms are inconsistent.

### Searching for substrings with diacritics

If you want `contains()` or `indexOf()` to honor canonical equivalence, you can normalize both the source string and the search term to NFC before searching. However, the offset returned by `indexOf()` is a UTF-16 offset **on the normalized string**. If you need that offset to highlight the **unnormalized source string**, you must map the position back; do not feed the new offset directly into the old source string.

If the application needs language-aware search, case insensitivity, accent-variant handling, or dictionary sorting, NFC alone may not suffice; define a locale-aware matching algorithm or an appropriate search engine.

## 8. Normalization and case conversion are two independent steps

NFC, NFD, NFKC, and NFKD are **not** "lowercase" or "case-insensitive" modes. For instance:

```java
String a = "Java";
String b = "java";

System.out.println(java.text.Normalizer.normalize(
        a, java.text.Normalizer.Form.NFC).equals(b)); // false
```

This is an **illustrative snippet** that can run inside a Java method; the printed result is `false`.

If business policy requires **case-insensitive** comparison, Java also provides `String.toLowerCase(Locale)`, `equalsIgnoreCase(...)`, and related APIs. Choose based on language and context:

- `toLowerCase(Locale.ROOT)` is convenient for certain identifiers with **locale-independent** rules, though it is not always equivalent to *full Unicode case folding*.
- A specific `Locale` can alter case conversion for certain letters, such as in Turkish.
- Case conversion can alter the code point sequence; if the design requires a fixed normalization form after transformation, consider **re-normalizing after the case-conversion step**.
- NFKC **does not automatically** perform full case folding; the `NFKC_Casefold` concept in certain Unicode standards is not simply calling `Normalizer.normalize(s, NFKC)`.

Therefore, do not call NFKC and assume two personal names, account names, or natural-language strings are "equal regardless of case." Comparison rules must be clearly specified and tested across the languages the application supports.

## 9. Which form to choose for real-world scenarios?

| Scenario | Candidate choice | Rationale and limitations |
|---|---|---|
| Store/compare ordinary text under canonical equivalence | **NFC** | Preserves compatibility distinctions while unifying precomposed/decomposed forms |
| Algorithm needs to analyze base characters and combining marks separately | **NFD** | Canonical decomposition for code point manipulation; avoid assuming marks can be stripped arbitrarily |
| Normalize identifiers with compatibility characters per an explicit spec | **NFKC** | Can fold fullwidth letters, ligatures, presentation symbols; requires a policy accepting those merges |
| Process individual elements after compatibility decomposition | **NFKD** | Keeps compatibility decomposition for analysis; can lose presentation distinctions |
| Legal documents, exact transcripts, digital signatures, or data requiring original bytes | **Do not convert arbitrarily** | Normalization can change code points and bytes; only do so when protocol/spec mandates |
| Passwords or secrets fed into a KDF/hash function | **Follow exact auth specification** | Out-of-contract normalization changes authentication values and can cause incompatibility |
| Language-sensitive, case-insensitive, or accent-insensitive search | **Dedicated search rules** | A single Normalizer form does not cover full language rules |
| Need visually uniform glyph/width rendering | **Font and UI handling** | Normalization does not control how a renderer shapes glyphs |

**NFC is usually a relatively safe consistent choice when only canonical equivalence is required**, yet even NFC can alter byte sequences and offsets. There is no single "best" normalization form for every application. NFKC/NFKD are stronger in the sense of merging compatibility differences too; "stronger" does not mean "better" for all data.

### Avoid automatically stripping diacritics after NFD

A common trick is decomposing with NFD and deleting every character in the *Mark* category (e.g., regex `\p{M}`). This can turn `"café"` into `"cafe"`, but that is a **custom diacritic-stripping algorithm**, going beyond pure normalization. In Vietnamese and many other scripts, diacritics carry lexical and grammatical meaning; stripping them can create ambiguity or alter meaning. If accent-insensitive search is needed, design a dedicated search index/matcher while keeping the original text intact.

## 10. Performance, Unicode versions, and stability

- Normalization has the cost of scanning and transforming content. For large datasets or hot paths, avoid normalizing the same unchanged string repeatedly if you can organize a single normalization step at ingestion/storage boundaries.
- `isNormalized(...)` helps detect strings already in the right form, but checking still scans the data; do not assume a check call plus a normalize call is always faster than normalizing directly. When performance is a requirement, measure with benchmarks on representative workloads.
- Standard Java APIs return results following the Unicode data implemented by the JDK. Character data and support can be updated across JDK upgrades; if a system exchanges data across multiple runtimes, verify critical characters and upgrade policies.
- Unicode normalization provides **normalization stability** guarantees under standard rules, but that does not mean every JDK version recognizes all newly added Unicode characters identically, or that all search/display behaviors are uniform.
- Always document the normalization form at important data boundaries: for example, "keys are stored and queried in NFC" is easier to verify than an implicit convention.
- Do not use `==` to compare content after normalization: two results with the same character sequence are not guaranteed to be the same `String` object. Use `equals()` or `Objects.equals()`.

## 11. Common mistakes

| Misconception or mistake | Why it is wrong | How to handle |
|---|---|---|
| `"é".equals("e\u0301")` must be `true` because they look alike | `equals()` compares code unit sequences, without normalizing | Pick NFC/NFD and normalize both sides when canonical equivalence is needed |
| NFC means "strip accents" | NFC can compose accents into precomposed characters | Use NFC for canonical composition, not as an accent filter |
| NFD always produces one code point per character | NFD decomposes, which can yield multiple code points | Distinguish code unit, code point, and grapheme cluster |
| NFC/NFD and NFKC/NFKD are always equivalent | K forms also perform compatibility decomposition | Choose the form based on business rules |
| NFKC does not affect important content | `①` becoming `1` or `ﬃ` becoming `ffi` can lose needed distinctions | Do not default to NFKC for data where distinctions must be preserved |
| Normalizing only query input | Stored keys may be in a different form | Normalize consistently at both storage and lookup time |
| Normalization keeps `indexOf` offsets valid on the old source | Length/code points can change | Compute offsets on the target string itself or map positions |
| Normalization automatically handles case | Normalizer does not perform general case folding | Design a separate case-handling step |
| Using `==` to compare two normalized strings | `==` compares references | Use `equals()` for content |
| Normalization removes confusable characters or sanitizes dangerous input | Unicode confusables, validation, and input security are distinct problems | Use dedicated validation rules; do not treat Normalizer as a security filter |
| Calling normalize and discarding the return value | `String` is immutable | Reassign the variable or use the returned value |

## 12. Self-check

Before running, predict the values below:

**`NormalizationSelfCheck.java`**

```java
import java.text.Normalizer;

public class NormalizationSelfCheck {
    public static void main(String[] args) {
        String a = "\u00E9";
        String b = "e\u0301";

        System.out.println(a.equals(b));
        System.out.println(Normalizer.normalize(a, Normalizer.Form.NFC)
                .equals(Normalizer.normalize(b, Normalizer.Form.NFC)));

        String circledOne = "\u2460";
        String plainOne = "1";

        System.out.println(Normalizer.normalize(
                circledOne, Normalizer.Form.NFC).equals(plainOne));
        System.out.println(Normalizer.normalize(
                circledOne, Normalizer.Form.NFKC).equals(plainOne));

        String mixedCase = "Java";
        System.out.println(Normalizer.normalize(
                mixedCase, Normalizer.Form.NFKC).equals("java"));
    }
}
```

```bash
javac NormalizationSelfCheck.java
java NormalizationSelfCheck
```

**Stdout:**

```text
false
true
false
true
false
```

Explanation:

1. Unnormalized `a` and `b` look equivalent visually, yet direct `String.equals()` is still `false`.
2. When both are normalized to NFC, they become canonically equivalent code point sequences, so `equals()` returns `true`.
3. NFC does not apply the compatibility mapping `①` → `1`, hence `false`.
4. NFKC does apply that compatibility mapping, hence `true`.
5. NFKC does not turn uppercase `J` into lowercase `j`, so `"Java"` still differs from `"java"`.

**Question to choose your form:** does your application need to preserve all compatibility symbols and unify only canonical representations (NFC/NFD), or does it accept folding certain presentation characters to ordinary letters/digits (NFKC/NFKD)? Next, pick a well-founded form, normalize consistently at data boundaries, then compare with `equals()` and test with representative Unicode data.
