# Collator Decomposition Modes and Their Relationship to Unicode Normalization in Java

## 1. Why Do Two Strings That Look Identical Compare Differently?

In a multilingual application, two users may enter the letter `é` in two different Unicode representations:

- **Precomposed:** `U+00E9`, the character `é`.
- **Decomposed:** `U+0065` (`e`) + `U+0301` (COMBINING ACUTE ACCENT).

The two forms are normally perceived as the same accented letter, yet `String.equals` compares `String` contents by UTF-16, so they are **not equal**. Similarly, full-width Latin `Ａ` (`U+FF21`) and `A` (`U+0041`) have related appearances yet **different code points**.

When sorting or searching person names in Vietnamese, French, German, and many other languages, comparing code units in binary order alone is insufficient. Java provides `java.text.Collator` to **compare strings according to linguistic rules (collation)** and `java.text.Normalizer` to **normalize Unicode character sequences**. A key part of `Collator` is the **decomposition** mode—decomposing before/during collation processing.

This lesson distinguishes the three modes `NO_DECOMPOSITION`, `CANONICAL_DECOMPOSITION`, and `FULL_DECOMPOSITION`; their relationship to `Normalizer.Form.NFD`/`NFKD`; the independence between **decomposition** and **strength**; runnable Java 17+ examples; and warnings about comparison, search, data keys, and performance.

## 2. What Does Collator Do and Not Do?

`Collator` is a `Comparator<Object>` specialized for text by `Locale`. Created via factory:

```java
import java.text.Collator;
import java.util.Locale;

Collator vietnamese = Collator.getInstance(
        Locale.forLanguageTag("vi-VN"));
int comparison = vietnamese.compare("an", "bình");
```

This is a **snippet** placed inside a method. The negative/0/positive `compare` result indicates collation order, **not** code point order or UTF-8 byte order. Exact behavior depends on the Java runtime's locale/provider rules.

Key APIs:

| API | Meaning |
| --- | --- |
| `Collator.getInstance(locale)` | Obtains a comparator for the locale |
| `compare(a, b)` | Returns negative, 0, or positive per collation |
| `setStrength(level)` | Selects the **level of difference** considered |
| `getStrength()` | Reads the current difference level |
| `setDecomposition(mode)` | Selects **how Unicode is decomposed** during collation |
| `getDecomposition()` | Reads the current decomposition mode |
| `getCollationKey(text)` | Creates a comparison/sort key for the same collator configuration |
| `clone()` | Creates a copy for separate configuration or use |

**Collation is not normalization.** `Collator.compare(a, b) == 0` only means two strings are treated as equivalent **under the current comparison configuration**; it does not mean `a.equals(b)`, `a.getBytes(...)`, or their business identities are equal. A collator at `PRIMARY` may consider two differently accented strings equivalent, but that does not establish a Unicode normalization relationship between them.

## 3. The Three Decomposition Modes of Collator

Java defines three integer constants in `Collator`:

```java
Collator.NO_DECOMPOSITION
Collator.CANONICAL_DECOMPOSITION
Collator.FULL_DECOMPOSITION
```

Set on an instance:

```java
Collator collator = Collator.getInstance(Locale.US);
collator.setDecomposition(Collator.CANONICAL_DECOMPOSITION);
int selectedMode = collator.getDecomposition();
```

| Mode | Meaning | Relation to Unicode normalization | When to consider |
| --- | --- | --- | --- |
| `NO_DECOMPOSITION` | Does not decompose input characters as a separate configuration step | Does not correspond to an enforced normalization form | When certain the data/locale needs no decomposition or inputs are already appropriately processed; conditional speed priority |
| `CANONICAL_DECOMPOSITION` | Decomposes **canonical equivalents** | Corresponds to canonical decomposition form `NFD` | Comparing accented text, strings with combining/precomposed forms |
| `FULL_DECOMPOSITION` | Decomposes both **canonical** and **compatibility equivalents** | Corresponds to compatibility decomposition form `NFKD` | When formatting variants like full-width/half-width and characters with compatibility decompositions must also be handled |

Per Java SE documentation, `NO_DECOMPOSITION` may be fastest, though it does not always give accurate comparisons for accented languages. `CANONICAL_DECOMPOSITION` handles accent variants accurately, while `FULL_DECOMPOSITION` handles additional compatibility forms at higher cost. Actual cost depends on data, implementation, caching, and comparison volume; **do not assume FULL is always necessary**.

One subtlety: the `RuleBasedCollator` implementation may **automatically generate precomposed character mappings** when compiling the collation rule table. Consequently, even `NO_DECOMPOSITION` can sometimes treat precomposed and combining forms of a letter as equivalent at certain strength levels. Never infer in reverse that because `compare` returns 0 decomposition mode is enabled, or that `NO_DECOMPOSITION` **always** returns non-zero for every canonically equivalent pair.

### 3.1. NO_DECOMPOSITION

In this mode, the collator does not perform character decomposition as configured by the decomposition setting. An upside is potentially less work; the downside is that strings with differently ordered combining marks or variants absent from the rule table may not be handled as expected.

```java
collator.setDecomposition(Collator.NO_DECOMPOSITION);
```

Choose this only after confirming suitability for the script, data rules, and deployment version in use. If multi-source inputs contain Unicode with combining marks, `CANONICAL_DECOMPOSITION` is usually safer.

### 3.2. CANONICAL_DECOMPOSITION

In this mode, canonically equivalent Unicode forms are decomposed per rules related to `NFD`. For example:

```text
U+00E9       →  U+0065 U+0301
é (precomposed) e + combining acute accent
```

Can be configured as:

```java
collator.setDecomposition(Collator.CANONICAL_DECOMPOSITION);
```

Canonical decomposition does not automatically strip accents or ignore case. **Whether accents are treated as differences during comparison** still depends on `strength` (and locale rules). Thus `CANONICAL_DECOMPOSITION` is **not equivalent** to "accent-insensitive comparison."

### 3.3. FULL_DECOMPOSITION

`FULL_DECOMPOSITION` handles both canonical equivalents and compatibility forms:

```text
U+FF21  FULLWIDTH LATIN CAPITAL LETTER A → U+0041 A
U+FB00  LATIN SMALL LIGATURE FF          → U+0066 U+0066 (ff)
```

Can be configured as:

```java
collator.setDecomposition(Collator.FULL_DECOMPOSITION);
```

In this example, characters with related semantics can be compared on a common basis. However, compatibility decomposition **can erase distinctions of presentation or application meaning** (e.g., between full-width and ASCII). Do not use FULL to declare two identifiers, passwords, or security codes equal unless explicitly specified by system standards.

## 4. Strength and Decomposition Are Two Separate Configuration Axes

`Collator` also has four `strength` levels:

| Strength | Differences considered (general) | Typical example |
| --- | --- | --- |
| `PRIMARY` | Base letter differences | "a" and "á" may be treated similarly in many locales |
| `SECONDARY` | Adds accent differences | "a" and "á" are usually distinguished |
| `TERTIARY` | Adds case/variant differences | "a" and "A" are usually distinguished |
| `IDENTICAL` | Adds differences not examined at lower levels | May distinguish Unicode representations when corresponding decomposition is not enabled |

The description above is a mental model; which letters are distinguished at which level depends on **locale rules and provider**. `PRIMARY` is not a standard "strip all accents" function, and `TERTIARY` does not mean "guaranteed to match `String.equals`."

The two settings **do not replace each other**:

- `strength`: **which kinds of differences matter** in comparison.
- `decomposition`: **how characters are decomposed** for comparison.

For instance, `"é"` vs. `"e"` may compare equal at `PRIMARY` whether decomposition is on or off, because accents are ignored at that strength level. Conversely, `"é"` vs. `"e\u0301"` are two encodings of **the same accented letter**, so enabling canonical decomposition yields more consistent comparison even when strength is raised to `IDENTICAL`.

### 4.1. Choosing Configuration by Requirement

**Search that may ignore accents:** start with `Collator.getInstance(userLocale)` and test `PRIMARY` against real vocabulary. However, design explicitly which differences are ignored rather than using it as an identity gate.

**Sorting names with accents and case:** `SECONDARY` or `TERTIARY` are starting points, combined with `CANONICAL_DECOMPOSITION` when inputs contain multiple accent representations.

**Requiring distinction of even tiny Unicode variants:** `IDENTICAL` can be tested, though it still depends on decomposition. If exact UTF-16 verification is needed, use `String.equals`; if byte-exactness is needed, compare bytes in a defined encoding.

## 5. Runnable Example: NO, CANONICAL, and FULL at Strength IDENTICAL

To observe decomposition modes most clearly, fix `Locale.US` and `strength = IDENTICAL`, then compare three pairs:

1. `"\u00E9"` (precomposed é) vs. `"e\u0301"` (e + acute accent): canonically equivalent.
2. `"\uFF21"` (full-width A) vs. `"A"`: compatibility-equivalent, not canonically equivalent.
3. `"\uFB00"` (ff ligature) vs. `"ff"`: compatibility-equivalent, not canonically equivalent.

Create file **`CollatorDecompositionDemo.java`**:

```java
import java.text.Collator;
import java.util.Locale;

public class CollatorDecompositionDemo {
    private static void show(String modeName, int mode,
                             String composed, String decomposed,
                             String wide, String plain,
                             String ligature, String letters) {
        Collator collator = Collator.getInstance(Locale.US);
        collator.setStrength(Collator.IDENTICAL);
        collator.setDecomposition(mode);

        System.out.println(modeName
                + " | accent=" + (collator.compare(composed, decomposed) == 0)
                + " | width=" + (collator.compare(wide, plain) == 0)
                + " | ligature=" + (collator.compare(ligature, letters) == 0));
    }

    public static void main(String[] args) {
        String composed = "\u00E9";
        String decomposed = "e\u0301";
        String wide = "\uFF21";
        String plain = "A";
        String ligature = "\uFB00";
        String letters = "ff";

        show("NO", Collator.NO_DECOMPOSITION,
                composed, decomposed, wide, plain, ligature, letters);
        show("CANONICAL", Collator.CANONICAL_DECOMPOSITION,
                composed, decomposed, wide, plain, ligature, letters);
        show("FULL", Collator.FULL_DECOMPOSITION,
                composed, decomposed, wide, plain, ligature, letters);
    }
}
```

Compile and run on Java 17 or higher:

```bash
javac -encoding UTF-8 CollatorDecompositionDemo.java
java CollatorDecompositionDemo
```

**Output verified on JDK 24 (Locale.US, default provider in test environment):**

```text
NO | accent=false | width=false | ligature=false
CANONICAL | accent=true | width=false | ligature=false
FULL | accent=true | width=true | ligature=true
```

Explanation:

- **NO:** decomposition disabled; at `IDENTICAL` on the tested provider, the pairs are distinguished.
- **CANONICAL:** the two representations of `é` become collation-equivalent. Full-width `Ａ` and ligature `ﬀ` are **compatibility** equivalents, not resolved by canonical decomposition.
- **FULL:** pairs with matching canonical or compatibility decompositions are treated as equivalent in this test.

**Portability note:** `Collator` is a factory that may be backed by different `CollatorProvider`s/locale data. The sample output above is one observed test run, not a promise that every provider/JDK has the exact same collation table. In production tests, pin the JDK/provider or test invariants required by the application contract.

The program uses `compare(...) == 0` rather than checking exact numerical values `-1` or `1`, because `Comparator` only promises **negative, 0, or positive**, not specific magnitudes.

## 6. Relationship to java.text.Normalizer: NFD, NFKD, NFC, and NFKC

`java.text.Normalizer` transforms **string contents** into a Unicode normalization form. It is a different API from `Collator`:

```java
String normalized = Normalizer.normalize(
        input, Normalizer.Form.NFC);
```

`Normalizer` forms:

| Form | Name | Function |
| --- | --- | --- |
| `NFD` | Canonical Decomposition | Decomposes by canonical equivalence; reorders combining marks canonically |
| `NFC` | Canonical Decomposition, followed by Composition | Canonical decomposition followed by canonical composition where possible |
| `NFKD` | Compatibility Decomposition | Canonical and compatibility decomposition |
| `NFKC` | Compatibility Decomposition, followed by Composition | Compatibility decomposition followed by canonical composition where possible |

Two common conceptual correspondences:

- `Collator.CANONICAL_DECOMPOSITION` ↔ decomposition level corresponding to **`Normalizer.Form.NFD`**.
- `Collator.FULL_DECOMPOSITION` ↔ decomposition level corresponding to **`Normalizer.Form.NFKD`**.

This does **not** mean `Collator` calls `Normalizer.normalize` and returns a transformed string. `Collator` **compares** by rules and strength, whereas `Normalizer` **produces a new normalized string**.

### 6.1. Comparing Canonical Equivalence with Normalizer

```java
String a = "\u00E9";
String b = "e\u0301";

boolean rawEqual = a.equals(b); // false

String normalizedA = Normalizer.normalize(
        a, Normalizer.Form.NFC);
String normalizedB = Normalizer.normalize(
        b, Normalizer.Form.NFC);

boolean canonicalEqual = normalizedA.equals(normalizedB); // true
```

This pair is canonically equivalent. `NFD` can be used instead of `NFC` if a data pipeline requires decomposed marks. In most standard storage UIs, `NFC` is usually convenient, though form choice must rest on the data contract.

### 6.2. Comparing Compatibility Equivalence with Normalizer

```java
String wide = "\uFF21";
String ascii = "A";

boolean nfdEqual = Normalizer.normalize(
        wide, Normalizer.Form.NFD).equals(
        Normalizer.normalize(ascii, Normalizer.Form.NFD));  // false

boolean nfkdEqual = Normalizer.normalize(
        wide, Normalizer.Form.NFKD).equals(
        Normalizer.normalize(ascii, Normalizer.Form.NFKD)); // true
```

**NFKD/NFKC can lose meaningful distinctions.** For example, full-width letters, ligatures, or superscript/subscript digits can turn into common compatibility forms. Therefore, do not replace `NFC` with `NFKC` or `NFKD` across an entire database without an explicit design/migration decision.

## 7. Java 17+ Example: Normalization Changes Strings, Collation Changes Comparison

Create file **`NormalizationVsCollationDemo.java`**:

```java
import java.text.Collator;
import java.text.Normalizer;
import java.util.Locale;

public class NormalizationVsCollationDemo {
    public static void main(String[] args) {
        String composed = "\u00E9";
        String decomposed = "e\u0301";
        String wide = "\uFF21";
        String plain = "A";

        System.out.println("raw accent equals: "
                + composed.equals(decomposed));
        System.out.println("NFC accent equals: "
                + Normalizer.normalize(composed, Normalizer.Form.NFC)
                    .equals(Normalizer.normalize(
                            decomposed, Normalizer.Form.NFC)));

        System.out.println("NFD width equals: "
                + Normalizer.normalize(wide, Normalizer.Form.NFD)
                    .equals(Normalizer.normalize(
                            plain, Normalizer.Form.NFD)));
        System.out.println("NFKD width equals: "
                + Normalizer.normalize(wide, Normalizer.Form.NFKD)
                    .equals(Normalizer.normalize(
                            plain, Normalizer.Form.NFKD)));

        Collator collator = Collator.getInstance(Locale.US);
        collator.setStrength(Collator.IDENTICAL);
        collator.setDecomposition(Collator.CANONICAL_DECOMPOSITION);

        System.out.println("collator accent equal: "
                + (collator.compare(composed, decomposed) == 0));
        System.out.println("String still different: "
                + !composed.equals(decomposed));
    }
}
```

Commands:

```bash
javac -encoding UTF-8 NormalizationVsCollationDemo.java
java NormalizationVsCollationDemo
```

Output in the tested JDK 24 environment:

```text
raw accent equals: false
NFC accent equals: true
NFD width equals: false
NFKD width equals: true
collator accent equal: true
String still different: true
```

**Conclusion from the example:** normalization and collation both care about Unicode relationships, yet have **different outputs/contracts**. `Normalizer` creates `String`s for comparison/reuse, while `Collator.compare` only returns an ordering relation. Calling `compare` does not mutate the two original strings.

## 8. Vietnamese Accents: Decomposition Does Not Mean Accent Removal

Vietnamese has many tone marks and letter-forming diacritics. For instance, the letter `ấ` can have forms composed from one or multiple combining characters in Unicode, where canonical normalization helps reconcile equivalent representations.

However:

- **Decomposing accents:** splits Unicode code components, e.g., `ấ` into canonical components when applying `NFD`.
- **Stripping accents:** removes combining marks per a separate policy—**not** the default function of `Collator.CANONICAL_DECOMPOSITION` or `Normalizer.normalize(..., NFD)`.
- **Accent-relaxed comparison:** `Collator.PRIMARY` may be considered for certain search features, though exact order and distinction levels depend on locale.

Do not blindly use a regex to delete all marks as a general Vietnamese comparison strategy, as it can cause many semantically distinct words to collide. A search feature allowing users to type without accents can use a dedicated search index while retaining original strings for accurate display.

### 8.1. When to Use Strength PRIMARY?

If a UI offers "fuzzy matching" or sorting that need not emphasize accent differences, `Collator.PRIMARY` is an option to **evaluate**. However, PRIMARY may also ignore case distinctions or certain variants depending on locale. It is neither a technical key normalizer nor an accentless Unicode converter.

If users must distinguish `ma`, `má`, and `mà` for semantic reasons, consider `SECONDARY` or `TERTIARY` and test on real words. **Decomposition determines how character representations are prepared, not whether accents are distinguished.**

## 9. Standalone Illustration for Strength and Decomposition

Create file **`CollatorStrengthDemo.java`**:

```java
import java.text.Collator;
import java.util.Locale;

public class CollatorStrengthDemo {
    public static void main(String[] args) {
        Collator c = Collator.getInstance(Locale.US);
        c.setDecomposition(Collator.CANONICAL_DECOMPOSITION);

        int[] strengths = {
                Collator.PRIMARY, Collator.SECONDARY,
                Collator.TERTIARY, Collator.IDENTICAL
        };
        String[] names = {
                "PRIMARY", "SECONDARY",
                "TERTIARY", "IDENTICAL"
        };

        for (int i = 0; i < strengths.length; i++) {
            c.setStrength(strengths[i]);

            System.out.println(names[i]
                    + " | composed-vs-decomposed="
                    + (c.compare("\u00E9", "e\u0301") == 0)
                    + " | accented-vs-plain="
                    + (c.compare("\u00E9", "e") == 0)
                    + " | upper-vs-lower="
                    + (c.compare("E", "e") == 0));
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 CollatorStrengthDemo.java
java CollatorStrengthDemo
```

Verified output in `Locale.US`/JDK 24 environment:

```text
PRIMARY | composed-vs-decomposed=true | accented-vs-plain=true | upper-vs-lower=true
SECONDARY | composed-vs-decomposed=true | accented-vs-plain=false | upper-vs-lower=true
TERTIARY | composed-vs-decomposed=true | accented-vs-plain=false | upper-vs-lower=false
IDENTICAL | composed-vs-decomposed=true | accented-vs-plain=false | upper-vs-lower=false
```

At every strength level, the two representations of **the same accented letter** remain equal due to canonical decomposition. However, `é` and `e` are only considered equal at `PRIMARY` on the tested provider, while `E` and `e` are distinguished from `TERTIARY` upward.

**Reasonable workflow order:** pin locale → determine strength by search/sort requirement → determine decomposition by input Unicode quality → test edge cases. Never treat a strength or decomposition setting stumbled upon on a developer machine as a universal cross-environment contract.

## 10. NO_DECOMPOSITION Does Not Mean "Never Handles Accents"

`RuleBasedCollator` documentation notes that it can incorporate **precomposed** and **combining-character** variants into its rule table when building the collation table. Therefore:

1. A pair like `é` and `e + acute` may be treated as equivalent **even under NO_DECOMPOSITION** if the rule table already includes that mapping, especially at low strength.
2. Combining marks in **non-canonical order** are an important situation requiring `CANONICAL_DECOMPOSITION` or `FULL_DECOMPOSITION` to ensure proper handling.
3. **Compatibility** characters such as full-width/half-width generally require `FULL_DECOMPOSITION` if compatibility-decomposed comparison is desired.

Do not build tests assuming "NO always differs, CANONICAL always equals" for every pair and locale/provider. Sound tests reflect **product requirements** and the supported runtime. For uncontrolled international user input, `CANONICAL_DECOMPOSITION` is usually a better starting point than NO.

## 11. CollationKey, Sorting, and Configuration Consistency

When sorting large volumes of strings repeatedly, `Collator.getCollationKey(text)` can help avoid recomputing collation on every comparison. However:

- Only compare `CollationKey`s created from **collators with the same configuration**: locale, strength, decomposition, provider, and compatible collation data.
- Never call `setStrength`/`setDecomposition` between key creations and mix them in the same sort.
- Collation keys are internal collation data, **not a standard format for long-term storage across JDK versions**.
- If a collator considers two strings equal, their keys compare equal in order, yet the two strings can still differ under `String.equals`.

`Collator` is mutable and not guaranteed thread-safe if multiple threads mutate configuration; documentation recommends obtaining **a separate instance per thread** when needed. You can `clone()` a configured template to create a per-task instance, or create fresh ones as needed. Never mutate a shared collator on a server when concurrent requests have different locales and strengths.

### TreeSet/TreeMap Pitfall

`TreeSet<String>` with a `Collator` comparator uses `compare(a,b)==0` to decide whether two elements occupy the same slot in the sort order. If `Collator.PRIMARY` treats `"e"` and `"é"` as equal, adding both can leave the set with only one element. This can **differ from `String.equals`**, causing surprises or data loss if you treat the set as a collection of unique IDs.

Use collation for **sorting and linguistic searching**, not implicitly as a **uniqueness/identity** rule. When wanting a stable total sort order that still distinguishes different strings, you can add a `String.compareTo` (or immutable ID) tie-breaker per contract, while carefully considering whether collation equality needs to remain a distinct grouping concept.

## 12. Normalize Before Storage or Only for Comparison?

This is an important architectural decision:

| Goal | Approach | Caveats |
| --- | --- | --- |
| Compare/sort names linguistically | `Collator(locale)` with chosen strength/decomposition | Locale/provider affect results |
| Ensure two canonically equivalent forms share a storage form | `Normalizer.normalize(s, NFC)` at appropriate data boundary | Requires normalization rules and migration of legacy data if changed |
| Build a search index ignoring certain text differences | A separate search field/index | Do not delete original; define acceptable ignored differences |
| Compare exact technical codes | `String.equals` or byte comparison by encoding | Do not use `Collator.PRIMARY` |
| Match compatibility variants | `FULL_DECOMPOSITION` or deliberate compatibility normalization | May collapse forms that were previously business-distinct |
| Case-insensitive comparison | Define explicit locale/case-folding/collation policy | Never assume lowercasing replaces all comparison rules |
| Store and verify passwords/tokens | Follow system-specified security/normalization standards | Never enable FULL or PRIMARY arbitrarily to reduce distinction |

If a workflow only needs **on-the-fly comparison**, collator may suffice without transforming original data. If multiple system components must store **a single consistent canonical Unicode form**, normalizing at the ingestion boundary can help. However, never normalize all existing data blindly without assessing collision risks, backward compatibility, and API contracts.

### NFC vs. NFD and NFKC/NFKD

- `NFC` preserves canonical equivalence and **composes** characters where possible; usually convenient for text representation.
- `NFD` performs **canonical decomposition**, e.g., `é` into `e + acute`.
- `NFKC`/`NFKD` additionally apply **compatibility** and can collapse character styles that differ only in formatting.

`Collator.CANONICAL_DECOMPOSITION` is described as corresponding to **NFD**, and `FULL_DECOMPOSITION` to **NFKD**, not NFC/NFKC; all must still be understood in the context of **collation**. You can normalize strings to NFC for storage and still use Collator with canonical decomposition to ensure accurate comparisons when receiving unnormalized input.

## 13. Common Mistakes and Fixes

| Mistake | Why it is dangerous | Fix |
| --- | --- | --- |
| Treating `NO_DECOMPOSITION` as always the right default | Accented text / combining marks may compare unexpectedly | Test canonical equivalence; consider CANONICAL |
| Thinking `CANONICAL_DECOMPOSITION` means accent stripping | Decomposition differs from ignoring accent differences | Pick the right `strength` and test Vietnamese |
| Thinking `FULL_DECOMPOSITION` is always better | Compatibility folding can collapse important distinctions | Use only when comparing compatibility variants is required |
| Inferring `String.equals==true` from `compare==0` | Collation equivalence can be broader than byte/code-unit equality | Use `equals` for data requiring exactness |
| Using `String.equals` to sort linguistically | Compares code units without language rules | Use an appropriate Collator/Comparator |
| Enabling PRIMARY for search and reusing it as a unique key | Multiple words differing in accents/case may collide | Keep IDs and unique constraints separate |
| Confusing strength with decomposition | Two orthogonal axes | Specify both explicitly in configuration |
| Believing NO guarantees distinguishing every precomposed/combining pair | RuleBasedCollator can auto-generate mappings | Read implementation contract and test |
| Assuming getInstance returns the same collator on all JDKs | Locale provider/data change | Pin runtime if reproducibility is required |
| Sharing a mutable collator and mutating per request | Configuration can leak across threads | Create/copy instance per task or synchronize |
| Storing CollationKeys and comparing across versions | No stable serialization contract for keys | Use keys only within compatible config/runtime scope |
| Applying NFKD/NFKC to all strings unconditionally | Can collapse full-width, ligatures, styling characters | Design normalization policy per data domain |
| Using one rule set for secrets and person names | Security constraints differ from UI collation | Separate identity policy from display |
| Skipping tests with Vietnamese accents | Easy to miss accent order and canonical form bugs | Maintain realistic dataset in both NFC/NFD forms |

## 14. Recommended Test Matrix

For a multilingual sorting or search feature, test at minimum:

1. **Canonical equivalents:** `"\u00E9"` vs. `"e\u0301"`, plus composed/decomposed Vietnamese letters. With canonical decomposition, canonically equivalent representations should compare appropriately.
2. **Compatibility equivalents:** `"Ａ"` vs. `"A"` and `"ﬀ"` vs. `"ff"`; decide whether treating them as equal is allowed.
3. **Accent differences:** `"e"` vs. `"é"` and Vietnamese examples like `"ma"`/`"má"`; verify across different strengths.
4. **Case differences:** `"e"` vs. `"E"`, plus letters with special Unicode casing contexts.
5. **Combining order:** combining mark sequences with differing canonical orders; verify decomposition mode.
6. **Locale:** `Locale.US`, `vi-VN`, and locales the product genuinely supports.
7. **Null/empty/bad input:** handle `null` explicitly before calling `compare`; test empty strings and malformed Unicode if sources can contain them.
8. **Multithreading:** ensure no thread mutates strength/decomposition of a collator used by another thread.
9. **JDK/provider version:** snapshot or invariant tests in a pinned environment; do not draw universal conclusions from one runtime.
10. **Data integrity:** equal collation comparisons must not merge records/identifiers when business rules require distinction.

For these tests, record **locale, strength, decomposition, JDK/provider**, and Unicode input data; a lone `compare==0` expression is insufficient to explain the cause of behavior.

## 15. Review Questions

**Question 1.** Is `Collator.CANONICAL_DECOMPOSITION` equivalent to "stripping Vietnamese accents"?

**Answer:** No. It handles **canonically equivalent** representations, whereas whether accents are distinguished during comparison is determined by **strength** and locale rules.

**Question 2.** When can `FULL_DECOMPOSITION` yield a different result from `CANONICAL_DECOMPOSITION`?

**Answer:** For characters that have **compatibility decompositions**, such as `Ａ` vs. `A` or the ligature `ﬀ` vs. `ff`. Canonical decomposition does not necessarily collapse those forms.

**Question 3.** Do `Normalizer.Form.NFC` and `Collator.CANONICAL_DECOMPOSITION` have the same effect?

**Answer:** No. NFC produces a `String` normalized via canonical composition; `Collator.CANONICAL_DECOMPOSITION` configures comparison to use canonical decomposition (related to NFD). Collator does not return a normalized string.

**Question 4.** Why do `"é"` and `"e\u0301"` sometimes still compare equal under `NO_DECOMPOSITION`?

**Answer:** `RuleBasedCollator` can prebuild precomposed and combining-form mappings in its rule table, and low strength can ignore differences. Do not use that observation to conclude NO always handles all canonical equivalence properly.

**Question 5.** When `Collator.PRIMARY` gives `compare(a,b)==0`, may one of the two records be deleted?

**Answer:** Not by default. That is merely equivalence **by collation strength**, not necessarily the same identifier. Uniqueness rules must be defined by the business domain.

**Question 6.** If data is already normalized to NFC when saved, do we still need to consider Collator decomposition?

**Answer:** Yes. Other input sources may not be normalized, and locales/providers have specific collation requirements. If the entire data pipeline enforces a normalization contract, performance optimization can be evaluated, but must be tested.

**Question 7.** Should `FULL_DECOMPOSITION + PRIMARY` be used for passwords to make typing easier?

**Answer:** Never arbitrarily. Those are settings for linguistic collation and can collapse many distinct strings. Passwords must follow system-defined input handling and security comparison rules.

## 16. Conclusion

- `Collator` compares text **by locale**; `Normalizer` produces **normalized Unicode string forms**.
- Three modes: **NO_DECOMPOSITION** (no decomposition), **CANONICAL_DECOMPOSITION** (equivalent to `NFD`), **FULL_DECOMPOSITION** (equivalent to `NFKD`).
- **Strength** and **decomposition** are two separate controls. Decomposition does not mean stripping accents or ignoring case.
- `compare(...)==0` does not prove `String.equals(...)`; collation equivalence does not replace exact identity.
- Choose decomposition according to data sources and processing goals, test text with accents/combining marks/compatibility characters, and keep collator configuration immutable during sorting.

**Official documentation:**

- [Java SE 21 — Collator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/Collator.html)
- [Java SE 21 — RuleBasedCollator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/RuleBasedCollator.html)
- [Java SE 21 — Normalizer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/Normalizer.html)
- [Unicode UAX #15 — Unicode Normalization Forms](https://www.unicode.org/reports/tr15/)