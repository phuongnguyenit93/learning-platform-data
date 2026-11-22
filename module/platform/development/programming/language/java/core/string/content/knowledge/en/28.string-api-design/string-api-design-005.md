# Separating Raw Data, Normalized Data, and Display Values in String API Design

## Objectives

In real-world applications, the same string can serve three different roles: evidence of what the user submitted, a normalized value for searching/matching, and text displayed to the reader. When all three are collapsed into a single `String` variable and repeatedly overwritten, the application easily loses data, mismatches lookups, or displays something other than what the user intended.

After this lesson, you will know how to:

- Distinguish **raw/original values**, **normalized/canonical keys**, and **display values**.
- Clearly choose policies for `strip()`, Unicode normalization via `Normalizer`, case conversion via `Locale`, and the limits of these transformations.
- Design Java 17 APIs with immutable data without losing the original input.
- Handle search, duplicate detection, storage, policy changes, and security without corrupting text.
- Write tests for visually similar Unicode strings, whitespace, and edge-case values.

## 1. Three data roles that should not be mixed

For example, a user enters a display name with leading/trailing spaces and the letter `é` represented as `e` plus a combining mark:

~~~text
Received data:    "  Café  "
                      ↓
Raw/original:     "  Café  "      // keep the received String intact
                      ↓
Normalized key:   "café"          // example policy: strip + NFC + lowercase ROOT
                      ↓
Display value:    "Café"          // example policy: strip + NFC, preserve original casing
~~~

In the example, `"Café"` uses two code points for `e` and the acute accent, whereas `"Café"` uses one code point `é`. To the naked eye they can look identical even though their code sequences differ.

| Layer | Question the value answers | What usually needs to be preserved |
| --- | --- | --- |
| **Raw** | "What exactly did the system receive?" | Characters, whitespace, casing, diacritics, code unit order after decoding |
| **Normalized** | "Are two values considered equivalent for this business case?" | Deterministic, reproducible normalization rules suitable for lookup keys |
| **Display** | "What should the reader see in this context?" | Readability, locale/context appropriateness, without destroying original data |

These are **roles**, not three mandatory steps for every data field. Some fields display exactly as raw; some identifier keys must not discard casing; some sensitive data must match byte for byte. An API must define a dedicated policy for each field kind.

**Raw in this lesson means the `String` after the application has decoded the input.** If the requirement is to store exact raw bytes for digital signatures, encoding inspection, or legal compliance, also retain the original bytes and charset metadata. A decoded `String` does not guarantee 100% reconstruction of the original bytes when the source contains invalid data or uses multiple encodings.

## 2. Why you should not overwrite the original variable with normalized data

An approach that easily loses information:

~~~java
String name = requestName;
name = name.strip();
name = name.toLowerCase();
save(name); // Only the transformed version remains; the user's original input is lost.
~~~

Potential issues:

- `strip()` removes whitespace per `Character.isWhitespace` at both ends. This may be right for a display name, but wrong for free-form text, security codes, or fields with meaningful whitespace.
- `toLowerCase()` does not merely swap uppercase letters for lowercase; its default behavior depends on the environment's `Locale.getDefault()`, which can produce different results across machines or users.
- Unicode normalization can alter the code unit sequence; some compatibility normalizations also change character presentation.
- When users want to review or edit exactly what they entered, you no longer have the original source.

A more controllable model:

~~~java
String raw = requestName;
String normalized = normalizeForLookup(raw);
String display = prepareForDisplay(raw);
~~~

Do not treat `normalized` as "the one true string" in every situation. It is the output **under a specific policy**, such as a user lookup key or a label comparison key. Each policy needs a clear purpose, transformation order, and tests.

## 3. Java 17+ example: raw, normalized, and display

Illustrative policy for a **non-empty label name**:

1. Keep the user's input `String` intact.
2. When producing the display value, remove whitespace at both ends with `strip()` and normalize Unicode to **NFC**; preserve the user's chosen casing.
3. When producing the lookup key, take the value processed in step 2 and call `toLowerCase(Locale.ROOT)` to obtain a stable locale-neutral key.

Save the following program to `TextLayersDemo.java`:

~~~java
import java.text.Normalizer;
import java.util.Locale;

public class TextLayersDemo {
    static String toDisplay(String raw) {
        return Normalizer.normalize(raw.strip(), Normalizer.Form.NFC);
    }

    static String toLookupKey(String raw) {
        return toDisplay(raw).toLowerCase(Locale.ROOT);
    }

    public static void main(String[] args) {
        String raw = "  Cafe\u0301  ";

        String display = toDisplay(raw);
        String key = toLookupKey(raw);

        System.out.println("Raw length: " + raw.length());
        System.out.println("Display: " + display);
        System.out.println("Lookup key: " + key);
        System.out.println("Raw retained: " + raw.equals("  Cafe\u0301  "));
        System.out.println("Same key: "
                + key.equals(toLookupKey("CAFÉ")));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 TextLayersDemo.java
java TextLayersDemo
~~~

Output:

~~~text
Raw length: 9
Display: Café
Lookup key: café
Raw retained: true
Same key: true
~~~

Explanation:

- `"  Cafe\u0301  "` has 9 UTF-16 code units: two spaces, `C`, `a`, `f`, `e`, one combining mark, and two spaces.
- `strip()` removes leading/trailing whitespace per the example policy.
- `Normalizer.normalize(..., Normalizer.Form.NFC)` composes `e` + acute accent into `é` when a canonical precomposed form exists.
- `toLowerCase(Locale.ROOT)` produces `"café"` from `"Café"`, independent of the machine's default locale.
- The `raw` value **is not mutated**, because `String` is immutable; every transformation returns a new `String` or reuses an existing value if no change is needed.
- `"CAFÉ"` and `"  Cafe\u0301  "` share the same key under the current policy, while their display forms can still differ.

`Locale.ROOT` works well for many language-neutral key policies. It is **not** equivalent to full *Unicode case folding* or linguistic collation. When searching people's names in Vietnamese, Turkish, or another specific language, evaluate the policy based on actual search and collation requirements.

## 4. Unicode normalization: how NFC and NFKC differ

Java provides `java.text.Normalizer` with forms `NFC`, `NFD`, `NFKC`, and `NFKD`:

| Form | General Purpose | Example Use Case |
| --- | --- | --- |
| `NFC` | Canonical decomposition followed by canonical composition | Normalizing string representation when preserving canonical equivalence |
| `NFD` | Canonical decomposition | Analyzing combining marks or specialized processing |
| `NFKC` | Compatibility decomposition followed by canonical composition | Keys with a policy that also folds compatibility characters |
| `NFKD` | Compatibility decomposition | Specialized processing needing compatibility characters decomposed |

**NFC** is usually a safer starting point for general text because it preserves canonical equivalence. **NFKC** can merge characters that differ in presentation or function, so a business decision is required before using it.

Java 17 example:

~~~java
import java.text.Normalizer;

public class UnicodeFormDemo {
    public static void main(String[] args) {
        String decomposed = "Cafe\u0301";
        String composed = "Café";

        System.out.println(decomposed.equals(composed));
        System.out.println(Normalizer.normalize(
                decomposed, Normalizer.Form.NFC).equals(composed));

        String circledOne = "①";
        System.out.println(Normalizer.normalize(
                circledOne, Normalizer.Form.NFC));
        System.out.println(Normalizer.normalize(
                circledOne, Normalizer.Form.NFKC));
    }
}
~~~

Save `UnicodeFormDemo.java` and run:

~~~bash
javac -encoding UTF-8 UnicodeFormDemo.java
java UnicodeFormDemo
~~~

Output:

~~~text
false
true
①
1
~~~

The two ways of writing `é` are not `equals` initially, but become equal after NFC; `NFKC` turns the circled digit one into `1`, whereas `NFC` keeps it unchanged. If `①` and `1` are two distinct product codes, NFKC causes key collisions—so do not apply NFKC broadly without a deliberate policy.

### Does transformation order matter?

Yes. `strip`, Unicode normalization, case conversion, diacritic removal, and whitespace replacement do not automatically commute in all cases. **Define a formal pipeline**, test across diverse inputs, and version the pipeline if keys are persisted long-term. For example, if case conversion introduces additional Unicode characters, some systems normalize back to NFC at the end to guarantee the desired output form.

For the simple example in this lesson:

~~~text
raw
  ├── raw: keep intact
  ├── display: strip → NFC
  └── lookupKey: strip → NFC → lowercase(Locale.ROOT)
~~~

This is an **illustrative application rule**, not a mandatory order imposed by Java.

## 5. Separating transformations to use each for the right purpose

### Case A: display name and lookup key

A catalog application may want to display `"Café"` while still matching when a user types `"café"`. Store the submitted text, display it per product policy, and match using a dedicated key.

~~~text
original    = "  Café "
display     = "Café"
searchKey   = "café"
~~~

Do not strip diacritics by default. If diacritic-insensitive search is needed, design a separate **search index** and test it with supported languages. Removing all combining marks after NFD can change word identities in many languages and is not guaranteed to produce proper spellings for all accented letters.

### Case B: identifiers with a fixed format

If an item code must strictly match `[A-Z0-9_-]+`, the rule may be to reject whitespace, lowercase letters, or invalid Unicode rather than silently `strip`ping and uppercasing. For fields like order codes, **validate first and canonicalize deliberately** to avoid two distinct valid codes being unintentionally merged.

~~~java
static boolean isValidCode(String candidate) {
    return candidate != null
            && candidate.matches("[A-Z0-9_-]+");
}
~~~

This policy considers `"ID_42"` valid and `" id_42 "` invalid; this is a **business decision**, not a limitation of the `String` API.

### Case C: free-form text content

Messages, annotations, addresses, or notes may need to preserve line breaks, spaces, and capitalization. In those cases, raw and display can be the same original string. A search key or full-text index can be generated independently, but it should not overwrite the author's content.

### Case D: passwords, tokens, and signed data

Do not automatically `trim`, `strip`, lowercase, or Unicode-normalize passwords/tokens unless the authentication protocol explicitly specifies it. Altering characters can collapse two distinct secrets into one, break signature verification, or break compatibility. Where byte-level processing is required, preserve the exact byte/protocol representation; passwords must be processed and stored using dedicated hashing mechanisms rather than storing raw values unnecessarily.

## 6. Designing immutable value types to avoid mixing data layers

One way to reduce mistakes is to have an object hold the information layers with clear names. This example chooses a policy for a **catalog label**; do not copy it verbatim for every string type in a system.

Save as `LabelValueDemo.java`:

~~~java
import java.text.Normalizer;
import java.util.Locale;
import java.util.Objects;

final class LabelValue {
    private final String raw;
    private final String normalizedKey;
    private final String display;

    private LabelValue(String raw) {
        this.raw = Objects.requireNonNull(raw, "raw");

        String prepared = Normalizer.normalize(
                raw.strip(), Normalizer.Form.NFC);

        if (prepared.isEmpty()) {
            throw new IllegalArgumentException("Label must not be blank");
        }

        this.display = prepared;
        this.normalizedKey = prepared.toLowerCase(Locale.ROOT);
    }

    public static LabelValue of(String raw) {
        return new LabelValue(raw);
    }

    public String raw() {
        return raw;
    }

    public String normalizedKey() {
        return normalizedKey;
    }

    public String display() {
        return display;
    }
}

public class LabelValueDemo {
    public static void main(String[] args) {
        LabelValue first = LabelValue.of("  Cafe\u0301 ");
        LabelValue second = LabelValue.of("CAFÉ");

        System.out.println(first.raw().length());
        System.out.println(first.display());
        System.out.println(first.normalizedKey());
        System.out.println(second.display());
        System.out.println(first.normalizedKey()
                .equals(second.normalizedKey()));
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 LabelValueDemo.java
java LabelValueDemo
~~~

Output:

~~~text
8
Café
café
CAFÉ
true
~~~

Here `raw()` always returns the data the application received. `display()` prepares it for presentation per the label policy; `normalizedKey()` serves matching without replacing the display value. The `final` fields keep all three values consistent from construction. There are no setters silently mutating one layer while the others remain stale.

The example object illustrates the `prepared.isEmpty()` check. In a real API, you also must decide on maximum length, control characters, non-breaking spaces, special Unicode formats, and validation errors. `String.strip()` does not remove every kind of space humans might imagine; for example, certain `NO-BREAK SPACE` characters are not treated as whitespace to remove by `Character.isWhitespace`.

**Do not unconditionally use `normalizedKey` in place of a global identifier.** If two distinct labels produce the same normalized key, they may be treated as duplicates in search while still being two separate records requiring distinct IDs.

## 7. API contract design: clear naming and separation

Avoid a generic `value` field when the product has three distinct purposes. A DTO can be used:

~~~java
public record LabelResponse(
        String original,
        String normalizedKey,
        String displayText) {}
~~~

The snippet above is a valid Java 17 record declaration illustrating the **data structure**; it is not a standalone runnable program and does not require returning every field to the client.

Several design principles:

- **Incoming request:** use names like `submittedText` or `rawText` when you need to store exactly what the user submitted.
- **Domain/value object:** a factory with a clear policy produces `normalizedKey`; treat that policy as part of the business contract.
- **UI response:** usually send only `displayText` and ID; do not send raw if raw may contain sensitive data or if the viewer is not permitted to access it.
- **Search/lookup:** can accept a user query, normalize **the query with the same policy version**, and match against stored keys.
- **Audit:** if you need proof of the submitted input, store raw per policy and enforce access/retention controls; do not dump secret data into logs just to "preserve the original".

An API should also clearly state: which Unicode form it returns, whether keys are case- and diacritic-sensitive, whether empty strings are allowed, and whether normalization happens at ingestion time or query time.

## 8. Persistence and long-term consistency

When storing raw, normalized, and display together in a database, decide which layer is the source of truth and when to recompute:

| Data Field | Example | Should be used for |
| --- | --- | --- |
| `raw_text` | `"  Café  "` | Tracing submitted data; editing/updating |
| `normalized_key` | `"café"` | Searching, filtering, policy-based duplicate checks |
| `display_text` | `"Café"` | UI output if a pre-prepared display value is stored |
| `normalization_version` | `"label-v1"` | Knowing which policy generated the key when algorithms change |

In many systems, there may be **no need to persist display separately** if it can always be derived quickly and deterministically from raw using the same policy. Conversely, if the display value is manually edited by an editor, a `Locale`-based translation, or derived from other sources, explicitly model its source and lifecycle.

### When changing a policy

Suppose keys previously used only `strip`, and later add lowercase and NFC:

1. Determine whether new keys cause **collisions**: `"Café"`, `"Café"`, and `"CAFÉ"` may all become `"café"`.
2. Check *unique constraints* and decide how to resolve colliding records before deployment.
3. Regenerate `normalized_key` or build a new index under the new version, ensuring read/write flows use the right version.
4. Do not overwrite `raw_text` solely to update the search key.
5. If query logic and storage logic use different policies, search results become unreliable; synchronize and test the migration.

**Idempotence** is a useful property: normalizing an already-normalized key with the same policy should yield the same result whenever possible. However, do not assume every custom chain of operations is idempotent; test it, especially when mixing multiple rounds of diacritic/whitespace replacement and case conversion.

### The gap between Java and the database

Java `String.equals` compares code unit contents; a database may use a case-insensitive or accent-insensitive collation. Thus, even when `normalizedKey` values differ in Java, a unique index under the database's collation may still treat them as equal (or vice versa). Explicitly choose storage, collation, unique constraints, and application-side normalization. If keys genuinely require deterministic binary comparison, configure storage/indexing appropriately for the specific DBMS.

## 9. Display values also depend on context

`displayText` is not necessarily just `strip()` and NFC. It may need:

- Viewer's language or locale: language names, numbers, dates, currencies, and messages can differ.
- UI formatting rules: adding separators, truncating long strings, multi-line formatting, bilingual display.
- Authorization: some fields need partial masking when displayed, while raw is kept in protected storage.
- HTML, JSON, or log contexts: each place has different **output escaping** rules.

Distinguish **content transformations for display meaning** from **escaping for the output context**. For example, when rendering `displayText` on the web, the UI must ensure text data is properly escaped to prevent HTML/script injection. Do not store HTML-escaped strings as a general "normalized" form; doing so can cause double escaping across multiple output channels.

Similarly, use prepared statements to pass values in SQL queries. Unicode normalization or lowercasing does not replace output control, validation, or authorization.

## 10. Common mistakes

**1. Keeping only normalized and losing raw.** Users cannot recover what they entered; the system struggles to trace bugs or apply a new policy. Keep raw when product and retention policies permit, and enforce access control.

**2. Using the normalized key for display.** If `"Nguyễn Văn An"` is lowercased or stripped of diacritics in the lookup key, displaying that key directly distorts the person's name. Use a display value under its own policy.

**3. Treating trim/strip as harmless.** Whitespace can be meaningful in notes, codes, or tokens; `strip` also differs from `trim` in handled characters. Define rules per field rather than creating one `normalizeEverything` function for the whole application.

**4. Omitting Locale during case conversion.** `toLowerCase()` uses the default locale and can vary across environments. For locale-neutral keys, use `toLowerCase(Locale.ROOT)`; for language-specific text, properly evaluate `Locale` and collation.

**5. Confusing NFC with NFKC.** NFKC can turn compatibility characters such as `①` into `1`, causing unwanted loss of distinction. Choose the Unicode form per policy and test visually similar examples with different meanings.

**6. Treating lowercasing as full case folding/collation.** `toLowerCase(Locale.ROOT)` does not automatically solve all Unicode/linguistic cases. When language-aware matching is needed, consider `Collator` or an appropriate search indexing engine.

**7. Rolling out a new policy without detecting duplicate keys.** Adding Unicode normalization and lowercasing can map multiple distinct records to the same key. Check collisions, unique indexes, and migration paths before changing policies.

**8. Ad-hoc normalization of passwords/tokens/signatures.** Doing so alters secret data or breaks signatures. Transform only when required by the protocol specification.

**9. Separating raw/normalized/display but forgetting to sync after edits.** When a user updates raw, every corresponding derived value must be updated or invalidated. Immutable factories and centralized conversion logic help prevent this bug.

**10. Logging full user data indiscriminately.** Raw may contain personal information. When measuring normalization errors, prefer logging error codes, transformation types, and safe metadata; govern raw storage according to authorization and data policies.

## 11. Practice exercises and testing

With the lookup policy `strip() → NFC → toLowerCase(Locale.ROOT)` and display policy `strip() → NFC`, predict the outputs:

| Raw Input | Display | Lookup Key | Notes |
| --- | --- | --- | --- |
| `"  Café  "` | `"Café"` | `"café"` | Leading/trailing spaces removed |
| `"Cafe\u0301"` (decomposed) | `"Café"` | `"café"` | NFC composes to canonical form |
| `"CAFÉ"` | `"CAFÉ"` | `"café"` | Preserves uppercase in display |
| `"  "` | `""` | `""` | The value object example above rejects empty display |
| `"Alice"` | `"Alice"` | `"alice"` | Case-insensitive in lookup |
| `"alice"` | `"alice"` | `"alice"` | Shares lookup key with `Alice` |

You can use the following self-check program (save to `TextLayerChecks.java`):

~~~java
import java.text.Normalizer;
import java.util.Locale;

public class TextLayerChecks {
    static String display(String raw) {
        return Normalizer.normalize(raw.strip(), Normalizer.Form.NFC);
    }

    static String key(String raw) {
        return display(raw).toLowerCase(Locale.ROOT);
    }

    public static void main(String[] args) {
        String[] inputs = {"  Café  ", "Cafe\u0301", "CAFÉ",
                "  ", "Alice", "alice"};

        for (String input : inputs) {
            System.out.println("[" + display(input) + "] -> ["
                    + key(input) + "]");
        }
    }
}
~~~

Run with `javac -encoding UTF-8 TextLayerChecks.java` and `java TextLayerChecks`. Output:

~~~text
[Café] -> [café]
[Café] -> [café]
[CAFÉ] -> [café]
[] -> []
[Alice] -> [alice]
[alice] -> [alice]
~~~

Extended exercise: create an additional test suite for `null`, non-breaking spaces, case-sensitive identifiers, the `①` character under NFC/NFKC, and Vietnamese data with decomposed diacritics. Clearly document which fields are normalized, which must be preserved verbatim, and which are displayed differently from raw.

## Checklist before publishing an API

1. Define precisely whether **raw** is the decoded string or also original bytes, and whether that data must be stored/audited.
2. Give **normalized key** a distinct name and type; document pipeline order, Unicode form, Locale, and policy version.
3. Decide whether **display** is derived from raw, user-edited values, or translated resources; ensure lookup keys are never accidentally displayed.
4. Check duplicates and collation in both Java and the database; prepare collision handling when changing algorithms.
5. Synchronize derived values after raw updates, and test idempotence, Unicode, whitespace, null, empty values, and equivalent strings.
6. For passwords, tokens, signed data, and sensitive information, follow dedicated security contracts; do not mechanically apply the display-name pipeline.
7. Escape for the output context (HTML/JSON/SQL), enforce access control on raw data, and avoid logging unnecessary content.

## Official references

- [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [Java SE 17 — Normalizer and Unicode normalization forms](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html)
- [Java SE 17 — Locale](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html)
- [Java SE 17 — Collator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Collator.html)
- [Java SE 17 — Character](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html)