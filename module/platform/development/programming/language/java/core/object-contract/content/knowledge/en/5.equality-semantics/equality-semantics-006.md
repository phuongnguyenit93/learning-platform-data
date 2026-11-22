# Case-Insensitive Comparison and Explicit Business Rules

## 1. The Problem: Which Rule Defines "Equal"?

In Java, two strings with the same letters but differing uppercase/lowercase can be considered equal or different **depending on the business context**:

- Coupon codes `Save10` and `SAVE10` may be **two different codes** if the system defines codes as case-sensitive.
- Usernames `Alice_7` and `alice_7` may be treated as **the same username** if the system declares usernames to be case-insensitive.
- Search tags `Java` and `JAVA` may be matched case-insensitively, yet “matching during search” is not necessarily the rule for determining an object's **identity**.
- Personal names, natural text, and multilingual terms may require rules dependent on language, diacritics, spelling variants, and intended use.

Therefore, the first question is not “use `equalsIgnoreCase` or `equals`?” but **what equality relation does this field require?** Only after defining the business rule should you choose Java APIs, normalization steps, and storage/query mechanisms.

An important limitation: `String.equals(Object)` remains case-sensitive. Calling `equalsIgnoreCase` for one operation does not change `String`'s definition of `equals`; if a value class should treat two representations as equal, you must design `equals` and `hashCode` of **that class** consistently.

## 2. Common Java Tools

| Tool | What it checks | When it fits |
| --- | --- | --- |
| `left.equals(right)` | String content equality per `String.equals`, case-sensitive. | Codes, keys, values with exact matching rules. |
| `left.equalsIgnoreCase(right)` | Case-insensitive character comparison according to Java's Unicode rules, **not based on a passed `Locale`**. | Case-insensitive string matching when this Java rule matches business requirements. |
| `left.toLowerCase(Locale.ROOT)` | Produces a string converted to lowercase using a locale-neutral rule. | One step in a pre-designed strategy for creating a **canonical key**. |
| `String.CASE_INSENSITIVE_ORDER` | A `Comparator<String>` ordering strings case-insensitively with rules compatible with `compareToIgnoreCase`. | Sorted sets/trees whose policy treats upper/lowercase as the same key. |
| `Collator` | Compares according to linguistic collation rules, locale, and strength level. | Sorting or searching text in the user's language. |
| `Normalizer.normalize(text, Form.NFC)` | Normalizes equivalent Unicode representations into one canonical form. | When data may contain composed/decomposed Unicode characters. |

The tools above **are not completely interchangeable**. For example, lowercasing two strings and calling `equals` does not always agree with `equalsIgnoreCase` across all Unicode characters. `Collator` may also treat two strings differing only by accents as equivalent at a given comparison strength, which a “ignore case but preserve accents” policy does not want.

### `equals` vs `equalsIgnoreCase`

```java
"Java".equals("JAVA");            // false
"Java".equalsIgnoreCase("JAVA");  // true
"Java".equalsIgnoreCase(null);    // false
```

These are **illustrative expressions**, not a standalone Java program. If the left reference is `null`, both `left.equals(...)` and `left.equalsIgnoreCase(...)` throw `NullPointerException`; handling of `null` inputs must be specified and guarded with checks or appropriate utilities.

Do not confuse “case-insensitive” with “accent-insensitive”, “ignore whitespace”, “Unicode-representation-insensitive”, or “fuzzy search match”. Each requirement is a separate rule.

## 3. Designing Business Rules Explicitly

Before coding, answer the following questions for **each kind of data**:

1. **What is being compared?** Username, coupon, SKU, order code, display tag, or search keyword? Two fields in the same object may have different rules.
2. **Case-sensitive or not?** If not, use direct case-insensitive matching or build a canonical key for storage?
3. **Strip leading/trailing whitespace?** If yes, by what rule? `strip()` and `trim()` are not identical for all characters; do not automatically strip internal whitespace.
4. **Which characters are accepted?** ASCII only (`A-Z`, `a-z`, digits, underscore) or multilingual Unicode? The character domain determines normalization complexity.
5. **Are accents and Unicode normalization considered?** Precomposed `é` and `e` + combining acute accent represent the same visual text yet are two different code sequences.
6. **Does locale matter?** Machine-key matching typically requires locale-independent rules; human names or display text may need the user's locale.
7. **Are `null`, empty strings, and whitespace-only strings valid?** Returning `false`, treating two `null`s as equal, or rejecting input are all business choices that must be stated.
8. **Is the identity definition stable?** If the value determining `equals`/`hashCode` is allowed to mutate, objects used as `HashMap`/`HashSet` keys risk losing lookup reliability.

For example, a username specification can be written explicitly:

> “Accept 3–20 ASCII characters, consisting only of letters, digits, and `_`. Strip leading/trailing whitespace before validation. Usernames are unique ignoring ASCII case. The storage/lookup key is lowercased with `Locale.ROOT`. Other Unicode scripts or accented spellings are not accepted.”

This is merely **an example policy**. It produces predictable results because valid data lies strictly within ASCII; systems supporting international usernames need separate specifications, tests, and Unicode policies.

A username policy does not automatically apply to emails, customer names, or item codes. For email addresses, the domain part is case-insensitive while handling rules for the local part depend on the provider and application; do not automatically strip dots, plus suffixes, or lowercase the entire address and treat that as canonical identity across all systems.

## 4. Standalone Runnable Java 17+ Example

The following program demonstrates **three separate policies**:

- `sameTag` allows case-insensitive tag matching using `equalsIgnoreCase`.
- `sameCouponCode` uses exact, case-sensitive matching.
- `Username` is an **immutable value class**; `equals`/`hashCode` both rely on a normalized ASCII username key. This is a value-domain example and does not assume every user account's identity must be based on username.

Save as exact file `CasePolicyDemo.java`:

```java
import java.util.HashSet;
import java.util.Locale;
import java.util.Objects;
import java.util.Set;
import java.util.TreeSet;

public class CasePolicyDemo {
    static boolean sameTag(String left, String right) {
        Objects.requireNonNull(left, "left");
        Objects.requireNonNull(right, "right");
        return left.equalsIgnoreCase(right);
    }

    static boolean sameCouponCode(String left, String right) {
        Objects.requireNonNull(left, "left");
        Objects.requireNonNull(right, "right");
        return left.equals(right);
    }

    static String canonicalUsername(String raw) {
        Objects.requireNonNull(raw, "raw");

        String cleaned = raw.strip();
        if (!cleaned.matches("[A-Za-z0-9_]{3,20}")) {
            throw new IllegalArgumentException("Invalid username");
        }
        return cleaned.toLowerCase(Locale.ROOT);
    }

    static final class Username {
        private final String key;

        Username(String raw) {
            this.key = canonicalUsername(raw);
        }

        @Override
        public boolean equals(Object other) {
            return this == other
                    || (other instanceof Username that
                    && key.equals(that.key));
        }

        @Override
        public int hashCode() {
            return key.hashCode();
        }
    }

    public static void main(String[] args) {
        System.out.println("tag ignore case: "
                + sameTag("Java", "JAVA"));
        System.out.println("coupon exact: "
                + sameCouponCode("Save10", "SAVE10"));
        System.out.println("canonical username: "
                + canonicalUsername("  Alice_7  "));

        Username a = new Username("Alice_7");
        Username b = new Username("alice_7");
        Username c = new Username("ALICE_7");
        System.out.println("username equal: " + a.equals(b));
        System.out.println("reflexive: " + a.equals(a));
        System.out.println("symmetric: " + (a.equals(b) == b.equals(a)));
        System.out.println("transitive: "
                + (!a.equals(b) || !b.equals(c) || a.equals(c)));
        System.out.println("hash agreement: "
                + (a.hashCode() == b.hashCode()));

        Set<Username> usernames = new HashSet<>();
        usernames.add(a);
        System.out.println("HashSet contains b: " + usernames.contains(b));

        Set<String> exactStrings = new HashSet<>();
        exactStrings.add("Java");
        exactStrings.add("JAVA");

        Set<String> ignoreCaseStrings =
                new TreeSet<>(String.CASE_INSENSITIVE_ORDER);
        ignoreCaseStrings.add("Java");
        ignoreCaseStrings.add("JAVA");

        System.out.println("HashSet strings size: " + exactStrings.size());
        System.out.println("TreeSet strings size: " + ignoreCaseStrings.size());
        System.out.println("sharp-s expansion: "
                + "straße".equalsIgnoreCase("STRASSE"));
    }
}
```

Compile and run on JDK 17 or newer:

```bash
javac -encoding UTF-8 CasePolicyDemo.java
java CasePolicyDemo
```

Output:

```text
tag ignore case: true
coupon exact: false
canonical username: alice_7
username equal: true
reflexive: true
symmetric: true
transitive: true
hash agreement: true
HashSet contains b: true
HashSet strings size: 2
TreeSet strings size: 1
sharp-s expansion: false
```

**Explanation:**

- `sameTag("Java", "JAVA")` returns `true` because tag matching is allowed to ignore case. `sameCouponCode("Save10", "SAVE10")` returns `false` because the coupon policy is case-sensitive.
- `canonicalUsername` strips boundary whitespace under the example policy, then **validates the ASCII domain before lowercasing**. Because only ASCII is allowed, `toLowerCase(Locale.ROOT)` avoids hard-to-control Unicode expansion cases.
- `Username` is a `final` class with an immutable `key` field. The three objects `a`, `b`, `c` share the same canonical key, so `equals` is reflexive, symmetric, and transitive across the sample data. The printed output only checks this dataset; contract compliance also rests on the key definition and other tests.
- `hashCode` is computed from the same `key` as `equals`. Hence `HashSet` recognizes `b` as the same value as the stored `a`.
- `HashSet<String>` uses `String.equals`/`hashCode`, so it holds both `Java` and `JAVA`. `TreeSet<String>` here uses a case-insensitive comparator, so it keeps only one element for that pair. The comparator's equivalence relation **differs from `String.equals`**; this is a set-semantics decision you must understand before using it.
- `"straße"` and `"STRASSE"` have different character counts, so `equalsIgnoreCase` returns `false`. It does not perform all multi-character expansions used in certain Unicode case folding concepts.

## 5. Why Does Key Normalization Help Design `equals` Correctly?

Suppose two `Username` objects were compared by raw strings via `String.equals`: `"Alice_7"` and `"alice_7"` differ. Yet business rules established they are the same username. Therefore, the value class stores **the key representing the equality relation**, such as `"alice_7"`, and uses that key consistently.

If every accepted input passes through **the same deterministic normalization function**, we define:

```text
x ~ y  if and only if  canonical(x).equals(canonical(y))
```

That is equality of canonical string keys; it is reflexive, symmetric, and transitive. This rule is easier to verify than a tangle of “approximate” conditions written inside `equals`. Remember that the equivalence relation applies only to **valid values in the domain**; invalid inputs should be handled per constructor/API contract.

Most important rules when implementing a value object:

1. **Define one unified normalization function** for all creation, import, API, batch job, and lookup paths.
2. **Do not decouple `equals` and `hashCode` criteria.** If `equals` ignores case while `hashCode` relies on the raw string, two equal objects can produce different hashes and break the contract.
3. **Keys must be stable** when objects are used as `HashSet` elements or `HashMap` keys. A `final` field on a value class is a safe choice.
4. **Define the type domain clearly.** For instance, `Username` equals only another `Username`; it does not equal a `String` even with the same text. Allowing `Username.equals("alice_7")` usually breaks symmetry because `String.equals(Username)` returns `false`.
5. **Align rules between application and storage.** If the application normalizes usernames while the database index checks only raw strings, two requests creating a username can pass checks and cause duplicate identities. Use the canonical key, unique constraints, and appropriate write operations to guarantee uniqueness, even under concurrent requests.

Note: an **account entity** may need to be identified by a stable `userId` rather than username if usernames are allowed to change. The `Username` class in the example is a *value object representing a login name*, not the entire user entity. An entity's `equals` rule must reflect that entity's actual identity.

## 6. Unicode, Locale, and Easily Misunderstood Cases

### 6.1. Case-Insensitivity Is Not Full Unicode Case Folding

`String.equalsIgnoreCase` is a case-insensitive comparison as specified by Java. It **does not automatically** normalize Unicode, run full Unicode case folding across strings, or use a user-specified locale.

For example, `"straße".equalsIgnoreCase("STRASSE")` returns `false` because the two strings have different lengths. Do not infer from the ASCII example `"java"` vs `"JAVA"` that every pair of naturally equivalent spellings is treated as equal by Java.

If business requirements support international Unicode usernames or keys, you need **an explicit canonicalization policy, clear rule versioning, and tests with representative data**. Calling `toLowerCase(Locale.ROOT)` alone is not equivalent to a full standardized Unicode identifier algorithm.

### 6.2. Composed and Decomposed Unicode Forms

For example, the letter `é` can be represented by a single precomposed code point or by `e` plus a combining acute accent. In Java, those two strings have different code point sequences and usually are not equal under `String.equals` or `equalsIgnoreCase`. When policy permits treating them as the same text, normalize to **NFC** before comparing:

```java
import java.text.Normalizer;

String composed = "\u00E9";    // precomposed é
String decomposed = "e\u0301"; // e and combining acute accent

boolean before = composed.equals(decomposed); // false
boolean after = Normalizer.normalize(
        composed, Normalizer.Form.NFC
).equals(Normalizer.normalize(
        decomposed, Normalizer.Form.NFC
)); // true
```

This is an **illustrative snippet**, not a standalone program. `NFC` preserves distinctions among texts other than canonically equivalent cases; `NFKC` additionally normalizes certain compatibility differences and may merge characters displayed or used with different meanings. Only use `NFKC` if business specifications permit it. Unicode normalization also does not mean automatically “stripping Vietnamese accents”.

### 6.3. Locale Affects Case Conversion

Java has locale-dependent case conversions: `toLowerCase()` with no arguments uses the environment's default locale, which can produce different results across machine configurations. A familiar example is the `I`/`i` rule in Turkish.

- For **machine keys** independent of location/language, consider `Locale.ROOT` when the policy uses case conversion. In the ASCII username example, this yields predictable keys.
- For **human-facing text**, choose the data/user's locale and specified search behavior. Avoid assuming all languages share English casing rules.
- `equalsIgnoreCase` does not accept a `Locale` parameter, so it cannot be tuned accurately per language with this call alone.

### 6.4. Linguistic Ordering With `Collator`

When comparing names or display text linguistically, `java.text.Collator` lets you choose a locale and comparison strength. Example **illustrative code snippet**:

```java
import java.text.Collator;
import java.util.Locale;

Collator collator =
        Collator.getInstance(Locale.forLanguageTag("vi-VN"));
collator.setStrength(Collator.SECONDARY);

boolean sameForCollation = collator.compare(left, right) == 0;
```

In many collation rule sets, `SECONDARY` strength ignores case differences while still distinguishing accents. However, detailed results depend on locale, linguistic data, and the environment's collation provider. Do not replace stored-key `equals` with a custom `Collator` without precisely specifying the contract, versioning, and stability across runs.

`Collator` is useful for display and linguistic search; using it to define long-term database identity requires separate policies and verification.

## 7. Separating "Search Matching" From "Object Equality"

A system can simultaneously face three different questions:

| Scenario | Business question | Example API/rule |
| --- | --- | --- |
| Searching tags in the UI | “Should `Java` and `JAVA` be shown as matching results?” | `equalsIgnoreCase` or search using an appropriate analyzer/collation. |
| Checking a coupon code | “Is `SAVE10` the code `Save10`?” | `equals` if codes are case-sensitive; this choice is documented in the specification. |
| Preventing duplicate usernames | “Does `ALICE_7` create a new username compared to `alice_7`?” | Use an immutable canonical key, a unique constraint on the key, and matching `equals`/`hashCode` for the value object. |

Do not implement a generic `equalsIgnoreCaseForEverything` method and apply it to every field. Semantically named functions like `canonicalUsername`, `sameCouponCode`, or `matchesSearchLabel` make the policy explicit at call sites; when requirements change, you can update within the business scope without inadvertently altering other fields' semantics.

For long-lived persisted data, key-generation rules and versioning/migration must be treated as part of the data contract. When changing a normalization policy, two previously distinct keys may collapse into one; duplicates must be checked and resolved before updating indexes/constraints or regenerating keys.

## 8. Common Pitfalls

| Pitfall | Consequence | Fix |
| --- | --- | --- |
| Calling `equalsIgnoreCase` for all strings “to be user-friendly” | Can wrongly merge distinct security codes, coupons, or product codes. | Define policy per field and per operation. |
| Using `String.equals` while expecting usernames to be case-insensitive | `Alice_7` and `alice_7` are treated as two keys. | Normalize per policy and compare canonical keys. |
| Calling `toLowerCase()` without a locale for system keys | Keys may depend on the environment's default locale. | Pass `Locale.ROOT` when appropriate for policy; restrict character set or define thorough Unicode canonicalization. |
| Assuming `equalsIgnoreCase` handles all Unicode equivalences | Does not handle all decomposed forms or multi-character expansions. | Specify normalization/case folding and test Unicode if data allows it. |
| Normalizing at registration but forgetting to normalize at login | A username can be stored yet never found again. | Use one normalization path for creation, lookup, and uniqueness checks. |
| `equals` uses canonical key, `hashCode` uses raw string | Equal objects have different hashes, breaking hash collection logic. | Both use the same immutable, canonical key field. |
| Using `String.CASE_INSENSITIVE_ORDER` thinking `TreeSet` has the same equality as `HashSet` | The two sets differ in element count for `Java`/`JAVA`. | Understand that `TreeSet` determines duplicates via comparator (`compare == 0`); choose structure/comparator to match desired semantics. |
| Treating username and account as the same identity concept | Changing username can alter the account's equality semantics. | Distinguish the username value object from an account entity identified by a stable ID. |
| Ignoring post-normalization duplicates in the DB | Two records with the same business key can be created, especially under concurrent access. | Enforce a unique constraint on the chosen canonical key and handle collisions explicitly. |
| Arbitrarily stripping accents or dots/plus signs in emails | Merges addresses not guaranteed to belong to the same mailbox. | Follow the verified email policy for the system; do not apply one provider's rules to all emails. |

## 9. Test Suite Checklist Before Production

For any case-insensitive comparison rule, build tests using **real domain values**:

- **ASCII case:** Are `Alice_7`, `alice_7`, `ALICE_7` treated as one key? Test both creation and lookup.
- **Rule separation:** `Save10` and `SAVE10` differ for coupons if policy mandates exact matching, even when tags `Java` and `JAVA` match.
- **Whitespace:** Does `" Alice_7 "` normalize to `Alice_7`? Are internal spaces or invalid characters properly rejected?
- **`null`/empty:** Does the API reject or handle them per contract? Do not let one call path return `false` while another unexpectedly throws an unintended error.
- **Unicode and locale:** Test accented data, precomposed/decomposed strings, letter `I` under special locales, letter `ß`, and confirm behavior matches the supported character scope.
- **`equals` contract:** For three equivalent value objects, test reflexivity, symmetry, and transitivity; for equal pairs, ensure `hashCode` matches; for different types and `null`, ensure correct behavior.
- **Persistence uniqueness:** Two concurrent requests creating `Alice_7` and `ALICE_7` must be controlled by uniqueness rules in storage, not solely by a pre-insert check.
- **Stability:** Verify legacy data after updating Unicode rules, locale providers, database collations, or normalization policies; if changes occur, consider migration.

Property-based tests can be written over large numbers of input triples, especially for Unicode. However, a test returning `true` for three specific strings does not by itself prove the policy holds across the entire domain; transitivity must rest on a consistent equality definition.

## 10. Takeaways

“Case-insensitive comparison” is **a scoped business choice**, not an inherent property of all strings. `equalsIgnoreCase` is a convenient tool for certain matching operations; key normalization explicitly represents value object identity; `Collator` serves linguistic text comparison. Publish the character domain, handling of case, whitespace, Unicode, locale, and `null`, then use the exact same policy across all data creation and query paths. If the policy becomes a value class's `equals`, `hashCode` must use the exact same equivalence key, and that key should be immutable.