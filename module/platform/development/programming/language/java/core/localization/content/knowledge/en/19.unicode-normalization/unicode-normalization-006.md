# Why Stripping Accents Is Not a Neutral Normalization Step

## 1. Problem: “Unicode Normalization” and “Accent Stripping” Are Not Synonymous

Two strings can be encoded with different Unicode code points yet still represent **the same text** under Unicode equivalence rules. Conversely, two words with different accents can represent **completely different meanings**. Therefore, in multilingual Java applications, two operations must be separated:

1. **Unicode normalization**: converts a string into one of the standard *normalization forms* such as NFC or NFD to handle representations that are equivalent under Unicode rules.
2. **Diacritic removal / accent stripping**: intentionally **deletes marks** (typically combining characters in Unicode category Mark), producing a **lossy representation** that is sometimes useful for fuzzy search, yet is not a meaning-preserving replacement.

Vietnamese example:

| Original string | Potentially distinct meaning | After NFD + removing Mark |
| --- | --- | --- |
| `ma` | Word “ma” | `ma` |
| `má` | Word “má” | `ma` |
| `mà` | Word “mà” | `ma` |
| `mả` | Word “mả” | `ma` |
| `mã` | Word “mã” | `ma` |
| `mạ` | Word “mạ” | `ma` |

After stripping accents, multiple **distinct** entries collapse into **the same string**. No general algorithm can reliably reverse `ma` back into the original word.

**Core conclusion:** stripping accents is a **lossy and goal-dependent** transformation. It is not a neutral “cleanup” step that can be applied to personal names, place names, Vietnamese sentences, identifiers, or general text without altering meaning.

## 2. Canonical Equivalence: Same Visible Character, Multiple Encodings

Unicode allows certain accented characters to be represented in two ways:

- **Precomposed**: a single precomposed character, e.g., `é` (U+00E9).
- **Decomposed**: a base character `e` (U+0065) plus a combining acute accent `◌́` (U+0301).

The two strings below can look identical:

~~~text
"café"       -> c a f U+00E9
"cafe\u0301" -> c a f U+0065 U+0301
~~~

On the second line, `\u0301` is the Java escape notation for **COMBINING ACUTE ACCENT**. These are not two words with different meanings; they are **canonically equivalent** representations.

However, `String.equals(...)` compares strings by UTF-16 code units without normalizing Unicode beforehand. As a result, two canonically equivalent strings can be **unequal under `equals`** if encoded differently.

### Standalone Runnable Java 17+ Example

Save `CanonicalNormalizationDemo.java`:

~~~java
import java.text.Normalizer;

public class CanonicalNormalizationDemo {
    public static void main(String[] args) {
        String composed = "caf\u00E9";
        String decomposed = "cafe\u0301";

        System.out.println("Raw equals: "
                + composed.equals(decomposed));
        System.out.println("Raw lengths: "
                + composed.length() + " and " + decomposed.length());

        String leftNfc = Normalizer.normalize(
                composed, Normalizer.Form.NFC);
        String rightNfc = Normalizer.normalize(
                decomposed, Normalizer.Form.NFC);

        System.out.println("NFC equals: "
                + leftNfc.equals(rightNfc));
        System.out.println("NFC lengths: "
                + leftNfc.length() + " and " + rightNfc.length());
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 CanonicalNormalizationDemo.java
java CanonicalNormalizationDemo
~~~

Output:

~~~text
Raw equals: false
Raw lengths: 4 and 5
NFC equals: true
NFC lengths: 4 and 4
~~~

Key points to remember:

- The precomposed string `caf\u00E9` has length 4 in UTF-16 units; the decomposed form `cafe\u0301` has length 5.
- `Normalizer.Form.NFC` converts both to the canonical composed form, so they are equal under `equals` after normalization.
- **The acute accent is still preserved in `café`.** NFC does not turn `café` into `cafe`.

This clearly demonstrates why **“normalization” does not mean “removing accents.”**

## 3. The Four Unicode Normalization Forms and Their Roles

Java's standard API is `java.text.Normalizer`, with `Normalizer.Form`:

| Form | Name | Main Effect | Intentionally strips accents? |
| --- | --- | --- | --- |
| `NFD` | Canonical Decomposition | Decomposes characters by canonical equivalence | **No** |
| `NFC` | Canonical Decomposition + Composition | Decomposes and canonically composes to produce a normalized form | **No** |
| `NFKD` | Compatibility Decomposition | Also decomposes compatibility characters | **No**, though it can alter meaningful representations |
| `NFKC` | Compatibility Decomposition + Composition | Performs compatibility decomposition then canonical composition | **No**, though it can collapse compatibility differences |

Example:

~~~java
String nfc = Normalizer.normalize(input, Normalizer.Form.NFC);
String nfd = Normalizer.normalize(input, Normalizer.Form.NFD);
String nfkc = Normalizer.normalize(input, Normalizer.Form.NFKC);
String nfkd = Normalizer.normalize(input, Normalizer.Form.NFKD);
~~~

This is a **code snippet inside a method**, requiring `import java.text.Normalizer` and an existing `String input` variable.

### NFC: Generally Suitable for Unifying Ordinary Text Storage

NFC prevents the same accented letter from being stored under two canonically equivalent encodings. It **does not** remove accents and is usually a reasonable choice for Vietnamese text whose content must be preserved.

However, there is no rule that “every kind of data must use NFC” in every system. Identifiers, protocols, digital signatures, filenames, security matching, and domain-specific standards may have their own Unicode profiles or byte policies. Follow the contract of that data.

### NFD: Decomposing to Process Characters and Combining Marks

An accented character can become a base character plus one or more combining marks. For example, an accented Vietnamese vowel can split into a base letter and marks indicating vowel shape and tone.

**NFD still retains the accents.** Only if you subsequently delete `Mark` characters is information removed.

### NFKC and NFKD: Compatibility Equivalence Is Not Presentational-Meaning Neutral

Compatibility normalization can convert characters such as:

- Circled digit `①` into `1`.
- Ligature `ﬁ` into two characters `fi`.
- Fullwidth Latin `Ａ` into `A`.

These compatibility transformations are useful in some lookup systems and identifier normalizations under dedicated specifications, yet **must not** be assumed to preserve all presentational or semantic distinctions users care about.

### Standalone NFKC Example

Save `CompatibilityNormalizationDemo.java`:

~~~java
import java.text.Normalizer;

public class CompatibilityNormalizationDemo {
    public static void main(String[] args) {
        String source = "\u2460 \uFB01 \uFF21";

        System.out.println("Original: " + source);
        System.out.println("NFC: "
                + Normalizer.normalize(source, Normalizer.Form.NFC));
        System.out.println("NFKC: "
                + Normalizer.normalize(source, Normalizer.Form.NFKC));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 CompatibilityNormalizationDemo.java
java CompatibilityNormalizationDemo
~~~

Output:

~~~text
Original: ① ﬁ Ａ
NFC: ① ﬁ Ａ
NFKC: 1 fi A
~~~

**Distinction:** NFKC is a **standard Unicode normalization**, whereas accent stripping is an optional custom rule chosen by an application. However, NFKC being standard does not mean it is always right for all data; compatibility equivalence itself can discard stylistic distinctions.

## 4. What Does the Common Java “Accent-Stripping” Recipe Actually Do?

A widely shared recipe:

~~~java
String stripped = Normalizer
        .normalize(input, Normalizer.Form.NFD)
        .replaceAll("\\p{M}+", "");
~~~

This is a **code snippet inside a method**, requiring `import java.text.Normalizer` and a `String input` variable.

It performs **two distinct steps**:

1. `Normalizer.Form.NFD` decomposes characters that have canonical decompositions.
2. The regex `\p{M}` matches Unicode category **Mark** and deletes all characters belonging to this category.

Unicode general category **M** includes several subcategories:

- `Mn`: *Nonspacing Mark*.
- `Mc`: *Spacing Combining Mark*.
- `Me`: *Enclosing Mark*.

In a French example, `é` decomposes into `e + ◌́`. Deleting `◌́` turns `é` into `e`. Yet that accent can determine pronunciation and meaning; deleting it is **intentionally lossy**.

**Common pitfall:** the pattern `\p{M}` does not mean “only remove Vietnamese acute, grave, hook, tilde, and dot-below marks.” It deletes **combining marks across many scripts**, including marks that cannot be regarded as decorative.

## 5. Vietnamese: Removing Accents Changes the Word, Not Just Its Appearance

Vietnamese has **tones** and **vowel-shaping marks**, both of which distinguish words. For example, `a`, `ă`, and `â` are not free spelling variants of a single vowel; `má`, `mã`, `mạ` can be completely different words.

### Standalone Runnable Java 17+ Example

Create `VietnameseDiacriticLossDemo.java`:

~~~java
import java.text.Normalizer;

public class VietnameseDiacriticLossDemo {
    static String removeMarks(String source) {
        return Normalizer
                .normalize(source, Normalizer.Form.NFD)
                .replaceAll("\\p{M}+", "");
    }

    public static void main(String[] args) {
        String[] words = {
                "ma", "má", "mà", "mả", "mã", "mạ"
        };

        for (String word : words) {
            System.out.println(word + " -> " + removeMarks(word));
        }

        System.out.println("Đặng -> " + removeMarks("Đặng"));
    }
}
~~~

Compile/run (save Java source as UTF-8):

~~~bash
javac -encoding UTF-8 VietnameseDiacriticLossDemo.java
java VietnameseDiacriticLossDemo
~~~

Output:

~~~text
ma -> ma
má -> ma
mà -> ma
mả -> ma
mã -> ma
mạ -> ma
Đặng -> Đang
~~~

### Analysis

- All six words in the example turn into `ma` after deleting combining marks.
- Removing the vowel mark and tone mark in `Đặng` leaves the letter `Đ` intact, yielding `Đang`.
- This is **not** an accurate orthographic conversion from Vietnamese to ASCII. `Đ` and `đ` do not become `D`/`d` via NFD + deleting `\p{M}` alone.

This has two consequences:

1. **Loss of meaning**: the output no longer contains enough information to recover the original word.
2. **May not even meet the technical goal**: many expect “accent stripping” to produce ASCII, yet the string can still contain `Đ/đ` and other characters that do not decompose into base Latin letters.

If a product requires converting Vietnamese names to ASCII for URLs or a specific machine standard, it needs a **dedicated transliteration policy**, documented and tested. `NFD + \p{M}` cannot be treated as a universal transliteration standard.

## 6. Not Just Vietnamese: Multilingual Impacts Vary Greatly

### 6.1. Latin-Script Languages

- French: `café` → `cafe`; `côte`, `côté`, and `cote` can collapse together even though they are distinct words.
- Spanish: `ñ` is not merely a decorative version of `n` in orthography; stripping the mark erases a letter distinction.
- Polish: characters such as `ł` do not necessarily decompose into `l + Mark` under NFD, so a Mark-stripping algorithm does not yield the ASCII Latin form a developer expects.
- German: `ß` does not turn into `ss` through NFD and Mark removal; that is a separate orthographic conversion/transliteration task.
- Turkish: `I`, `İ`, `ı`, and `i` involve locale-sensitive casing rules. Stripping marks and calling `toLowerCase` out of context can merge unintended forms.

### 6.2. Scripts Where Combining Marks Are Core Components

In many scripts, Marks represent **vowels, tones, or essential orthographic components**, not optional diacritics. Removing `\p{M}` on Indic, Thai, or other scripts can severely corrupt pronunciation and word structure.

In Arabic script, short vowel marks (*harakat*) are omitted in some writing contexts, yet removing them can also discard information needed to determine pronunciation and meaning. Whether to permit that is a **language- and goal-specific policy**, not a blanket technical rule applied worldwide.

### 6.3. Special Characters, Symbols, and Emoji

Category Mark does not contain only the “grammatical” diacritics developers usually think of. Some display variation selectors (such as `U+FE0F`) belong to Mark. Removing all Marks can alter **the visual presentation of symbols/emoji**.

Conversely, many components that build complex emoji—such as zero-width joiners or modifiers—are not in category Mark, so Mark stripping is **not** a complete “emoji normalizer” either.

**Conclusion:** never build a global rule that strips all `\p{M}` across international content just because a few Latin examples look reasonable.

## 7. Accent Stripping Is Not Transliteration, Case Folding, or Collation

Three concepts are very easy to confuse:

| Task | Goal | Always preserves meaning/identity? |
| --- | --- | --- |
| Unicode normalization (NFC) | Unify canonically equivalent representations consistently | Preserves meaningful diacritic distinctions like `má`/`mã` |
| Diacritic stripping | Intentionally delete a set of marks | **No**, lossy |
| Transliteration | Convert text into another writing system by rules | May be lossy, depending on script and rules |
| Case conversion/case folding | Handle uppercase/lowercase differences by rules | Can collapse distinctions; must check locale/standard |
| Collation | Compare/sort strings linguistically with configurable sensitivity | Does not transform the original string into a new text |

### Why Are `Đ` and `ß` Good Examples?

`Đ` and `đ` do not turn into `D`/`d` simply by calling NFD. Likewise, `ß` generally does not turn into `ss` via NFD + Mark removal. If you need an accent-free form for search or slugs, you must define a **specific transliteration mapping**, potentially using a library or mappings for target languages.

Do not build a global transliteration using a couple of `replace` calls for Vietnamese and apply it to all languages. Decisions around `Đ`, `ł`, `ø`, `æ`, or non-Latin scripts require distinct policies and dedicated tests.

### Case Mapping Also Has Locale Traps

A step like:

~~~java
String key = source.toLowerCase(Locale.ROOT);
~~~

is a **code snippet inside a method**, requiring `import java.util.Locale` and variable `source`. It provides a user-locale-independent lowercasing, yet **is not synonymous with Unicode full case folding for all standards**, nor does it guarantee all Turkish, Greek, or other script rules in natural-language matching.

When matching words in a specific language, specify the locale and comparison criteria rather than treating `lowercase + removeMarks` as universally right.

## 8. Accent-Free Search: A Reasonable Requirement That Needs a Contract

There are many scenarios where users type `"cafe"` hoping to find `"café"`, or type `"dang"` hoping to find `"Đặng"`. This is a **diacritic-tolerant search feature**, not a reason to discard accents from original data.

A generally appropriate design:

~~~text
Stored source (content preserved verbatim):
    "Má", "Mã", "Ma", "Đặng", "café"
            |
            +--> NFC to unify canonical representation
            |
            +--> Separate search index:
                  case/diacritic folding, transliteration,
                  or collation per product rules
            |
            +--> When returning results:
                  always display the original accented string
~~~

**Diacritic-tolerant search must accept multiple matching results.** A user typing `ma` may match `ma`, `má`, `mà`, `mả`, `mã`, `mạ`. The system can rank exact matches higher, yet cannot recover distinctions from an accent-stripped key alone.

### Java Example: Keep Source and Build a Separate Search Key

Save `SearchKeyDemo.java`:

~~~java
import java.text.Normalizer;
import java.util.Locale;

public class SearchKeyDemo {
    static String nfc(String source) {
        return Normalizer.normalize(
                source, Normalizer.Form.NFC);
    }

    static String approximateKey(String source) {
        String decomposed = Normalizer.normalize(
                source, Normalizer.Form.NFD);
        return decomposed
                .replaceAll("\\p{M}+", "")
                .toLowerCase(Locale.ROOT);
    }

    public static void main(String[] args) {
        String original = nfc("Má");
        String key = approximateKey(original);

        System.out.println("Original: " + original);
        System.out.println("Search key: " + key);
        System.out.println("Original preserved: "
                + original.equals("Má"));

        System.out.println("Ma key: "
                + approximateKey("Ma"));
        System.out.println("Mã key: "
                + approximateKey("Mã"));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 SearchKeyDemo.java
java SearchKeyDemo
~~~

Output:

~~~text
Original: Má
Search key: ma
Original preserved: true
Ma key: ma
Mã key: ma
~~~

This is an **example for learning the mechanism**, not a production-ready multilingual search processor. It intentionally creates collisions; it does not handle `Đ → D`, Turkish, or non-Latin scripts automatically. A real system must define language scope, transliteration rules, index optimization, and ranking.

### Useful Ranking Policy

When searching personal names or place names:

1. Prioritize **exact original string** matches.
2. Next prioritize **NFC/case-insensitive** matches per policy.
3. Only then consider **accent-insensitive** or transliterated matches if enabled/supported.
4. Display accented names and distinguishing attributes so users pick the right result.

Never collapse every approximate search match into a single unique identifier.

## 9. Collator: Locale-Based Comparison Instead of Manually Deleting Accents

`java.text.Collator` supports comparing and sorting text by locale rules. `Collator` has `strength` levels controlling which differences are examined.

Examples:

- **PRIMARY**: primary difference level; in many locales, can ignore accent and uppercase/lowercase differences.
- **SECONDARY**: considers additional differences such as accents in appropriate languages.
- **TERTIARY**: also considers differences like case and other locale-dependent variants.

**Important point:** this is a **comparison** rule, not an operation that deletes characters from stored strings.

### Complete Example

Create `CollationDemo.java`:

~~~java
import java.text.Collator;
import java.util.Locale;

public class CollationDemo {
    public static void main(String[] args) {
        Collator collator = Collator.getInstance(Locale.FRENCH);

        collator.setStrength(Collator.PRIMARY);
        System.out.println("Primary equal: "
                + (collator.compare("cafe", "café") == 0));

        collator.setStrength(Collator.TERTIARY);
        System.out.println("Tertiary equal: "
                + (collator.compare("cafe", "café") == 0));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 CollationDemo.java
java CollationDemo
~~~

Output with typical French matching rules in the JDK:

~~~text
Primary equal: true
Tertiary equal: false
~~~

### Limitations to Know

- `Collator.PRIMARY` **does not** mean “only strip accents while keeping all other distinctions”; it can also ignore case and other secondary differences depending on locale.
- Collation rules depend on locale, provider, and data versions. Never assume the same `PRIMARY` level treats the same letter pairs identically across all languages.
- `Collator` is a mutable configurable object (e.g., `setStrength`). If used across threads, ensure thread safety or create separate instances; never share a mutable instance whose configuration changes per request.
- Never use accent-insensitive collation to decide that two accounts, legal documents, or identifiers **are definitely the same entity**.

When the goal is merely linguistic search/sorting, collation is usually preferable to destroying accents in original data.

## 10. Accent Stripping in Safety-Critical Systems

### 10.1. Usernames, Identifiers, Keys, and Digital Signatures

If two distinct usernames `Má` and `Mã` both collapse to `ma`, using that string as a **unique key** causes collisions. Worse, one system checking access permissions on the folded name while another checks the original name creates **identity inconsistency**.

For business keys, accounts, authorization paths, signatures, or passwords:

- Choose a specific **Unicode/identifier profile** or matching contract.
- Normalize at the right boundary per that profile.
- Never apply `NFD + removeMarks` as a “neutral” validation step.
- Keep internal identifiers independent of display-name strings whenever possible.
- Define policies for confusable characters, Unicode normalization, and character-set restrictions where truly needed.

**Specifically:** Unicode normalization **is not** the same as detecting visually identical characters with different code points (*homoglyphs/confusables*). Latin `a` and a visually similar letter in another script can still pose confusion risks, while NFC does not resolve all of those cases automatically.

### 10.2. Proper Names, Legal Records, and Translations

Personal names, place names, addresses, legal documents, educational content, and localized messages must preserve accents. Stripping accents can:

- Corrupt registered spellings of names.
- Change Vietnamese pronunciation and meaning.
- Lose data when the system re-exports records.
- Make matching against official documents or sources inaccurate.

If an accent-free version must be generated for an external ASCII-only system, **keep the original as well** and document the conversion version, algorithm, target language, and limitations.

### 10.3. URL Slugs and Paths

Accent-free slugs are sometimes a valid product decision. However, two differently accented titles can produce **the same slug**. Therefore, slug generators must resolve collisions with an independent ID or suffix rather than assuming accent removal is one-to-one.

Conceptual example:

~~~text
Display name:  "Má"    -> search key "ma"
Display name:  "Mã"    -> search key "ma"

Distinct slugs:
  /articles/ma-101
  /articles/ma-102
~~~

Never use an accent-stripped slug as **proof that two titles are identical**.

## 11. Inspecting and Processing Unicode at the Right Character Level

Java `String` uses UTF-16. `length()` counts **code units**, not the number of grapheme clusters a user perceives as characters. A letter with combining marks can consist of multiple code points; emoji can consist of multiple code points joined by joiners.

### Inspecting Code Points Instead of Only Printing Strings

Standalone example `CodePointDemo.java`:

~~~java
import java.text.Normalizer;
import java.util.Locale;
import java.util.stream.Collectors;

public class CodePointDemo {
    static String hex(String input) {
        return input.codePoints()
                .mapToObj(cp -> String.format(
                        Locale.ROOT, "U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    public static void main(String[] args) {
        String composed = "caf\u00E9";
        String decomposed = Normalizer.normalize(
                composed, Normalizer.Form.NFD);

        System.out.println("Composed: " + hex(composed));
        System.out.println("Decomposed: " + hex(decomposed));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 CodePointDemo.java
java CodePointDemo
~~~

Output:

~~~text
Composed: U+0063 U+0061 U+0066 U+00E9
Decomposed: U+0063 U+0061 U+0066 U+0065 U+0301
~~~

Seeing `U+0301` tells us the acute accent exists as a **combining mark**. NFC can change *how it is encoded* while preserving meaning; deleting `U+0301` is **altering the content**.

When processing by user-perceived *grapheme clusters*, you cannot just call `substring` by code unit and treat each slice as a complete letter. Use a Unicode/language-appropriate text segmentation algorithm; Java offers `BreakIterator` for segmentation tasks, though exact behavior and grapheme support should be tested on your target dataset.

## 12. Recommended Workflow: Keep Original and Limit Secondary Transformations

A clean way to structure data in a Java application:

~~~text
User submits: "Má"
        |
        v
Validate input (length, characters, data rules)
        |
        v
Normalize to NFC if appropriate for schema
        |
        +----> STORE ACCENTED ORIGINAL: "Má"
        |
        +----> SECONDARY SEARCH INDEX:
               case/accent folding per policy
               (may produce "ma")
        |
        +----> Approximate queries and ranking
        |
        v
Display original: "Má"
~~~

### 12.1. Java Model Example

~~~java
import java.text.Normalizer;
import java.util.Locale;
import java.util.Objects;

public record SearchableName(String displayName, String searchKey) {
    public static SearchableName from(String raw) {
        Objects.requireNonNull(raw, "raw");

        String original = Normalizer.normalize(
                raw, Normalizer.Form.NFC);
        String folded = Normalizer
                .normalize(original, Normalizer.Form.NFD)
                .replaceAll("\\p{M}+", "")
                .toLowerCase(Locale.ROOT);

        return new SearchableName(original, folded);
    }
}
~~~

Save as `SearchableName.java`. This is only an illustrative model using a simple folding policy. It **does not** claim this fold is right for every locale or turns every character into ASCII.

In a real application, consider:

- Which languages are supported in the search key.
- Whether additional mappings are needed for `Đ/đ`, `ł`, `ø`, or other scripts.
- Whether multiple records sharing the same search key are acceptable.
- Whether to store the search-key algorithm version to reindex when the policy changes.
- Whether ranking by exact match and by language is needed.
- Whether `Collator` or database/search-engine collation/indexing can be used instead of manual processing.

### 12.2. Testing the Two Separate Layers

**Content preservation layer:**

- NFC of two canonically equivalent strings must match.
- `Má` and `Mã` remain distinct strings after NFC.
- Returned display data must keep exact accents.
- Serialization/deserialization must not alter Unicode content outside the documented policy.

**Approximate search layer:**

- Users typing `ma` can find `ma`, `má`, and `mã` per policy.
- Exact matches should be prioritized where possible.
- Key collisions must not drop records or break ID uniqueness.
- The algorithm is tested on the actual languages and scripts in use.
- Unsupported characters must be handled by explicit rules, never silently dropped.

## 13. Common Mistakes

| Misconception | Consequence | Correct understanding/approach |
| --- | --- | --- |
| “NFC means stripping accents” | Content loss if stripping is added blindly | NFC preserves meaningful accent distinctions |
| “NFD has no accents” | Misunderstanding code point structure | NFD **keeps** accents as combining marks |
| “`replaceAll("\\p{M}+", "")` is Unicode normalization” | Deletes essential marks in many scripts | It is a lossy Mark-removal operation, not a normal form |
| “Stripping accents doesn't change Vietnamese meaning” | `má`/`mã`/`mạ` collide | Keep original; fold only for functions that need it |
| “NFD + Mark creates ASCII” | `Đ`, `ł`, `ß`, etc. can remain | Transliteration requires its own policy |
| “NFKC is completely neutral” | Loses compatibility distinctions, e.g., `①`→`1` | Pick NFKC when appropriate for the data profile |
| “Lowercase works identically for all languages” | Wrong case mapping in some contexts | Use the right locale/algorithm for the need |
| “Collator PRIMARY only ignores accents” | Also merges case/other differences | Check strength and specific locale data |
| “Search keys can serve as unique IDs” | Collisions and mixed-up records | Keep independent IDs and original displayName |
| “String.length is the visible character count” | Splits graphemes/combining marks | Understand UTF-16, code points, grapheme clusters |
| “Stripping accents gives complete Unicode security” | Fails to handle confusables/standard identifiers | Use dedicated validation/security profiles |
| “You can strip accents on translations and restore them later” | No unique inverse exists | Preserve original content |

## 14. Practice Exercises and Self-Check Questions

1. Write two Java strings representing `é` with `\u00E9` and `e\u0301`. Why does `equals` return `false`, yet after `Normalizer.Form.NFC` they become equal?
2. Pass `"má"`, `"mã"`, and `"mạ"` through NFC then NFD. At which step does content remain distinct, and at which step are distinctions lost if you delete category Mark?
3. Run `VietnameseDiacriticLossDemo`. Why does `"Đặng"` become `"Đang"` instead of `"Dang"`?
4. Write an accent-stripping function using `\p{M}` and explain why it should not be applied indiscriminately to Arabic/Indic/Thai text.
5. Compare NFC and NFKC on `①`, `ﬁ`, `Ａ`. How could this difference affect product names or identifiers?
6. Use `Collator.getInstance(Locale.FRENCH)` with `PRIMARY` and `TERTIARY` to compare `"cafe"` and `"café"`. Why should collation results not be used to conclude two accounts share the same identity?
7. Design a feature where searching `"dang"` finds `"Đặng"`, while displaying `"Đặng"` intact. What steps are needed beyond `NFD + removeMarks`?
8. Two articles titled `"Má"` and `"Mã"` both generate search key `ma`. Design slugs that avoid collisions while still allowing accent-free search.
9. Distinguish the differences among **canonical normalization**, **compatibility normalization**, **diacritic removal**, **transliteration**, and **collation**.
10. A form collecting legal information must keep names exactly as shown on official documents. Should only the accent-stripped version be stored? Why or why not?

**Takeaway:** Unicode normalization (especially NFC/NFD) is designed to handle **equivalent representations under the Unicode Standard**; its goal is not to erase accent information. The recipe `NFD + replaceAll("\\p{M}+", "")` is a **lossy Mark-stripping operation**: it can collapse distinct Vietnamese words into the same string, break other writing systems, and still not guarantee ASCII. Always **keep accented text as original data**, generating secondary search/slug variants only when explicitly required, with proper language, collision, security, and testing policies.

### References

- [Java SE 17 — Normalizer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html) — NFC, NFD, NFKC, NFKD forms.
- [Java SE 17 — Collator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Collator.html) — locale-sensitive text comparison and strength.
- [Java SE 17 — Character](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html) — code points and Unicode general categories.
- [Java SE 17 — Pattern](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html) — Unicode categories and `\p{M}`.
- [Unicode Standard Annex #15 — Unicode Normalization Forms](https://www.unicode.org/reports/tr15/) — normal forms, canonical and compatibility equivalence.
- [Unicode Technical Standard #10 — Unicode Collation Algorithm](https://www.unicode.org/reports/tr10/) — collation and comparison levels.
