# Testing Combining Marks, Emoji, and Case Conversions in Java

A system can handle `"Hello"` cleanly yet fail on accented Vietnamese, emoji, the Turkish letter `I`, or the German letter `ß`. Unicode bugs usually stem not from **Java lacking Unicode support**, but from the application picking the wrong counting unit or applying the wrong transformation rule: slicing by individual `char`, assuming `String.length()` equals the visible character count, lowercasing with the default locale, or comparing visually identical strings with `equals` and assuming they must match at the encoding level.

This Knowledge lesson belongs to **Testing and Pitfalls** in the **Java core - localization** module, focusing on designing tests for **combining marks, emoji, and case conversions** using **Java 17+**. The examples run standalone on the JDK with assertions for deterministic outcomes; places that depend on Unicode/JDK version, fonts, or locales are noted explicitly rather than assuming every machine renders and segments identically.

**Core principle:** distinguish at least five layers: UTF-8 bytes, UTF-16 code units (`char`), Unicode code points, *extended grapheme clusters* (user-perceived character units), and **domain-specific** comparison/transformation semantics. Every test must state which layer it is checking.

## 1. One Visible Character Is Not Necessarily One Java char

Java `String` exposes APIs built on **UTF-16 code units**. `String.length()` returns the count of `char` code units, not Unicode code points, and certainly not user-perceived "characters."

| Sample text | Unicode composition | `String.length()` | Code point count | Notes |
| --- | --- | ---: | ---: | --- |
| `A` | U+0041 | 1 | 1 | Plain ASCII |
| Precomposed `é` | U+00E9 | 1 | 1 | Precomposed |
| `e◌́` (e + combining acute accent) | U+0065, U+0301 | 2 | 2 | Typically renders close to a single `é` |
| `😀` | U+1F600 | 2 | 1 | Supplementary emoji outside BMP, surrogate pair |
| `✈️` | U+2708, U+FE0F | 2 | 2 | Variation selector can request emoji presentation |
| `👩‍💻` | U+1F469, U+200D, U+1F4BB | 5 | 3 | Emoji ZWJ sequence |
| `🇻🇳` | U+1F1FB, U+1F1F3 | 4 | 2 | Regional indicator pair |

The **grapheme cluster** length is typically 1 for each sample in the table, yet the Unicode segmentation standard and the runtime's Unicode data version are what determine it—not the appearance of a single glyph on screen. Fonts or platforms may render a ZWJ emoji as one combined image or separate images while the underlying code-point sequence stays identical.

**Never use `substring(i, i + 1)` to extract a visible character.** Half of a surrogate pair or an isolated combining mark can produce broken fragments that cannot even be encoded as valid Unicode scalar values.

## 2. Precomposed vs. Combining Marks: Two Strings That Look Alike

An accented letter can be represented in multiple canonically equivalent ways:

- *Precomposed*: `"\u00E9"` consisting of U+00E9.
- *Decomposed*: `"e\u0301"` consisting of U+0065 and combining mark U+0301.

Many fonts render both nearly identically, yet:

```text
String.equals(...)             -> false
String.length()                -> 1 and 2
codePointCount(...)            -> 1 and 2
UTF-8 bytes                    -> C3 A9 and 65 CC 81
Normalizer.normalize(..., NFC) -> equal strings
```

This is especially important for Vietnamese text, where vowels can combine with multiple diacritics and tone marks. Do not infer from "looks the same to the user" that data is **byte-for-byte** identical, and do not blindly rewrite every string if it is a token, signature, or byte-preserved datum.

### Canonical vs. Compatibility Normalization

`java.text.Normalizer` supports:

| Form | Meaning |
| --- | --- |
| `NFC` | Canonical decomposition followed by composition |
| `NFD` | Canonical decomposition |
| `NFKC` | Compatibility decomposition followed by composition |
| `NFKD` | Compatibility decomposition |

`NFC`/`NFD` handle **canonical equivalence**; `NFKC`/`NFKD` also fold compatibility characters such as fullwidth letters or specially styled symbols. Consequently, `NFKC` **can discard meaningful distinctions** in certain data fields; never use it as a default "sanitizer" on personal names, passwords, or legal data.

### Example 1 — CanonicalNormalizationDemo.java

```java
import java.text.Normalizer;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public class CanonicalNormalizationDemo {
    public static void main(String[] args) {
        String composed = "\u00E9";
        String decomposed = "e\u0301";

        System.out.println("Raw equals: "
                + composed.equals(decomposed));
        System.out.println("Lengths: "
                + composed.length() + "/" + decomposed.length());
        System.out.println("UTF-8 bytes equal: "
                + Arrays.equals(
                        composed.getBytes(StandardCharsets.UTF_8),
                        decomposed.getBytes(StandardCharsets.UTF_8)));

        String a = Normalizer.normalize(
                composed, Normalizer.Form.NFC);
        String b = Normalizer.normalize(
                decomposed, Normalizer.Form.NFC);

        System.out.println("NFC equals: " + a.equals(b));
        System.out.println("NFC idempotent: "
                + a.equals(Normalizer.normalize(
                        a, Normalizer.Form.NFC)));
        System.out.println("NFKC fullwidth A: "
                + Normalizer.normalize(
                        "\uFF21", Normalizer.Form.NFKC)
                        .equals("A"));
    }
}
```

```bash
javac -encoding UTF-8 CanonicalNormalizationDemo.java
java CanonicalNormalizationDemo
```

Stdout:

```text
Raw equals: false
Lengths: 1/2
UTF-8 bytes equal: false
NFC equals: true
NFC idempotent: true
NFKC fullwidth A: true
```

**Critical testing note:** Unicode normalization must be applied **according to each field's contract**. For searchable text, you can build a separate canonical index; for an access token or byte-level signature, **never** normalize silently because doing so can invalidate the value being verified.

## 3. String.length, codePointCount, and offsetByCodePoints

A valid surrogate pair represents one code point outside the Basic Multilingual Plane. For example, `"A😀B"`:

```text
Visible characters: A       😀       B
UTF-16 positions:   0  1  2  3  4
Code units:         A  high low B
Code-point index:   0     1     2
```

Offset `2` sits between the emoji's high surrogate and low surrogate, **not a valid split point for the emoji**. Advancing two code points from the start lands at UTF-16 offset **3**, not 2.

Key APIs:

- `length()`: count of **UTF-16 code units**.
- `codePointCount(begin, end)`: number of code points Java counts within the UTF-16 range, counting unpaired surrogates individually if input is malformed.
- `offsetByCodePoints(index, count)`: steps by code points and returns a **UTF-16 offset**.
- `codePoints()`: streams code point values from the string.
- `charAt(i)`: one UTF-16 code unit, which may be **half** of a surrogate pair.
- `substring(begin, end)`: slices by **UTF-16 offsets** over the half-open range `[begin,end)`.

### Example 2 — CodePointBoundaryDemo.java

```java
import java.nio.charset.StandardCharsets;

public class CodePointBoundaryDemo {
    public static void main(String[] args) {
        String text = "A\uD83D\uDE00B";

        System.out.println("UTF-16 length: " + text.length());
        System.out.println("Code points: "
                + text.codePointCount(0, text.length()));
        System.out.println("UTF-8 byte length: "
                + text.getBytes(StandardCharsets.UTF_8).length);
        System.out.println("After 2 code points: "
                + text.offsetByCodePoints(0, 2));
        System.out.println("High surrogate: "
                + Character.isHighSurrogate(text.charAt(1)));
        System.out.println("Low surrogate: "
                + Character.isLowSurrogate(text.charAt(2)));
        System.out.println("Emoji slice length: "
                + text.substring(1, 3).length());
    }
}
```

```bash
javac -encoding UTF-8 CodePointBoundaryDemo.java
java CodePointBoundaryDemo
```

Stdout:

```text
UTF-16 length: 4
Code points: 3
UTF-8 byte length: 6
After 2 code points: 3
High surrogate: true
Low surrogate: true
Emoji slice length: 2
```

The `UTF-8 byte length: 6` comes from ASCII `A` (1 byte), emoji (4 bytes), ASCII `B` (1 byte). Byte length depends on the encoding; **never use `String.length()` to set HTTP byte lengths**.

## 4. Grapheme Clusters: The Unit Users Expect to Select, Delete, or Navigate

Two Unicode code points can form a single character cluster. `"e\u0301"` has base `e` and combining acute accent, forming one **extended grapheme cluster**. A ZWJ emoji or a flag made of two regional indicators is also normally one cluster.

Java provides at least two relevant tools:

- `BreakIterator.getCharacterInstance(locale)` to find character boundaries for text tasks; exact behavior and complex emoji support depend on the Unicode/JDK/provider version.
- `java.util.regex.Pattern` with `\\X` (supported in Java 17) to match extended grapheme clusters per the runtime's Unicode rules.

**Do not equate "extended grapheme cluster" with every glyph drawn by a renderer.** Some fonts combine multiple code points into one ligature/glyph, or split emoji into separate pictures depending on the platform. Segmentation is a text algorithm, whereas rendering belongs to the font/shaping/rendering engine.

### Example 3 — GraphemeBoundaryDemo.java

```java
import java.text.BreakIterator;
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class GraphemeBoundaryDemo {
    private static int countGraphemes(String text) {
        Matcher matcher = Pattern.compile("\\X").matcher(text);
        int count = 0;
        while (matcher.find()) {
            count++;
        }
        return count;
    }

    public static void main(String[] args) {
        String text = "e\u0301";

        BreakIterator it =
                BreakIterator.getCharacterInstance(Locale.ROOT);
        it.setText(text);

        System.out.println("UTF-16 length: " + text.length());
        System.out.println("Code points: "
                + text.codePointCount(0, text.length()));
        System.out.println("Regex clusters: "
                + countGraphemes(text));
        System.out.println("Boundary at 1: "
                + it.isBoundary(1));
        System.out.println("Following 0: " + it.following(0));
        System.out.println("Preceding 2: " + it.preceding(2));
    }
}
```

```bash
javac -encoding UTF-8 GraphemeBoundaryDemo.java
java GraphemeBoundaryDemo
```

Stdout for the basic combining-mark example on Java 17:

```text
UTF-16 length: 2
Code points: 2
Regex clusters: 1
Boundary at 1: false
Following 0: 2
Preceding 2: 0
```

If an application must handle all modern emoji, build a **test corpus versioned by Unicode version**; do not run a single `e + accent` example and assume the runtime supports every sequence. When strict consistency is needed across clients and servers running different runtimes, consider a segmentation library with pinned Unicode data.

## 5. Emoji Are Often Multi-Code-Point Sequences

An emoji can be:

- **A single supplementary code point:** `😀` (U+1F600; UTF-16 length 2).
- **Emoji + variation selector:** `✈️` = U+2708 + U+FE0F.
- **Emoji + skin tone modifier:** some emoji add modifiers in U+1F3FB–U+1F3FF.
- **ZWJ sequence:** `👩‍💻` = WOMAN + ZERO WIDTH JOINER + PERSONAL COMPUTER.
- **Flag sequence:** `🇻🇳` = pair of regional indicator letters.
- **Keycap sequence:** digit, variation selector, and combining enclosing keycap.

There is no rule that "one emoji = two `char`s." Only single supplementary emoji code points occupy two UTF-16 units; emoji sequences can be much longer.

### Example 4 — EmojiSequenceDemo.java

```java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class EmojiSequenceDemo {
    private static int clusters(String text) {
        Matcher m = Pattern.compile("\\X").matcher(text);
        int n = 0;
        while (m.find()) {
            n++;
        }
        return n;
    }

    public static void main(String[] args) {
        String grin = "\uD83D\uDE00";
        String airplane = "\u2708\uFE0F";
        String developer = "\uD83D\uDC69\u200D\uD83D\uDCBB";

        System.out.println("Grin units/codepoints: "
                + grin.length() + "/"
                + grin.codePointCount(0, grin.length()));
        System.out.println("Airplane units/codepoints: "
                + airplane.length() + "/"
                + airplane.codePointCount(0, airplane.length()));
        System.out.println("Developer units/codepoints: "
                + developer.length() + "/"
                + developer.codePointCount(0, developer.length()));
        System.out.println("Grin clusters: " + clusters(grin));
        System.out.println("Airplane clusters: "
                + clusters(airplane));
        // Compare result against the runtime's Unicode version.
        System.out.println("Developer clusters: "
                + clusters(developer));
    }
}
```

```bash
javac -encoding UTF-8 EmojiSequenceDemo.java
java EmojiSequenceDemo
```

On Java 17 with a `\\X` implementation supporting the sample ZWJ sequence, output is typically:

```text
Grin units/codepoints: 2/1
Airplane units/codepoints: 2/2
Developer units/codepoints: 5/3
Grin clusters: 1
Airplane clusters: 1
Developer clusters: 1
```

The **units/codepoints** values are independent of the renderer. `Developer clusters` is computed by the Unicode grapheme algorithm implemented in the **active JDK**; when testing across JDK/Unicode versions, verify on the target runtime rather than freezing one snapshot for all future releases. An emoji may render as separate symbols on an older terminal, which does not prove the string is corrupted.

### Why Counting Code Points Alone Is Still Insufficient

`offsetByCodePoints` avoids splitting surrogate pairs, yet it **can still split between a base character and a combining mark**, or between code points of a ZWJ emoji sequence. When implementing a "delete one character" action, caret/selection movement, or user-visible character limits, verify explicitly whether you need **grapheme segmentation** or code-point counting.

## 6. Vietnamese Combining Marks: Testing Multiple Orders and Representations

Many Vietnamese letters combine a base letter, vowel/consonant diacritics, and a tone mark. Unicode defines **canonical combining classes** that normalize the relative order of certain combining marks. However, not every permutation of code points is equivalent; conclude equivalence only when **`Normalizer`** or Unicode data confirms it.

Your test suite should include:

1. Canonically equivalent precomposed and decomposed letters.
2. Strings with multiple combining marks in differing order where canonically equivalent.
3. A leading combining mark at the start of a string (with no base): UI input policy must be explicit.
4. Accented characters at segment starts/ends and adjacent to emoji.
5. NFC/NFD round-trip under canonical equivalence, plus idempotence.
6. Keys/identifiers remaining unaltered outside policy.
7. UTF-8 round-trip checks on well-formed normalized strings.
8. Inspecting code points and bytes alongside screenshots when investigating bugs.

### Normalization Property Test Pattern

For every valid Unicode string `s` in the application's domain:

```text
NFC(NFC(s)) == NFC(s)
NFD(NFD(s)) == NFD(s)
NFC(s) canonically equivalent s
NFD(s) canonically equivalent s
```

The first two lines verify **idempotence**. The last two do not mean `NFC(s).equals(s)` always holds; on the contrary, normalization intentionally alters the representation while preserving **canonical equivalence**. For strings containing invalid lone surrogates, test input and encoding policies separately.

## 7. Case Conversions Can Change String Length

A common mistake is treating `toUpperCase`/`toLowerCase` as a 1:1 character replacement. In Unicode, case mapping can **change both code-point count and UTF-16 unit count**.

Examples:

- `"Straße"` transformed with `toUpperCase(Locale.ROOT)` becomes `"STRASSE"`; `ß` maps to `SS` in `String` uppercasing.
- `"\u0130"` (LATIN CAPITAL LETTER I WITH DOT ABOVE) lowercased with `Locale.ROOT` becomes `i` + combining dot U+0307.
- In Turkish, uppercase dotless-less `I` lowercases to dotless `ı`, distinct from ASCII `i`.
- Certain Greek letters have word-position-dependent casing; never implement linguistic casing with `Character.toLowerCase(char)` instead of `String.toLowerCase(Locale)`.

**`Character.toUpperCase(int codePoint)`** returns a single code point and cannot represent multi-character expansions; `String.toUpperCase(Locale)` supports context- and string-level mappings. Even so, `String.toLowerCase(Locale.ROOT)` is **not complete Unicode full case folding** for every matching problem.

### Example 5 — CaseExpansionDemo.java

```java
import java.util.Locale;

public class CaseExpansionDemo {
    public static void main(String[] args) {
        String german = "Stra\u00DFe";
        String upper = german.toUpperCase(Locale.ROOT);
        String dottedI = "\u0130";
        String rootLower = dottedI.toLowerCase(Locale.ROOT);

        System.out.println("German upper: " + upper);
        System.out.println("German length: "
                + german.length() + " -> " + upper.length());
        System.out.println("Ignore case equals: "
                + german.equalsIgnoreCase("STRASSE"));
        System.out.println("Uppercase equals: "
                + upper.equals("STRASSE"));
        System.out.println("Dotted I ROOT lower length: "
                + rootLower.length());
        System.out.println("Dotted I ROOT has combining dot: "
                + rootLower.equals("i\u0307"));
    }
}
```

```bash
javac -encoding UTF-8 CaseExpansionDemo.java
java CaseExpansionDemo
```

Stdout on Java 17:

```text
German upper: STRASSE
German length: 6 -> 7
Ignore case equals: false
Uppercase equals: true
Dotted I ROOT lower length: 2
Dotted I ROOT has combining dot: true
```

**Do not misinterpret this:** `"Straße".equalsIgnoreCase("STRASSE")` is `false`, whereas comparing the two strings after ROOT uppercasing is `true` here. **Do not conclude** that uppercasing then calling `equals` is standard Unicode full case folding. This is only a counterexample showing that not all case-insensitive APIs behave equivalently.

## 8. Default Locale Makes Tests Flaky: Turkish I

Parameterless `String.toLowerCase()` uses `Locale.getDefault()`. Thus `"TITLE"` can produce different keys under default locale `en-US` vs. `tr-TR`.

Recommended policy:

- For **application-defined ASCII machine keys**, validate the character set and case-convert with `Locale.ROOT` if required by contract.
- For **locale-sensitive display text**, pass the user's actual `Locale`; never force `ROOT` when Turkish or another language's orthography is required.
- For **passwords, tokens, and signatures**, never alter case outside the authentication contract.
- For **Unicode usernames**, do not treat ROOT lowercasing as a complete security profile; specify normalization, case folding, confusables, uniqueness, and Unicode version.
- Never mutate `Locale.setDefault` between concurrent tests or HTTP requests.

### Example 6 — TurkishCaseDemo.java

```java
import java.util.Locale;

public class TurkishCaseDemo {
    public static void main(String[] args) {
        Locale tr = Locale.forLanguageTag("tr-TR");
        String source = "TITLE";

        String root = source.toLowerCase(Locale.ROOT);
        String turkish = source.toLowerCase(tr);

        System.out.println("ROOT lower: " + root);
        System.out.println("Turkish equals title: "
                + turkish.equals("title"));
        System.out.println("Turkish has dotless i: "
                + turkish.contains("\u0131"));
        System.out.println("Different keys: "
                + !root.equals(turkish));

        System.out.println("Capital dotted I -> Turkish i: "
                + "\u0130".toLowerCase(tr).equals("i"));
    }
}
```

```bash
javac -encoding UTF-8 TurkishCaseDemo.java
java TurkishCaseDemo
```

Stdout:

```text
ROOT lower: title
Turkish equals title: false
Turkish has dotless i: true
Different keys: true
Capital dotted I -> Turkish i: true
```

These results do not depend on the **host machine's default locale** because the program passes locales explicitly. What to audit in application code is not merely whether `toLowerCase` is called, but **which locale is used, on which data field, and for what purpose**.

## 9. What equals, equalsIgnoreCase, Normalizer, and Collator Check

| Tool | Question answered | Should not replace |
| --- | --- | --- |
| `String.equals` | Do two UTF-16 sequences have identical values? | Canonical Unicode equivalence or linguistic comparison |
| `equalsIgnoreCase` | Case-insensitive per `String`'s rules | Locale-aware collation or Unicode full case folding |
| `Normalizer.normalize(..., NFC)` | Same canonical Unicode form for comparison/storage per policy? | Case conversion |
| `toLowerCase(Locale.ROOT)` | Lowercase independent of default locale | Full identifier/security profile |
| `Collator.getInstance(locale)` | Compare/sort text by language rules | Exact tokens, signatures, identifier keys |
| `Pattern.compile("\\X")` | Find grapheme clusters per runtime algorithm | Counting bytes/Unicode code points |
| `BreakIterator.getCharacterInstance` | Find text boundaries in JDK implementation | Specialized tokenizers or UI renderers |

**Separate four contracts:**

1. **Display:** preserve what the user typed (e.g., personal names), transforming case only when UI design calls for it.
2. **Search:** may be case-/diacritic-insensitive per locale and search engine; store the original separately.
3. **Identity:** canonical keys follow explicit rules and collision tests; never casually substitute JDK collation for username rules.
4. **Exact bytes/tokens:** apply no normalization or case conversion unless permitted by the protocol.

For instance, the same letter `é` may compare canonically equivalent after NFC while still differing in raw input bytes. A password should never be silently "repaired" just to pass string equality.

## 10. Regex with Unicode: Do Not Confuse \w, ., and \X

Regex patterns carry specific semantics:

- `.` normally matches a Unicode code point per Java regex rules (except line terminators depending on flags); it is **not guaranteed to match one grapheme cluster**. Use `\\X` when you specifically need extended grapheme cluster segments.
- `\\w` and character classes like `[A-Za-z]` mean different things. `[A-Za-z]` matches ASCII Latin only; `\\w` has its own default rules and expands when `UNICODE_CHARACTER_CLASS` is enabled. Never treat them as "all letters of all languages" without defining rules.
- `\\p{L}` matches Unicode **Letters** per runtime Unicode data, whereas combining marks belong to Mark categories; a decomposed accented name may require handling marks or normalizing beforehand per policy.
- `Pattern.CASE_INSENSITIVE` is not full locale-aware mapping; adding `UNICODE_CASE` enables Unicode-aware regex case folding, yet still does not replace an identity policy.
- `Pattern.CANON_EQ` supports canonical equivalence with its own cost and semantics; for large datasets or keys, consider explicit normalization and benchmark performance.

### Program 7 — RegexUnicodeDemo.java

```java
import java.util.regex.Pattern;

public class RegexUnicodeDemo {
    public static void main(String[] args) {
        String decomposed = "e\u0301";
        String emoji = "\uD83D\uDE00";

        System.out.println("ASCII-only letters match: "
                + Pattern.matches("[A-Za-z]+", decomposed));
        System.out.println("Unicode letter then mark: "
                + Pattern.matches("\\p{L}\\p{M}", decomposed));
        System.out.println("One grapheme cluster: "
                + Pattern.matches("\\X", decomposed));
        System.out.println("Emoji one grapheme: "
                + Pattern.matches("\\X", emoji));
    }
}
```

```bash
javac -encoding UTF-8 RegexUnicodeDemo.java
java RegexUnicodeDemo
```

Stdout:

```text
ASCII-only letters match: false
Unicode letter then mark: true
One grapheme cluster: true
Emoji one grapheme: true
```

This tests **regex semantics**, not whether a font draws the emoji. If the product requires personal names to support valid Unicode letters/marks, also define spacing, punctuation, normalization, and security policies; the two-token regex above merely illustrates the distinction between `Letter` and `Mark`.

## 11. UTF-8 Round-Trip and Invalid Unpaired Surrogates

A Java `String` can hold an **unpaired surrogate**, even though that value is not a valid Unicode scalar value encodable to standard UTF-8. For example, `"\uD83D"` is a lone high surrogate without a low surrogate.

Convenience APIs such as `String.getBytes(StandardCharsets.UTF_8)` can replace malformed data with replacement bytes/characters. For data needing exact preservation, tests cannot merely check whether the call threw an exception.

Use `CharsetEncoder`/`CharsetDecoder` with `CodingErrorAction.REPORT` when the contract requires rejecting invalid data. Malformed bytes and unmappable characters are distinct failure modes:

- **Malformed UTF-8 bytes:** e.g., `C3 28`, missing a valid continuation byte.
- **Malformed UTF-16 string:** e.g., a lone high surrogate.
- **Unmappable character:** e.g., encoding an emoji into ISO-8859-1.

### Program 8 — StrictUnicodeEncodingDemo.java

```java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class StrictUnicodeEncodingDemo {
    public static void main(String[] args) {
        byte[] badUtf8 = {(byte) 0xC3, (byte) 0x28};
        String replacement = new String(
                badUtf8, StandardCharsets.UTF_8);

        System.out.println("Replacement present: "
                + replacement.contains("\uFFFD"));

        try {
            StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(badUtf8));
            System.out.println("Unexpected decoded bytes");
        } catch (CharacterCodingException ex) {
            System.out.println("Strict decode rejected");
        }

        try {
            StandardCharsets.UTF_8.newEncoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .encode(CharBuffer.wrap("\uD83D"));
            System.out.println("Unexpected encoded surrogate");
        } catch (CharacterCodingException ex) {
            System.out.println("Strict encode rejected");
        }
    }
}
```

```bash
javac -encoding UTF-8 StrictUnicodeEncodingDemo.java
java StrictUnicodeEncodingDemo
```

Stdout:

```text
Replacement present: true
Strict decode rejected
Strict encode rejected
```

**Do not check "does the string contain U+FFFD" as a general detector for malformed source bytes:** the character `�` can appear legitimately in input. To detect whether a decoder encountered bad bytes, configure `REPORT` and catch `CharacterCodingException`.

## 12. An Assertion-Backed Regression Suite, Not Just Exploratory Printing

To make tests fail automatically on defects, use JUnit or a helper throwing `AssertionError`. Java's `assert` keyword **can be disabled by default unless `-ea` is enabled**, so the example below uses `check` regardless of JVM flags.

### Program 9 — UnicodeRegressionTest.java

```java
import java.text.BreakIterator;
import java.text.Normalizer;
import java.util.Locale;
import java.util.regex.Pattern;

public class UnicodeRegressionTest {
    private static int checked = 0;

    private static void check(boolean condition, String description) {
        if (!condition) {
            throw new AssertionError(description);
        }
        checked++;
    }

    public static void main(String[] args) {
        String pre = "\u00E9";
        String de = "e\u0301";
        String emoji = "\uD83D\uDE00";
        String whole = "A" + emoji + "B";

        check(!pre.equals(de), "raw representations");
        check(Normalizer.normalize(pre, Normalizer.Form.NFC)
                .equals(Normalizer.normalize(
                        de, Normalizer.Form.NFC)), "canonical NFC");
        check(Normalizer.normalize(de, Normalizer.Form.NFC)
                .equals(Normalizer.normalize(
                        Normalizer.normalize(
                                de, Normalizer.Form.NFC),
                        Normalizer.Form.NFC)), "NFC idempotent");

        check(whole.length() == 4, "UTF-16 units");
        check(whole.codePointCount(0, whole.length()) == 3,
                "code points");
        check(whole.offsetByCodePoints(0, 2) == 3,
                "code point offset");

        BreakIterator it =
                BreakIterator.getCharacterInstance(Locale.ROOT);
        it.setText(de);
        check(!it.isBoundary(1), "combining mark boundary");
        check(Pattern.matches("\\X", de),
                "single grapheme cluster");
        check("\u00DF".toUpperCase(Locale.ROOT)
                .equals("SS"), "case expansion");
        check("I".toLowerCase(Locale.ROOT)
                .equals("i"), "locale-neutral ASCII");
        check("I".toLowerCase(
                Locale.forLanguageTag("tr-TR"))
                .equals("\u0131"), "Turkish case");

        System.out.println("Passed checks: " + checked);
    }
}
```

```bash
javac -encoding UTF-8 UnicodeRegressionTest.java
java UnicodeRegressionTest
```

Stdout when all assertions pass:

```text
Passed checks: 11
```

This program verifies **11 conditions** and halts immediately when any fails. The checks target Java 17 with core Unicode cases while avoiding dependencies on screen cursor coordinates. For production applications, expand into JUnit parameterized tests across scripts/locales and co-locate the suite with the supported Unicode data version.

## 13. Property-Based Testing: Generating Valid Unicode Data with a Fixed Seed

Testing a handful of fixed strings guards against known bugs, yet cannot cover all combinations of base letters, marks, emoji, ZWJ, and case mappings. Property-based testing generates many strings and asserts valid invariants.

**Invariants to check:**

- `NFC(NFC(s)) == NFC(s)`.
- `NFD(NFD(s)) == NFD(s)`.
- `NFC(s)` and `NFD(s)` maintain proper canonical equivalence.
- For well-formed strings, UTF-8 encode/decode with the same charset preserves `String.equals`.
- A string split into grapheme segments must **reassemble to the exact original string** without losing code units.
- Every segment offset stays within `0..length`; segments never overlap.
- After a case conversion, never assume `length` and code-point count stay fixed; tests must **allow expansion**.

**Non-invariants:**

- `s.toUpperCase(locale).toLowerCase(locale).equals(s)`: can fail due to many-to-one case mappings.
- `s.equalsIgnoreCase(t)` always equals `NFC(s).equalsIgnoreCase(NFC(t))`: equivalence rules differ; verify per contract.
- "Number of code points equals number of graphemes": false with combining marks/ZWJ.
- "Every emoji is one code point": false for many emoji sequences.
- "NFKC never alters data meaning": false in several business domains.

### Program 10 — SeededUnicodePropertiesDemo.java

```java
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;
import java.util.Random;

public class SeededUnicodePropertiesDemo {
    private static void check(boolean okay) {
        if (!okay) {
            throw new AssertionError("Unicode property failed");
        }
    }

    public static void main(String[] args) {
        String[] atoms = {
                "a", "e", "\u0301", "\u00E9",
                "\uD83D\uDE00", "\u0130",
                "\u00DF", "\u200D", "\uFE0F"
        };
        Random random = new Random(271);
        int trials = 200;

        for (int i = 0; i < trials; i++) {
            StringBuilder input = new StringBuilder();
            int count = 1 + random.nextInt(8);
            for (int j = 0; j < count; j++) {
                input.append(atoms[random.nextInt(atoms.length)]);
            }
            String text = input.toString();

            String nfc = Normalizer.normalize(
                    text, Normalizer.Form.NFC);
            check(nfc.equals(Normalizer.normalize(
                    nfc, Normalizer.Form.NFC)));

            String nfd = Normalizer.normalize(
                    text, Normalizer.Form.NFD);
            check(nfd.equals(Normalizer.normalize(
                    nfd, Normalizer.Form.NFD)));

            byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);
            check(text.equals(
                    new String(utf8, StandardCharsets.UTF_8)));
        }

        System.out.println("Passed trials: " + trials);
    }
}
```

```bash
javac -encoding UTF-8 SeededUnicodePropertiesDemo.java
java SeededUnicodePropertiesDemo
```

Stdout:

```text
Passed trials: 200
```

**Why these atoms were chosen:** each atom is a **well-formed** Unicode sequence: the emoji is a valid surrogate pair, while combining marks, ZWJ, and variation selectors—even standalone—are valid code points. They can form odd-looking strings yet **never create unpaired surrogates**, so UTF-8 round-trip is a valid property over this corpus.

**Do not confuse random text with natural language:** random generation does not replace testing Vietnamese sentences, personal names, common emoji sequences, or edge-case data from production bug reports. The seed is fixed so failing cases remain reproducible.

## 14. Testing String Slicing Without Dropping Marks or Splitting Emoji

In a text editor, character selection/deletion normally operates on **grapheme boundaries**, not UTF-16 unit counts. Using `Pattern.compile("\\X")`, you can extract each match as a segment whose concatenation must equal the original string.

### Example 11 — GraphemeRoundTripDemo.java

```java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class GraphemeRoundTripDemo {
    public static void main(String[] args) {
        String original = "A" + "e\u0301"
                + "\uD83D\uDE00" + "B";
        Matcher matcher = Pattern.compile("\\X").matcher(original);
        StringBuilder rebuilt = new StringBuilder();
        int segments = 0;

        while (matcher.find()) {
            rebuilt.append(matcher.group());
            segments++;
        }

        System.out.println("UTF-16 units: " + original.length());
        System.out.println("Code points: "
                + original.codePointCount(0, original.length()));
        System.out.println("Segments: " + segments);
        System.out.println("Round trip exact: "
                + original.contentEquals(rebuilt));
    }
}
```

```bash
javac -encoding UTF-8 GraphemeRoundTripDemo.java
java GraphemeRoundTripDemo
```

Stdout with Java 17's grapheme algorithm for this simple string:

```text
UTF-16 units: 6
Code points: 5
Segments: 4
Round trip exact: true
```

Breakdown: `A` (1 unit), `e + mark` (2 units), emoji (2 units), `B` (1 unit) → **6 UTF-16 units**; code points **1 + 2 + 1 + 1 = 5**, yet **4 grapheme clusters**.

For longer ZWJ emoji sequences, different JDK versions or segmentation algorithms may vary: **test on the actual runtime rather than treating one machine's cluster count as an indefinite universal contract**.

## 15. Locale-Based Comparison: Separating Search from Identity

For natural-language content, search features may want to ignore case or accents. `java.text.Collator` supports `Locale`-based comparison with sensitivity levels:

- `PRIMARY`: generally compares base differences only; may ignore case/accents per locale rules.
- `SECONDARY`: generally distinguishes accents while ignoring case in many locales.
- `TERTIARY`: can distinguish letter case and other variants.
- `IDENTICAL`: deeper distinction, involving canonical decomposition.

These are **common conventions**, not a guarantee that every accented letter equals its unaccented letter across every language and provider. Instantiate a `Collator` for the user's locale when sorting/searching, and verify results on supported JDKs/providers.

**Never use `Collator` to compare access tokens, digital signatures, or automatic username uniqueness.** Those need explicit identifier policies or exact matching stable across environments. If the application uses database collation, it may differ from Java's `Collator` in Unicode/CLDR version; run integration tests rather than assuming parity.

### Sample Contracts for Key Fields

| Field | Acceptable policy | Required tests |
| --- | --- | --- |
| `displayName` | Preserve original spelling; optional NFC index for search | Precomposed/decomposed, special casing |
| ASCII case-insensitive `username` | Validate ASCII, lowercase `ROOT`, unique key | `Lan`/`LAN` collision; Turkish locale |
| `password` | Never auto-trim/normalize/change case outside auth contract | Differing only by case or diacritics |
| `accessToken` | Compare per token spec, usually case-sensitive | `aB` differs from `ab` |
| `searchQuery` | Locale-sensitive search/collation as needed | Accents, case, marks, Unicode versions |
| `filePath` | Follow actual filesystem policy | Never lowercase entire path |
| `apiFieldName` | Exact match per JSON schema | `userId` differs from `userid` when schema requires |
| `localizationKey` | Exact key in `ResourceBundle` | Never lowercase automatically on lookup |

Accented letters and emoji are not "bad data" to strip from every field. Conversely, data at risk of mixed scripts or confusables in **identifiers** must be handled by dedicated profiles and security rules, not merely `Normalizer` or `toLowerCase`.

## 16. Collision Tests After Normalization and Case Conversion

Two distinct inputs can collapse to the same key after normalization/case conversion. If a database already holds both before a policy change, a migration cannot merge them without resolving ownership.

Example:

```text
Raw 1: Lan_01
Raw 2: LAN_01
ASCII lowercase ROOT -> lan_01 for both
```

Likewise, two canonically equivalent forms like `"\u00E9"` and `"e\u0301"` yield the same NFC key. That may be desired for search or usernames, yet cannot be applied blindly as a universal rule for emails, tokens, or filenames.

### Program 12 — CanonicalCollisionDemo.java

```java
import java.text.Normalizer;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;

public class CanonicalCollisionDemo {
    private static String key(String text) {
        return Normalizer.normalize(
                text, Normalizer.Form.NFC)
                .toLowerCase(Locale.ROOT);
    }

    public static void main(String[] args) {
        String[] inputs = {
                "Lan_01", "LAN_01",
                "\u00E9", "e\u0301"
        };
        Map<String, String> first = new LinkedHashMap<>();

        int collisions = 0;
        for (String value : inputs) {
            String canonical = key(value);
            String earlier = first.putIfAbsent(
                    canonical, value);
            if (earlier != null) {
                collisions++;
            }
        }

        System.out.println("Inputs: " + inputs.length);
        System.out.println("Unique keys: " + first.size());
        System.out.println("Collisions: " + collisions);
    }
}
```

```bash
javac -encoding UTF-8 CanonicalCollisionDemo.java
java CanonicalCollisionDemo
```

Stdout:

```text
Inputs: 4
Unique keys: 2
Collisions: 2
```

**This is only a collision example**, not a recommended canonicalizer for every Unicode field. `NFC + lowercase(ROOT)` is neither Unicode full case folding nor a Unicode security profile; a product supporting Unicode usernames must also define and test Unicode version, confusables, allowed characters, and database collation. For passwords or tokens, key transformations like this are normally forbidden.

## 17. QA Matrix to Include in Your Test Suite

| Category | Sample data | Checks |
| --- | --- | --- |
| Canonical forms | `é` / `e + U+0301` | Raw differs, NFC matches, UTF-8 bytes may differ |
| Vietnamese diacritics | Letters with tone and vowel marks | NFC/NFD, caret/selection respects clusters |
| Leading combining mark | U+0301 before letter | No crash; explicit input policy |
| Surrogate pair | `A😀B` | length 4, codepoints 3, never slice at offset 2 |
| Variation selector | `✈️` | 2 codepoints; test grapheme on runtime |
| ZWJ sequence | `👩‍💻` | 5 UTF-16 units, 3 codepoints |
| Regional indicators | `🇻🇳` | Multiple codepoints/UTF-16 units |
| Emoji modifier | Emoji + skin tone | Do not count every codepoint as a character |
| Regex `\\X` | `e\u0301` | One extended grapheme cluster |
| Case expansion | `ß` → `SS` on uppercase `ROOT` | Length changes |
| Dotted I | `İ` `ROOT` lower | `i` + combining dot |
| Turkish I | `TITLE` `ROOT` vs. `tr-TR` | Two different lowercase keys |
| Exact vs. ignore-case | `Straße`/`STRASSE` | Do not assume `equalsIgnoreCase` = full fold |
| Charset | UTF-8 encode/decode | Round-trip on well-formed text |
| Malformed data | UTF-8 `C3 28`, lone high surrogate | Strict codec rejects |
| Identifier collision | `Lan_01`/`LAN_01` | Detect unique-key conflicts |
| Grapheme segmentation | Join all `\\X` matches | Exact string round-trip |
| Locale-driven search | `en`, `vi`, `tr` | Locale passed explicitly |
| Unicode version | Newer ZWJ emoji | Pin runtime/provider or verify expected data |
| UI renderer | Different fonts/platforms | Never treat rendered glyphs as canonical bytes/codepoints |
| Database | Java string vs. DB collation | Integration test uniqueness |
| File/API boundary | UTF-8/normalization contracts | Never alter bytes/semantics silently |

Every test must declare whether it verifies **exact bytes, code points, graphemes, layout, or business logic**. Mixing these layers yields false tests or missed bugs.

## 18. Testing Across JDK and Unicode Versions

JDK releases ship specific Unicode and locale data versions. When upgrading the JDK, re-test:

- `Character` classifications under updated Unicode data.
- `BreakIterator`, `Pattern("\\X")` segmentation, and new emoji handling.
- Locale-sensitive case mapping and collation.
- `Normalizer` and canonical representations under Unicode standards.
- Fonts/rendering if desktop UIs or text previews depend on the platform.

Not everything changes on every upgrade, and Unicode provides stability guarantees for many normalization aspects. Still, **never assume segmentation snapshots for new emoji stay identical forever**. Catch regressions with a corpus tagged against the runtime or standard your app claims to support.

**Suggested test corpus structure:**

```text
case-id, source-escaped, expected-codepoints, expected-graphemes, unicode-version
combining-e, e\u0301, 2, 1, target-runtime
grinning-face, \uD83D\uDE00, 1, 1, target-runtime
woman-technologist, \uD83D\uDC69\u200D\uD83D\uDCBB, 3, 1, target-runtime
```

This is **illustrative corpus data**, not standard machine-readable CSV because `source-escaped` contains backslash escapes needing a dedicated parser. In a real repo, use JSON or test fixtures with a defined escaping format rather than naive `split(",")` if values can contain commas.

In particular, if an app spans multiple runtimes (Java backend, JS frontend, native mobile), their Unicode segmentation engines may implement **different Unicode versions**. UI/editors should agree on length-limit and selection policies, or clearly surface backend re-validation.

## 19. Common Mistakes to Avoid

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Treating `String.length()` as glyph count | Emoji counted as 2 or more | Pick code points/graphemes per requirement |
| Using `substring(i,i+1)` on emoji | Splits surrogate pair | Slice only on valid boundaries |
| Treating `offsetByCodePoints` as enough for caret | Can split marks/ZWJ | Use grapheme segmentation |
| Using `equals` for canonical Unicode check | NFD/NFC treated as unequal | Normalize per policy |
| Auto-normalizing tokens/passwords | Alters values under verification | Respect protocol |
| Applying NFKC everywhere | May merge semantically distinct chars | Use only when profile permits |
| Using default `toLowerCase()` for IDs | Turkish I bug, env-dependent | Validate + explicit locale |
| Assuming uppercasing preserves length | Buffer truncation, collisions | Check length after mapping |
| Treating `equalsIgnoreCase` as full fold | Fails on `ß` expansion | Pick proper casefold/profile |
| Counting each combining mark as a char | Broken caret/backspace UX | Operate on graphemes |
| Hard-coding one JDK's emoji segmentation everywhere | Breaks on Unicode/runtime changes | Test target versions |
| Comparing screenshots/fonts to verify code points | Glyph rendering varies | Inspect actual code points/UTF-8 |
| Decoding malformed UTF-8 with replacement and calling it success | Silent data loss | Use `REPORT` decoder |
| Running only ASCII/English tests | Misses multilingual bugs | Include Vietnamese, Turkish, emoji corpus |
| Using `[A-Za-z]` regex for all personal names | Rejects valid Unicode names | Language-specific policy |
| Assuming `\\w` equals Unicode Letter | Regex scope varies with flags | Specify Unicode classes |
| Using `Collator` for tokens/IDs | Matching varies by locale | Exact/identifier policy |
| Ignoring database collation | Java vs. DB uniqueness mismatch | Integration testing |
| Calling `Locale.setDefault` in concurrent tests | Interferes with other tests | Pass `Locale` per operation |
| Fuzzing lone surrogates and expecting exact UTF-8 | Violates property preconditions | Generate valid scalars or test malformed separately |

## 20. Debugging Roadmap for Unicode Bugs

When a user reports "accents vanished" or "emoji got half-deleted," do not start by hacking regex replacements. Inspect in order:

1. **Original input:** did it come from keyboard, clipboard, UTF-8 file, or API? Must original bytes be preserved?
2. **Code points:** log as `U+XXXX` in a safe environment, avoiding raw PII or tokens.
3. **Normalization:** did raw inputs differ or match under NFC/NFD? Did something force NFKC or strip marks?
4. **UTF-16 offsets:** did `substring`/`charAt`/length truncation split a surrogate pair?
5. **Grapheme segmentation:** do caret/selection use `BreakIterator` or `\\X` matching the target Unicode version?
6. **Case mapping:** did default locale or case conversion expand/shrink length?
7. **Encoding:** are UTF-8 bytes valid? Was the wrong charset decoded or replaced with `U+FFFD`?
8. **Database/API:** do column collation, normalization, length limits, and encoding match Java's policy?
9. **Rendering:** do the font and terminal support emoji/combining-mark glyphs? Display bugs can differ from data bugs.
10. **Reproduction:** save an escaped test case plus runtime/Unicode version; use a fixed seed for fuzzers.

Before patching, pinpoint whether the bug sits at the **byte**, **Unicode string**, **grapheme boundary**, **case equivalence**, or **display renderer** layer. Fixing the wrong layer can mask the symptom while introducing new bugs.

## 21. Applied Exercises

**Exercise 1 — Comparing raw and NFC.** Take `"\u00E9"` and `"e\u0301"`. Compute UTF-16 length, code point count, UTF-8 hex, raw equality, and NFC equality. Explain why visual output can match while raw equality fails.

**Exercise 2 — Complex emoji.** Build tests for `😀`, `✈️`, `👩‍💻`, and `🇻🇳`. Count UTF-16 units/codepoints/graphemes; ensure no slicing inside surrogate pairs or ZWJ sequences. Run on two JDK versions supported by your project.

**Exercise 3 — Slicing/deleting one character.** Use `Pattern.compile("\\X")` to iterate graphemes in `"A" + "e\u0301" + "😀" + "B"`. Reassembly must equal the original string. Implement a function that deletes the final grapheme instead of `substring(0,length-1)`.

**Exercise 4 — Turkish I.** Compare `"TITLE".toLowerCase(Locale.ROOT)` and `"TITLE".toLowerCase(Locale.forLanguageTag("tr-TR"))`. Design an ASCII-only canonical username and test it when the JVM default locale is Turkish without calling `Locale.setDefault` between tests.

**Exercise 5 — Case expansion.** Compare `"Straße".equalsIgnoreCase("STRASSE")` against ROOT uppercasing. Why should one example not lead you to equate uppercasing with Unicode full case folding? Test `"\u0130"` under `ROOT` and Turkish locales.

**Exercise 6 — Strict Unicode input.** Take bytes `C3 28` and a `String` containing a lone high surrogate. Compare convenience codecs against strict decoder/encoder. Write a clear reject or repair policy with diagnostics for imports/APIs.

**Exercise 7 — Property-based testing.** Extend `SeededUnicodePropertiesDemo` with supplementary Unicode scalar values, multiple combining marks, and regional indicators. Keep the seed fixed; test NFC/NFD idempotence, UTF-8 round-trip, and grapheme reconstruction.

**Exercise 8 — Identity collision.** Take usernames `Lan_01`, `LAN_01`, `é`, `e\u0301`. Generate canonical keys under a documented policy, detect duplicates before creating a unique index, and never merge accounts automatically.

## 22. Official Documentation

- [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): UTF-16 `length`, `codePointCount`, `offsetByCodePoints`, `toUpperCase`/`toLowerCase`, `equalsIgnoreCase`.
- [Java SE 17 — Normalizer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html): NFC/NFD/NFKC/NFKD.
- [Java SE 17 — BreakIterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/BreakIterator.html): locale-aware text boundaries.
- [Java SE 17 — Pattern](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html): `\\X`, Unicode classes, Unicode case, canonical equivalence.
- [Java SE 17 — Character](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html): code points, surrogate pairs, and Unicode operations.
- [Java SE 17 — CharsetEncoder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetEncoder.html): malformed input and error actions.
- [Java SE 17 — CharsetDecoder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html): strict UTF-8 decoding.
- [Unicode Standard Annex #29](https://www.unicode.org/reports/tr29/): extended grapheme cluster segmentation.
- [Unicode Standard Annex #15](https://www.unicode.org/reports/tr15/): normalization forms.
- [Unicode Default Case Algorithms](https://www.unicode.org/versions/latest/core-spec/chapter-3/#G33992): case mappings and case folding.
- [Unicode Technical Standard #39](https://www.unicode.org/reports/tr39/): confusable identifiers and Unicode security profiles.

## 23. Key Takeaways

**A single user-perceived character can span multiple UTF-16 units and multiple code points.** Test `String.length()`, `codePointCount`, grapheme boundaries, and UTF-8 bytes separately. Accented letters in NFC/NFD can be canonically equivalent even when `String.equals` returns `false`; ZWJ emoji, variation selectors, and flags are not always single code points.

**Case conversions do not preserve length and can depend on `Locale`.** `ß` expands to `SS` when uppercased, `İ` can become `i + combining dot`, and Turkish `I` lowercases differently from `ROOT`. Never let default locale affect machine keys, never treat `equalsIgnoreCase` as full Unicode case folding, and never normalize/case-convert passwords or tokens outside contract.

**A solid test suite fails automatically on errors, uses diverse Unicode data, fixed seeds, strict codecs for malformed input, and pins JDK/Unicode versions when required.** Define per-field policies, preserve originals where needed, detect collisions, and separate text-data bugs from font/rendering bugs.
