# Canonical Equivalence vs. Compatibility Equivalence in Unicode Normalization

In Java, two strings can **look alike yet not have the same Unicode code point sequence**. For example, the letter **é** can be represented by a single precomposed code point **U+00E9 LATIN SMALL LETTER E WITH ACUTE**, or by two code points **U+0065 LATIN SMALL LETTER E** followed by **U+0301 COMBINING ACUTE ACCENT**. Both carry the same character meaning under **canonical equivalence**, yet **String.equals** compares UTF-16 contents and can return **false** if unnormalized.

Unicode also defines a broader relationship called **compatibility equivalence**. For example, the circled digit character **①** can be compatibility-normalized to the digit **1**, yet the two characters are not canonically equivalent: they serve different presentation roles. This is an important distinction in searching, comparison keys, storage, identifiers, and data preservation.

This lesson explains these two relationships precisely, the normalization forms **NFC, NFD, NFKC, NFKD**, how to use **java.text.Normalizer** on Java 17+, and scenarios where each form should and should not be used. The focus is on understanding **which normalizations preserve semantic/typographic distinctions, and which ones can merge characters that were originally distinct**.

## 1. A Unicode Code Point Is Not Synonymous with a User-Perceived Character

Before discussing equivalence, several concepts must be distinguished:

| Concept | Meaning | Example |
| --- | --- | --- |
| **Code point** | Numeric Unicode value, written U+XXXX | **U+00E9**, **U+0301** |
| **UTF-16 code unit** | 16-bit unit counted by **String.length()** | A code point outside the BMP typically needs two code units |
| **Combining mark** | Mark that combines with a preceding or surrounding character | **U+0301** is a combining acute accent |
| **Grapheme cluster** | Sequence of characters usually perceived by users as a single unit | **e + U+0301** looks like a single letter é |
| **Unicode normalization** | Conversion into a deterministic canonical form | **NFC, NFD, NFKC, NFKD** |

Strings that render identically do not necessarily share the same **String.length()**, code point count, UTF-8 byte count, or **String.equals** result.

Example:

~~~java
String precomposed = "\u00E9";  // é
String decomposed = "e\u0301"; // e + acute accent

System.out.println(precomposed.length()); // 1
System.out.println(decomposed.length());  // 2
System.out.println(precomposed.equals(decomposed)); // false
~~~

The snippet above illustrates code inside a Java method. Both spellings can look nearly indistinguishable to the naked eye, yet the first string consists of one BMP code point and the second consists of two code points. **String.equals** does not automatically normalize.

**Note:** Unicode normalization is not a grapheme-cluster counting algorithm. A single grapheme can contain multiple code points, and **String.length()** is not the number of user-perceived characters. Slicing display text by code unit can split a surrogate pair or a combining mark.

## 2. What Is Canonical Equivalence?

Two strings are called **canonically equivalent** if they represent the same text content according to Unicode's **canonical decomposition** and combining-mark ordering rules. They may differ in encoding representation, yet do not differ in the character meaning considered identical by the standard.

Classic example:

~~~text
U+00E9                    LATIN SMALL LETTER E WITH ACUTE
U+0065 U+0301             LATIN SMALL LETTER E + COMBINING ACUTE ACCENT
~~~

Both represent the letter **é**. After **NFD** normalization, both become the sequence **U+0065 U+0301**. After **NFC** normalization, both typically become **U+00E9**.

Key points:

- **Canonical equivalence** does not require the original strings to have the same bytes or code points.
- Equivalence is defined by Unicode data and rules, not by comparing two rendered images.
- **NFD** performs canonical decomposition; **NFC** performs canonical decomposition followed by recomposition per composition rules.
- If two strings are already canonically equivalent, normalizing both to **the same NFC or NFD form** yields directly comparable strings.
- Canonical equivalence does **not** mean “accent stripping”: **é** and **e** are not canonically equivalent, because the acute accent carries information.

Beyond precomposed characters and combining marks, Unicode also defines **canonical ordering** rules for certain combining marks. Two sequences with combining marks in different orders can still be canonically equivalent if Unicode rules reorder them into the same canonical order. Do not sort all marks manually by code point or ASCII position: canonical ordering is based on **canonical combining class**, with defined conditions and exceptions.

## 3. What Is Compatibility Equivalence?

**Compatibility equivalence** is a broader relationship. Unicode defines **compatibility decomposition** to map characters that were encoded separately for layout, typography, or historical compatibility reasons to a common form.

Examples:

| Original character | Code point | Typically becomes after NFKC | Reason |
| --- | --- | --- | --- |
| **①** | U+2460 CIRCLED DIGIT ONE | **1** (U+0031) | Removes circled-digit styling |
| **ﬃ** | U+FB03 LATIN SMALL LIGATURE FFI | **ffi** | Expands presentation ligature |
| **Ａ** | U+FF21 FULLWIDTH LATIN CAPITAL LETTER A | **A** | Removes fullwidth width variant |
| **²** | U+00B2 SUPERSCRIPT TWO | **2** | Removes superscript styling |
| **Ⅳ** | U+2163 ROMAN NUMERAL FOUR | **IV** | Converts Roman numeral character to letters |
| **U+00A0** | NO-BREAK SPACE | **U+0020 SPACE** | Removes the non-breaking property of the space |

These examples can be useful for **search keys** or inputs where presentation differences should be reduced, yet they also reveal risks: **①** and **1** are not always interchangeable in UI meaning, **²** and **2** differ in mathematical formulas, **Ⅳ** may be a Roman section label, and **NO-BREAK SPACE** controls line wrapping.

**Compatibility equivalence does not mean two strings are completely equivalent encodings for every purpose.** It intentionally merges certain presentational/legacy distinctions. An application that needs to preserve mathematical expressions, product codes, brand names, or typographically meaningful content verbatim must be cautious before applying NFKC/NFKD.

**Subset relationship:** every canonically equivalent pair is also considered compatibility equivalent; the converse is not true. For instance, **①** and **1** are compatibility equivalent but not canonically equivalent.

## 4. The Four Unicode Normalization Forms: NFC, NFD, NFKC, NFKD

Unicode defines four normalization forms. In Java, they reside in **java.text.Normalizer.Form**:

| Form | Main Mechanism | Properties |
| --- | --- | --- |
| **NFD** | Canonical Decomposition | Canonical decomposition, canonically ordering combining marks |
| **NFC** | Canonical Decomposition followed by Canonical Composition | Composes to precomposed canonical form when possible |
| **NFKD** | Compatibility Decomposition | Compatibility decomposition, including canonical decompositions |
| **NFKC** | Compatibility Decomposition followed by Canonical Composition | Compatibility merging followed by canonical composition |

**The letter K** in **NFKC/NFKD** marks the **compatibility** forms. Do not guess that NFKC is merely “faster NFC” or “stronger NFC for security”: the two serve different comparison purposes.

Relationship on the same examples:

~~~text
Initial data: é
  NFC  -> é
  NFD  -> e + acute accent
  NFKC -> é
  NFKD -> e + acute accent

Initial data: ①
  NFC  -> ①
  NFD  -> ①
  NFKC -> 1
  NFKD -> 1

Initial data: ﬃ
  NFC  -> ﬃ
  NFD  -> ﬃ
  NFKC -> ffi
  NFKD -> ffi
~~~

**NFC does not guarantee that every decomposable code point gets composed.** Composition follows rules and exclusion lists; some characters have no corresponding composed form. **NFD is not simply “splitting every character into multiple characters”**: characters without a canonical decomposition remain unchanged.

### 4.1. Why Is NFC Commonly Chosen for Storing Text?

NFC has useful properties:

- Normalizes different encodings that are canonically equivalent.
- Does not aggressively merge characters like **①**, **ﬃ**, **²** the way NFKC does.
- When an allowed composed form exists, generally uses a more compact representation for accented letters.
- Convenient for comparison once a normalization policy is set at data boundaries.

However, **NFC does not guarantee a smaller size than NFD**, nor does it resolve every visual difference. If a system's data already follows a different representation contract, do not switch without understanding the impact on signatures, character offsets, or client compatibility.

### 4.2. Why Is NFKC Often Useful for Search Keys?

NFKC can collapse fullwidth/halfwidth variants and decorative symbols into common strings, allowing users searching with **A** to match **Ａ** when the application sets a compatibility search key.

However, **NFKC discards some distinctions that Unicode encoded intentionally**. Therefore, it is better suited for a **search index**, **normalization key**, or data with an explicit contract, rather than unconditionally replacing original display text.

## 5. Java 17+ API: java.text.Normalizer

Java provides:

~~~java
import java.text.Normalizer;

String normalized = Normalizer.normalize(
        input, Normalizer.Form.NFC);

boolean alreadyNormalized = Normalizer.isNormalized(
        input, Normalizer.Form.NFC);
~~~

This is an illustrative snippet requiring **input** to be a non-null string. **Normalizer.normalize(CharSequence, Normalizer.Form)** returns a normalized **String**. **Normalizer.isNormalized(CharSequence, Normalizer.Form)** checks whether the string is already in the requested form.

The four enum values:

~~~java
Normalizer.Form.NFC
Normalizer.Form.NFD
Normalizer.Form.NFKC
Normalizer.Form.NFKD
~~~

**Normalizer does not mutate the original String:** String is immutable. Caller code receives a separate result string; there is no in-place operation.

A simple API at a data boundary:

~~~java
public static String canonicalKey(String text) {
    if (text == null) {
        throw new IllegalArgumentException("text is null");
    }
    return Normalizer.normalize(
            text, Normalizer.Form.NFC);
}
~~~

The snippet above is a method placed inside a Java class that imports **java.text.Normalizer**. This is an example of a **canonical comparison key**, not a case-insensitive search key, not a personal-name validator, and not a guaranteed anti-spoofing measure for Unicode.

**Normalizer.normalize** does not solve security by itself, does not change Locale, does not translate text, and does not collapse every look-alike character into one code point.

## 6. Complete Java 17+ Example: Canonical vs. Compatibility

The following example represents characters using Unicode escapes in source code to avoid encoding mistakes when copying. It prints only clear ASCII results for comparisons.

**File UnicodeEquivalenceDemo.java**

~~~java
import java.text.Normalizer;
import java.text.Normalizer.Form;

public class UnicodeEquivalenceDemo {
    public static void main(String[] args) {
        String composed = "\u00E9";
        String decomposed = "e\u0301";

        String circledOne = "\u2460";
        String digitOne = "1";
        String ligature = "\uFB03";
        String fullwidth = "\uFF21";

        System.out.println(
                "rawEqual=" + composed.equals(decomposed));

        System.out.println(
                "canonicalNFC=" +
                Normalizer.normalize(composed, Form.NFC)
                        .equals(Normalizer.normalize(
                                decomposed, Form.NFC)));

        System.out.println(
                "canonicalNFD=" +
                Normalizer.normalize(composed, Form.NFD)
                        .equals(Normalizer.normalize(
                                decomposed, Form.NFD)));

        System.out.println(
                "circledNFC=" +
                Normalizer.normalize(circledOne, Form.NFC)
                        .equals(digitOne));

        System.out.println(
                "circledNFKC=" +
                Normalizer.normalize(circledOne, Form.NFKC)
                        .equals(digitOne));

        System.out.println(
                "ligatureNFKC=" +
                Normalizer.normalize(ligature, Form.NFKC));

        System.out.println(
                "fullwidthNFKC=" +
                Normalizer.normalize(fullwidth, Form.NFKC));

        String once = Normalizer.normalize(
                decomposed, Form.NFC);
        String twice = Normalizer.normalize(
                once, Form.NFC);

        System.out.println(
                "idempotent=" + once.equals(twice));
    }
}
~~~

Compile and run in the directory containing the file:

~~~bash
javac -encoding UTF-8 UnicodeEquivalenceDemo.java
java UnicodeEquivalenceDemo
~~~

Stdout:

~~~text
rawEqual=false
canonicalNFC=true
canonicalNFD=true
circledNFC=false
circledNFKC=true
ligatureNFKC=ffi
fullwidthNFKC=A
idempotent=true
~~~

**Explanation of each check:**

1. **rawEqual=false:** Java String.equals compares UTF-16 code units without automatic normalization.
2. **canonicalNFC=true:** both encodings of the letter é become the same NFC form.
3. **canonicalNFD=true:** both become the sequence e + combining acute accent.
4. **circledNFC=false:** NFC does not strip the circle from the digit **①**.
5. **circledNFKC=true:** NFKC merges **①** with **1** under compatibility mapping.
6. **ligatureNFKC=ffi:** the presentation ligature is expanded.
7. **fullwidthNFKC=A:** the fullwidth form is converted to the ordinary Latin letter A.
8. **idempotent=true:** once normalized to a form, normalizing again with **the same form** does not change the content.

This is a complete program whose class name matches the file name and uses APIs present in Java 17. The comparisons are chosen to verify **core rules** rather than relying on how a terminal font renders glyphs.

## 7. Inspecting Code Points Instead of Eyeballing Glyphs

When two strings print identically, inspect **codePoints()**. Unicode normalization operates on code point sequences; inspecting code points reveals combining marks, ligatures, fullwidth forms, and special whitespace characters.

**File NormalizationCodePoints.java**

~~~java
import java.text.Normalizer;
import java.text.Normalizer.Form;
import java.util.Locale;
import java.util.stream.Collectors;

public class NormalizationCodePoints {
    private static String describe(String value) {
        return value.codePoints()
                .mapToObj(cp -> String.format(
                        Locale.ROOT, "U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    private static void show(String label, String value) {
        System.out.println(label
                + " | NFC=" + describe(
                        Normalizer.normalize(value, Form.NFC))
                + " | NFD=" + describe(
                        Normalizer.normalize(value, Form.NFD))
                + " | NFKC=" + describe(
                        Normalizer.normalize(value, Form.NFKC))
                + " | NFKD=" + describe(
                        Normalizer.normalize(value, Form.NFKD)));
    }

    public static void main(String[] args) {
        show("accent", "\u00E9");
        show("circled", "\u2460");
        show("ligature", "\uFB03");
        show("fullwidth", "\uFF21");
        show("nbsp", "\u00A0");
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 NormalizationCodePoints.java
java NormalizationCodePoints
~~~

Stdout:

~~~text
accent | NFC=U+00E9 | NFD=U+0065 U+0301 | NFKC=U+00E9 | NFKD=U+0065 U+0301
circled | NFC=U+2460 | NFD=U+2460 | NFKC=U+0031 | NFKD=U+0031
ligature | NFC=U+FB03 | NFD=U+FB03 | NFKC=U+0066 U+0066 U+0069 | NFKD=U+0066 U+0066 U+0069
fullwidth | NFC=U+FF21 | NFD=U+FF21 | NFKC=U+0041 | NFKD=U+0041
nbsp | NFC=U+00A0 | NFD=U+00A0 | NFKC=U+0020 | NFKD=U+0020
~~~

**Why use codePoints instead of chars?** Java String uses UTF-16; **chars()** iterates by individual code units, whereas **codePoints()** combines valid surrogate pairs into code points. Although the examples in the table are all in the BMP, writing codePoints is the right approach for multiple languages and supplementary characters.

**Why pass Locale.ROOT to String.format?** Solely to print hex codes and technical labels consistently; it has no effect on Normalizer results. The Normalizer API does not consult the browser or server locale to decide canonical or compatibility decomposition.

## 8. Canonical Equivalence: Both Decomposition and Combining-Mark Ordering

An inaccurate understanding is that “canonical normalization just replaces each precomposed accented letter with a base letter + one mark.” In reality, NFD performs:

1. Decomposing characters that have a **canonical decomposition** in Unicode.
2. Putting combining marks into canonical order according to **canonical combining class** rules.
3. Handling special scripts per the Unicode algorithm, notably **Hangul** syllables.

**NFC** further performs canonical composition under standard-permitted conditions.

This provides a useful property: if two strings are **canonically equivalent**, we can normalize both to NFD or NFC for comparison. However, never write a custom “strip marks then reattach” algorithm, because there are combining marks, composition exclusions, non-decomposable characters, and non-obvious ordering rules.

### 8.1. Hangul and Canonical Equivalence

Precomposed Hangul syllables in Unicode can be decomposed into their corresponding Jamo and recomposed according to Unicode rules. Consequently, NFD/NFC is not just for accented Latin letters. When an application supports Korean, do not assume every Hangul string has exactly one code point per visible syllable.

This also shows that **code point count** is not the visible character count. Normalization can increase or decrease the number of code points without changing content at the canonical equivalence level.

### 8.2. Easy-to-Misunderstand Case: the Angstrom Sign

The character **U+212B ANGSTROM SIGN (Å)** has a **canonical decomposition** related to **U+00C5 LATIN CAPITAL LETTER A WITH RING ABOVE (Å)**. This is a notable example: even though its Unicode name sounds like a “specialized symbol,” you cannot judge whether it is only compatibility-equivalent just by looking at its appearance or name.

**You must rely on Unicode property tables and rules**, not on the guess “it has a special role, so it must be compatibility.”

Conversely, **U+2460 ①** has a compatibility decomposition to the digit **1**, not a canonical decomposition; hence NFC does not merge this pair.

## 9. When Are Two Strings Considered Equal?

There are multiple notions of “equal,” and they cannot be interchanged:

| Criterion | Question | Example |
| --- | --- | --- |
| **String.equals equality** | Are the UTF-16 sequences strictly identical? | Precomposed é differs from e + acute accent |
| **Canonical equivalence** | Do they share the same NFC/NFD form? | Both representations of é are equivalent |
| **Compatibility equivalence** | Do they share the same NFKC/NFKD form? | ① and 1 are equivalent |
| **Case-insensitive** | Ignore uppercase/lowercase differences per policy? | A and a can match, though NFKC alone does not do this |
| **Accent-insensitive** | Ignore certain accents? | café and cafe can match in search, not due to NFC |
| **Collation** | Sort/compare linguistically per locale rules? | Accented names may sort differently depending on language |
| **Visual similarity/confusables** | Could two strings look alike? | Latin a and Cyrillic а can look visually identical |
| **Application-specific equality** | Does the product have custom equivalence rules? | Usernames, product codes, search keys |

**Do not claim “NFKC turns all look-alike strings into the same string.”** Many visually similar characters are not considered compatibility-equivalent by Unicode; for example, **Latin a** and **Cyrillic а** (two distinct code points) are not automatically merged by standard Java Normalizer.

**Do not claim “NFC removes accents.”** NFC preserves the distinction between **é** and **e**; even NFD keeps the acute accent as a combining mark.

## 10. Unicode Normalization Is Not Transliteration or Case Folding

Several search needs are often mistakenly lumped together:

- **Normalization:** choosing a standard Unicode representation (NFC/NFD/NFKC/NFKD).
- **Case conversion:** converting uppercase/lowercase per Locale or custom rules.
- **Case folding:** Unicode's mechanism for case-insensitive comparison; not completely identical to **String.toLowerCase**.
- **Transliteration:** converting one script into another script, e.g., phonetic spelling.
- **Diacritic removal:** removing certain combining marks, which can lose linguistic distinctions.
- **Collation:** comparing/sorting text according to linguistic rules.
- **Confusable detection:** detecting characters that enable visual spoofing.

**java.text.Normalizer** performs only **normalization**. It does not convert Cyrillic to Latin, translate Vietnamese to English, or handle full case folding or confusable detection.

### 10.1. Combining Lowercase When Required by the Product

Example of a basic case-insensitive search key:

~~~java
import java.text.Normalizer;
import java.util.Locale;

public class SearchKey {
    public static String simpleKey(String input) {
        return Normalizer.normalize(
                input, Normalizer.Form.NFKC)
                .toLowerCase(Locale.ROOT);
    }
}
~~~

This is a utility class without `main`. **Locale.ROOT** avoids picking up the JVM default locale during lowercasing, yet **lowercasing is not fully equivalent to Unicode case folding**. Moreover, the ordering between case mapping and normalization can matter for special characters; products needing sophisticated international matching must use appropriate algorithms and tests rather than assuming the helper above covers every language.

**Note on Turkish:** characters involving **I/i** have special casing rules. Use the user's locale or Locale.ROOT according to the comparison contract; do not let the server's default locale decide implicitly.

### 10.2. Stripping Accents Is a Different Rule

A common illustrative recipe is normalizing to NFD and filtering out characters in category **Mark**. That recipe can turn **é** into **e**, yet it is no longer canonical-equivalent comparison: it is a **lossy transformation**.

In Vietnamese, stripping accents can collapse multiple words with different meanings into the same string. Never apply it by default to personal names, legal information, original Vietnamese data, or exact identifier checks.

## 11. NFC and NFKC Can Cause Different Types of Collisions

A **collision** occurs when two distinct original strings map to the same normalized key.

### 11.1. Canonically Accepted Collisions

~~~text
"é"           -> NFC -> "é"
"e\u0301"      -> NFC -> "é"
~~~

At the canonical equivalence level, Unicode treats both strings as having the same content. If a product wants to prevent users from registering two account names that differ only in how combining marks are encoded, NFC helps unify them.

However, if two legacy records already exist prior to normalization, adding a UNIQUE constraint on an NFC column can cause duplicates. A migration is needed to identify duplicate data and decide how to resolve it, rather than overwriting records automatically.

### 11.2. Additional Collisions Under Compatibility

~~~text
"①"           -> NFKC -> "1"
"1"           -> NFKC -> "1"

"Ａ"          -> NFKC -> "A"
"A"           -> NFKC -> "A"
~~~

For a search system, this collision may be desirable. Yet in **order codes**, **account names**, **technical labels**, or **mathematical symbols**, the two values may need to remain distinct. NFKC is not a safe default for every data field.

**Design rule:** determine the data type, comparison contract, and acceptable level of information loss before choosing a normalization form. The normalization form is part of the field's **semantics**, not merely a character-cleanup step.

## 12. How Should Input, Storage, Search, and Display Be Handled?

They can be categorized as follows:

| Data Type | Reasonable Approach | Warning |
| --- | --- | --- |
| Ordinary text content | Consider NFC when canonical consistency is needed | Must respect legacy contracts and verbatim data |
| Personal names, addresses, legal text | Prefer preserving the original; optionally build a separate NFC key | Do not drop diacritics or alter language |
| Search index | Can use NFKC if the product wants to merge compatibility variants | Use a separate key; account for collisions |
| Username | Define normalization, case, script, and confusable policies | NFKC alone does not guarantee safety |
| Product codes/QR codes/protocol identifiers | Follow protocol definition; often needs exact byte comparison | Do not apply NFKC unless specified |
| Passwords | Follow the system's password handling standard | Do not alter before hashing/matching unless policy specifies |
| Mathematical/technical content | Preserve meaningful symbol distinctions | NFKC can turn **²** into **2** |
| Rich text/presentations needing no-break space | Consider preserving raw or NFC | NFKC can turn NBSP into SPACE |

In many applications, a sound design stores:

1. **originalText:** the text as entered by the user, for display/editing.
2. **canonicalText:** if canonical comparison is needed, use NFC.
3. **searchKey:** compatibility and case transformations per policy, potentially using NFKC and dedicated steps.

These fields must not be conflated arbitrarily. **The search key is not the original content**, and changing key rules can change query results or cause unique-index conflicts.

## 13. Example Design Storing Original and Canonical Key

A Java record can store both the original and normalized forms:

~~~java
import java.text.Normalizer;

public record LocalizedLabel(
        String originalText,
        String canonicalText) {

    public static LocalizedLabel from(String input) {
        if (input == null) {
            throw new IllegalArgumentException("input is null");
        }
        return new LocalizedLabel(
                input,
                Normalizer.normalize(
                        input, Normalizer.Form.NFC));
    }
}
~~~

This is a valid Java 17 record without `main`. It keeps the received text verbatim alongside an NFC variant for canonical comparison. Generating an NFKC searchKey should be a separate method per product contract, never silently replacing **originalText**.

Suppose a system receives two label names that look identical on screen but differ in encoding:

~~~text
Original #1: U+00E9
Original #2: U+0065 U+0301
Canonical #1: U+00E9
Canonical #2: U+00E9
~~~

Both originals can still be retained for auditing or exact export, while the canonical unique key detects the duplicate.

If historical data already exists, run the migration in read-only mode to **measure collisions before** applying constraints or rewriting content. Never auto-merge two accounts or profiles just because NFKC produces the same key: that can impact access control and business data.

## 14. Idempotence: Normalizing Twice with the Same Form Does Not Change the Output

A fundamental property:

~~~text
normalize(normalize(s, NFC), NFC)   = normalize(s, NFC)
normalize(normalize(s, NFD), NFD)   = normalize(s, NFD)
normalize(normalize(s, NFKC), NFKC) = normalize(s, NFKC)
normalize(normalize(s, NFKD), NFKD) = normalize(s, NFKD)
~~~

In code:

~~~java
String once = Normalizer.normalize(
        text, Normalizer.Form.NFC);
String twice = Normalizer.normalize(
        once, Normalizer.Form.NFC);

assert once.equals(twice);
~~~

This illustrative snippet sits inside a method, importing Normalizer and using variable `text`. Idempotence helps test pipelines: data already stored in NFC should not change upon repeated NFC normalizations.

**However, do not conclude that mixing forms always yields the same result.** NFKC can strip compatibility distinctions that NFC keeps; converting to NFKC and back to NFC cannot recover **①** from **1**.

### 14.1. isNormalized Does Not Mean “Clean Text”

**Normalizer.isNormalized(s, NFC) == true** only states that `s` is in NFC. It does not confirm:

- That the user did not enter look-alike spoofing characters.
- That the string contains no unwanted control characters.
- That the string is in the right language or valid email format.
- That there are no cross-script homoglyphs.
- That there are no out-of-policy zero-width or bidi characters.
- That the string is safe as a filename or account name.

It is a normalization check, not a general security or business validator.

## 15. Normalization and String Splitting in Java

Java String stores UTF-16. After normalization:

- **length()** can increase or decrease.
- **codePointCount(...)** can change.
- **getBytes(StandardCharsets.UTF_8).length** can change.
- **substring** or saved indices from old character positions may no longer point to the same spot.
- Cursors, highlights, and offsets in an editor may need remapping if the normalized version is displayed.

For example, precomposed **é** is one code point, whereas NFD produces two code points; that affects indices. An application that uses offsets to highlight search matches in original text must not apply offsets from an NFKC searchKey directly onto originalText without mapping.

**Be careful with text segmentation:** accented letters are not “one code point per user character.” To slice by visible characters, you need an appropriate grapheme-cluster solution; **String.codePoints()** iterates by code point rather than grouping combining marks into clusters.

## 16. Does Normalization Affect Signatures, Hashes, and Protocols?

Yes. The UTF-8 encodings of precomposed **é** and **e + acute accent** differ. Therefore:

~~~text
SHA-256(UTF-8(original-1)) != SHA-256(UTF-8(original-2))
~~~

Two canonically equivalent strings still produce different hashes because **hashing operates on input bytes**, unaware of Unicode equivalence. If a protocol requires both representations to be treated identically, **normalization and encoding before hashing/signing must be specified** across all participating parties.

Conversely, if a protocol defines signatures over **raw bytes**, normalizing before verifying a signature can fail verification or create client/server mismatches. Never change the normalization form in a deployed signature system without contract versioning.

For passwords, arbitrarily applying NFKC/NFC before hashing when it was not done previously can lock users out. Any change to how Unicode passwords are handled must follow the system's design/standard and a safe migration plan, never treated as an undiscussed “cleanup” step.

## 17. Normalization and Unicode Security: Do Not Confuse the Goal

Unicode security cannot be solved by NFC or NFKC alone.

### 17.1. Homoglyphs / Confusables

A Latin letter **a** and a Cyrillic letter **а** can look easily alike in many fonts, yet are two code points in two scripts. NFKC does not convert Cyrillic to Latin by default. If usernames or domains must guard against look-alike spoofing, you must consider **script restrictions**, **confusable** detection, and the rules of an appropriate identifier standard.

### 17.2. Bidi and Invisible Characters

Strings can contain bidirectional formatting marks, zero-width joiners, or non-joiners. Normalizer is not a tool to “strip all invisible characters”; some characters are retained because they serve linguistic functions.

If an application serves scripts such as Arabic, indiscriminate filtering can corrupt text. Identify the data domain (username, chat, technical code) before applying rules on control/default-ignorable characters.

### 17.3. Unicode Normalization Does Not Replace Escaping

Before placing text into HTML, SQL, URLs, or a shell, use appropriate escaping/parameter binding. Normalizer does not prevent XSS, SQL injection, or path traversal. Do not use **NFKC** as a sole “security filter.”

### 17.4. Order of Validation and Normalization

For identifiers with strict policies, the order of steps can change outcomes. For instance, if you validate first, a string containing fullwidth letters may fail an ASCII regex; if you run NFKC first, it can turn into ASCII and pass. This is a **protocol decision**, not a case where one order is universally right.

A pipeline must make clear: receive data → choose normalization form → validate characters/length/limits → compare unique key → store. Also inspect original data and the consequences of normalization altering content. When policy is unclear, it is safer to preserve raw input and reject out-of-contract forms.

## 18. Normalization and Databases

A Java application may use NFC for keys, yet the database might:

- Compare bytes directly or use a custom collation.
- Have a case-insensitive/accent-insensitive collation that does not match Java's algorithm.
- Have a unique index based on a different normalization or transformation.
- Hold legacy unnormalized data.

Do not deduce that **NFKC in Java** is fully equivalent to **LOWER**, **UNACCENT**, or a particular database collation. The algorithms have different scopes.

A practical design:

~~~text
User submits text
       |
       v
Validate input contract
       |
       +------> Store originalText
       |
       v
Create canonicalKey (NFC) per policy
       |
       +------> Unique index if goal is canonical equality
       |
       v
Create searchKey (NFKC/case/... per policy)
       |
       +------> Search index, without replacing originalText
~~~

When changing normalization versions or policies, run a controlled backfill and **check for collisions first**. Never merge records based solely on a lossy key without explicit business rules.

## 19. When Should You Use NFC, NFD, NFKC, or NFKD?

### Choose NFC if

- You need to compare canonically equivalent encodings.
- You want text consistency while preserving compatibility distinctions.
- You want to create a canonical key for names, labels, or general Unicode content.
- Your protocol/application defines NFC as the storage or interchange form.

### Choose NFD if

- You need to inspect combining marks or decomposed components for specialized text processing.
- A downstream tool requires the canonical decomposed form.
- You understand the increased code point count and its impact on offsets/display.

**NFD is not an accent-removal command**; it keeps accents as combining marks. If a downstream step removes marks, that is a separate lossy step.

### Choose NFKC if

- You need to collapse differences between fullwidth and ordinary Latin letters, circled digits and ordinary digits, or certain ligatures and expanded sequences.
- You have an explicit policy stating compatibility variants are considered equivalent.
- You are generating a searchKey or identifier profile whose specification calls for this form.

**Do not pick NFKC just because “characters look alike” or it seems like the “strongest standard.”** It can destroy the meaning of mathematical symbols, typography, and non-breaking spaces.

### Choose NFKD if

- You need compatibility decomposition into components for further processing/lookup.
- A downstream algorithm requires compatibility decomposition rather than the composed form.
- You have explicitly decided whether to keep or remove combining marks after decomposition.

**NFKD also keeps combining marks**, rather than deleting them automatically. It is not transliteration or general ASCII conversion.

## 20. Common Mistakes When Learning and Applying Normalization

### Mistake 1 – Assuming Unicode strings that look alike must return true from equals

Precomposed **é** and **e + acute accent** can look identical while String.equals returns false. Normalize both to NFC/NFD before canonical-equivalence comparison.

### Mistake 2 – Confusing NFC with NFKC

NFC does not turn **①** into **1**; NFKC does. If you accidentally use NFKC on data that needs to preserve symbols, you can alter content.

### Mistake 3 – Thinking compatibility always means “completely equivalent”

**²** and **2** are related by compatibility decomposition, yet do not carry the same presentational meaning in mathematics. Compatibility equivalence is not automatic permission to overwrite originals.

### Mistake 4 – Thinking normalization strips accents

Both NFC and NFD distinguish **café** from **cafe**. NFD only splits accents into separate code points; stripping accents is a different, potentially lossy algorithm.

### Mistake 5 – Using NFKC to stop all homoglyphs

Latin and Cyrillic contain visually identical characters that are not compatibility-equivalent. Dedicated script/confusable policies are needed for secure identifiers.

### Mistake 6 – Using the JVM default in toLowerCase

When building lowercase keys, do not rely on an arbitrary environment Locale. Pick Locale.ROOT or a business locale, remembering that lowercasing is still not full Unicode case folding.

### Mistake 7 – Normalizing in one service but not another

Two systems comparing keys under different policies can accept duplicates or fail lookups. Normalization is part of the data contract and must be applied consistently at every boundary.

### Mistake 8 – Deleting the original after creating a searchKey

NFKC can alter typographic details that cannot always be recovered. Keep the original when the application must render user content accurately.

### Mistake 9 – Measuring length before normalizing and using offsets afterward

UTF-16 length and code-point count can change after NFC/NFD/NFKC/NFKD. Offsets on the original and normalized strings can differ. Track mappings if highlighting results.

### Mistake 10 – Failing to check duplicates before adding a UNIQUE constraint

Different original strings can collapse to the same canonical or search key. Migrate data in a controlled manner, count collisions, and resolve them before enabling constraints.

### Mistake 11 – Normalizing arbitrary bytes without knowing the encoding

Unicode normalization operates on character/code point sequences. First decode bytes with the defined encoding, usually UTF-8. Normalization does not auto-detect UTF-8/UTF-16 or fix corrupted bytes.

### Mistake 12 – Mixing normalization with XSS/SQL handling

Normalizer does not escape HTML, parameterize SQL, or validate access rights. Use the proper tool for each security layer.

## 21. Recommended Test Matrix

| Input A | Input B | Equal originally? | Equal after NFC? | Equal after NFKC? |
| --- | --- | --- | --- | --- |
| **é** U+00E9 | **e + U+0301** | No | Yes | Yes |
| **①** | **1** | No | No | Yes |
| **ﬃ** | **ffi** | No | No | Yes |
| **Ａ** | **A** | No | No | Yes |
| **²** | **2** | No | No | Yes |
| **NBSP U+00A0** | **SPACE U+0020** | No | No | Yes |
| **é** | **e** | No | No | No |
| **A** | **a** | No | No | No |
| **Latin a** | **Cyrillic а** | No | No | No |

The table above illustrates representative pairs; it does not imply NFKC is an appropriate comparison policy for every data field.

Beyond the pairs above, test:

1. **Idempotence:** normalizing twice with the same form yields the same result.
2. **Canonical ordering:** combining-mark sequences defined as equivalent by Unicode yield the same NFC/NFD.
3. **Hangul:** canonical decomposition and recomposition.
4. **Supplementary Unicode (outside BMP):** never split surrogate pairs.
5. **NBSP and formatting characters:** preserve meaningful whitespace when retaining content.
6. **JDK/Unicode version changes:** application contracts hold as expected.
7. **Collisions in existing data:** new keys do not overwrite old records.
8. **Case and accents:** clearly separate normalization from lowercasing/diacritic removal.
9. **Cross-script confusables:** do not assume Normalizer handles them.
10. **Null, empty, and long inputs:** handle safely to avoid unnecessary resource exhaustion.

### 21.1. A Simple Property-Based Check

For any valid string **s** per contract:

~~~java
String nfc = Normalizer.normalize(
        s, Normalizer.Form.NFC);

if (!nfc.equals(Normalizer.normalize(
        nfc, Normalizer.Form.NFC))) {
    throw new AssertionError("NFC is not idempotent");
}
~~~

This illustrative snippet sits inside a method and requires importing Normalizer and defining variable `s`. In tests, include character sets from real languages. Avoid testing only ASCII text, as ASCII rarely exposes combining-mark or compatibility issues.

## 22. Decision Process for a Unicode Field

When designing a text field in an application:

**Step 1:** Decide whether you need to **keep the exact original** or are allowed to unify representations.

**Step 2:** If you only want canonically equivalent encodings to match, consider **NFC**.

**Step 3:** If you want to collapse presentational differences like fullwidth, circled digits, or ligatures, consider **NFKC**, but evaluate information loss and collisions.

**Step 4:** If case-insensitivity is required, handle case under a **separate** contract; do not treat NFKC as case folding.

**Step 5:** If accent-insensitive search is required, define the exact language rules and acceptable information loss; **do not apply a default accent-stripping algorithm to original data**.

**Step 6:** If the field is an identifier or security-sensitive, consider scripts, confusables, allowed characters, post-normalization length, and the system's applicable standard rules.

**Step 7:** Audit legacy data before changing policy; calculate collisions and impact on unique indexes in advance.

**Step 8:** Create tests for canonical pairs, compatibility pairs, emoji/combining sequences, whitespace, case, and real-language datasets.

**Step 9:** Document the normalization form explicitly in the API contract or data specification so other systems do not pick a different form on their own.

## 23. Self-Check Questions

1. Why can **é** and **e + acute accent** differ under **String.equals** yet still be canonically equivalent?
2. Why are **①** and **1** merged only by NFKC/NFKD, and not by NFC/NFD?
3. If an application stores mathematical content containing **²**, should it always run NFKC on all text? Why or why not?
4. When normalized to NFD, does the acute accent disappear automatically?
5. Does NFKC automatically make **A** and **a** equal? Does it convert Cyrillic а into Latin a?
6. When using NFC to build a unique key, what must the system do with historical records that had different Unicode sequences but share the same canonical form?
7. When building an NFKC searchKey, should originalText be deleted?
8. When computing a hash or signature, why must normalization and encoding be specified in the protocol?
9. When normalization changes the code point count, what happens if the UI keeps using offsets from the original string?
10. In Java 17, which API checks whether a string is already in NFC, and which API converts it to NFC?

**Hints:** (1) Two different Unicode sequences, String.equals does not normalize; (2) circled digits have a compatibility decomposition; (3) no, it would lose superscript distinction; (4) no; (5) no; (6) collision detection/migration; (7) no, if preservation is needed; (8) different bytes produce different hashes; (9) position mapping is required; (10) **Normalizer.isNormalized** and **Normalizer.normalize**.

## 24. Practical Checklist

- [ ] Distinguished **canonical equivalence** from **compatibility equivalence**.
- [ ] Selected **NFC/NFD/NFKC/NFKD** based on intended purpose, not on guessing which is “stronger.”
- [ ] Understood that **String.equals** compares raw UTF-16 representations.
- [ ] Preserved diacritics/combining marks when content fidelity is required.
- [ ] Recognized that NFKC can convert **① → 1**, **ﬃ → ffi**, **Ａ → A**, **NBSP → SPACE**.
- [ ] Separated normalization from case folding, accent removal, transliteration, collation, and confusable detection.
- [ ] Decided explicitly whether to retain **originalText** and maintain a separate **searchKey/canonicalKey**.
- [ ] Planned collision handling and legacy data migration.
- [ ] Avoided altering bytes of signed messages or password data unless specified by protocol.
- [ ] Tested combining marks, fullwidth, ligatures, circled digits, whitespace, and multi-script strings.
- [ ] Inspected **codePoints()** when strings look alike but `equals` results differ.
- [ ] Accounted for UTF-16 length/offset changes after normalization.
- [ ] Tested on target JDK versions when cross-upgrade consistency is needed.
- [ ] Enforced a uniform normalization policy at data boundaries.

## 25. Conclusion

**Canonical equivalence** addresses different encodings of the same character content in Unicode; **NFC/NFD** bring them to the same representation for comparison or processing. **Compatibility equivalence** additionally merges presentational/historical variants such as **①** with **1**, **ﬃ** with **ffi**, and **Ａ** with **A**; **NFKC/NFKD** perform this, sometimes losing necessary distinctions.

In Java 17+, **java.text.Normalizer** provides normalization and form-checking operations. Choose **NFC** when canonical equivalence consistency is needed while preserving compatibility distinctions; choose **NFKC** when an explicit policy requires compatibility variants to share a key. Always separate the **original string** from **lookup/comparison keys** when data carries display or business value. Never confuse Unicode normalization with accent stripping, lowercasing, transliteration, spoofing detection, or security validation.
