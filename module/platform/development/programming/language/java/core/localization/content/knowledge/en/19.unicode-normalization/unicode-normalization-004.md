# `Normalizer.isNormalized` and Choosing a Unicode Normalization Policy in Java

## 1. Why Can Two Strings That Look Alike Still Differ?

A Java interface may receive personal names, search queries, localized messages, or text copied from multiple devices. Unicode allows certain visually similar or semantically equivalent characters to be represented by **different sequences of code points**.

For example, the letter `é` has at least two common representations:

```text
Precomposed representation:  U+00E9
Decomposed representation:   U+0065 U+0301
                             letter e  combining acute accent
```

Two strings can display identically, yet Java's `String.equals` compares **string contents by UTF-16 code units** and does not perform Unicode normalization automatically:

```java
String precomposed = "\u00E9";
String decomposed = "e\u0301";

System.out.println(precomposed.equals(decomposed)); // false
```

If an application uses input strings as search keys, cache keys, usernames, or values to match, different representations can lead to unexpected outcomes.

Java provides `java.text.Normalizer` with two key methods:

```java
Normalizer.normalize(text, Normalizer.Form.NFC)
Normalizer.isNormalized(text, Normalizer.Form.NFC)
```

- `normalize` returns the **normalized string** in the chosen form.
- `isNormalized` returns a **boolean** indicating whether the input string **is already in that form**. This method **does not modify or return a new string**.
- The normalization policy (**which form, at which layer, for which data type**) is a product decision, not something `Normalizer` decides on its own.

**Key point:** checking normalization with `isNormalized` is only meaningful once you have chosen **the appropriate form for the data type**. There is no single policy that is always right for display names, search, passwords, identifiers, and legal documents.

## 2. Concepts You Must Distinguish

### Code Point, Code Unit, and User-Perceived Character

Unicode defines a **code point** such as `U+00E9`; Java `String` stores **UTF-16** code units. A code point outside the BMP can occupy two `char` values (a surrogate pair). A user-perceived character (*grapheme cluster*) can consist of **multiple code points** (such as a base letter plus combining marks).

Therefore:

- `String.length()` counts **UTF-16 code units**, not “letters” or graphemes.
- `String.codePoints()` iterates over Unicode code points, though it also does not split text into graphemes.
- `String.equals()` does not automatically perform canonical equivalence, case folding, or collation.
- Unicode normalization can **change the code point count and UTF-16 length** while visual appearance stays nearly identical.

For example, `"\u00E9".length() == 1`, whereas `"e\u0301".length() == 2`. Normalization can shift caret indices, error-highlighting positions, and offsets in the original data. If an application needs to map positions between the original and normalized versions, it must design that mapping explicitly; never assume indices stay intact.

### Canonical Equivalence vs. Compatibility Equivalence

**Canonical equivalence**: sequences regarded by Unicode as orthographically equivalent encodings of the same content, such as `U+00E9` and `U+0065 U+0301`.

**Compatibility equivalence**: additionally includes characters differing in **presentation style or representation convention**, which can be mapped to a base form when compatibility handling is desired. Examples:

```text
U+FF21 (Ａ, fullwidth A) → A   under compatibility normalization
U+FB03 (ﬃ, ligature)   → ffi
U+2460 (①, circled 1)  → 1
```

Compatibility mappings **can lose meaningful distinctions** in brand names, research data, mathematical symbols, or originals that must be preserved. Do not equate “normalizable under Unicode” with “correct for business logic.”

## 3. The Four Forms in `Normalizer.Form`

Java provides the enum `java.text.Normalizer.Form` with four options:

| Form | Name | Core Behavior | Considered Use Cases |
| --- | --- | --- | --- |
| `NFD` | Canonical Decomposition | Decomposes characters with **canonical** decompositions, orders combining marks canonically | Analyzing mark/character components, certain internal processing steps |
| `NFC` | Canonical Decomposition then Composition | Canonical normalization and recomposition when rules allow | Storing ordinary display text, canonical matching |
| `NFKD` | Compatibility Decomposition | Decomposes both canonical and compatibility mappings | Specialized processing/search pipelines where losing distinctions is acceptable |
| `NFKC` | Compatibility Decomposition then Canonical Composition | Collapses compatibility forms then canonically composes when possible | Well-defined search keys, specific identifier profiles per dedicated standards |

Visualize two axes:

```text
                     Decomposition             Recomposition when allowed
Canonical            NFD                       NFC
Compatibility        NFKD                      NFKC
```

**Both NFC and NFD are canonical forms**, though their encoded outputs differ. `NFKC` and `NFKD` go further: they accept **compatibility mappings**, and can therefore merge presentational forms that originally carried distinct meanings.

The forms are not four ranked levels of “more correct/cleaner.” **NFKC is not an always-better version of NFC.** Each form has its own semantic contract.

### Accented Letter Example

```text
Input A: U+00E9
Input B: U+0065 U+0301

NFC(A)  = U+00E9
NFC(B)  = U+00E9

NFD(A)  = U+0065 U+0301
NFD(B)  = U+0065 U+0301
```

For these canonically equivalent cases, normalizing **both sides to the same form** makes `String.equals` comparison meaningful.

### Compatibility Example

```text
Input: ＡＢＣ１２３  (fullwidth)
NFC:   ＡＢＣ１２３  (preserves compatibility differences)
NFKC:  ABC123

Input: ﬃ
NFKC:  ffi

Input: ①
NFKC:  1
```

If product codes distinguish the symbol `①` from the digit `1`, NFKC can **discard information you needed to keep**. Conversely, if a search engine intentionally treats both forms as equivalent, a **separate search key** using NFKC can be helpful.

## 4. How Does `isNormalized` Work?

API signature:

```java
public static boolean isNormalized(
        CharSequence src,
        Normalizer.Form form)
```

`src` is the string or `CharSequence` to check; `form` is one of the four values of `Normalizer.Form`. The result applies only to **the specified form** and does not mean “the string is normalized under all forms.”

Example:

```java
String text = "e\u0301";

boolean alreadyNfc =
        Normalizer.isNormalized(text, Normalizer.Form.NFC);
boolean alreadyNfd =
        Normalizer.isNormalized(text, Normalizer.Form.NFD);
```

With the data above, `alreadyNfc` is `false`, while `alreadyNfd` is `true`. Being valid NFD does not mean a string is also valid NFC.

**Difference from `normalize`:**

```java
boolean check = Normalizer.isNormalized(text, Normalizer.Form.NFC);
String result = Normalizer.normalize(text, Normalizer.Form.NFC);
```

- `check`: **tests** the condition; does not produce a normalized version for storage.
- `result`: **obtains the value** converted to the requested form; the `text` string is not mutated.
- If `check == true`, as far as Unicode content goes, the string already satisfies that form. You can keep the original value instead of calling `normalize` if the check serves your control flow.
- **Do not assume “check first then normalize” is always faster**: `isNormalized` also has to scan the string; if most inputs require conversion, doing two passes can cost more than normalizing once. Measure on realistic workloads.

For `src == null` or `form == null`, the API does not return a fallback “unnormalized” result; `null` input is invalid and can throw `NullPointerException`. If a pipeline has optional fields, handle `null` at the data/validation layer before calling the API.

## 5. Standalone Program: Inspecting NFC/NFD and `String.equals` Behavior

Create the file **`NormalizationInspectionDemo.java`**:

```java
import java.text.Normalizer;
import java.util.Locale;
import java.util.stream.Collectors;

public class NormalizationInspectionDemo {
    private static String points(String value) {
        return value.codePoints()
                .mapToObj(cp -> String.format(Locale.ROOT, "U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    public static void main(String[] args) {
        String precomposed = "\u00E9";
        String decomposed = "e\u0301";

        System.out.println("rawEquals=" +
                precomposed.equals(decomposed));
        System.out.println("precomposed.length=" +
                precomposed.length());
        System.out.println("decomposed.length=" +
                decomposed.length());

        System.out.println("precomposed NFC=" +
                Normalizer.isNormalized(
                        precomposed, Normalizer.Form.NFC));
        System.out.println("decomposed NFC=" +
                Normalizer.isNormalized(
                        decomposed, Normalizer.Form.NFC));
        System.out.println("decomposed NFD=" +
                Normalizer.isNormalized(
                        decomposed, Normalizer.Form.NFD));

        String a = Normalizer.normalize(
                precomposed, Normalizer.Form.NFC);
        String b = Normalizer.normalize(
                decomposed, Normalizer.Form.NFC);

        System.out.println("NFC equal=" + a.equals(b));
        System.out.println("NFC codePoints=" + points(b));
        System.out.println("NFD codePoints=" + points(
                Normalizer.normalize(
                        precomposed, Normalizer.Form.NFD)));
    }
}
```

Run with JDK 17+:

```bash
javac -encoding UTF-8 NormalizationInspectionDemo.java
java -cp . NormalizationInspectionDemo
```

Output:

```text
rawEquals=false
precomposed.length=1
decomposed.length=2
precomposed NFC=true
decomposed NFC=false
decomposed NFD=true
NFC equal=true
NFC codePoints=U+00E9
NFD codePoints=U+0065 U+0301
```

**Explanation:** `String.equals` does not treat the two initial UTF-16 representations as equal. When **both are normalized to NFC**, they become the same string and `equals` returns `true`. NFD decomposes the character into `e` and the combining acute accent. Keep **both sides** consistent in form; never normalize one side and compare against an unnormalized side.

Using `codePoints()` to print `U+...` makes differences clearly visible that the naked eye can miss in a terminal or UI.

## 6. Standalone Program: Why Can `NFKC` Erase Distinctions?

Create **`CompatibilityNormalizationDemo.java`**:

```java
import java.text.Normalizer;

public class CompatibilityNormalizationDemo {
    private static String nfkc(String source) {
        return Normalizer.normalize(
                source, Normalizer.Form.NFKC);
    }

    public static void main(String[] args) {
        String wide = "\uFF21\uFF22\uFF23\uFF11\uFF12\uFF13";
        String ligature = "\uFB03";
        String circledOne = "\u2460";

        System.out.println("wide NFC=" +
                Normalizer.isNormalized(
                        wide, Normalizer.Form.NFC));
        System.out.println("wide NFKC=" + nfkc(wide));
        System.out.println("ligature NFKC=" + nfkc(ligature));
        System.out.println("circled NFKC=" + nfkc(circledOne));

        String vietnameseD = "\u0111";
        System.out.println("d-stroke NFD unchanged=" +
                vietnameseD.equals(Normalizer.normalize(
                        vietnameseD, Normalizer.Form.NFD)));

        String latinA = "a";
        String cyrillicA = "\u0430";
        System.out.println("confusable equality=" +
                nfkc(latinA).equals(nfkc(cyrillicA)));
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 CompatibilityNormalizationDemo.java
java -cp . CompatibilityNormalizationDemo
```

Output:

```text
wide NFC=true
wide NFKC=ABC123
ligature NFKC=ffi
circled NFKC=1
d-stroke NFD unchanged=true
confusable equality=false
```

Key takeaways:

- `wide NFC=true`: fullwidth characters can **already be in NFC**, yet NFKC converts them to their corresponding ASCII forms. Thus `isNormalized(text, NFC)` **cannot** tell you whether `normalize(text, NFKC)` will modify it.
- The ligature `ﬃ` becomes `ffi`, and `①` becomes `1`; presentational distinctions are lost in the NFKC version.
- The letter `đ` (`U+0111`) does not split into `d` plus a mark and disappear: normalizing to NFD **is not a Vietnamese accent-stripping algorithm**.
- Latin `a` and Cyrillic `а` (`U+0430`) look very similar visually, yet **remain distinct after NFKC**. **Unicode normalization is not a detector for all spoofing/confusable characters.**

## 7. Choosing a Normalization Policy by Data Purpose

Instead of “normalizing everything to NFKC” on input, define a **data contract** for each kind of string.

| Data Type | Reasonable Starting Policy | Rationale / Notes |
| --- | --- | --- |
| Ordinary display text | Often **NFC** for processed storage, while preserving source when needed | Unifies canonical equivalence, less intrusive than compatibility normalization |
| `ResourceBundle` translation data | Consistent NFC in the publishing pipeline if required; preserve meaning and placeholders | Avoids unintended encoding differences; do not auto-“fix” grammar |
| Name/product search fields | Build a **separate search key**, potentially NFC or NFKC paired with appropriate matching/language rules | Aims for broad matching while controlling which distinctions are collapsed |
| Username/identifier | Follow a **published identifier profile/contract**, never choose NFKC arbitrarily | Normalization can cause two distinct identifiers to collide; requires migration and uniqueness controls |
| Passwords and opaque secrets | **Do not modify arbitrarily**; follow the authentication protocol and two-sided policy | Altering input before hashing can break verification of existing passwords |
| Data requiring verbatim preservation (signatures, evidence, code, legal docs) | Preserve the original; if a normalized view is needed, create a **derived copy** | Normalization can change bytes, hashes, and presentational meaning |
| URL/domain/email | Follow rules of the **corresponding standard and component**, do not use `NFKC` as a validator | IDNA, URL/email standards, and security checks cannot be replaced by mere normalization |
| Auto-generated ASCII-only internal keys | Prefer **rejecting** out-of-contract Unicode rather than coercing to ASCII | Avoids silent mappings and identifier collisions |

**General design recommendation:** preserve original data when it has audit or display value; build a **canonical form for business comparisons**; specify the form and version/policy explicitly so all ingestion and lookup points apply it consistently.

### 7.1. Display Policy

If an interface accepts natural text, NFC is usually a reasonable choice to bring canonically equivalent strings into a uniform representation. Still, do not use NFC as a “sanitizer” for all data: it does not validate syntax, remove control characters, verify valid language, or block malicious payloads.

For content requiring exact byte preservation (signatures, external raw data), store **the original** and create a **derived normalized copy** when needed. Never normalize and overwrite original data without authorization.

### 7.2. Search Policy

A system may allow users to enter fullwidth `ＡＢＣ` to find `ABC`. Generating a search key with NFKC helps fold those variants, though results also depend on **case folding, accent matching, language, tokenization**, and query behavior.

Usually, keep at least two logical fields:

```text
originalText  → kept for display / audit
searchKey     → generated per the chosen search profile
```

**Do not overwrite display content with the search key.** Under NFKC, `①` turns into `1`; overwriting `originalText` loses the original form.

### 7.3. Identifier Policy

Suppose two accounts named `ABC123` and `ＡＢＣ１２３` were allowed to exist. If NFKC is later applied during duplicate checks, both collapse to the same key. This is an **identifier collision** requiring a migration plan, not a one-line Java change.

Before changing an ID policy:

1. Define the allowed character list and the semantics of transformations.
2. Determine whether prior representations are considered the same or distinct identifiers.
3. Audit legacy data for post-normalization collisions.
4. Define a clear **order of validation and normalization**.
5. Align the policy across registration, login, lookup, authorization, logs, and databases.
6. Manage version/policy migration if operating a system with live users.

Never use `isNormalized(..., NFC) == true` as proof that an identifier is “safe,” “valid,” or “non-spoofable.” That only answers a question about **normalization form**.

## 8. Standalone Program: Separating Display Text, Search Key, and Validation

This example demonstrates three deliberate decisions:

- Display text is converted to NFC for canonical consistency.
- A search key tries NFKC and `toLowerCase(Locale.ROOT)` as **a very simple example policy**.
- ASCII account IDs follow their own contract: **reject characters outside the allowed set before coercing via NFKC**.

Create **`NormalizationPolicyDemo.java`**:

```java
import java.text.Normalizer;
import java.util.Locale;

public class NormalizationPolicyDemo {
    private static String displayText(String input) {
        return Normalizer.normalize(
                input, Normalizer.Form.NFC);
    }

    private static String simpleSearchKey(String input) {
        return Normalizer.normalize(
                input, Normalizer.Form.NFKC)
                .toLowerCase(Locale.ROOT);
    }

    private static boolean acceptsAsciiAccountId(String input) {
        return input != null
                && input.matches("[A-Za-z0-9_-]{3,20}");
    }

    public static void main(String[] args) {
        String composed = "Caf\u00E9";
        String decomposed = "Cafe\u0301";
        String fullwidth = "\uFF21\uFF22\uFF23\uFF11\uFF12\uFF13";

        System.out.println("displaySameMeaning=" +
                displayText(composed).equals(displayText(decomposed)));

        System.out.println("searchSameMeaning=" +
                simpleSearchKey(composed)
                        .equals(simpleSearchKey(decomposed)));

        System.out.println("searchWide=" +
                simpleSearchKey(fullwidth));

        System.out.println("asciiOriginalAllowed=" +
                acceptsAsciiAccountId(fullwidth));

        System.out.println("asciiNormalizedAllowed=" +
                acceptsAsciiAccountId(Normalizer.normalize(
                        fullwidth, Normalizer.Form.NFKC)));

        String nfc = displayText(decomposed);
        System.out.println("idempotent=" +
                nfc.equals(displayText(nfc)));
    }
}
```

Run:

```bash
javac -encoding UTF-8 NormalizationPolicyDemo.java
java -cp . NormalizationPolicyDemo
```

Output:

```text
displaySameMeaning=true
searchSameMeaning=true
searchWide=abc123
asciiOriginalAllowed=false
asciiNormalizedAllowed=true
idempotent=true
```

**Important warning:** the line `asciiNormalizedAllowed=true` shows **why you should not automatically normalize to “legitimize” an identifier that violated the initial input contract**. The exact same fullwidth string is rejected by the strict ASCII policy, yet gets accepted if the code silently converts it to ASCII prior to validation. An application must choose one of the two policies and state/apply it consistently.

`simpleSearchKey` is also not a universal search normalizer for every language. `toLowerCase(Locale.ROOT)` **is not fully equivalent to Unicode full case folding**, nor does it solve tokenization, script differences, or locale-sensitive ordering. It is only an illustrative derived step to be adapted to search engine requirements.

## 9. `isNormalized` Workflows in Real Applications

### When You Only Need to Enforce a Policy

If the contract mandates stored text **must be in NFC**, check and reject non-conforming input:

```java
boolean validForm =
        Normalizer.isNormalized(input, Normalizer.Form.NFC);
```

This snippet requires `input` to be non-null and typed as a string. If `validForm == false`, the product can:

- Ask the client to resend in NFC;
- Or normalize on the server, if permitted by contract;
- Or store the original and the NFC version in two separate fields.

Being “not in NFC” is not always a **user data error**; in particular, natural text content can legitimately be entered in NFD.

### When You Need to Transform Data

```java
String normalized =
        Normalizer.normalize(input, Normalizer.Form.NFC);
```

This is the straightforward choice when the pipeline specifies **always converting to NFC**. There is no need to call `isNormalized` first only to call `normalize` unconditionally: that can be duplicate work.

### When You Want to Avoid Unnecessary Conversion

```java
String normalized = Normalizer.isNormalized(
        input, Normalizer.Form.NFC)
        ? input
        : Normalizer.normalize(input, Normalizer.Form.NFC);
```

This snippet keeps `input` if it is already NFC. It helps when code branches by policy or measures normalization status. However, for **performance**, scanning first and then normalizing is not faster by default; benchmark on real data.

### Idempotence Property

As long as the form and data remain unchanged:

```text
normalize(normalize(x, form), form) == normalize(x, form)
```

This means applying the same form a second time does not keep changing the **normalized content**. However, it does not mean normalizing across **two different forms** leaves data unchanged—for example, NFC followed by NFKC can still alter compatibility characters.

## 10. Normalization Is Not Stripping Vietnamese Accents

Some search systems want `café` to match when a user types `cafe`. Distinguish **canonical normalization** from **diacritic-insensitive search**.

- `NFD` decomposes many accented characters into a base character and combining marks, while **keeping the marks**.
- Removing characters in Unicode category `Mark` after NFD is **a separate operation**, not a normalization form.
- Accent stripping can produce colliding strings with different meanings and does not work uniformly across all scripts.
- In Vietnamese, `đ` does not turn into `d` via NFD alone. A naive accent-stripping algorithm can miss letters or alter text inconsistently.
- Accent stripping for a **secondary search index** can be a business choice, yet should not replace original text or be used for exact identifier matching without an explicit contract.

When language-based comparison is needed (sorting names, locale-specific accent/case sensitivity), examine `java.text.Collator` or a library/search engine with collation support. `Normalizer` handles **Unicode representation**, **not** the full orthography and sort order of a language.

## 11. Normalization Is Not Lowercasing or Anti-Spoofing

Related but distinct concepts:

| Operation | Question it resolves | What it does not resolve automatically |
| --- | --- | --- |
| Unicode normalization | Should two Unicode representations map to the same canonical/compatibility form? | Does not automatically lowercase all uppercase letters |
| `toLowerCase(locale)` | Convert letter case per case-mapping rules | Not full case folding; does not automatically normalize Unicode |
| Full Unicode case folding | Define a case-insensitive matching key for a profile | Not an all-purpose `String.toLowerCase` API |
| Locale-aware collation | How do two strings compare/sort per linguistic conventions? | Does not replace validation or authentication |
| Identifier profile/security checks | Which characters are valid, and do they cause confusion/spoofing? | Cannot conclude from `isNormalized` alone |

An easy-to-understand security example: Latin `a` (`U+0061`) and Cyrillic `а` (`U+0430`) look nearly identical to the eye, yet **NFKC does not merge them into one letter**. That proves Unicode normalization **does not eliminate all homograph/confusable attacks**.

If an application must check international identifiers, apply an appropriate security/syntax profile, allowed-character lists, mixed-script rules, and confusable detection when needed; for domain names, use the corresponding IDNA standard. Never treat `NFKC` as a “filter against dangerous Unicode.”

Likewise, Unicode normalization does not automatically strip control characters, bidirectional formatting marks, zero-width characters, or malicious payloads in HTML. Web output still requires **context-appropriate output escaping**; input data requires separate validation.

## 12. Normalization with Vietnamese and Localization

Vietnamese text can contain multiple tone marks and vowel diacritics, sometimes represented with multiple code points. For instance, an accented letter may exist either in precomposed form or as a base letter plus combining marks. Canonical normalization gives a system a **consistent representation** for storage or comparison, provided you understand:

1. **NFC does not remove accents**; it composes them according to Unicode rules.
2. Not every character combination has a single precomposed code point. “Composition” does not mean every grapheme becomes a single `char`.
3. Combining-mark ordering is governed by canonical ordering; do not try to enforce custom mark ordering with ad-hoc string manipulation.
4. If an application counts characters, positions a caret, or highlights search matches, transforming the string can shift offsets, so you must map positions or perform processing in a consistent form.
5. `ResourceBundle`, `MessageFormat`, and UI resources must be tested for **exact source-file Unicode and build-time encoding**, not merely by how text looks in an IDE.

Java `Normalizer` does not select `Locale.VIETNAM` to normalize; **NFC/NFD/NFKC/NFKD take no locale parameter**. Normalization rules belong to Unicode, distinct from language-specific sorting, casing, and phrasing.

## 13. When Should Normalization Occur in the Pipeline?

A common design:

```text
Receive input
    ↓
Check null, data type, size limits, and encoding
    ↓
Determine profile by field type:
    - display content
    - search key
    - identifier
    - password/opaque
    ↓
Normalize if required by profile
    ↓
Validate against profile on the appropriate value
    ↓
Store original/derived versions per contract
    ↓
Lookup and comparison use the same policy
```

Whether normalization runs **before or after validation** depends on the goal:

- For fields **accepting strictly exact ASCII**, check the input contract before any compatibility normalization step can turn non-ASCII Unicode into ASCII; otherwise, the application silently widens acceptance criteria.
- For fields **allowing multiple Unicode representations while needing canonical comparison**, you can normalize prior to matching/duplicate checks while still validating the allowed character profile.
- For **security-sensitive identifiers**, define the step order explicitly and verify system-wide consistency; no single order fits every protocol.
- For **passwords**, never normalize arbitrarily before hashing unless specified by the system/protocol; changing the policy after legacy accounts exist can break logins or alter security properties.
- For **digitally signed or hashed content**, original bytes and post-normalization bytes usually differ; never normalize one side of a protocol without the other side knowing.

**Comparison contracts must stay synchronized:** data written to the database, lookup inputs, and indexes must all be processed by the same policy version. Normalizing at query time without normalizing the index causes mysterious “not found” bugs.

## 14. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Comparing two Unicode strings with `equals` and thinking they display differently | Precomposed and decomposed forms can differ in encoding | Normalize both sides to the same form if comparison requires canonical equivalence |
| Calling `isNormalized(text, NFC)` expecting a new string back | Returns only a `boolean` | Use `normalize(text, NFC)` to get the string |
| Applying NFKC to all original text | Can alter fullwidth, ligatures, circled symbols, etc. | Choose policy per field; keep original if meaningful |
| Checking only `isNormalized(..., NFC) == true` to approve usernames | Fails to verify characters, scripts, or confusables | Add an identifier profile and security checks |
| Using NFD to “strip” Vietnamese accents | NFD keeps accents as combining marks | Separate normalization from accent-insensitive search processing |
| Calling NFKC and claiming all spoofing is handled | Many cross-script characters remain look-alikes | Check confusables/mixed-script per real profile |
| Treating `toLowerCase(Locale.ROOT)` as full Unicode casefold | Not equivalent to all case folding rules | Use an appropriate engine/profile when full Unicode case folding is needed |
| Normalizing passwords or opaque identifiers without a rule | Alters input meaning and breaks compatibility | Follow protocol contracts and migration plans |
| Normalizing on write but not on comparison | Keys and queries have different forms | Use a single unified policy pipeline |
| Replacing source content with normalized text and deleting the original | Loses audit trail and data needing preservation | Separate original text from derived versions |
| Computing length/offsets before normalizing and using them afterward | Wrong highlights/carets/indices | Recompute or map offsets between representations |
| Inferring semantic validity from normalization form | Normalization does not prove content is valid | Run separate business validation |
| Assuming `isNormalized` is always a performance optimization | Can perform two scans of the data | Benchmark before adding a pre-check branch |
| Ignoring JDK/Unicode version differences | Supported characters/rules can change across runtimes | Test on target Java runtimes and version the policy |

## 15. Recommended Test Suite

A normalization pipeline should test these categories:

1. **Canonical equivalence:** `"\u00E9"` and `"e\u0301"` differ before normalization, and match after both use NFC or NFD.
2. **All four forms:** test `isNormalized` for each form without inferring from another form's result.
3. **Compatibility characters:** fullwidth `Ａ`, ligature `ﬃ`, circled character `①`; confirm NFKC converts them when policy permits.
4. **Vietnamese diacritics:** multiple combining marks, letter `đ`, inputs with differing combining-mark orders; ensure accents are not lost under canonical normalization.
5. **Idempotence:** normalizing twice with the same form produces identical content.
6. **Read/write consistency:** same policy at database write, index generation, and search query.
7. **No ID collisions:** dry-run datasets with `ABC123` and its fullwidth version before adopting an NFKC policy.
8. **Multi-source text:** IMEs, copy/paste, mobile, resource bundles, APIs, and files with different encodings.
9. **Supplementary Unicode (outside BMP):** strings with emoji/supplementary code points; check offsets computed in UTF-16.
10. **Input limits:** null, empty strings, very long strings, unusual combining-mark chains; size limits may need checking before heavy processing.
11. **Security:** confusables/mixed-script, control characters, bidi, and zero-width; never claim normalization replaces these checks.
12. **Stability across updates:** manage Unicode/JDK changes and run controlled reindexing or policy version transitions when needed.

### Simple Verification Example

Create **`NormalizationAssertions.java`**:

```java
import java.text.Normalizer;

public class NormalizationAssertions {
    private static String nfc(String text) {
        return Normalizer.normalize(text, Normalizer.Form.NFC);
    }

    private static void require(boolean condition) {
        if (!condition) {
            throw new AssertionError("Normalization check failed");
        }
    }

    public static void main(String[] args) {
        String a = "\u00E9";
        String b = "e\u0301";

        require(!a.equals(b));
        require(nfc(a).equals(nfc(b)));
        require(Normalizer.isNormalized(nfc(b),
                Normalizer.Form.NFC));
        require(nfc(nfc(b)).equals(nfc(b)));
        require(Normalizer.normalize("\u2460",
                Normalizer.Form.NFKC).equals("1"));

        System.out.println("5 checks passed");
    }
}
```

Run:

```bash
javac -encoding UTF-8 NormalizationAssertions.java
java -cp . NormalizationAssertions
```

If all conditions hold:

```text
5 checks passed
```

The `require` method throws `AssertionError` directly, so it does not depend on whether the JVM `-ea` flag is enabled.

## 16. Summary

- `Normalizer.isNormalized(text, form)` only **checks** whether a string is in the requested form; `Normalizer.normalize(text, form)` **returns the normalized string** without mutating the old string.
- **NFC/NFD** handle canonical equivalence; **NFKC/NFKD** also handle compatibility equivalence and can merge representations the product needs to distinguish.
- **Normalization must follow a per-data policy**: display text, search keys, identifiers, passwords, and preserved documents do not necessarily use the same form.
- **NFC is not accent removal**, **NFKC is not full confusable detection**, and Unicode normalization does not replace collation, case folding, validation, or escaping.
- Normalize **both sides of a comparison**, keep storage/indexing/querying consistent, and account for Unicode/JDK versions when changing policies.
- For localized systems, prioritize preserving textual meaning and providing targeted derived normalizations rather than silently rewriting all incoming Unicode.
