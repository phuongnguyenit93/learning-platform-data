# Strings That Look Identical Yet Have Different Unicode Code Point Sequences

## 1. Why is this a practical issue?

Two strings can **look identical or nearly identical on screen** while still containing **different Unicode code point sequences**. In Java, this directly affects:

- `String.equals(...)`, `compareTo(...)`, and `indexOf(...)` when comparing content.
- Searching, deduplicating, counting, sorting, and building keys for `Map`/`Set`.
- Validating usernames, identifiers, filenames, addresses, or user-entered data.
- Slicing strings, counting characters, and processing Vietnamese diacritics or emojis.

**What you see** is the result of the *text rendering* engine, fonts, and Unicode composition rules. **A `String` value** is a sequence of UTF-16 code units. Therefore, visual similarity does not automatically produce data equality.

After this lesson, you will be able to distinguish code points, UTF-16 code units, and grapheme clusters; detect differences using `codePoints()`; use the four Unicode normalization forms (`NFC`, `NFD`, `NFKC`, `NFKD`) via `java.text.Normalizer`; and understand the limits of normalization when dealing with different scripts, casing, or invisible characters.

## 2. Distinguishing the three concepts

**Unicode code point:** a numeric value such as `U+0061` (Latin `a`), `U+00E9` (`é`), `U+0301` (combining acute accent), or `U+1F600` (emoji 😀).

**UTF-16 code unit:** the 16-bit unit stored by Java's `char`. A code point in the Basic Multilingual Plane (BMP) typically takes one code unit; a supplementary code point like `U+1F600` needs two code units forming a *surrogate pair*.

**Grapheme cluster:** a unit of text that a user typically perceives as one character. A grapheme cluster can contain multiple code points, such as a base letter with combining marks or an emoji built from multiple code points and joiners.

| Visible text | Code point sequence | Code points | UTF-16 code units |
| --- | --- | ---: | ---: |
| `A` | `U+0041` | 1 | 1 |
| `é` (precomposed form) | `U+00E9` | 1 | 1 |
| `é` (`e` + combining acute accent) | `U+0065 U+0301` | 2 | 2 |
| `😀` | `U+1F600` | 1 | 2 |

**Note on reading the table:** `é` in the second row and the sequence `e` + `U+0301` in the third row usually render almost identically. Exact rendering depends on fonts, text-shaping software, and environment.

In Java:

~~~java
String composed = "caf\u00E9";  // café: precomposed character é U+00E9
String decomposed = "cafe\u0301"; // cafe + combining acute accent U+0301

System.out.println(composed.length());  // 4 UTF-16 code units
System.out.println(decomposed.length()); // 5 UTF-16 code units
System.out.println(composed.equals(decomposed)); // false
~~~

The two strings look nearly the same visually yet have different data sequences. `String.length()` and `equals` are working strictly according to the API contract.

## 3. Different code point sequences, same appearance: the `café` example

There are two common representations of the letter `é`:

1. **Precomposed:** one code point `U+00E9`, Unicode name *LATIN SMALL LETTER E WITH ACUTE*.
2. **Decomposed:** code point `U+0065` (*LATIN SMALL LETTER E*) followed by `U+0301` (*COMBINING ACUTE ACCENT*).

Correspondingly:

~~~text
Form 1: "café"
U+0063 U+0061 U+0066 U+00E9

Form 2: "cafe" + U+0301
U+0063 U+0061 U+0066 U+0065 U+0301
~~~

Both can render as `café`. However:

~~~java
String a = "caf\u00E9";
String b = "cafe\u0301";

System.out.println(a.equals(b));    // false
System.out.println(a.indexOf(b));   // -1
System.out.println(a.length());     // 4
System.out.println(b.length());     // 5
~~~

This is a **canonical representation** difference, which Unicode normalization can resolve. Do not conclude that one side is "invalid Unicode": both are valid sequences allowed by Unicode. If your application wants to treat them as equal, define a **canonical normalization** policy before comparing.

### Does writing `\uXXXX` in source code matter?

In a `.java` file, `\u00E9` is a **source-code** Unicode escape processed by the compiler before string-literal recognition. If the source file directly contains `é` and is read with the right encoding, both ways of writing it can result in the **same code point**.

The important distinction here is **`U+00E9` versus `U+0065 U+0301`**, not "using an escape versus typing the character directly." Likewise, a string received from a file, HTTP, or database can carry a different normalization form that is invisible to the naked eye.

## 4. `String.equals` compares values, not visual appearance

`String.equals(Object)` returns `true` when strings contain the same **sequence of UTF-16 code units**; it does not automatically:

- Normalize Unicode according to NFC/NFD/NFKC/NFKD.
- Ignore uppercase or lowercase.
- Strip Vietnamese diacritics.
- Remove zero-width characters or variation selectors.
- Recognize two visually similar glyphs belonging to different scripts.
- Use language-specific matching or locale settings.

Example:

~~~java
String first = "caf\u00E9";
String second = "cafe\u0301";

boolean equalRaw = first.equals(second); // false
~~~

`==` tests **reference identity** and is even less appropriate for comparing content. Switching `==` to `equals` only solves **identity vs. value**; canonical equivalence still requires a normalization step per application policy.

For `HashMap` and `HashSet`, `String.hashCode()` is also computed from the string's code unit values. Two representations of `café` can become **two separate keys** if not normalized before insertion into data structures.

## 5. Using normalization to determine whether two sequences are equivalent

When two strings look alike yet `equals` returns `false`, try normalizing **both sides** to the same form:

```java
String a = "caf\u00E9";
String b = "cafe\u0301";
System.out.println(a.equals(b)); // false
System.out.println(java.text.Normalizer.normalize(a, java.text.Normalizer.Form.NFC)
        .equals(java.text.Normalizer.normalize(b, java.text.Normalizer.Form.NFC))); // true
```

`NFC/NFD` handle **canonical equivalence** (e.g., `é` and `e + ◌́`), while `NFKC/NFKD` also consider **compatibility equivalence** (e.g., `ﬃ` and `ffi`). This lesson focuses on **diagnosing differences**; the `Normalizer` lesson covers the four forms and form-selection policies in depth.

If two strings **still differ** after NFKC, they are not necessarily invalid Unicode: Latin `a` (`U+0061`) and Cyrillic `а` (`U+0430`) look alike yet have different code points. Normalization is not a detector for all confusables; you must inspect code points, scripts, and comparison goals.

## 6. Complete Java 17+ example: printing code points and testing cases

Create **`UnicodeLookalikeDemo.java`** with the following content:

~~~java
import java.text.Normalizer;
import java.util.Locale;
import java.util.stream.Collectors;

public class UnicodeLookalikeDemo {
    private static String points(String s) {
        return s.codePoints()
                .mapToObj(cp -> String.format("U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    public static void main(String[] args) {
        String composed = "caf\u00E9";
        String decomposed = "cafe\u0301";

        System.out.println("composed=" + points(composed));
        System.out.println("decomposed=" + points(decomposed));
        System.out.println("rawEquals=" + composed.equals(decomposed));
        System.out.println("rawLengths=" + composed.length() + "/" + decomposed.length());
        System.out.println("codePoints=" + composed.codePointCount(0, composed.length())
                + "/" + decomposed.codePointCount(0, decomposed.length()));

        String nfc1 = Normalizer.normalize(composed, Normalizer.Form.NFC);
        String nfc2 = Normalizer.normalize(decomposed, Normalizer.Form.NFC);
        System.out.println("nfcEquals=" + nfc1.equals(nfc2));
        System.out.println("nfcPoints=" + points(nfc2));
        System.out.println("nfdEquals="
                + Normalizer.normalize(composed, Normalizer.Form.NFD)
                .equals(Normalizer.normalize(decomposed, Normalizer.Form.NFD)));

        String ligature = "\uFB03";
        System.out.println("ligature=" + points(ligature));
        System.out.println("nfcLigatureEqualsFfi="
                + Normalizer.normalize(ligature, Normalizer.Form.NFC).equals("ffi"));
        System.out.println("nfkcLigatureEqualsFfi="
                + Normalizer.normalize(ligature, Normalizer.Form.NFKC).equals("ffi"));
        System.out.println("fullwidthNfkc=" + points(
                Normalizer.normalize("\uFF21", Normalizer.Form.NFKC)));

        String latinA = "a";
        String cyrillicA = "\u0430";
        System.out.println("lookalikeRawEqual=" + latinA.equals(cyrillicA));
        System.out.println("lookalikeNfkcEqual="
                + Normalizer.normalize(latinA, Normalizer.Form.NFKC)
                .equals(Normalizer.normalize(cyrillicA, Normalizer.Form.NFKC)));
        System.out.println("lookalikePoints=" + points(latinA) + " / " + points(cyrillicA));

        String upperDottedI = "\u0130";
        System.out.println("rootLower=" + points(upperDottedI.toLowerCase(Locale.ROOT)));
        System.out.println("turkishLower=" + points(upperDottedI.toLowerCase(
                Locale.forLanguageTag("tr"))));
        System.out.println("caseStillDifferent=" + "Java".equals("java"));
    }
}
~~~

Run:

~~~bash
javac --release 17 -encoding UTF-8 UnicodeLookalikeDemo.java
java UnicodeLookalikeDemo
~~~

Verified `stdout` output from the Java compiler and JVM:

~~~text
composed=U+0063 U+0061 U+0066 U+00E9
decomposed=U+0063 U+0061 U+0066 U+0065 U+0301
rawEquals=false
rawLengths=4/5
codePoints=4/5
nfcEquals=true
nfcPoints=U+0063 U+0061 U+0066 U+00E9
nfdEquals=true
ligature=U+FB03
nfcLigatureEqualsFfi=false
nfkcLigatureEqualsFfi=true
fullwidthNfkc=U+0041
lookalikeRawEqual=false
lookalikeNfkcEqual=false
lookalikePoints=U+0061 / U+0430
rootLower=U+0069 U+0307
turkishLower=U+0069
caseStillDifferent=false
~~~

**Meaning of the result groups:**

1. `composed` and `decomposed` differ in length and code point sequence, so `equals` returns `false`. After normalizing both to `NFC` or `NFD`, they are equal.
2. `NFC` does not turn the ligature `ﬃ` into three `ffi` letters, whereas `NFKC` does; `NFKC` also converts fullwidth `Ａ` into `A`.
3. Latin `a` (`U+0061`) and Cyrillic `а` (`U+0430`) can look alike, yet `NFKC` still does **not** turn them into the same code point.
4. Changing case is a **different transformation from normalization**. Lowercasing `İ` (Latin Capital I With Dot Above, `U+0130`) with `Locale.ROOT` produces two code points `U+0069 U+0307`; with the Turkish locale (`tr`), it produces one code point `U+0069`.

The `points` helper uses `String.codePoints()`, so it can print supplementary code points like `U+1F600` in full rather than splitting them into two surrogate `char`s as `charAt` looping would.

## 7. Another category: characters from different scripts that look alike

Not every visually similar pair is canonically or compatibility equivalent. For example:

| Character | Script | Code point |
| --- | --- | --- |
| `a` | Latin small letter a | `U+0061` |
| `а` | Cyrillic small letter a | `U+0430` |
| `A` | Latin capital letter A | `U+0041` |
| `Α` | Greek capital letter Alpha | `U+0391` |
| `О` | Cyrillic capital letter O | `U+041E` |
| `O` | Latin capital letter O | `U+004F` |

Depending on the font, those characters can have similar glyphs. However, they are **distinct code points** in different scripts. `Normalizer.normalize(..., NFKC)` is not designed to resolve the general problem of lookalike characters (*confusable characters*, *homoglyphs*).

Example:

~~~java
String latin = "a";          // U+0061
String cyrillic = "\u0430"; // U+0430

System.out.println(latin.equals(cyrillic)); // false
System.out.println(
    Normalizer.normalize(latin, Normalizer.Form.NFKC).equals(
        Normalizer.normalize(cyrillic, Normalizer.Form.NFKC)
    )
); // false
~~~

This is a risk when a system allows creating usernames/identifiers that "look identical." Two accounts with nearly indistinguishable display names can still have different Unicode sequences.

**Separate the goals:** canonical normalization unifies equivalent spellings of *the same text*. Anti-spoofing policies for identifiers additionally require script rules, confusable checks, and confusable-handling procedures per standards such as Unicode Technical Standard #39. Do not rely on `NFKC` alone as a complete "anti-spoofing filter."

## 8. Combining marks, zero-width characters, variation selectors, and emojis

Two strings do not differ only by precomposed marks or letters from different scripts. **Code points that affect rendering** can also cause confusion:

- **Combining mark:** a combining diacritic such as `U+0301` attaches to the preceding letter to form one grapheme cluster. The string has multiple code points yet may appear as a single accented letter.
- **Zero-width joiner (ZWJ, `U+200D`):** participates in certain emoji sequences and character-joining rules; it may not render as an independent visible glyph.
- **Variation selector:** for example, `U+FE0F` can request emoji-style presentation on supported sequences. Its presence or absence changes the code point sequence even if rendering software makes them look similar.
- **Invisible control or formatting characters:** can affect spacing, visual ordering, text direction, or matching, depending on the character and environment.

For instance, these two strings have different values:

~~~java
String plain = "\u2764";        // U+2764, HEAVY BLACK HEART
String emojiStyle = "\u2764\uFE0F"; // U+2764 + VARIATION SELECTOR-16

System.out.println(plain.equals(emojiStyle)); // false
System.out.println(plain.codePointCount(0, plain.length())); // 1
System.out.println(emojiStyle.codePointCount(0, emojiStyle.length())); // 2
~~~

Depending on the font and platform, both may render as hearts or have two distinct styles. You cannot evaluate a `String` from a screenshot alone.

`NFC`/`NFD` normalizations are not meant to arbitrarily strip ZWJ, variation selectors, or other formatting characters. **Do not blindly delete invisible code points** just because they are hard to see: many of them serve legitimate linguistic and emoji roles. Define proper processing rules for each field type.

## 9. Casing and locale are separate concerns from normalization

Within the **case and normalization** topic, distinguish at least three comparison modes:

1. **Code-unit exact equality:** `a.equals(b)`; no normalization, no case folding.
2. **Canonical-normalized equality:** `Normalizer.normalize(a, NFC).equals(Normalizer.normalize(b, NFC))`; still case-sensitive.
3. **Case-insensitive or language-aware comparison:** requires choosing the right API and locale, such as `equalsIgnoreCase` for simple problems or a language-configured `Collator`, combined with normalization when the contract requires it.

The `İ` (`U+0130`) example in section 6 shows that a lowercasing operation can return **one or multiple code points** and depends on locale. In some languages, choosing the wrong locale distorts meaning; for language-independent technical keys, `Locale.ROOT` can be preferable to the host locale, yet it **does not automatically satisfy all Unicode case-folding requirements**.

Do not assume `equalsIgnoreCase` always considers all linguistically or canonically equivalent strings equal. Similarly, `Collator` serves **locale-aware text comparison** and has decomposition/strength settings; picking the right tool depends on the goal, not as an unconditional drop-in replacement for `equals`.

Note: case conversion or normalization **can change length and UTF-16 indices**. If you found a position in the string before transforming it, do not apply that index directly to the transformed string.

## 10. A reliable data comparison workflow

Suppose business rules define two strings as equal if they are **canonically equivalent**, regardless of whether they were entered in precomposed or decomposed form. You can write:

~~~java
import java.text.Normalizer;
import java.util.Objects;

public class CanonicalComparison {
    static String nfc(String value) {
        return Normalizer.normalize(
                Objects.requireNonNull(value, "value"),
                Normalizer.Form.NFC);
    }

    static boolean sameCanonicalText(String left, String right) {
        return nfc(left).equals(nfc(right));
    }

    public static void main(String[] args) {
        System.out.println(sameCanonicalText("caf\u00E9", "cafe\u0301"));
    }
}
~~~

When compiled and run, this class prints `true`. Null handling is defined explicitly with `Objects.requireNonNull`; if business logic treats `null` as a special value, adjust the contract accordingly.

When using strings as **lookup keys**:

~~~java
// Illustrative snippet: map is an already-created Map<String, Integer>.
map.put(nfc(userInput), 1);
Integer value = map.get(nfc(query));
~~~

This is an illustrative snippet, not standalone runnable code. Normalize consistently **at write time and read time** so canonically identical text maps to the same key. If you also keep the original form for display, separate the **original value** from the **normalized lookup key**. This preserves how the user typed the text while still enabling deterministic matching.

### Normalization policy questions to answer explicitly

| Data type | Approach to consider |
| --- | --- |
| Free-form display content | Preserve original; normalize only if there is a technical/business reason |
| Product names, search keywords | Specify normalization, casing, and diacritic rules by language; build search index on the same policy |
| Usernames/identifiers | Define allowed character set, normalization, case rules, confusable checks, and uniqueness; never rely on visual appearance alone |
| Data with stylized letters or academic symbols | Be cautious with `NFKC`/`NFKD` as they can erase compatibility distinctions |
| Multilingual text | Pick language-appropriate policies; do not unify all casing and collation rules |

A straightforward strategy for canonical equality is choosing `NFC` and applying it consistently. However, **there is no single optimal normalization form for every system**: intended use, traceability to original input, and identifier policies determine the choice.

## 11. Inspecting code point sequences when two strings "look identical"

When a comparison bug occurs, do not start by switching fonts and guessing. Inspect **length, code points, and normalization form**:

~~~java
String text = "cafe\u0301";

System.out.println(text.length());
System.out.println(text.codePointCount(0, text.length()));
text.codePoints().forEach(cp -> System.out.printf("U+%04X%n", cp));
~~~

Output:

~~~text
5
5
U+0063
U+0061
U+0066
U+0065
U+0301
~~~

Each supplementary code point such as `U+1F600` appears as **one** `int` value when using `codePoints()`; if iterated with `charAt`, it appears as two surrogate `char`s. Thus `codePoints()` is far more useful when diagnosing Unicode issues at the code point level.

A practical debugging workflow:

1. Print code points in `U+XXXX` format for **both** strings.
2. Compare `length()`, `codePointCount(...)`, and `equals(...)` to see where they differ.
3. Try normalizing both to `NFC` to check whether they share a canonical form; if investigating compatibility, try `NFKC` **for diagnostic purposes only**, avoiding imposing new transformation policies onto production data.
4. If they still differ, check scripts, combining marks, variation selectors, ZWJ, and formatting characters; for identifiers, apply confusable checks per your specification.
5. Clarify the desired application rule: *byte/code-unit identical*, *canonically equivalent*, *case-insensitive*, *locale-equivalent*, or *visually similar*. These are distinct requirements.

Avoid logging code points of sensitive data in production without proper controls; when debugging, limit logged data to what is actually needed.

## 12. Common mistakes

1. **Assuming two visually identical characters make `equals` return true.** `equals` compares data, not glyph appearance.
2. **Assuming one of two different `café` representations is invalid Unicode.** Both precomposed and base-letter + combining-mark forms are valid; canonical equality is a business decision.
3. **Confusing `String.length()` with visible character count.** It counts UTF-16 code units; `codePointCount` still does not count grapheme clusters.
4. **Using `==` to compare content.** `==` checks reference identity only; `equals` compares values, after normalization if needed.
5. **Normalizing one side without normalizing the other.** When canonical equality is the goal, apply the same `Normalizer.Form` to both sides.
6. **Using NFKC as a cure-all for lookalike strings.** NFKC does not merge visually similar Latin/Cyrillic/Greek letters, and it can erase meaningful compatibility distinctions.
7. **Ignoring locale during case conversion.** The character `İ` shows that lowercasing can produce different results by locale and change the code point count.
8. **Arbitrarily stripping combining marks, zero-width characters, or variation selectors.** This can corrupt valid content, especially in Vietnamese, multilingual text, and emojis.
9. **Reusing old indices after normalization.** Because normalization can change code unit length, `substring`/`charAt` positions from before normalization are not always valid afterward.
10. **Normalizing only at query time and not when storing keys.** A map or search index will fail to match if both sides use different representation policies.
11. **Building an anti-spoofing mechanism out of a few character substitutions.** Confusable handling is a specialized problem requiring proper identifier policies and tooling.

## 13. Self-check exercises

**Question 1.** Why does `"caf\u00E9".equals("cafe\u0301")` return `false`?

**Answer:** The left side has `U+00E9` while the right side has `U+0065 U+0301`; the two code point and UTF-16 code unit sequences differ despite being canonically equivalent visually.

**Question 2.** How do you transform them to test canonical equivalence?

**Answer:** Normalize **both** to the same form (`NFC` or `NFD`) and then call `equals`.

**Question 3.** Does `NFC` convert `ﬃ` to `ffi`? What about `NFKC`?

**Answer:** `NFC` does not; `NFKC` performs compatibility decomposition and converts the ligature `U+FB03` into the three letters `ffi`.

**Question 4.** Why do `Normalizer.normalize("a", NFKC)` and `Normalizer.normalize("\u0430", NFKC)` still differ?

**Answer:** They belong to different scripts: Latin `U+0061` and Cyrillic `U+0430`. Visual similarity does not imply Unicode normalization equivalence.

**Question 5.** Does `String.length()` measure the number of grapheme clusters?

**Answer:** No. It counts UTF-16 code units. `codePointCount` counts code points, which still is not grapheme clusters.

**Question 6.** Can `NFKC` be used by default for all user input?

**Answer:** No. NFKC can merge meaningful compatibility distinctions; choose the form according to the field's purpose.

**Question 7.** Why keep the original string when building a normalized search key?

**Answer:** The normalized key enables consistent searching, while the original preserves what the user actually entered for display and auditing when needed. These two roles should not be conflated.

## 14. References

- [Java SE 17 — `java.text.Normalizer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html): the four normalization forms and how to use them in Java.
- [Java SE 17 — `String`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): `equals`, `length`, `codePoints`, `codePointCount`, and case conversion.
- [Unicode Standard Annex #15 — Unicode Normalization Forms](https://www.unicode.org/reports/tr15/): definitions of NFC, NFD, NFKC, and NFKD.
- [Unicode Standard Annex #29 — Unicode Text Segmentation](https://www.unicode.org/reports/tr29/): grapheme clusters and text segmentation.
- [Unicode Technical Standard #39 — Unicode Security Mechanisms](https://www.unicode.org/reports/tr39/): identifying confusable characters in identifiers.

**Key takeaway:** "Looking alike" is a rendering property, whereas a `String` holds a **specific sequence of UTF-16 code units**. Use `codePoints()` to inspect the real data; use `Normalizer` when canonical or compatibility normalization is needed under a **defined policy**; and handle cross-script lookalikes, Unicode casing rules, and complex grapheme clusters separately.
