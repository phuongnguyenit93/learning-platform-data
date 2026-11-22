# What Is Unicode Normalization and How Does It Differ from Translation or Transliteration?

When building Java software that serves multiple languages, a piece of text that looks identical on screen can still contain **different Unicode code point sequences**. As a result, string comparison, searching, `Map` keys, input matching, and tests can behave unexpectedly. **Unicode normalization** solves part of this problem by converting equivalent representations of Unicode text into a standardized form.

However, **normalization is not translation**, and it is also **not phonetic transcription or transliteration**. It does not turn a Vietnamese sentence into English, does not turn every Cyrillic letter into Latin, does not automatically strip diacritics, and does not understand sentence meaning. Normalization acts on **how characters are represented**; translation and transliteration are different processes with different goals and limits.

This lesson explains how to recognize Unicode issues, distinguish the four normalization forms NFC/NFD/NFKC/NFKD, use `java.text.Normalizer` in Java 17+, understand Vietnamese cases, and avoid mistakes when applying normalization to search, personal names, identifiers, and security.

## 1. Unicode and Three Representation Levels to Distinguish

To understand why normalization is needed, separate three concepts:

1. **Abstract character / grapheme**: what a reader perceives as a single accented letter, for example `é`.
2. **Unicode code point**: a value such as `U+00E9` or a sequence consisting of `U+0065` (`e`) and `U+0301` (combining acute accent).
3. **Storage encoding unit**: Java `String` uses UTF-16 code units, each being a 16-bit `char`; UTF-8 is a way of encoding code points into bytes when writing/transmitting text.

For example, two strings can look the same:

~~~text
A (precomposed): U+00E9             → é
B (decomposed):  U+0065 U+0301      → e + ◌́
~~~

Line B is the letter `e` plus a **combining** acute accent (combining mark). If the font and rendering engine support it, the two strings can produce a nearly identical visual appearance. However, they contain **different code points** and a different number of UTF-16 code units.

In Java:

~~~java
String a = "\u00E9";       // U+00E9: é
String b = "e\u0301";      // U+0065 U+0301: e + acute accent

System.out.println(a.equals(b)); // false
System.out.println(a.length());  // 1
System.out.println(b.length());  // 2
~~~

This is an **illustrative snippet** inside a Java method. `String.equals` compares exact sequences of UTF-16 code units and does not automatically perform Unicode normalization. The number of characters the user *sees* also does not necessarily match the result of `length()`.

In particular, emoji may use surrogate pairs, combining marks, or sequences joined by ZWJ; therefore, **code point count, UTF-16 code unit count, and grapheme cluster count** are three different quantities. Unicode normalization **is not** a grapheme-counting or word-segmentation algorithm.

## 2. What Does Unicode Normalization Do?

Normalization is defined by the Unicode Standard using **decomposition**, **canonical ordering** of combining marks, and, for some forms, **composition**.

Some characters have **canonical equivalence**, meaning they can be represented either by a precomposed character or by a sequence consisting of a base character + combining marks. Normalization converts equivalent strings into the same standard representation.

~~~text
Input 1: é        (U+00E9)
Input 2: e + ◌́   (U+0065 U+0301)
         |
         | NFC
         v
Both:    é        (U+00E9)
~~~

Key point: **only certain transformations are considered canonically equivalent or compatibility equivalent by the Unicode Standard**. Normalization does not turn all look-alike letters into one character, does not guarantee that synonymous spellings are equal, and does not translate content.

A normalization function for a fixed form is typically **idempotent**:

~~~text
normalize(normalize(s, NFC), NFC) = normalize(s, NFC)
~~~

If the input is already normalized in NFC, applying NFC again does not change the string. However, if you convert to a different form—for example from NFC to NFD—the representation can change.

### Normalization Does Not Fix Linguistic Meaning

Normalization cannot tell whether “bank” refers to a financial institution or a riverbank; it cannot know which words need translation. Stripping Vietnamese diacritics to create a search key can merge many words with different meanings into one; that is a **lossy** transformation, not the definition of NFC.

## 3. The Four Normalization Forms: NFC, NFD, NFKC, NFKD

Java's `java.text.Normalizer.Form` has four values:

| Form | Name | Mechanism | Characteristics |
| --- | --- | --- | --- |
| `NFD` | Canonical Decomposition | Canonical decomposition and canonical ordering of combining marks | Typically splits accented characters into base + combining marks |
| `NFC` | Canonical Decomposition followed by Composition | Canonical decomposition followed by composition when valid | Commonly chosen for storing/comparing natural text |
| `NFKD` | Compatibility Decomposition | Compatibility decomposition, including compatibility presentation differences | Can remove stylistic/formatting distinctions |
| `NFKC` | Compatibility Decomposition followed by Composition | Compatibility decomposition followed by canonical composition | Useful in certain identifier/search policies, **not safe by default for all text** |

The letter `K` in `NFKC` and `NFKD` stands for **compatibility**. These two forms can eliminate distinctions between certain specially formatted characters and their compatibility-equivalent sequences. **They are not a “stronger and always better NFC”.**

### Example 1: the letter é

~~~text
Input: "é" (U+00E9)
NFD:   "e" + U+0301
NFC:   "é" (U+00E9)
~~~

Both forms can render similarly. For canonically equivalent string pairs, NFC produces equal results; NFD does the same, favoring the decomposed form.

### Example 2: the ligature ﬃ

The ligature character `ﬃ` (U+FB03) represents the joined typographic form of the three Latin letters `f`, `f`, `i`:

~~~text
Input:      ﬃ (U+FB03)
NFC:        ﬃ
NFKC:       ffi
~~~

`NFC` does not replace this ligature because it belongs to **compatibility** equivalence, not canonical equivalence. `NFKC` expands it into three characters. The result uses fewer special characters, but loses the distinction between the ligature glyph and the three separate letters.

### Example 3: fullwidth Latin letters

~~~text
Input:  Ａ (U+FF21, FULLWIDTH LATIN CAPITAL LETTER A)
NFKC:   A (U+0041)
~~~

This is a classic example of compatibility normalization. It is useful if an identifier policy treats the two forms as equivalent, but it can also discard typographic/presentation information that the user expected to keep.

### Why Shouldn't You Blindly Use NFKC on Personal Names, Articles, or Raw Data?

Original text can contain stylistic distinctions or symbols used intentionally. If you automatically apply NFKC to every string before storing it, some data cannot be restored to its original form. Decide based on the **data field type** and product requirements.

For user-written content, you can **store the original** alongside a normalized copy used for searching or comparison. If exact signed/digitally signed bytes must be preserved, even NFC can alter the source bytes; never normalize after signing or hash verification unless specified by the protocol.

## 4. NFC and NFD Are Not UTF-8/UTF-16 Transcoding

Three operations are often confused:

- **Encoding**: how Unicode code points are represented as bytes, such as UTF-8 or UTF-16. Choosing the wrong charset when reading bytes can produce corrupted text (*mojibake*).
- **Normalization**: once you have a valid Unicode `String`, converting canonically or compatibility equivalent sequences into one form.
- **Font shaping/rendering**: determines how glyphs appear on screen, including fonts, combining marks, and various display features.

A string already in NFC can still render incorrectly if the font does not support the character. A file decoded with the wrong charset will not be “repaired” by NFC. And a valid UTF-8 string is not necessarily in NFC.

An easy-to-follow pipeline:

~~~text
Byte input --[decode with right charset]--> Java String
                |
                v
         [validate input]
                |
                v
        [normalize per policy]
                |
                v
       [compare / store / index]
                |
                v
        [render with font/UI]
~~~

These steps can occur at different boundaries depending on the system. Do not use Unicode normalization to compensate for byte-decoding errors.

## 5. How Does Normalization Differ from Translation, Phonetic Transcription, and Transliteration?

| Task | Goal | Example | Handled automatically by `Normalizer`? |
| --- | --- | --- | --- |
| Unicode normalization | Convert equivalent representations into a deterministic form | `e + U+0301` → `é` under NFC | **Yes** |
| Translation | Convert a message to another language while preserving appropriate meaning | “Xin chào” → “Hello” | **No** |
| Transliteration | Rewrite letters/sounds from one script to another by rules | Cyrillic → Latin under a transliteration convention | **No** |
| Phonetic transcription | Represent sounds/pronunciation using a symbol system | A word → IPA phonetic notation | **No** |
| Accent stripping / search simplification | Reduce variants for flexible search | `á` → `a` by custom rules | **Not by default** |
| Case folding / case handling | Standardize uppercase/lowercase comparison | `A` / `a` per policy | **Not NFC/NFD** |
| Locale-sensitive collation | Sort/compare text according to language rules | Language-specific comparison rules for accented letters | **No** |

A clear example:

~~~text
"Xin chào" --translate to English-->   "Hello"
"Xin chào" --simple accent removal-->  "Xin chao"
"Xin chào" --NFC-->                    still the same Vietnamese sentence, in NFC form
~~~

Removing accents can help users type accent-free search queries, but it **loses lexical distinctions**. In Vietnamese, `ma`, `má`, `mà`, `mạ`, `mã`, `mả` are distinct words; collapsing them all to “ma” is neither orthographic normalization nor translation.

**Transliteration is also not necessarily one-to-one or lossless.** How personal names are converted across scripts depends on conventions, languages, and purposes (passports, libraries, maps). NFC cannot choose those conventions on its own.

### NFD + Deleting Combining Marks Is Not “Converting All Vietnamese to ASCII”

A common trick is decomposing with NFD and deleting characters in Unicode General Category `Mark`, but this is a **custom accent-stripping algorithm** and is lossy. It also does not automatically turn letters like `đ` into `d`, nor does it handle all scripts/pronunciation features in general. Do not call it “Unicode normalization” in the equivalence-preserving sense.

In real applications, only use accent stripping when search requirements are confirmed, and explicitly test its impact on precision/recall, personal names, product codes, and legal data.

## 6. How Does Java 17+ Use java.text.Normalizer?

Standard API:

~~~java
import java.text.Normalizer;

String normalized = Normalizer.normalize(
        input,
        Normalizer.Form.NFC);

boolean already = Normalizer.isNormalized(
        input,
        Normalizer.Form.NFC);
~~~

This is an **illustrative snippet** assuming `String input` is already defined. Two methods are used:

- `Normalizer.normalize(CharSequence src, Normalizer.Form form)` returns the string in the chosen form.
- `Normalizer.isNormalized(CharSequence src, Normalizer.Form form)` checks whether the string is already in that form.

Passing `null` is not a representation of “missing text”; validate the input and normalization form before calling. Normalization must not be treated as a “filter for all dangerous characters”; it only performs the algorithm stated in its contract.

### Building a Stable Search Key

If the product decides to search using NFC, normalize **both at indexing time and at query time**:

~~~java
String storedKey = Normalizer.normalize(
        displayName, Normalizer.Form.NFC);
String queryKey = Normalizer.normalize(
        query, Normalizer.Form.NFC);

boolean same = storedKey.equals(queryKey);
~~~

This is an illustrative snippet with existing `String displayName` and `String query`. Normalizing one side without normalizing the other yields inconsistent results.

This **does not** make `"Alice"` equal to `"alice"`, does not unify different Vietnamese tone marks, and does not replace a full-text search engine. If you need case-insensitive matching or language-specific ordering, you must add a separate policy, such as `Collator` or an appropriate indexing engine.

## 7. Runnable Java 17+ Example with Verified Stdout

This example uses Unicode escapes so the source code is easy to share across different consoles. It tests canonical equivalence, string length, ligatures, fullwidth letters, Vietnamese text, and the fact that NFC does not turn lowercase letters into uppercase.

Create the file **`UnicodeNormalizationDemo.java`**:

~~~java
import java.text.Normalizer;

public class UnicodeNormalizationDemo {
    public static void main(String[] args) {
        String composed = "\u00E9";
        String decomposed = "e\u0301";

        String nfcA = Normalizer.normalize(
                composed, Normalizer.Form.NFC);
        String nfcB = Normalizer.normalize(
                decomposed, Normalizer.Form.NFC);

        System.out.println("Raw equals: "
                + composed.equals(decomposed));
        System.out.println("UTF-16 lengths: "
                + composed.length() + " / " + decomposed.length());
        System.out.println("NFC equals: " + nfcA.equals(nfcB));
        System.out.println("NFC idempotent: "
                + nfcA.equals(Normalizer.normalize(
                        nfcA, Normalizer.Form.NFC)));

        String nfd = Normalizer.normalize(
                composed, Normalizer.Form.NFD);
        System.out.println("NFD code points: "
                + nfd.codePointCount(0, nfd.length()));

        String ligature = "\uFB03";
        System.out.println("NFC keeps ligature: "
                + ligature.equals(Normalizer.normalize(
                        ligature, Normalizer.Form.NFC)));
        System.out.println("NFKC expands ligature: "
                + "ffi".equals(Normalizer.normalize(
                        ligature, Normalizer.Form.NFKC)));

        String fullwidthA = "\uFF21";
        System.out.println("NFKC folds fullwidth: "
                + "A".equals(Normalizer.normalize(
                        fullwidthA, Normalizer.Form.NFKC)));

        String vietnamese = "Ti\u1EBFng Vi\u1EC7t";
        String vietnameseNfd = Normalizer.normalize(
                vietnamese, Normalizer.Form.NFD);
        System.out.println("Vietnamese NFC round-trip: "
                + vietnamese.equals(Normalizer.normalize(
                        vietnameseNfd, Normalizer.Form.NFC)));

        System.out.println("NFC changes case: "
                + "A".equals(Normalizer.normalize(
                        "a", Normalizer.Form.NFC)));
    }
}
~~~

Save the file and run it with JDK 17 or later:

~~~bash
javac --release 17 -encoding UTF-8 UnicodeNormalizationDemo.java
java UnicodeNormalizationDemo
~~~

Stdout verified with JDK:

~~~text
Raw equals: false
UTF-16 lengths: 1 / 2
NFC equals: true
NFC idempotent: true
NFD code points: 2
NFC keeps ligature: true
NFKC expands ligature: true
NFKC folds fullwidth: true
Vietnamese NFC round-trip: true
NFC changes case: false
~~~

### Program Explanation

1. `composed` is code point `U+00E9`, while `decomposed` is two code points `U+0065 U+0301`. Thus unnormalized `String.equals` returns `false`.
2. The two strings have UTF-16 lengths of 1 and 2, respectively. After NFC, they are equal as Java character sequences, so `NFC equals` is `true`.
3. Applying NFC a second time does not change the string; `NFC idempotent` is `true`.
4. NFD decomposes `é` into two code points, printing `NFD code points: 2`.
5. NFC keeps `ﬃ`, whereas NFKC decomposes that character into `ffi`; this demonstrates the difference between canonical and compatibility forms.
6. NFKC converts fullwidth `Ａ` into the Latin `A` commonly used in ASCII.
7. The accented Vietnamese string is converted to NFD and back to NFC and equals the original string.
8. NFC does not change `"a"` to `"A"`. Normalization does not handle uppercase/lowercase automatically.

The program intentionally prints boolean/ASCII results instead of relying on terminal fonts. Unicode escapes in Java string literals are a way to write code points; they **do not** mean the normalized content becomes ASCII.

## 8. Vietnamese: Tone Marks, Circumflex/Breve Marks, and Combining Marks

Vietnamese uses many accented characters. For example, the letter `ế` can be represented by a single precomposed code point, or as a base letter and combining marks according to Unicode rules. For certain combinations, Unicode also defines a canonical order for combining marks so that canonically equivalent strings are processed consistently.

Conceptual example:

~~~text
Display: “Tiếng Việt”
NFC: prefers the precomposed representation when a canonical form exists
NFD: canonical decomposed form, potentially with more code points
NFKC/NFKD: additionally apply compatibility rules (depending on the character)
~~~

Not every Vietnamese string has a single character per grapheme. Do not use the rule `String.length() == number of visible letters`.

### Should Vietnamese Text Be Stored in NFC?

In many application systems, **NFC is a reasonable choice for validated Unicode text data**, enabling canonically equivalent strings to compare consistently while preserving distinctions between characters that are only compatibility equivalent.

However, that is **a data policy decision**, not a mandatory rule for every application. Specifically:

- Data that must be preserved verbatim for legal, digital signature, or audit purposes may need to store the original text.
- Systems with their own normalization policies must agree on the same form across all services.
- Do not strip diacritics and treat the result as NFC. Stripping diacritics is a different transformation and can corrupt names or meanings.
- For lookup keys and uniqueness constraints, you must control both the normalizer in the application and the collation in the database.

In Java, `Normalizer.normalize(text, Form.NFC)` does not automatically transliterate `"Đà Nẵng"` to `"Da Nang"`; creating an accent-free alias if needed is an additional step with its own rules.

## 9. At Which Step in the System Should You Normalize?

You need to choose a consistent **normalization boundary**. A suggested pipeline for ordinary text data:

1. Receive bytes from HTTP/file/database and **decode with the right charset** (typically UTF-8 by contract).
2. **Validate the input** according to its purpose: length limits, control characters, required fields; handle cases that are not valid Unicode strings.
3. Apply the chosen normalization form, typically NFC for text content; NFKC may be used on identifier fields only when explicitly approved.
4. Apply **field-specific** rules if needed: whitespace normalization, case folding, filtering disallowed characters, generating search aliases.
5. Re-check sensitive constraints after transformations and store data according to policy.
6. When searching or matching, use the same normalization rules for both the query value and the indexed value.

Why validate **after** normalization? A compatibility transformation can change the number of code points and character types, such as `ﬃ` → `ffi`. If validation is only applied before transformation, conditions on length, allowed characters, or uniqueness can become invalid after normalization.

Do not lump all processing into a method named `sanitize` without specifying each transformation. Steps like NFKC, lowercasing, trimming, blocking control characters, and HTML escaping have **different purposes**; their order can affect the outcome.

### Store the Original or the Normalized Version?

| Data field | Policy typically considered |
| --- | --- |
| Article content, legal text | Store the original; create a separate normalized version for search if needed |
| User display name | Consider NFC for comparison, while preserving the display version if the product requires it |
| Unicode lookup key | Pick a fixed normalization form and apply it to both storage and queries |
| Username/identifier | Design a profile specifying allowed characters, case mapping, normalization, confusables, and uniqueness |
| System-generated transaction code | Usually has a fixed machine syntax; do not arbitrarily apply NFKC |
| Signed/hashed strings | Strictly follow the protocol's canonicalization rules; do not alter content after signing |
| Password | Follow the system's authentication standard; do not normalize unless specified by the contract |

For passwords, undocumented transformations can prevent users from logging in even when they type the exact string they registered with. Define a clear, consistent policy aligned with the chosen standard; do not apply NFKC arbitrarily.

## 10. Normalization Is Not a Character-Security Solver

Unicode supports many visually similar letters and symbols. For example, the Latin letter `a` and a visually similar character in another script may not be canonically equivalent. Normalization **does not guarantee** detection of all **confusables/homoglyphs** and does not prevent all display-name spoofing attacks.

In addition:

- NFKC can erase compatibility distinctions that some protocols want to preserve.
- NFC does not automatically strip zero-width characters, remove control characters, or replace script checks.
- Normalization does not replace HTML escaping, SQL parameterization, URL encoding, or input validation.
- Combining NFKC with case folding/IDNA or username rules must follow a **specific profile**; `java.text.Normalizer` does not provide a comprehensive `NFKC_Casefold` API equivalent to every identifier standard.
- Normalizing two strings into the same form can affect **uniqueness** and account-name ownership; collisions must be handled intentionally.

If the product supports internationalized domain names, internationalized email, or security-sensitive identifiers, consult the corresponding standards such as IDNA and Unicode security profiles. Do not apply ordinary text rules to every identifier protocol.

**A wrong conclusion:** “Since it is NFC-normalized, the username is safe.” **The right conclusion:** “NFC stabilizes canonically equivalent representations; username security checking is a separate problem.”

## 11. Locale-Sensitive Comparison, Sorting, and Search Are Different Tasks

If you need to compare text according to **linguistic rules**, such as accented letters and sorting order, look at `java.text.Collator` with the appropriate locale. `Collator` handles **collation** according to configuration; it does not mean every matching problem is solved by NFC alone.

If you need flexible search:

- NFC helps unify certain canonically equivalent representations.
- Case folding / case-insensitive matching is a separate decision.
- Accent-insensitive search is a separate decision, which can cause many distinct words to collide.
- Tokenization, stemming, synonyms, and multilingual queries are different search problems.
- Translating a query to another language is a **translation** or cross-lingual retrieval feature, not normalization.

For example, `café` and `cafe` **do not become equal strings through NFC alone**. If you want users typing “cafe” to still find “café”, design an appropriate **search key** and keep the original text for display.

Do not use an “ASCII-fied” string as proof of spelling or as an authoritative translation.

## 12. Normalization Data, Unicode Versions, and Regression Testing

How normalization works relies on the Unicode data supported by the runtime. When updating the JDK, Unicode data can change across versions. Unicode stability policies are designed to preserve normalization compatibility for assigned characters under specific conditions, yet a rigorous system should still test its actual datasets and JDK version.

Things to watch out for:

- Unicode can update character tables and metadata; the system needs an upgrade policy.
- `Normalizer` output does not prove a string passed language validation.
- When data is stored by multiple services, all parties must standardize on the **normalization form** and policy.
- Databases have their own collations: a unique index may compare/match differently from Java's `String.equals`.
- CSV/JSON/XML import/export must specify charset (bytes) and normalization (characters) **separately** if strict compatibility is required.

### Recommended Tests

| Group | Test case |
| --- | --- |
| Canonical equivalence | `é` vs `e + U+0301`: different raw, equal after NFC |
| Idempotence | `NFC(NFC(s)) == NFC(s)` |
| Decomposition | `NFD(é)` consists of `e` and combining accent |
| Compatibility | `NFKC(ﬃ) == "ffi"`, while NFC preserves the ligature |
| Fullwidth | `NFKC(Ａ) == "A"` |
| Vietnamese | Multi-accented string round-trips through NFD then NFC |
| Uppercase/lowercase | NFC does not make `"a"` equal `"A"` |
| Accent stripping | NFC does not make `"má"` equal `"ma"` |
| Different scripts | Visually similar characters are not necessarily unified by NFC |
| Length | Do not assume `String.length()` equals visible grapheme count |
| Null/abnormal input | Check before calling, clear validation |
| Search | Query/index use the same form; uniqueness follows policy |
| Data preservation | Original text is not overwritten when needed for audit/signatures |

Write **invariant tests** rather than merely eyeballing two strings that look similar. Printing code points or hex during tests/debugging helps uncover differences the human eye cannot see.

## 13. Common Mistakes

| Mistake | Why it is wrong | Correct approach |
| --- | --- | --- |
| Using `String.equals` expecting automatic canonical equivalence | Compares UTF-16 code unit sequences directly | Normalize both sides per policy |
| Treating NFC as translating to English | NFC does not understand meaning | Use a translation system |
| Treating NFC as phonetic transcription or transliteration | No sound/script conversion rules | Use appropriate transliteration/transcription |
| Using NFD then stripping marks and calling it “lossless normalization” | It is a lossy transformation | Separate search alias from original text |
| Using NFKC on every field because it is “stronger” | Compatibility folding can lose distinctions | Choose form per field and test |
| Thinking UTF-8 guarantees NFC | Encoding is distinct from normalization | Specify both charset and form |
| Thinking NFC fixes mojibake | Bytes were decoded incorrectly | Fix charset/data source |
| Thinking NFC prevents all homoglyphs | Confusables are not necessarily Unicode-equivalent | Maintain a dedicated identifier/security policy |
| Using `length()` as visible character count | UTF-16 code units differ from grapheme clusters | Use an appropriate grapheme segmentation API |
| Normalizing only the query side | Misses matches | Apply the same policy to index and query |
| Ignoring database collation | DB uniqueness can differ from Java | Test and define canonical keys |
| Applying normalization after creating a digital signature | Alters bytes/hash | Canonicalize before signing per protocol |
| Confusing transliteration with accent removal | Different scripts have different conversion rules | Separate requirements and pick the right tool |

## 14. Self-Check Exercises

**Question 1.** Two strings both display “é”, yet `equals` returns `false`. What situation could cause this?

**Answer:** One string contains `U+00E9`, while the other contains `U+0065 U+0301`. They are canonically equivalent but do not have the same UTF-16 sequence. Normalize both to NFC or NFD before comparing.

**Question 2.** If an application wants to turn “Xin chào” into “Hello”, should it use `Normalizer.Form.NFKC`?

**Answer:** No. That is a language translation task, not Unicode normalization.

**Question 3.** Why can NFKC turn the ligature `ﬃ` into `ffi`, whereas NFC normally keeps it unchanged?

**Answer:** `ﬃ` has a compatibility decomposition; NFC only handles canonical equivalence, while NFKC adds compatibility equivalence.

**Question 4.** A user enters “má” and “ma”. Will NFC make them equal?

**Answer:** No. The tone mark here is a meaningful written difference. Stripping accents for search is a separate, lossy policy.

**Question 5.** Can the result of `Normalizer.isNormalized(text, NFC)` be used to declare a username safe?

**Answer:** No. It only indicates the normalization form; it does not verify confusables, script policies, length, disallowed characters, ownership, or other security checks.

**Practice exercise:** Write a program that accepts two `String` inputs from different sources; print their code point sequences in hex, compare before/after NFC, compare NFKC, and test a fullwidth letter case. Design a schema with `displayText` (preserving the display version when needed) and `searchKey` (normalized per policy), then write a test case that detects collisions when two source strings become the same key.

## 15. References

- [Normalizer — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html): `normalize`, `isNormalized`, and the four normalization forms.
- [Normalizer.Form — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.Form.html): NFC, NFD, NFKC, NFKD.
- [String — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): `length`, `equals`, and `codePointCount`.
- [Unicode Standard Annex #15 — Unicode Normalization Forms](https://unicode.org/reports/tr15/): definition of normalization and canonical/compatibility equivalence.
- [Unicode Technical Standard #39 — Unicode Security Mechanisms](https://unicode.org/reports/tr39/): confusables and Unicode security issues.
- [Collator — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Collator.html): linguistic comparison and sorting, distinct from normalization.

**Takeaway:** Unicode normalization stabilizes **how characters are represented**, not **meaning/language**, and does not necessarily change **script**. NFC/NFD preserve canonical equivalence; NFKC/NFKD also process compatibility equivalence and can lose representational distinctions. Choose the form per data field, standardize at system boundaries, and keep translation, phonetic transcription/transliteration, accent stripping, search, and security as separate responsibilities.
