# Impact of Unicode Normalization on Comparison, Search, and Data Keys in Java

## 1. Same Visual Display, Different Binary Data

In multilingual applications, two strings can **look alike** yet not share the same sequence of Unicode characters. This directly affects:

- Comparisons via `String.equals()`, `compareTo()`, `equalsIgnoreCase()`.
- Searching via `contains()`, `indexOf()`, text indexes, or search engines.
- Keys in `HashMap`, `HashSet`, caches, data tables, UNIQUE indexes, slugs, and identifiers.
- Consistency when a system receives input from keyboards, browsers, files, APIs, or multiple operating systems.

For example, the letter **é** can appear in two representations:

```text
Precomposed form:  U+00E9          é
Decomposed form:   U+0065 U+0301   e + combining acute accent
```

These two sequences are **canonically equivalent** under Unicode, yet differ in character code count. In Java:

```java
String composed = "caf\u00E9";
String decomposed = "cafe\u0301";

System.out.println(composed.equals(decomposed)); // false
System.out.println(composed.length());           // 4
System.out.println(decomposed.length());         // 5
```

`String.equals()` compares stored character contents without automatically normalizing Unicode. `String.length()` counts **UTF-16 code units**, not user-perceived characters. Therefore, merely looking at the UI or relying on font rendering is not enough to determine whether two strings represent the same **data key**.

The goal of this lesson is to determine **when normalization is needed**, use `java.text.Normalizer` in Java 17+, choose comparison/search rules, and avoid turning normalization into an operation that causes data loss or introduces identifier vulnerabilities.

## 2. What Is Unicode Normalization?

*Unicode normalization* converts strings into one of the forms defined by the Unicode Standard so that equivalent representations can be handled consistently. Java provides:

```java
import java.text.Normalizer;

String normalized =
        Normalizer.normalize(input, Normalizer.Form.NFC);
```

Main forms:

| Form | Name | General Meaning | Common Use Cases |
|---|---|---|---|
| `NFD` | Canonical Decomposition | Decomposes characters by canonical equivalence | Processing combining marks, character analysis |
| `NFC` | Canonical Decomposition + Composition | Canonical decomposition followed by recomposition per Unicode rules | Storing/comparing text when a stable canonical form is desired |
| `NFKD` | Compatibility Decomposition | Also decomposes compatibility characters | Only when business semantics permit collapsing presentational forms |
| `NFKC` | Compatibility Decomposition + Composition | Compatibility decomposition followed by recomposition | Certain explicitly designed search workflows or identifier normalizations |

**Canonical equivalence differs from compatibility equivalence.** NFD/NFC rely on canonical equivalence, whereas NFKD/NFKC can discard distinctions between characters considered compatible in presentational form.

For example, NFKC can transform:

```text
Original chars:  ﬁ   Ａ   ①
After NFKC:      fi  A    1
```

NFKC **does not only touch accented letters**; it can alter letterforms, digits, superscripts/subscripts, and ligatures. Therefore, **never default to NFKC to overwrite user text data**. Choosing a form must follow an identifier contract or search policy.

`Normalizer.isNormalized(text, form)` checks whether a string is already in the required form, useful for validation, controlled logging, and optimization when needed.

## 3. A Java 17+ Program Demonstrating the Difference

Create `UnicodeEqualityDemo.java`:

```java
import java.text.Normalizer;
import java.util.HashMap;
import java.util.Map;

public class UnicodeEqualityDemo {
    public static void main(String[] args) {
        String composed = "caf\u00E9";
        String decomposed = "cafe\u0301";

        System.out.println(
                "rawEquals=" + composed.equals(decomposed));
        System.out.println(
                "lengths=" + composed.length()
                        + "," + decomposed.length());

        String left = Normalizer.normalize(
                composed, Normalizer.Form.NFC);
        String right = Normalizer.normalize(
                decomposed, Normalizer.Form.NFC);

        System.out.println("nfcEquals=" + left.equals(right));
        System.out.println(
                "nfcLengths=" + left.length()
                        + "," + right.length());

        Map<String, String> map = new HashMap<>();
        map.put(composed, "found");

        System.out.println("lookupRaw=" + map.get(decomposed));
        System.out.println("lookupNfc=" + map.get(right));

        String compatibility = "X\uFB01\uFF21\u2460";
        System.out.println(
                "nfkc=" + Normalizer.normalize(
                        compatibility, Normalizer.Form.NFKC));
    }
}
```

Run:

```bash
javac UnicodeEqualityDemo.java
java UnicodeEqualityDemo
```

Output verified with JDK:

```text
rawEquals=false
lengths=4,5
nfcEquals=true
nfcLengths=4,4
lookupRaw=null
lookupNfc=found
nfkc=XfiA1
```

Explanation:

1. `composed` and `decomposed` share the same common visual rendering yet `equals()` returns `false`.
2. After normalizing both to `NFC`, they have identical content and `equals()` returns `true`.
3. `HashMap` stored the key in precomposed form, so querying with the decomposed form failed to match. Querying with the NFC-normalized form succeeded.
4. `NFKC` converts the ligature `ﬁ` into `fi`, fullwidth Latin `Ａ` into `A`, and circled digit `①` into `1`. This can be useful for flexible search, yet unsuitable for operations requiring verbatim preservation.

`HashMap` has no special Unicode rules for string keys: it relies on `String.equals()` and `hashCode()`. Two canonically equivalent strings are treated as the same key only when **the application proactively converts both to the same form**.

## 4. Comparison: equals, compareTo, equalsIgnoreCase, and Collator Differ

### `String.equals()`: Compares Exact Stored Content

`equals()` is the right comparison when the domain demands **exact character sequences**. It does not automatically fix casing, combining marks, or compatibility variants. Even when contents look identical, `equals()` can return `false` due to different Unicode representations.

Once you normalize **both sides** to an agreed form, `equals()` can test equality in the normalized space:

```java
static boolean canonicallyEqual(String a, String b) {
    return Normalizer.normalize(
            a, Normalizer.Form.NFC).equals(
            Normalizer.normalize(b, Normalizer.Form.NFC));
}
```

This is a **code snippet** to place in a class that imports `Normalizer`. With `NFC`, the intent is to compare canonically equivalent strings. It **does not** automatically strip accents, ignore case differences, or merge all look-alike characters.

### `String.compareTo()`: UTF-16 Order, Not Linguistic Sorting

`String.compareTo()` is not equivalent to dictionary ordering in a specific language. It is based on the comparison order of Java character code units. Even after NFC normalization, this order does not become proper lexical ordering for Vietnamese, French, or other accented languages.

Use `Collator` when the goal is **language-aware sorting or comparison**.

### `String.equalsIgnoreCase()`: Not Full Unicode Case Folding

`equalsIgnoreCase()` implements Java's case-insensitivity logic, which does not replace a full international canonicalization policy. For example, `Straße` and `STRASSE` have a special case-folding relationship in certain Unicode/linguistic rules, yet you cannot assume Java's `equalsIgnoreCase()` or `toLowerCase()` will always turn them into matching strings.

In addition, case-insensitive comparison and Unicode normalization are **two orthogonal dimensions**: strings with precomposed vs. combining marks still require a consistent normalization policy.

### `Collator`: Locale-Based Matching for UI and Flexible Search

`java.text.Collator` compares strings according to regional rules. Its `strength` setting controls which differences are considered:

- `PRIMARY`: typically ignores secondary differences such as accents and some case differences, depending on locale and rule set.
- `SECONDARY`: typically distinguishes accents while potentially ignoring case differences per locale.
- `TERTIARY`: typically also considers uppercase/lowercase and language-dependent styling differences.
- `IDENTICAL`: very strict distinction level; still not simply `String.equals()`.

The descriptions above are **general guidelines**, not an identical rule table across every language. Localization can alter how individual letters compare.

Example:

```java
Collator collator = Collator.getInstance(Locale.FRENCH);
collator.setStrength(Collator.PRIMARY);

boolean equivalentForSearch =
        collator.compare("cafe", "caf\u00E9") == 0;
```

With standard French collation rules, `equivalentForSearch` is `true` at PRIMARY strength; this is a **chosen matching rule**, not proof that the two strings have identical bytes or the same identity.

**Warning:** `Collator` is mutable and is not a default choice for implementing `equals/hashCode` on `HashMap` keys. Never use `Collator.compare(a,b)==0` in one place while storing/retrieving keys via `String.equals()` elsewhere and expect the two mechanisms to align.

## 5. Canonical Comparison and Linguistic Comparison Are Two Different Problems

Suppose we have three values:

```text
A: "café"   with U+00E9
B: "café"  with U+0065 + U+0301
C: "cafe"   without accent
```

- `A` and `B` are **canonically equivalent**. Converting both to NFC makes `equals()` return true.
- `A` and `C` are **not** canonically equivalent. NFC does not delete accents to produce `cafe`.
- An **accent-insensitive** search policy might want `A`, `B`, and `C` to all match. That is a separate search/collation requirement, not the definition of NFC.

Therefore, separate two responsibilities:

1. **Data key / identity:** defines when two values represent *the same entity*.
2. **Search / matching:** defines when a query *is relevant* to a record, even with differing accents, spelling, or casing.

A “search-friendly” mechanism intentionally allows more false positives than a unique-key mechanism. Never use loose search rules to override identity or merge records unless the business explicitly intends it.

## 6. Impact on HashMap, HashSet, and Caches

Standard `Map<String, V>` and `Set<String>` use `String.equals()/hashCode()`. Consequently, if one side uses NFC and another uses NFD, the following can happen:

- `map.get(key)` returns `null` even though the UI display looks right.
- `set.add(...)` accepts two visually identical strings as **two distinct elements**.
- Cache misses occur continuously across systems that generate text in different Unicode forms.
- Two accounts have identical display names yet different username keys if the system defines usernames by raw strings.

A simple canonicalization function for **text keys permitted to use NFC**:

```java
static String canonicalKey(String input) {
    Objects.requireNonNull(input, "input");
    return Normalizer.normalize(
            input, Normalizer.Form.NFC);
}
```

Use **the exact same function** on both insert and lookup:

```java
Map<String, String> accounts = new HashMap<>();

accounts.put(canonicalKey("caf\u00E9"), "account-42");

String account = accounts.get(
        canonicalKey("cafe\u0301"));
```

These two snippets are **code fragments**, requiring imports for `java.util.Objects`, `java.text.Normalizer`, `java.util.Map`, and `java.util.HashMap` along with the `canonicalKey` method in the class.

The key takeaway is not “NFC makes every key equal,” but rather **every path into the same key domain must follow the same policy**.

### Do Not Normalize on Read While Ignoring Writes

If legacy records were stored in raw NFD while new records use NFC, normalizing only on the request side **cannot fix** old indexes and will continue causing misses. A data migration plan and appropriate index/cache/key rebuild are required.

### Identity Keys Differ from Display Content

In a well-designed system, a display name can keep the user's preferred spelling for rendering; the internal key can be an immutable ID. If a unique username is needed, store a separate **canonical_username** built per defined policy instead of silently altering every display field.

Never mutate a key inside an active `HashMap` in the sense of “changing its key derivation while keeping old hashes”; `String` is immutable, yet changing key-computation logic across layers without reindexing/rebuilding still breaks logic.

## 7. Complete Java 17+ Example: Matching Keys After Normalization

Save as `CanonicalKeyDemo.java`:

```java
import java.text.Normalizer;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public class CanonicalKeyDemo {
    private static String key(String raw) {
        return Normalizer.normalize(
                raw, Normalizer.Form.NFC);
    }

    public static void main(String[] args) {
        String a = "caf\u00E9";
        String b = "cafe\u0301";

        Set<String> rawSet = new HashSet<>();
        rawSet.add(a);
        rawSet.add(b);
        System.out.println("rawSetSize=" + rawSet.size());

        Set<String> canonicalSet = new HashSet<>();
        canonicalSet.add(key(a));
        canonicalSet.add(key(b));
        System.out.println(
                "canonicalSetSize=" + canonicalSet.size());

        Map<String, Integer> counts = new HashMap<>();
        counts.put(key(a), 7);
        System.out.println("lookup=" + counts.get(key(b)));

        System.out.println("canonicalEquals=" +
                key(a).equals(key(b)));
    }
}
```

Run:

```bash
javac CanonicalKeyDemo.java
java CanonicalKeyDemo
```

Output:

```text
rawSetSize=2
canonicalSetSize=1
lookup=7
canonicalEquals=true
```

This illustrates the **direct impact on Set/Map identity**. When a username policy treats two canonically equivalent Unicode forms as one, normalizing before storing detects duplicates. Conversely, when importing product lists or text content where **two encodings must remain separate**, normalization may not be the desired behavior.

**Be careful when merging data:** if two legacy records were distinct as raw strings yet collapse to the same NFC key, the migration needs a conflict-resolution policy. Never silently drop one record or randomly pick a “winning” account upon detecting a collision.

## 8. Searching Inside Strings: contains and indexOf Can Miss Matches

Basic `String` methods like `contains()` and `indexOf()` search literal character sequences rather than Unicode equivalence.

Example:

```java
String text = "cafe\u0301";
String query = "\u00E9";

System.out.println(text.contains(query)); // false
```

In the text, a user sees `café` and expects searching for `é` to match. Yet the text uses two code points (`e` + combining mark), while the query contains one precomposed code point `é`.

One approach for **exact search with unified canonical form**:

```java
String normalizedText = Normalizer.normalize(
        text, Normalizer.Form.NFC);
String normalizedQuery = Normalizer.normalize(
        query, Normalizer.Form.NFC);

boolean found = normalizedText.contains(normalizedQuery);
```

`found` is `true`. Before applying this technique to a large document store, consider:

- Normalize both the **document** and the **query**, never just one side.
- Pick a single form; do not mix NFC data with NFKC data and compare them as if they belonged to a consistent system.
- Normalize/index data at ingestion time rather than repeating the cost on every query, if performance requires it.
- If you need locale-aware search with accent folding, case folding, or word variants, `String.contains()` after NFC is **not enough**; use an engine with an appropriate analyzer/collation.

### Match Positions on a Normalized String Are Not Raw String Positions

An important pitfall for search-result highlighting:

```text
raw:        "cafe" + combining acute
NFC:        "café"
raw length: 5
NFC length: 4
```

An `indexOf()` call on the normalized string returns an offset in **UTF-16 units of the normalized string**. It does not map automatically back to an offset in the original string for placing highlights. NFD/NFC/NFKC can change length, order, or code point sequences.

If the UI must highlight the exact span in raw text, **maintain an offset map** in the tokenizer/search pipeline, or render from the same normalized version that built the index with an explicit selection-preservation rule. Never slice a raw string using indices from a search index unless you are sure the offsets match.

## 9. Collator and a Java 17+ Example for Flexible Search

Another problem is when a user types `cafe` wanting to find `café`. NFC does not remove accents. `Collator` with `Locale.FRENCH` and `PRIMARY` strength can treat these forms as equivalent in linguistic comparison.

Create `LocaleComparisonDemo.java`:

```java
import java.text.Collator;
import java.text.Normalizer;
import java.util.Locale;

public class LocaleComparisonDemo {
    public static void main(String[] args) {
        String plain = "cafe";
        String accented = "caf\u00E9";
        String decomposed = "cafe\u0301";

        System.out.println("rawContains=" +
                decomposed.contains("\u00E9"));

        String nfcText = Normalizer.normalize(
                decomposed, Normalizer.Form.NFC);
        System.out.println("nfcContains=" +
                nfcText.contains("\u00E9"));

        Collator collator =
                Collator.getInstance(Locale.FRENCH);

        collator.setStrength(Collator.PRIMARY);
        System.out.println("primaryEquals=" +
                (collator.compare(plain, accented) == 0));

        collator.setStrength(Collator.TERTIARY);
        System.out.println("tertiaryEquals=" +
                (collator.compare(plain, accented) == 0));
    }
}
```

Compile/run:

```bash
javac LocaleComparisonDemo.java
java LocaleComparisonDemo
```

Verified output in a JDK environment with matching locale data:

```text
rawContains=false
nfcContains=true
primaryEquals=true
tertiaryEquals=false
```

Interpretation:

- `rawContains` is false because the two encodings of the accented letter do not share the same character sequence.
- `nfcContains` is true because both were normalized to the same form.
- At `PRIMARY`, the French collator in the example ignores this accent difference.
- At `TERTIARY`, the distinction between `cafe` and `café` is considered again.

Note that `Collator.compare(a,b)==0` indicates **equivalence under the collation configuration**, not proof that two strings have identical Unicode code points or represent the same person or account.

`Collator` supports configuring decomposition and strength; exact behavior depends on locale/provider and collation data versions. For large search indexes, use an engine with an appropriate analyzer and test with real data; `Collator` is a comparison/sorting tool, not a full-text search system with stemming, tokenization, and ranking.

## 10. Unicode Normalization Does Not Mean Lowercasing

Many systems want case-insensitive usernames. Here, NFC **is not enough**:

```text
"User" and "user" are both already NFC, yet are not equal via String.equals().
```

An illustrative pipeline for a **simple case-insensitive key**:

```java
static String simpleCanonicalUsername(String raw) {
    String lowered = raw.toLowerCase(Locale.ROOT);
    return Normalizer.normalize(
            lowered, Normalizer.Form.NFC);
}
```

This is only an **example policy**, not full Unicode case folding, and not automatically suitable for every language. Picking `Locale.ROOT` avoids machine default-locale dependencies when handling “language-neutral” identifiers.

### Why State Explicitly That This Is Not Full Case Folding?

Java `String.toLowerCase(Locale.ROOT)` can map a single character to **multiple code points**. For example, uppercase `İ` (Latin Capital Letter I with Dot Above, U+0130) converted to lowercase under `Locale.ROOT` can produce `i` + combining dot above, rather than a single ASCII `i`.

Conversely, `Straße` and `STRASSE` do not become identical solely through simple Java lowercasing. Uppercase/lowercase rules can depend on language, case-folding mode, and Unicode version.

If a product requires **exact Unicode caseless matching per a specific standard**, adopt a proper Unicode case-folding policy, potentially using a dedicated library supporting full case folding and a pinned Unicode data version. Never change the canonical username algorithm after accounts exist without a migration and collision-handling plan.

### Order of Transformations Can Matter

Case mapping sometimes introduces new combining characters. Thus, if a pipeline combines lowercasing and normalization, define an **official order** and keep it consistent. For example, `lowercase → NFC` differs in policy from `NFC` alone or `lowercase` alone. Some identifier systems follow dedicated standards (such as IDNA for domains) and cannot be replaced by these two calls.

## 11. NFC vs. NFKC: Which Is Right for Data Keys?

Two commonly confused policies:

**Policy A: canonical equivalence.** If a system wants precomposed `café` and `cafe + combining acute` to be treated as the same string, using NFC is reasonable. It does not equate `cafe` with `café`, and does not attempt to unify every visually similar glyph.

**Policy B: compatibility equivalence.** If a system wants fullwidth characters, ligatures, or styled digits to collapse with standard forms, NFKC can be a step in a **designed and documented** pipeline.

| String | NFC | NFKC | Risk if used for identity |
|---|---|---|---|
| `caf\u00E9` precomposed | `café` | `café` | Usually intended canonical equivalence |
| `cafe\u0301` decomposed | `café` | `café` | Merges two canonically equivalent forms |
| `ﬁ` | Keeps `ﬁ` | `fi` | Merges ligature with two letters |
| `Ａ` (fullwidth A) | Keeps `Ａ` | `A` | Merges fullwidth style |
| `①` | Keeps `①` | `1` | Merges circled digit with ordinary digit |

NFKC can destroy meaningful distinctions in documents, designs, or user content. Use it only when the **application domain** confirms those differences do not affect identity.

Never treat Unicode normalization as a tool to strip all dangerous characters, solve homographs, or eliminate all visual differences. There are **confusable** characters that look identical yet are not merged by Unicode normalization. Conversely, NFKC can merge pairs an application needed to keep distinct.

## 12. Accent-Free Search Requires Its Own Policy

Some applications want `"hoa"` to match `"hòa"` or `"hoà"`. A *search key* can be constructed by:

1. Normalizing to NFD to expose combining marks.
2. Stripping combining marks per search rules.
3. Normalizing to a chosen output form.
4. Optionally applying case folding or intentional replacements.

An illustrative code idea:

```java
String stripped = Normalizer.normalize(
        input, Normalizer.Form.NFD)
        .replaceAll("\\p{M}+", "");
```

**Mandatory warning:** this only deletes combining marks; **it is not a complete accent-free search algorithm for all languages**. It can erase semantic distinctions, does not convert all barred/special letters (such as `đ`) to ASCII, and can break text in languages where combining marks are essential letters.

For Vietnamese, stripping accents for search must account for `đ/Đ`, acute/grave/hook/tilde/dot-below tones, vowel-shaping marks, and phonetic distinction policies. The system must explicitly decide whether `đ` and `d` should match; never silently assume that is a canonical consequence of NFC/NFD.

In search systems, store the **original text** for display and build a separate **search index** using a controlled analyzer. A search index may be “looser” than identity, yet must never serve as the unique key of an account or proof that two entities are identical.

## 13. Stored Data and UNIQUE: Handle It at the Write Boundary

When storing strings from multiple sources, the following can occur:

- Client A sends precomposed `café`.
- Client B sends the equivalent decomposed sequence.
- A database with raw collation/indexes treats them as distinct.
- The Java layer normalizes in queries, while legacy table rows were never normalized, causing missed reads.

A common architecture:

```text
raw input
    |
    v
validate policy (allowed characters / length / domain rules)
    |
    v
canonicalize using chosen normalization + case policy
    |
    +--> raw/display value (preserve if required)
    |
    v
canonical key -> unique constraint / index / cache key
```

If storing both `display_name` and `canonical_username`:

- `display_name` is the display text as intended by the user, kept raw or in an allowed format.
- `canonical_username` must be derived by **one single function**, with a clear version/policy if long-lived.
- The canonical column needs uniqueness enforced at the **storage layer**, not only pre-checked in Java: two concurrent requests can still race without a constraint or equivalent transactional mechanism.

Never assume all DBs share the same **collation**. Some database engines compare case-insensitively, accent-insensitively, or by canonical equivalence differently, depending on product, version, and column/index configuration. Test the **actual uniqueness contract** directly rather than assuming the DB behaves identically to `Normalizer.normalize(..., NFC)`.

### Changing Canonicalization Policy Requires Migration

Replacing `NFC` with `NFKC` or adding case folding after data already exists can make two previously distinct names collapse onto **the same canonical key**.

A migration workflow should include:

1. Inventory all raw values and compute canonical keys under the new policy.
2. Detect collisions and resolve them per business rules **before** enforcing UNIQUE.
3. Rebuild indexes/caches and test reads/writes across both old and new APIs.
4. Cut over in a controlled transaction/deployment strategy; avoid running two app versions concurrently with conflicting identity policies.
5. Keep intentional mappings/aliases if legacy data compatibility is needed.

Never merge two user accounts solely because their display names or search keys match; identity must rely on IDs and explicit verification rules.

## 14. Security: Normalization Does Not Solve All Spoofing

Unicode normalization can be one layer in a defense strategy, yet **is not enough** to prevent identifier spoofing:

- Latin `a` and Cyrillic `а` can look almost identical; NFC/NFKC will not necessarily turn them into the same code point.
- Zero-width or bidirectional control characters can alter visual rendering without producing strings equal under `equals()`.
- Compatibility characters can change into other forms under NFKC, creating unexpected collisions.
- Input with abnormal combining marks or long Unicode sequences can stress UI layout, length limits, and performance if unchecked.
- Inconsistent case/collation rules across client, server, and database can break access control if strings serve as identities.

Explicitly define the **allowed character set**, length in appropriate units, normalization rules, mixed-script/confusable handling as needed, and ID type used in authorization. Never treat NFKC as a security filter or blindly delete unusual characters.

### Passwords and Digital Signatures

For **passwords**, never silently change normalization without a clear authentication policy. Altering input before hashing can make different passwords collide or lock users out after a system upgrade.

For **digital signatures, HMACs, content hashes, or canonical requests**, changing a single code point or combining-mark order alters the signed/hashed **byte sequence**. Normalize only if the **official protocol** specifies it and both sides apply the exact same rules. Never use `Normalizer` to “clean up data” after signing and expect signatures to remain valid.

Distinguish “comparing text for users” from “comparing protocol/secret bytes.” These two domains have different requirements.

## 15. Unicode Versions and Cross-System Synchronization

Unicode evolves across versions, and libraries/drivers/search engines may bundle different versions of normalization, case folding, or collation data.

For long-assigned characters, normalization forms have strong stability properties, yet **you should not assume every engine shares identical comparison, search ranking, case folding, or sorting behavior**. Collation and case folding especially require version-specific testing.

A long-lived data contract should document:

- Normalization form (`NFC` or `NFKC`, or unnormalized).
- Whether lowercasing/case folding is applied, and whether it is locale-dependent.
- Whether accents or combining characters are stripped (usually only for search).
- Whether whitespace is trimmed, and whether control/format characters are allowed.
- Where canonical keys are stored and which constraint enforces uniqueness.
- Policy/schema version and migration strategy if changed.
- Unicode test vectors covering canonical equivalence, compatibility equivalence, special case mappings, and confusables.

If both client and server normalize, **enforce canonicalization at the trusted server boundary**; never rely solely on client JavaScript or the UI having normalized input.

## 16. Testing Checklist

| Test Category | Suggested Input | Expected under NFC Policy |
|---|---|---|
| Canonical equivalence | `caf\u00E9` and `cafe\u0301` | Same canonical key |
| Compatibility ligature | `ﬁ` and `fi` | Not merged by default under NFC |
| Fullwidth | `Ａ` and `A` | Not merged by default under NFC |
| Uppercase/lowercase | `User` and `user` | Not merged automatically by NFC |
| Unaccented/accented | `cafe` and `café` | Not merged by NFC |
| Confusable characters | Latin `a` and Cyrillic `а` | NFC is not a spoofing detector |
| Search | Query `é` in raw `e + combining acute` | Raw search can miss; normalized matches |
| Cache | Insert NFC, lookup NFD | Canonicalize both before lookup |
| Uniqueness | Two different raw strings with identical NFC | Collision detected at canonical key |
| Unicode offsets | Raw `cafe + combining acute` vs. NFC `café` | Length/indices can differ |
| Special casing | `İ`, `Straße` | Do not assume lowercasing is full case folding |
| Passwords/signed data | Different Unicode sequences looking alike | Do not normalize outside contract |

Beyond isolated unit tests, test **end-to-end** through HTTP, databases, caches, and search indexes to discover any layer normalizing or matching inconsistently with the rest of the system.

## 17. Common Mistakes to Avoid

1. **Assuming strings that look alike on screen must return true from `String.equals()`.** Unicode allows multiple canonically equivalent sequences.
2. **Normalizing only one side.** Insert and lookup must use the same form.
3. **Defaulting to NFKC for all text.** Compatibility normalization can merge characters whose distinctions matter.
4. **Confusing normalization with lowercasing or accent stripping.** These are separate operations and policies.
5. **Treating `equalsIgnoreCase()` as full Unicode case folding.** Does not guarantee all special casing rules.
6. **Using Collator PRIMARY as proof two accounts are identical.** It represents locale-based search/sort equivalence, not identity.
7. **Calling `String.contains()` on raw Unicode expecting canonical equivalents to match.** Normalize both text and query, or use an appropriate search engine.
8. **Using an index from a normalized string to slice a raw string.** Offsets can shift due to UTF-16 length changes.
9. **Relying on default DB collation without testing.** Uniqueness/sorting/searching vary by DB, version, and configuration.
10. **Changing canonicalization after deployment without migration.** Causes collisions, cache misses, and broken data links.
11. **Passing secrets/passwords/hash inputs through unconditional normalization.** Can break protocols or alter authentication semantics.
12. **Believing NFC/NFKC alone blocks homographs.** Confusable characters are an additional concern not fully solved by normalization.
13. **Normalizing only on the client.** The server must enforce canonicalization at the trusted boundary.
14. **Using an accent-stripped search key as a unique key.** Flexible search rules are usually too broad for identity.
15. **Treating `length()` as the visible character count.** `String.length()` counts UTF-16 code units; normalization can change length.

## 18. Self-Check Questions

**Question 1.** Why can `"caf\u00E9".equals("cafe\u0301")` return false?  
**Answer:** The two strings use different Unicode sequences: a precomposed character vs. base letter + combining mark. `String.equals()` does not normalize automatically.

**Question 2.** Does normalizing both to NFC before comparing resolve that case?  
**Answer:** Yes, because the two canonically equivalent forms collapse to the same NFC representation in the example.

**Question 3.** Does NFC turn `cafe` into `café`?  
**Answer:** No. They are not canonically equivalent.

**Question 4.** Can `NFKC` turn `ﬁ` into `fi`?  
**Answer:** Yes. This is a compatibility mapping; its impact on identity must be evaluated.

**Question 5.** If a `HashMap` stores NFC keys and a client sends NFD, what should be done?  
**Answer:** Normalize all keys on write and lookup under the same policy; legacy data needs migration if it does not yet comply.

**Question 6.** Is `Collator` at PRIMARY strength suitable for enforcing UNIQUE usernames in every product?  
**Answer:** Not by default. It can merge accent/case differences depending on locale; identity needs explicit rules and database-level consistency.

**Question 7.** Can `indexOf()` offsets after normalization be applied directly to raw text?  
**Answer:** Not safely. Normalization can change the number of UTF-16 code units; either maintain an offset mapping or render from the same normalized text.

**Question 8.** Do NFC or NFKC eliminate all visually similar spoofing characters?  
**Answer:** No. Confusable detection, script controls, identifier security, and Unicode policies require dedicated design.

## 19. Takeaways

**Unicode normalization is part of your data contract, not a generic “sanitizer” for all fields.** When used for comparison, search, and key generation:

- Pick `NFC` for canonical equivalence when the domain treats different encodings of the same letter as equal.
- Pick `NFKC` only when compatibility differences are explicitly permitted to be lost.
- Separate **canonical identity keys** from **display values** and **search keys**.
- Normalize consistently across all write/read paths; handle collisions and UNIQUE constraints at the storage layer.
- Never confuse `Normalizer` with case folding, collation, diacritic stripping, or Unicode spoofing prevention.

**Official Documentation:** [Java SE 17 — Normalizer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html) · [Java SE 17 — Collator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Collator.html) · [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html) · [Unicode Standard Annex #15: Unicode Normalization Forms](https://www.unicode.org/reports/tr15/).
