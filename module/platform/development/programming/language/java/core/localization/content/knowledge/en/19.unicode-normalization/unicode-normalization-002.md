# Normalizer with NFC, NFD, NFKC, and NFKD in Java

Two Unicode strings can **look identical** yet contain **different Unicode code point sequences**. For example, the letter `é` can be a single precomposed code point `U+00E9` or two code points `U+0065` (letter e) and `U+0301` (combining acute accent). Java's `String.equals()` compares string contents by UTF-16 code units, so these two representations are not automatically equal. The consequences appear in searching, comparing record keys, storing names, matching content from different devices, and processing accented Vietnamese text.

`java.text.Normalizer` solves part of this problem using **four Unicode normalization forms** per Unicode Standard Annex #15:

- **NFC:** canonical decomposition followed by composition when possible (*canonical composition*).
- **NFD:** canonical decomposition (*canonical decomposition*).
- **NFKC:** **compatibility** decomposition followed by composition when possible (*compatibility decomposition + canonical composition*).
- **NFKD:** **compatibility** decomposition (*compatibility decomposition*).

More important than memorizing the names is **choosing the right form for the meaning of your data**. NFC/NFD preserve distinctions according to *canonical equivalence*; NFKC/NFKD can **merge spellings that are only compatibility-equivalent** and lose meaningful character distinctions. Normalization **is not** language translation, stripping Vietnamese accents, changing letter case, or comprehensive character-spoofing protection.

This lesson uses **Java 17+**, standalone runnable examples, and Unicode escape strings so outputs are verifiable across different machines.

## 1. Unicode Can Represent the Same Text with Multiple Code Point Sequences

Consider the Latin letter `é`:

```text
Form A: U+00E9               LATIN SMALL LETTER E WITH ACUTE
Form B: U+0065 U+0301        LATIN SMALL LETTER E
                              + COMBINING ACUTE ACCENT
On-screen appearance:        é      é
String.equals() comparison:  false (when unnormalized)
```

Even though renderers usually draw both forms very similarly, the computer sees two different code point sequences. For a Java `String`, code points in the BMP usually occupy one **UTF-16 code unit**; characters outside the BMP can occupy **two code units** (a surrogate pair). Therefore:

- `String.length()` returns the number of **UTF-16 code units**, not necessarily the number of Unicode code points.
- `String.codePoints()` iterates by code point, useful when inspecting Unicode representations.
- The number of code points still **does not** equal the number of user-perceived characters (*grapheme clusters*), because a letter with multiple combining marks or a joined emoji can consist of multiple code points.

Normalization operates on **Unicode sequences**, regardless of whether glyphs look alike in a particular font.

### Canonical Equivalence

Unicode defines certain distinct sequences as **canonically equivalent** (*canonically equivalent*). For example, `U+00E9` and `U+0065 U+0301`. `NFC` and `NFD` bring canonically equivalent sequences into **the same canonical form**, allowing normal string comparison when **both sides use the same form**.

Do not try to list “accented letters” manually and replace them yourself. The Unicode Standard also specifies **canonical ordering** of combining marks and complex composition rules, so use a standard-compliant normalizer implementation.

## 2. The Four Normalization Forms: What Do C, D, and K Mean?

| Form | Full Name | Decomposition | Composition | Equivalence Type |
| --- | --- | --- | --- | --- |
| `NFD` | Normalization Form D | Canonical | No | Canonical |
| `NFC` | Normalization Form C | Canonical | Yes, when rules allow | Canonical |
| `NFKD` | Normalization Form KD | Compatibility | No | Compatibility and canonical |
| `NFKC` | Normalization Form KC | Compatibility | Yes, when rules allow | Compatibility and canonical |

- **`D`** = *decomposition*.
- **`C`** = *composition*, re-composing after decomposition and canonical ordering.
- **`K`** = *compatibility*, allowing additional mappings beyond canonical equivalence.

The letter `K` **does not** mean “slightly deeper decomposition that still completely preserves meaning”. Compatibility mappings can replace characters with special visual styling with ordinary characters, such as circled numbers, fullwidth letters, or presentation ligatures.

### Illustrative Observation Table

| Source character | NFC | NFD | NFKC | NFKD |
| --- | --- | --- | --- | --- |
| `é` (U+00E9) | `é` | `e` + U+0301 | `é` | `e` + U+0301 |
| `ﬁ` (U+FB01, ligature fi) | `ﬁ` | `ﬁ` | `fi` | `fi` |
| `①` (U+2460) | `①` | `①` | `1` | `1` |
| `Ａ` (U+FF21, fullwidth A) | `Ａ` | `Ａ` | `A` | `A` |

For `é`, all four forms preserve canonical equivalence and output values differ in **code point sequence**, not necessarily in visual appearance. For `ﬁ`, `①`, and `Ａ`, only **NFKC/NFKD** perform the compatibility mappings shown above. This clearly illustrates the risk of **collapsing data** if NFKC is chosen carelessly.

There is no rule that “NFKC always yields the shortest string”: decomposition/recomposition can lengthen or shorten a string depending on the data. Nor should you promise that NFC always composes into a single code point: not every accented sequence has a precomposed character.

## 3. The java.text.Normalizer API and Forms

In Java 17+, the standard class is **`java.text.Normalizer`**, not `java.text.NumberFormat` or a charset conversion API.

```java
import java.text.Normalizer;

String result = Normalizer.normalize(text, Normalizer.Form.NFC);
boolean already = Normalizer.isNormalized(text, Normalizer.Form.NFC);
```

This is a **fragment** inside a method: `text` is an already-declared string.

Two primary methods:

| API | Purpose |
| --- | --- |
| `Normalizer.normalize(CharSequence src, Normalizer.Form form)` | Returns a `String` in the requested normalization form |
| `Normalizer.isNormalized(CharSequence src, Normalizer.Form form)` | Checks whether a string is already in the requested form |
| `Normalizer.Form.NFC` | Canonical decomposition + composition |
| `Normalizer.Form.NFD` | Canonical decomposition |
| `Normalizer.Form.NFKC` | Compatibility decomposition + composition |
| `Normalizer.Form.NFKD` | Compatibility decomposition |

`Normalizer` uses the Unicode rules built into the Java runtime. For `null` input, do not treat the result as an empty string: handle `null` according to your application contract (the API can throw `NullPointerException`). The returned `String` **does not mutate** the original `String` object because `String` is immutable.

### When Should You Use isNormalized?

If an input contract requires **input to already be in NFC**, use `isNormalized(...)` to **reject** other representations, or explicitly normalize before storing. These two policies are not the same:

- **Accept + normalize:** the application accepts multiple canonically equivalent representations and converts them to NFC when storing.
- **Require normalized:** the protocol requires the sender to normalize beforehand; the application rejects non-conforming input, which is useful for digitally signed data or when the contract demands stable bytes.

Choose one and document it clearly at the API boundary. If data carries a digital signature or MAC, **do not silently normalize after signature verification**: changing code points alters the signed bytes, even if the screen display looks the same.

## 4. Runnable Demo: NFC and NFD Resolve Code Point Differences

Save the file **`CanonicalFormsDemo.java`**:

```java
import java.text.Normalizer;
import java.util.stream.Collectors;

public class CanonicalFormsDemo {
    private static String codePoints(String input) {
        return input.codePoints()
                .mapToObj(cp -> String.format("U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    public static void main(String[] args) {
        String composed = "\u00E9";
        String decomposed = "e\u0301";

        System.out.println("Raw equal: "
                + composed.equals(decomposed));
        System.out.println("NFC equal: "
                + Normalizer.normalize(composed, Normalizer.Form.NFC)
                        .equals(Normalizer.normalize(
                                decomposed, Normalizer.Form.NFC)));
        System.out.println("NFD composed: "
                + codePoints(Normalizer.normalize(
                        composed, Normalizer.Form.NFD)));
        System.out.println("NFC decomposed: "
                + codePoints(Normalizer.normalize(
                        decomposed, Normalizer.Form.NFC)));
    }
}
```

Compile/run on Java 17+:

```bash
javac -encoding UTF-8 CanonicalFormsDemo.java
java CanonicalFormsDemo
```

Stdout:

```text
Raw equal: false
NFC equal: true
NFD composed: U+0065 U+0301
NFC decomposed: U+00E9
```

With `NFC`, the sequence `e` + acute accent is composed into the precomposed `é` because Unicode defines an appropriate canonical composition. With `NFD`, the precomposed character `é` decomposes into `e` + acute accent. Both paths produce **the same form** when the input sequences are canonically equivalent.

`String.format("U+%04X", cp)` prints numeric code point values in hexadecimal rather than font glyphs; this inspection approach is better than just looking at the screen when diagnosing Unicode bugs.

## 5. NFC and NFD with Multi-Diacritic Vietnamese Characters

Vietnamese often uses vowels with multiple diacritic components. One example is **`ắ`**, the precomposed code point `U+1EAF` (*LATIN SMALL LETTER A WITH BREVE AND ACUTE*):

```text
Precomposed form:   U+1EAF                 ắ
Decomposed NFD:     U+0061 U+0306 U+0301   a + breve + acute
NFC of NFD:         U+1EAF                 ắ
```

Components:

- `U+0061`: letter `a`.
- `U+0306`: **COMBINING BREVE**, breve mark.
- `U+0301`: **COMBINING ACUTE ACCENT**, acute accent.

When rendered, many fonts draw the decomposed sequence identically to the precomposed character. Yet their Java lengths differ: `"\u1EAF".length()` is 1, while `"a\u0306\u0301".length()` is 3, because all three code points are in the BMP.

**File `VietnameseFormsDemo.java`**:

```java
import java.text.Normalizer;
import java.util.stream.Collectors;

public class VietnameseFormsDemo {
    private static String codePoints(String input) {
        return input.codePoints()
                .mapToObj(cp -> String.format("U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    public static void main(String[] args) {
        String word = "\u1EAF";
        String nfd = Normalizer.normalize(
                word, Normalizer.Form.NFD);
        String nfc = Normalizer.normalize(
                nfd, Normalizer.Form.NFC);

        System.out.println("Original: " + codePoints(word));
        System.out.println("NFD: " + codePoints(nfd));
        System.out.println("NFC back: " + codePoints(nfc));
        System.out.println("Lengths: " + word.length()
                + " / " + nfd.length());
        System.out.println("Equal after NFC: "
                + word.equals(nfc));
    }
}
```

```bash
javac -encoding UTF-8 VietnameseFormsDemo.java
java VietnameseFormsDemo
```

Stdout:

```text
Original: U+1EAF
NFD: U+0061 U+0306 U+0301
NFC back: U+1EAF
Lengths: 1 / 3
Equal after NFC: true
```

**Practical implication:** if one user enters a Vietnamese name using a keyboard that produces combining marks while another system stores precomposed characters, direct byte comparison or `String.equals` can fail. When both sides normalize to **NFC**, canonically equivalent cases match consistently.

At the same time, **NFD is not “stripping Vietnamese accents”**: it **preserves the marks as combining marks**. Removing those combining marks after NFD is a **different** operation, which can turn `"má"` into `"ma"`, changing both content and meaning. If a product provides accent-insensitive search, that must be an **explicit search policy**, not the storage default.

## 6. Runnable Demo: NFKC and NFKD Alter Compatibility Characters

Two examples—**`ﬁ`** (the two-letter f-i ligature) and **`①`** (circled digit 1)—show the difference clearly. Under NFC/NFD, they are not turned into ordinary characters; NFKC/NFKD allow compatibility mappings.

**File `CompatibilityFormsDemo.java`:**

```java
import java.text.Normalizer;
import java.util.stream.Collectors;

public class CompatibilityFormsDemo {
    private static String cps(String value) {
        return value.codePoints()
                .mapToObj(cp -> String.format("U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    public static void main(String[] args) {
        String ligature = "\uFB01";
        String circled = "\u2460";
        String fullwidth = "\uFF21";

        System.out.println("Ligature NFC: " + cps(
                Normalizer.normalize(ligature, Normalizer.Form.NFC)));
        System.out.println("Ligature NFKC: " + cps(
                Normalizer.normalize(ligature, Normalizer.Form.NFKC)));
        System.out.println("Circled NFC: " + cps(
                Normalizer.normalize(circled, Normalizer.Form.NFC)));
        System.out.println("Circled NFKD: " + cps(
                Normalizer.normalize(circled, Normalizer.Form.NFKD)));
        System.out.println("Fullwidth NFKC: " + cps(
                Normalizer.normalize(fullwidth, Normalizer.Form.NFKC)));
        System.out.println("NFKC(fi) equal: "
                + Normalizer.normalize(ligature, Normalizer.Form.NFKC)
                        .equals("fi"));
    }
}
```

```bash
javac -encoding UTF-8 CompatibilityFormsDemo.java
java CompatibilityFormsDemo
```

Stdout:

```text
Ligature NFC: U+FB01
Ligature NFKC: U+0066 U+0069
Circled NFC: U+2460
Circled NFKD: U+0031
Fullwidth NFKC: U+0041
NFKC(fi) equal: true
```

**Do not think of this as a transformation just to save bytes.** It can erase the distinction between `ﬁ` and `fi`, between the decorative symbol `①` and the digit `1`, and between fullwidth letters and ASCII. Those distinctions can matter in original text, brand names, mathematical expressions, legal documents, or verbatim preservation requirements.

NFKC is useful for fields with an **identifier policy** that permits collapsing compatibility variants, or for building **secondary search keys**; however, also consider Unicode identifier rules and domain-specific security requirements. **Do not default to converting all stored data to NFKC.**

## 7. NFKC and NFKD Are Not Lowercasing, Transliteration, or Accent Stripping

Several other operations must be distinguished:

| Operation | Example | Is it Normalizer's responsibility? |
| --- | --- | --- |
| Canonical normalization | `e` + U+0301 → `é` under NFC | Yes |
| Compatibility normalization | `ﬁ` → `fi` under NFKC | Yes |
| Lowercasing | `ABC` → `abc` | No |
| Accent stripping | `má` → `ma` | No; this is a different transformation |
| Script conversion | Cyrillic letters to Latin | No |
| Detecting look-alike characters | Latin `a` and Cyrillic `а` | Not sufficient; requires dedicated confusable checks |
| Encoding conversion | UTF-8 bytes → Unicode characters | No, belongs to the decoder |
| Word translation | `hello` → `xin chào` | No |
| Merging emoji into one code point | Multi-code-point emoji → one code point | Not its purpose |

NFKC **does not** automatically turn `"ABC"` into `"abc"`. If case-insensitive comparison is needed, a separate **case policy** must be defined. `String.toLowerCase(Locale.ROOT)` supports some technical case-insensitive needs, but **is not fully equivalent to Unicode Default Case Folding** and does not replace security standards for usernames/domains.

Similarly, NFKD is often used as an **initial step** in an accent-free search pipeline because it separates letters and diacritics. However, deleting all combining marks can lose important orthographic distinctions, does not handle all marks/letter variants completely, and must not be applied indiscriminately to original data.

## 8. Normalizer.isNormalized: Validation and Idempotence

A fundamental property of Unicode normalization is **idempotence**: for a given form F, normalizing a string that is already in form F a second time **does not change** it.

```text
F(F(text)) == F(text)
```

However, **an individually normalized string concatenated with another individually normalized string is not guaranteed to remain in the same form**. For instance, `"e"` is already NFC, and the combining acute accent `"\u0301"` alone is also NFC; yet `"e\u0301"` after concatenation **is not NFC**, because it can compose into `é`.

**Program `NormalizationCheckDemo.java`:**

```java
import java.text.Normalizer;

public class NormalizationCheckDemo {
    public static void main(String[] args) {
        String base = "e";
        String mark = "\u0301";
        String joined = base + mark;

        System.out.println("Base NFC: "
                + Normalizer.isNormalized(base, Normalizer.Form.NFC));
        System.out.println("Mark NFC: "
                + Normalizer.isNormalized(mark, Normalizer.Form.NFC));
        System.out.println("Joined NFC: "
                + Normalizer.isNormalized(joined, Normalizer.Form.NFC));

        String normalized = Normalizer.normalize(
                joined, Normalizer.Form.NFC);
        System.out.println("Normalized NFC: "
                + Normalizer.isNormalized(
                        normalized, Normalizer.Form.NFC));
        System.out.println("Idempotent: "
                + normalized.equals(Normalizer.normalize(
                        normalized, Normalizer.Form.NFC)));
    }
}
```

```bash
javac -encoding UTF-8 NormalizationCheckDemo.java
java NormalizationCheckDemo
```

Stdout:

```text
Base NFC: true
Mark NFC: true
Joined NFC: false
Normalized NFC: true
Idempotent: true
```

Therefore, if a system concatenates Unicode strings at different times, **do not assume** the resulting string always stays NFC/NFD/NFKC/NFKD just because the individual pieces were normalized. Check or normalize at the boundary of the **final value** defined by the application.

**Performance:** `isNormalized` can skip allocating a new string when input is already in the target form, though it still incurs scanning overhead. When high performance is critical, benchmark with real data; do not hand-roll a naive detector based on checking ASCII characters or combining marks.

## 9. UTF-8 and Normalization Are Two Separate Layers

A common misconception: “If two strings both use UTF-8, they will be identical.” This is **false**.

UTF-8 defines how **code points** are converted to **bytes**. Unicode normalization defines how **equivalent code point sequences** are chosen. Two canonically equivalent strings can both be valid UTF-8 yet produce **different bytes**:

```text
Precomposed "é" (U+00E9):
  UTF-8: C3 A9

"e" + acute accent (U+0065 U+0301):
  UTF-8: 65 CC 81

Both are valid UTF-8.
Raw byte comparison: different.
Comparison after NFC: both U+00E9 → same UTF-8 C3 A9.
```

**File `NormalizationAndUtf8Demo.java`:**

```java
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;
import java.util.Arrays;

public class NormalizationAndUtf8Demo {
    public static void main(String[] args) {
        String first = "\u00E9";
        String second = "e\u0301";

        boolean before = Arrays.equals(
                first.getBytes(StandardCharsets.UTF_8),
                second.getBytes(StandardCharsets.UTF_8));

        boolean after = Arrays.equals(
                Normalizer.normalize(first, Normalizer.Form.NFC)
                        .getBytes(StandardCharsets.UTF_8),
                Normalizer.normalize(second, Normalizer.Form.NFC)
                        .getBytes(StandardCharsets.UTF_8));

        System.out.println("UTF-8 equal before: " + before);
        System.out.println("UTF-8 equal after NFC: " + after);
    }
}
```

```bash
javac -encoding UTF-8 NormalizationAndUtf8Demo.java
java NormalizationAndUtf8Demo
```

Stdout:

```text
UTF-8 equal before: false
UTF-8 equal after NFC: true
```

**Recommendation:** new systems commonly pick UTF-8 as the encoding and **NFC** as the normalization policy for ordinary user text. Both decisions must **be declared separately** in the data contract. Do not expect `Files.readString(path, UTF_8)`, `getBytes(UTF_8)`, or JSON parsing to automatically normalize content.

## 10. Applications: Comparison, Search, Database Keys, and Personal Names

### Comparing Ordinary Unicode Strings

If two canonically equivalent spellings should be treated as the same text:

```java
static boolean canonicalEquals(String a, String b) {
    return Normalizer.normalize(a, Normalizer.Form.NFC)
            .equals(Normalizer.normalize(b, Normalizer.Form.NFC));
}
```

This is a **fragment inside a Java class**, requiring `import java.text.Normalizer`; it assumes `a` and `b` are non-null. Better yet, if you can normalize **once at the input/storage boundary**, subsequent comparisons do not need to re-normalize every time.

**Do not blindly replace every `String.equals` call**: for passwords, tokens, digitally signed values, machine codes, hashes, or identifiers with specific byte contracts, out-of-policy normalization can **alter the identity of the string**. Each data domain needs its own equivalence and collision policy.

### Database Keys and UNIQUE Constraints

If an application uses NFC as the standard for a `displayName` or `userHandle` field, two common approaches exist:

1. **Store NFC and enforce uniqueness on the normalized column** according to the chosen schema/collation strategy.
2. **Preserve the original value** for display/audit, and store a **lookup key column** normalized per policy; place the uniqueness constraint on the key column if business rules require uniqueness.

Keep in mind that **database collations** may perform comparisons differently from `String.equals` or Java's `Normalizer` (by case, accents, or Unicode version). Therefore, never assume every database's `UNIQUE` constraint automatically understands Unicode canonical equivalence. Test against the actual DBMS and collation deployed.

### “Loose” Search and Original Content

A search system may build a secondary index using NFKC, lowercasing, or custom diacritic-handling rules. However, the original string should be kept when fidelity is needed, and **two distinct inputs can collide onto the same key**. For example, `ﬁ` and `fi` both become `fi` under NFKC. If that is a username or identifier, you must decide **who owns the post-normalization key** and whether to reject or log conflicts.

Do not blindly use NFKC to “clean” multilingual text; compatibility folding can affect semantics, mathematical notation, brand data, or legally mandated verbatim text.

## 11. Demo of Key Collision Risk Under NFKC

**File `NormalizationCollisionDemo.java`:**

```java
import java.text.Normalizer;

public class NormalizationCollisionDemo {
    public static void main(String[] args) {
        String ligature = "\uFB01";
        String plain = "fi";

        System.out.println("Raw equal: "
                + ligature.equals(plain));
        System.out.println("NFC equal: "
                + Normalizer.normalize(ligature, Normalizer.Form.NFC)
                        .equals(Normalizer.normalize(
                                plain, Normalizer.Form.NFC)));
        System.out.println("NFKC equal: "
                + Normalizer.normalize(ligature, Normalizer.Form.NFKC)
                        .equals(Normalizer.normalize(
                                plain, Normalizer.Form.NFKC)));
        System.out.println("Case unchanged: "
                + Normalizer.normalize("ABC", Normalizer.Form.NFKC)
                        .equals("ABC"));
    }
}
```

```bash
javac -encoding UTF-8 NormalizationCollisionDemo.java
java NormalizationCollisionDemo
```

Stdout:

```text
Raw equal: false
NFC equal: false
NFKC equal: true
Case unchanged: true
```

**Interpretation:** NFKC produces the **same key** for two strings that NFC still treats as distinct. This can be desirable for search matching or a well-defined identifier system, but it can also create unintended **collisions**. Do not rely on NFKC alone as an anti-spoofing mechanism. For Unicode security, you also need character restriction policies, script checks, and confusable checks following frameworks such as Unicode Technical Standard #39 when the domain requires it.

## 12. Where Should Normalizer Sit in the Data Flow?

A typical user-text processing flow:

```text
HTTP / JSON / form / UTF-8 file
          |
          v
Decode bytes with right charset + validate size
          |
          v
Input String (may be NFC, NFD, or another form)
          |
          v
Validate data domain + pick normalization policy
          |
          +-- ordinary text --> NFC
          |
          +-- specialized search/identifier --> NFKC/NFKC_Casefold
          |                                     if policy truly requires it
          |
          +-- signed bytes/token --> keep as-is per protocol,
          |                          do not normalize automatically
          v
Storage / index / service boundaries
          |
          v
Display according to Locale, with user-appropriate text
```

Note: **`java.text.Normalizer` only provides the four forms NFC/NFD/NFKC/NFKD**; it does not ship a built-in `NFKC_Casefold` API. If you need a complex Unicode standard profile for identifiers, you must use dedicated algorithms/libraries (such as ICU4J or rules based on UTS #39) and pin the appropriate Unicode data version.

### Put Normalization Before or After Validation?

There is no single answer for every field. Two options:

- **Validate raw input first, then normalize and re-validate:** useful when you need to detect forbidden characters in raw input while also ensuring the normalized output complies with output policy.
- **Normalize then validate:** useful when the formal contract treats equivalent variants as one input and validation is defined on the canonical form.

With NFKC, **evaluating collision risk is mandatory**. For example, a compatibility character may turn into an allowed ASCII character after normalization; if you check the allowed character set only before or only after in an unintended way, you can inadvertently widen or narrow valid input. In username registration systems, define normalization once, enforce uniqueness after normalization, and keep the policy stable across versions.

For Vietnamese personal/full names, using NFC is generally suitable for unifying canonical equivalence without trying to remove accents or alter letters. Unifying the Unicode form does not erase the distinguishing marks in `đ`, `ă`, `â`, `ơ`, `ư`.

## 13. Reading/Writing Files and APIs: Normalization Must Be an Explicit Contract

- **JSON:** JSON strings can contain text in various Unicode forms. JSON parsers primarily handle escaping/encoding; do not expect them to apply NFC to every string. Choose your policy after parsing and before serializing if needed.
- **CSV/TSV:** when data comes from Excel, other systems, or different operating systems, personal names and labels can contain combining marks. Do not split strings with sloppy Unicode regexes or compare raw bytes if canonical equivalence is the goal.
- **Database:** some collations treat multiple strings as “equivalent” at a linguistic level; results do not necessarily match NFC. Check both Java normalization and collation when designing keys/indexes.
- **File paths:** filesystems can apply different filename normalization behaviors or histories. Do not construct file paths from user text by assuming a single NFC/NFD behavior; you must also guard against path traversal and OS-reserved characters.
- **Cache keys:** if an API uses NFC as an identifier while the cache stores raw input, two canonically equivalent variants can occupy two entries. Normalize at the same cache-key boundary if the identity contract requires it.
- **Digitally signed data:** signatures are usually computed over the bytes of a specific representation. Normalizing before or after signing must follow the **protocol's canonicalization rules**—never do it ad hoc.
- **Logs/audit:** consider retaining raw input (subject to privacy policies) for diagnostics and the normalized version for lookups. Logging all inputs indiscriminately can expose personal data; do not use normalization as an excuse to log extra sensitive information.

### Is “Just Store NFC” Always Enough?

No. NFC solves **canonical equivalence**, but does not automatically handle:

- Uppercase/lowercase and language-specific casing rules.
- Confusable characters across multiple scripts.
- Stripping zero-width or control characters as required by the application.
- Glyphs that differ stylistically, semantically, or across ideographs.
- Validity of IDs, emails, domains, or file formats governed by dedicated RFCs.
- Unicode grapheme boundaries, cursor movement, and slicing display characters.

Use `Normalizer` as one **component** of a text pipeline, not as a security filter or a fix-all for every input issue.

## 14. Length, Performance, and Resource Limits

A string after normalization can be **shorter or longer** than the original string in UTF-16 code units or UTF-8 bytes; do not assume NFC always shrinks size or NFD always increases size. Compatibility characters under NFKD can expand into multiple code points; with untrusted input, expansion can noticeably increase data size.

Control these factors:

1. **Input limits** before normalization (bytes/code units/code points per policy).
2. **Output limits** after normalization if storage or an API has quotas.
3. **UI length** measured by grapheme/cell rendering if the product requires it; `String.length()` is not the visible character count.
4. **Performance** for large batches: normalize at boundaries, avoiding repeated normalization on every pairwise comparison.
5. **Unicode/JDK version** when stable results are required for keys, signatures, or long-lived distributed systems.
6. **Consistency** across Java, JavaScript, databases, and ICU libraries, as Unicode versions may differ.

Unicode provides stability guarantees for the normalization of assigned code points, yet that does not mean every old/new runtime, unassigned character, supplementary profile, and database comparison behavior is **automatically identical**. For long-lived identifiers, document the form, relevant version/profile, and migration strategy when changes occur.

### Does Already-Normalized Text Need to Run Again?

In principle, normalizing a second time with the same form does not change the result (*idempotent*). However, when **concatenating strings**, applying non-normalization transformations (lowercasing, adding prefixes, replacing marks...), or integrating external data, the output may no longer be in the desired form. Check or re-normalize at the **final boundary**, especially before building identifier keys.

## 15. Practice: Enforcing an NFC Contract on Input Data

Some API fields prefer to **accept only NFC strings** rather than silently converting them. This helps callers catch issues early when the exchange contract specifies it explicitly.

**File `RequireNfcDemo.java`:**

```java
import java.text.Normalizer;

public class RequireNfcDemo {
    private static String requireNfc(String text) {
        if (text == null) {
            throw new IllegalArgumentException("Missing text");
        }
        if (!Normalizer.isNormalized(text, Normalizer.Form.NFC)) {
            throw new IllegalArgumentException("Not NFC");
        }
        return text;
    }

    public static void main(String[] args) {
        String composed = "caf\u00E9";
        String decomposed = "cafe\u0301";

        System.out.println("Accepted: "
                + requireNfc(composed).length());

        try {
            requireNfc(decomposed);
            System.out.println("Unexpected acceptance");
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected non-NFC input");
        }
    }
}
```

```bash
javac -encoding UTF-8 RequireNfcDemo.java
java RequireNfcDemo
```

Stdout:

```text
Accepted: 4
Rejected non-NFC input
```

This example checks only the NFC condition; it does not verify maximum length, forbidden characters, HTML injection, or business validity. In a production API, **separate** schema, size, character-class, language, and identity policy checks.

If the product chooses **accept + normalize**, you can write:

```java
// Fragment inside a method that already has String input.
String stored = Normalizer.normalize(
        input, Normalizer.Form.NFC);
```

However, when dealing with identifiers or names that require auditing, consider preserving the original version per policy if normalization changes code point sequences that matter to the user or external systems.

## 16. Common Mistakes

| Mistake | Why it is wrong | How to handle it |
| --- | --- | --- |
| Assuming UTF-8 automatically normalizes Unicode | Encoding and normalization are different layers | Specify UTF-8 and the Unicode form separately |
| Directly comparing two accented strings from different sources | `String.equals` sees different UTF-16 sequences | Normalize both sides to the **same form** if the data domain requires it |
| Using NFKC for all content | Compatibility mapping can collapse distinct meanings | Use NFC for ordinary text; NFKC only under explicit policy |
| Treating NFD as accent stripping | NFD **retains** combining marks | Do not delete marks unless the search policy permits it |
| Treating NFC as lowercasing/uppercasing | Normalizer does not perform case folding | Define a separate case policy |
| Believing NFKC suffices against confusables/homoglyphs | Many cross-script look-alikes remain easily confused | Use an additional identifier security profile |
| Relying on `String.length()` as visible letter count | UTF-16 code units differ from code points/graphemes | Pick the measurement appropriate to the need |
| Concatenating two NFC strings and assuming the result is NFC | Concatenation can form new combinable sequences | Normalize the final result |
| Using `Normalizer.isNormalized` to validate semantic correctness | It only checks form, not semantics | Validate the data domain separately |
| Normalizing tokens/passwords/signed strings without a contract | Can change bytes and break verification | Follow the protocol and handle signatures in the right order |
| Normalizing an entire existing DB without predicting collisions | Keys may collide after normalization | Dry-run, detect collisions, run migration with rollback |
| Thinking database collation = Java Normalizer | String comparison rules can differ | Test collation and versions |
| Caching keys with a different normalization policy than the API | Same identity gets split across entries | Normalize consistently at boundaries |
| Skipping size checks after NFKD | Some characters can expand | Enforce both input and output limits |
| Implicitly depending on Unicode version for durable identifiers | Runtime upgrades can affect profiles/related factors | Document policy/version and test migrations |

## 17. Exercises

**Exercise 1 — Canonical equivalence.** Given `"\u00E9"` and `"e\u0301"`, print `equals`, `length`, and code points before/after NFC and NFD. Explain why the two sequences usually render identically yet initial `equals` returns false.

**Exercise 2 — Vietnamese.** Given `"\u1EAF"`, use `Normalizer.Form.NFD` to list its code points, then convert back to NFC. Demonstrate the difference between **diacritic decomposition** and **diacritic stripping**. Try another Vietnamese character that has two combining marks.

**Exercise 3 — Compatibility.** Compare `"\uFB01"` with `"fi"`, and `"\u2460"` with `"1"` under both NFC and NFKC. Decide whether a system storing brand names, a search index, and a username field should collapse these variants; explain by policy.

**Exercise 4 — String concatenation.** Check `isNormalized(..., NFC)` for `"e"`, `"\u0301"`, and their concatenation. Why do normalized pieces not guarantee a normalized concatenation?

**Exercise 5 — UTF-8 and API boundaries.** Create two canonically equivalent strings and compare `getBytes(StandardCharsets.UTF_8)` before and after NFC. Propose an API rule: allow senders to submit NFD and normalize on the server, or mandate NFC and reject other inputs? State the consequences for digital signatures, cache keys, and uniqueness.

**Exercise 6 — Existing data.** Suppose a database currently holds `ﬁ` and `fi` as two distinct keys. Before migrating the key policy from NFC to NFKC, how should you detect and resolve collisions to avoid accidentally merging records?

## 18. Official Documentation and Terminology

- [Java SE 21 — java.text.Normalizer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/Normalizer.html): `normalize` and `isNormalized`.
- [Java SE 21 — Normalizer.Form](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/Normalizer.Form.html): definitions of `NFC`, `NFD`, `NFKC`, `NFKD`.
- [Unicode Standard Annex #15 — Unicode Normalization Forms](https://www.unicode.org/reports/tr15/): canonical algorithm, compatibility, stability, and examples.
- [Unicode FAQ — Normalization](https://www.unicode.org/faq/normalization.html): canonical equivalence, idempotence, concatenation, choosing NFC/NFKC.
- [Unicode Technical Standard #39 — Unicode Security Mechanisms](https://www.unicode.org/reports/tr39/): identifier security, confusable characters, and supplementary profiles.

## 19. Takeaways

**`NFC` = canonical decomposition + composition; `NFD` = canonical decomposition; `NFKC` = compatibility decomposition + composition; `NFKD` = compatibility decomposition.** Use `Normalizer.normalize(text, Normalizer.Form.NFC)` to bring ordinary text into a single canonical representation when that is your data policy; use `isNormalized` to enforce contracts when needed.

NFC/NFD support comparing **canonically equivalent** strings; NFKC/NFKD also transform **compatibility variants** and can introduce collisions or lose meaningful distinctions. Normalization is not charset conversion, accent stripping, lowercasing, language translation, or complete Unicode security. Always **define the form at data boundaries**, bound sizes, test code points (not just visual glyphs), pick policies per identifier/search field, and keep behavior consistent across Java, databases, APIs, and Unicode versions.