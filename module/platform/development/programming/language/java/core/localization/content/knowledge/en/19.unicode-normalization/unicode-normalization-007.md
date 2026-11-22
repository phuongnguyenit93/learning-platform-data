# Preserving Original Data When Unicode Transformations Are Lossy

## 1. Problem: Normalization Is Useful but Not Always Reversible

In multilingual Java applications, we often want to normalize text before searching, comparing, or indexing. Familiar examples:

- `e\u0301` (letter e + combining acute accent) and `é` (U+00E9) can converge to the same NFC representation.
- `①` can become `1` after NFKC.
- Fullwidth `ＡＢＣ` can become `ABC` after NFKC.
- `Café` and `Cafe` can both become `cafe` if a search key is lowercased and stripped of accents.

Those transformations can be great for **matching**, yet if you overwrite the original text in the database, the application may no longer know what the user actually entered. From `"1"` after NFKC, you cannot deduce whether the source was `"1"` or `"①"`.

**Guiding principle:** keep **original data** separate from **transformed derived data** (normalized/index/search keys). Whenever a transformation is many-to-one, derived data is insufficient to reconstruct the verbatim original.

This lesson explains the lossy nature of Unicode transformations, how to use `java.text.Normalizer` in Java 17+, runnable code examples, model design for storing originals, handling post-normalization collisions, index versioning, and testing.

## 2. Three Data Forms to Distinguish

| Field | Purpose | Example |
| --- | --- | --- |
| `originalText` | Text entered/received per source contract | `①` |
| `normalizedText` | Representation after a specific normalization form | `1` after NFKC |
| `searchKey` | Value used for search, potentially multi-step | `abc` from `ＡＢＣ` after NFKC + lowercase |

An illustrative record:

~~~text
recordId:       1007
originalText:   ①
searchKey:      1
searchRule:     nfkc-lower-root-v1
~~~

Here, the ID identifies the record; original is for display and content storage; searchKey is for lookup. `searchRule` records the algorithm and version that produced that key.

**Do not treat searchKey as original data**, even if two strings occasionally look alike on the surface. Nor should you assume searchKey is a unique key: multiple distinct inputs can produce the same output.

## 3. Why Do Non-Injective Transformations Lose Information?

A function `f` can be uniquely inverted over an input set only if distinct inputs are not merged into a single output value. Conversely, when `x != y` yet `f(x) == f(y)`, knowing the output is not enough to recover the input.

With NFKC:

~~~text
NFKC("①") = "1"
NFKC("1") = "1"
~~~

With an accent-stripping and casing pipeline:

~~~text
key("Café") = "cafe"
key("Cafe") = "cafe"
key("CAFE") = "cafe"
~~~

All three inputs may carry different intended meanings or appearances. If only `"cafe"` is kept, there is no deterministic inverse function to restore how the user wrote it.

Whether “information loss” is acceptable depends on the goal. If a system intentionally defines all variants as the same username, merging may be permitted by policy. However, if display names, article text, evidence, or original files must be reproduced, the source cannot be silently overwritten.

## 4. NFC and NFD: Canonical Equivalence Does Not Mean Byte-Identical to Raw

Unicode can represent certain visually identical letters using multiple code point sequences. For instance, `é`:

~~~text
Precomposed: U+00E9
Decomposed:  U+0065 U+0301
~~~

In Java, these two strings can look like one letter yet differ structurally:

- `String.equals` returns false before normalization.
- `String.length()` is 1 and 2 UTF-16 code units, respectively.
- When UTF-8 encoded, they are 2 and 3 bytes long, respectively.
- `Normalizer.normalize(..., Normalizer.Form.NFC)` brings both to the same precomposed representation.

`NFC` preserves the **canonical equivalence** of Unicode text, yet does not preserve the **original representation**. Once the input is discarded, an NFC string does not tell you whether it came from a single precomposed code point or a base letter plus combining mark.

`NFD` performs canonical decomposition and likewise retains no trace of the original code point sequence. Saying “NFC/NFD are lossless” is only valid if what you want to preserve is **canonical equivalence**, not the **original code units or bytes**.

If a contract requires proving that source bytes are completely unaltered, store those exact bytes (along with required encoding/metadata) before decoding/normalizing. A decoded Java `String` usually cannot reproduce every BOM detail, encoding, or malformed byte sequence of the source.

## 5. NFKC/NFKD Also Apply Compatibility Mappings

Java provides four `Normalizer.Form` values:

| Form | Meaning | Remember |
| --- | --- | --- |
| `NFC` | Canonical composition | Canonically equivalent representations are standardized |
| `NFD` | Canonical decomposition | Canonical decomposition |
| `NFKC` | Compatibility composition | Can merge characters that have compatibility representations |
| `NFKD` | Compatibility decomposition | Also decomposes compatibility forms per Unicode rules |

Examples:

~~~text
NFKC("①")   -> "1"
NFKC("ＡＢＣ") -> "ABC"
NFC("①")    -> "①"
~~~

Because NFKC also applies compatibility mappings, it can be very useful for search indexes or certain identifier classes, yet it is not a “better NFC” to apply arbitrarily to all source data.

If a user intentionally uses `①` in an article or fullwidth letters in a product label, applying NFKC to the original field alters appearance. A system that must preserve authorial data should not do that merely for search convenience.

## 6. Java 17+: Demonstrating Colliding Transformations

Create `NormalizationCollisionDemo.java`:

~~~java
import java.text.Normalizer;
import java.nio.charset.StandardCharsets;

public class NormalizationCollisionDemo {
    public static void main(String[] args) {
        String composed = "\u00E9";
        String decomposed = "e\u0301";

        System.out.println("equal raw="
                + composed.equals(decomposed));

        String nfcA = Normalizer.normalize(
                composed, Normalizer.Form.NFC);
        String nfcB = Normalizer.normalize(
                decomposed, Normalizer.Form.NFC);

        System.out.println("equal NFC="
                + nfcA.equals(nfcB));
        System.out.println("raw lengths="
                + composed.length() + ","
                + decomposed.length());
        System.out.println("raw bytes="
                + composed.getBytes(StandardCharsets.UTF_8).length
                + ","
                + decomposed.getBytes(StandardCharsets.UTF_8).length);

        String circled = "\u2460";
        System.out.println("circled NFC="
                + Normalizer.normalize(circled, Normalizer.Form.NFC));
        System.out.println("circled NFKC="
                + Normalizer.normalize(circled, Normalizer.Form.NFKC));

        String fullwidth = "\uFF21\uFF22\uFF23";
        System.out.println("full NFKC="
                + Normalizer.normalize(fullwidth, Normalizer.Form.NFKC));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 NormalizationCollisionDemo.java
java NormalizationCollisionDemo
~~~

Stdout verified with the JVM:

~~~text
equal raw=false
equal NFC=true
raw lengths=1,2
raw bytes=2,3
circled NFC=①
circled NFKC=1
full NFKC=ABC
~~~

The first result shows `String.equals` comparing pre-normalization Java string values, unlike a canonical equivalence check. Both strings become equal under NFC, yet the NFC version **does not reveal the length or Unicode spelling of the original**.

The `①` and `ＡＢＣ` examples show that NFKC can yield representations markedly different from the input appearance. If the UI must render exact user-entered content, read from `original`, not from the NFKC form.

## 7. Beyond Normalization: Lowercasing, Accent Stripping, Whitespace Collapsing

Other steps often appear in a search pipeline:

- **Lowercasing:** `ABC` and `abc` both become `abc`.
- **Case folding:** Unicode rules for caseless matching, not strictly synonymous with `String.toLowerCase`.
- **Accent stripping:** using NFD then deleting combining marks per search policy; `Café` and `Cafe` can share a key.
- **Whitespace collapsing:** differences between single and multiple spaces, newlines, or tabs can disappear.
- **Punctuation removal:** codes, names, or text with differing punctuation can become the same key.
- **Transliteration:** converting letters from one script to another can merge multiple spellings.

Do not call all of these operations “Unicode normalization.” NFC/NFD/NFKC/NFKD are specific Unicode forms; deleting marks, changing case, collapsing spaces, or transliterating require **their own contracts** and can carry different linguistic implications.

**Linguistic context examples:**

- `"Straße".toUpperCase(Locale.ROOT)` can produce `"STRASSE"`. This transformation does not promise to preserve the original spelling.
- `"I".toLowerCase(Locale.forLanguageTag("tr-TR"))` becomes `ı` (dotless i) per Turkish rules. A `Locale.ROOT` strategy yields a stable technical key, yet is not natural for every linguistic search case.
- `"Café"` after NFD and deleting `\\p{M}` yields `"Cafe"`. That is *diacritic stripping*, not NFD's default effect.

In Vietnamese, diacritics/tones distinguish many words and names; stripping accents should normally be done only on **query or index keys** when accent-free search is required, never on display values.

## 8. Designing a Record That Keeps Original and searchKey

A simple model using a Java `record` to keep two separate fields. In the example, the search key uses NFKC and lowercasing with `Locale.ROOT`; this is **an example policy**, not a mandatory rule for all languages.

Create `OriginalAndKeyDemo.java`:

~~~java
import java.text.Normalizer;
import java.util.Locale;
import java.util.Objects;

public class OriginalAndKeyDemo {
    record TextEntry(String original, String searchKey) {
        static TextEntry from(String original) {
            Objects.requireNonNull(original, "original");
            String key = Normalizer.normalize(
                    original, Normalizer.Form.NFKC)
                    .toLowerCase(Locale.ROOT);
            return new TextEntry(original, key);
        }
    }

    public static void main(String[] args) {
        TextEntry a = TextEntry.from("\u2460");
        TextEntry b = TextEntry.from("1");

        System.out.println("sameKey="
                + a.searchKey().equals(b.searchKey()));
        System.out.println("rawEqual="
                + a.original().equals(b.original()));
        System.out.println("a=" + a.original()
                + "|" + a.searchKey());
        System.out.println("b=" + b.original()
                + "|" + b.searchKey());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 OriginalAndKeyDemo.java
java OriginalAndKeyDemo
~~~

Stdout:

~~~text
sameKey=true
rawEqual=false
a=①|1
b=1|1
~~~

`TextEntry` retains **two distinct values** even though their lookup keys collide. When displaying the entered label, use `original()`; when looking up under the defined policy, use `searchKey()`.

Java `record` and immutable `String` suit this data model well, though storage integrity still must be enforced in the database/service. Whenever `original` changes intentionally, derived keys must be recomputed accordingly.

## 9. One searchKey Can Point to Multiple Originals

Example of a search index that should not automatically drop distinct original values:

~~~text
original   normalized key
①          1
1          1
ＡＢＣ      abc
ABC        abc
~~~

Create `SearchIndexCollisionDemo.java`:

~~~java
import java.text.Normalizer;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

public class SearchIndexCollisionDemo {
    static String searchKey(String original) {
        return Normalizer.normalize(
                original, Normalizer.Form.NFKC)
                .toLowerCase(Locale.ROOT);
    }

    public static void main(String[] args) {
        Map<String, List<String>> index =
                new LinkedHashMap<>();

        List<String> originals = List.of(
                "\u2460", "1", "\uFF21\uFF22\uFF23", "ABC");

        for (String original : originals) {
            String key = searchKey(original);
            index.computeIfAbsent(key,
                    k -> new ArrayList<>()).add(original);
        }

        System.out.println("1 matches="
                + index.get("1").size());
        System.out.println("abc matches="
                + index.get("abc").size());
        System.out.println("first raw="
                + index.get("1").get(0));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 SearchIndexCollisionDemo.java
java SearchIndexCollisionDemo
~~~

Stdout:

~~~text
1 matches=2
abc matches=2
first raw=①
~~~

In the example, one searchKey can hold a **list of sources**. In a large system, have the index point to `recordId` values rather than duplicating original text across multiple places.

**Never place a unique constraint on searchKey automatically.** Only do so when the product **intentionally** defines values sharing a normalized key as a single unique identifier, such as a published username policy. Even with a uniqueness rule, if you want to preserve the user's chosen display styling, you still need a separate field for the original.

## 10. When Is Modifying the Original Allowed?

Some systems stipulate that input **must** conform to a canonical form:

- Technical identifiers restricted to lowercase ASCII.
- A protocol requiring a specific normalization prior to signing or storage.
- Usernames with a pre-announced rule ignoring certain character differences.
- A system-generated field rather than free-form user text.

In such cases, normalizing at ingestion can be part of a **formal data contract**, not a bug. Still, document clearly:

1. Which transformations are allowed, e.g., NFC or NFKC.
2. Is the field used for display, identity, or search only?
3. Does the user see and accept the modified outcome?
4. Is an audit trail or original needed per retention policy?
5. Are there collision cases that require rejection or asking for a rename?

The difference is **intentional transformation under contract** versus **silent loss of data that was not permitted to be lost**. Not every field must store raw input forever; however, fields requiring preservation must never store only the derived version.

## 11. Safe Storage Pipeline

A clear processing flow:

~~~text
Input source (text or bytes)
          |
          v
Decode + validate per contract
          |
          +----> original preserved
          |
          +----> normalize per purpose
                    |
                    v
               case handling
                    |
                    v
               searchKey + ruleVersion
~~~

When a user executes a search:

1. Build the query key using **the policy matching the index**.
2. Look up the key, which may match multiple records.
3. Return the ID and **original** for display.
4. If the user edits the original, update `original` and all derived fields in a single consistent operation.

Minimal schema example:

~~~text
id              PRIMARY KEY
original_text   TEXT
search_key      TEXT
key_version     TEXT
~~~

If the business must preserve exact uploaded file bytes, a field/blob/file storing raw bytes and encoding metadata may be necessary. A Java `String` does not satisfy byte-level provenance requirements.

Never build SQL by concatenating `original` or `searchKey` values directly. Use prepared statements and appropriate output encoding/escaping mechanisms; normalization is not a solution for SQL injection or XSS.

## 12. Versioning the Pipeline to Rebuild Indexes

Search-key generation rules can evolve over time:

- Switching from NFC to NFKC or vice versa.
- Adding or removing diacritic stripping.
- Changing case-handling logic.
- Updating i18n libraries, Unicode data, or locale providers.
- Changing rules for whitespace, punctuation, or script mixing.

Record an explicit version, e.g., `"nfkc-lower-root-v1"`. When migrating to `v2`, deployment teams can:

1. Keep `original` **unchanged**.
2. Recompute new keys from `original`, not from `v1` keys.
3. Detect newly colliding record pairs.
4. Rebuild indexes and run regression tests.
5. Cut queries over to the `v2` index on schedule.
6. Retain a rollback path to the `v1` index if needed.

If only `v1` keys were kept, many source distinctions are already collapsed and `v2` keys cannot be fully reconstructed. That is a major benefit of preserving original data: **the ability to evolve algorithms** without destroying content.

## 13. Hashing and Integrity Proofs

Two strings can be canonically equivalent yet differ in UTF-8 bytes:

~~~text
"é" as U+00E9         -> C3 A9
"e\u0301"              -> 65 CC 81
~~~

Hashing **raw bytes** typically yields different digests. If before hashing you normalize both to NFC and encode, they can produce **the same post-normalization bytes** and thus the same hash.

Three goals must remain separate:

| Question | How to verify |
| --- | --- |
| Are the source bytes unchanged? | Hash/compare the exact **stored source bytes** |
| Are two texts canonically equivalent? | Normalize to NFC/NFD per contract and compare |
| Do two records match under accent-free/case-insensitive search? | Apply the separate **search rule** |

**Never use a normalized hash to prove raw bytes did not change.** For digital signatures, the order of canonicalization, encoding, byte serialization, and signed scope must follow protocol standards; never normalize before verifying signatures on raw data.

## 14. Invalid Data and Decoding Policies

Java `String` uses UTF-16 code units; technically it can hold unpaired surrogates. Incoming byte streams can also contain malformed UTF-8 sequences. Decoders/encoders have modes to report errors or insert replacement characters; if data is replaced before storage, the resulting `String` may not allow recovering the byte source.

Therefore, define what “original” means:

- **Valid decoded character sequence**, when the source contract is Unicode text data.
- **Original bytes and charset**, when file re-export, signature verification, or byte-for-byte preservation is required.
- **User-confirmed post-validation value**, when input policy permits conversion prior to storage.

Never call `Normalizer.normalize` a tool to “fix all broken Unicode.” Nor should you automatically strip every odd-looking character: combining marks, ZWJs, directional controls, or special symbols can carry real meaning. For security-sensitive identifiers, blocking certain characters is a **separate validation policy**, not a property of normalization.

## 15. Unicode Normalization Differs from Natural-Language Matching

`java.text.Normalizer` supports NFC/NFD/NFKC/NFKD. It does not automatically:

- Translate or transliterate all scripts.
- Perform stemming or lemmatization.
- Handle full Unicode case folding.
- Sort natural words across all locales.
- Detect and block all confusable/homoglyph attacks.
- Handle all accent-omitted typing patterns linguistically.

When language-sensitive collation is needed, use `java.text.Collator` or an i18n library like ICU. When advanced search is needed, use a dedicated text analyzer. Whatever algorithm is used, separate **comparison results** from **the value stored for display**.

Never use the exact same indexing pipeline for every field when purposes differ: personal names, usernames, free text, SKU codes, phone numbers, and legal documents have very different requirements.

## 16. Access Control and Retention for Original Data

Preserving original data properly for technical correctness does not grant permission to retain data indefinitely. For personal information, sensitive data, and user content:

- Store only the original fields necessary for product purposes.
- Apply access controls, encryption, and audit controls per policy.
- Define retention periods, edit/delete rights, and how indexes are updated when originals are deleted.
- Do not log sensitive originals just to debug normalization.
- When deleting an original upon request or policy, also clean up copies, indexes, and derived versions accordingly.

The rule “keep original” exists to **prevent unintended data loss**, not as an excuse to ignore privacy and data minimization.

## 17. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Storing only the NFKC result | Cannot recover `①` from `1` | Store original separately |
| Using searchKey as the display name | Loses accents, capitalization, or text styling | Render original |
| Thinking NFC preserves raw UTF-8 bytes | Loses original code point/byte sequence | Separate canonical equivalence from raw identity |
| Using lowercasing without controlling locale | Inappropriate or unstable results | Specify locale/case policy explicitly |
| Assuming searchKey is unique by default | Wrongly merges multiple originals | Define identity rules and handle collisions |
| Stripping accents directly on original names | Loses semantic/linguistic distinctions | Generate derived keys only when permitted |
| Changing index rules without rebuilding | Old/new keys incompatible | Store ruleVersion and recompute from original |
| Using a normalized hash to prove unchanged source | Fails to prove byte-for-byte integrity | Hash the protected source bytes |
| Keeping only `String` when original file preservation is needed | Cannot reproduce encoding/BOM or malformed bytes | Store bytes with required metadata |
| Treating Normalizer as a complete security filter | Confusable/validation risks remain | Design separate validation and security controls |
| Retaining originals indefinitely | Increases personal data exposure | Enforce retention/access/deletion policies |

## 18. Testing

Cases to include in regression test suites:

1. **Canonical:** `"\u00E9"` and `"e\u0301"` differ raw, match after NFC.
2. **Compatibility:** `"①"` and `"1"` both NFKC to `"1"`.
3. **Fullwidth:** `"ＡＢＣ"` becomes `"ABC"` in the derived key while original remains intact.
4. **Case:** `"ABC"` and `"abc"` can match on a lowercase key.
5. **Locale:** Turkish `"I"` behaves differently under lowercasing than some other locales.
6. **Diacritics:** `"Café"` and `"Cafe"` can match if the pipeline intentionally strips accents.
7. **Identity:** multiple record IDs can share a searchKey, and any merging decision belongs to business logic.
8. **Display:** after any query, UI renders `original`, never `searchKey`.
9. **Versioning:** when changing algorithms, new keys can be rebuilt from originals.
10. **Integrity:** byte-level hashing runs on the exact bytes required by contract to be preserved.
11. **Malformed input:** decoding/validation follows an explicit policy.
12. **Privacy:** deleting original also handles indexes and derived versions per policy.
13. **Multilingual:** test with Vietnamese, emoji, other scripts, and accented name variants.
14. **Backward compatibility:** changing the indexing algorithm does not silently alter display text.

### Exercises

- Add `①`, `1`, `ＡＢＣ`, `ABC` to a list and count distinct `searchKey` groups after NFKC + lowercase. Explain why the group count is smaller than the original count.
- Create a dedicated accent-free search function using `Normalizer.Form.NFD` and combining-mark stripping, while never storing its output into the display-name field.
- Write a hypothetical migration from `nfkc-lower-v1` to `nfkc-lower-strip-v2`: recompute from `original`, generate a report of new collisions, and outline a rollback plan.
- Compare UTF-8 bytes of `"\u00E9"` and `"e\u0301"` before and after NFC. Pick the right method for byte-level auditing.
- Design a case-insensitive username rule that preserves the verbatim display name; describe how to detect collisions during registration.
- Discuss one scenario where altering the original is allowed by contract and one scenario where it must stay untouched (authorial text or legal records).

## 19. Summary

**Original data** and **derived data** must be separated right in the storage model. NFC/NFD can lose original code point/byte sequence details even while preserving canonical equivalence; NFKC/NFKD can collapse compatibility characters; lowercasing, accent stripping, transliteration, or whitespace simplification remove even more distinctions.

Store `original` in the form matching your contract, build `searchKey` with an explicit algorithm, preserve a one-to-many relationship when collisions occur, version your pipeline, and alter `original` only under an approved policy. If byte-for-byte identity must be preserved, safeguard the original at the byte level rather than relying solely on a Java `String`.

**Takeaway:** use normalization to **support comparison and search**, never trading away **verbatim reproducibility** unintentionally for mere convenience.

## References

- [Oracle JDK 21 — Normalizer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/Normalizer.html)
- [Oracle JDK 21 — String](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html)
- [Oracle JDK 21 — Locale](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.html)
- [Oracle JDK 21 — StandardCharsets](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/StandardCharsets.html)
- [Unicode UAX #15 — Normalization Forms](https://www.unicode.org/reports/tr15/)
