# Collator in Java: PRIMARY, SECONDARY, TERTIARY, and IDENTICAL Levels

## 1. The Problem: "Equal" and "Comes Before" Depend on Language

When handling multilingual data, sorting personal names, categories, products, or search results cannot always rely on character code order. For instance, the following strings may be seen by users as closely related yet carry real differences:

- `cafe` and `café`: differ in accent.
- `cafe` and `Cafe`: differ in uppercase/lowercase.
- `café` written with precomposed `\u00E9` and `cafe\u0301` using `e` plus a combining accent: may look identical and be canonically equivalent in Unicode.
- `A` and full-width Latin `Ａ`: differ in compatibility representation, not implicitly having the same identity.

`String.compareTo()`, `String.equals()`, and `String.equalsIgnoreCase()` are not designed to express the full lexical ordering rules of all languages. Java provides **`java.text.Collator`**, allowing string comparison by `Locale` while tuning the **distinction level** via `setStrength(int)`.

The four basic levels are:

```java
Collator.PRIMARY
Collator.SECONDARY
Collator.TERTIARY
Collator.IDENTICAL
```

So rather than asking vaguely "are these two strings equal?", a system must define: **equal at what level of distinction, under which locale's rules, and for search, sorting, or data identity?**

This lesson is about **language-aware comparison (collation)**. It does not replace all Unicode normalization, full-text search, or identity key generation rules.

## 2. What Is Collator and How Is It Created?

`Collator` is the abstract class for language-aware string comparison. Common creation pattern:

```java
import java.text.Collator;
import java.util.Locale;

Collator collator = Collator.getInstance(Locale.US);
```

Once you have the instance, use:

```java
int result = collator.compare(left, right);
```

Return value meanings:

| Return value | Meaning |
|---|---|
| Negative number | `left` comes before `right` under the collator |
| `0` | The two strings are considered equivalent under the collator configuration |
| Positive number | `left` comes after `right` under the collator |

**Do not assume the result is strictly `-1` or `1`.** What the `Comparator` contract guarantees is checking negative, 0, or positive sign. You can use `Integer.signum(result)` when only the sign is needed.

Example:

```java
if (collator.compare(a, b) == 0) {
    // Equivalent under the configured locale, strength, and decomposition.
}
```

This condition is **not synonymous** with `a.equals(b)`. Two strings differing in characters can have `collator.compare(a,b)==0`, especially at `PRIMARY`.

When sorting a list, `List.sort(collator)` can be used because `Collator` implements `Comparator<Object>` and accepts `String` objects in `compare`. For more strictly typed application code, you can pass a lambda `(a,b) -> collator.compare(a,b)` for `List<String>`.

## 3. Strength Determines Which Differences Are Significant

`Collator.setStrength(...)` selects a **sensitivity level**. The levels correspond to classes of differences in linguistic collation: each higher level typically considers additional differences ignored by the previous level.

### PRIMARY: fundamental letter differences

`PRIMARY` focuses on *primary* differences per collation rules. In many locales, this level may treat strings differing in accents or case as equivalent:

```text
cafe ~ café
cafe ~ Cafe
```

In the `Locale.US` example on Java 17, both pairs return `0` at `PRIMARY`.

**There is no universal rule that PRIMARY always ignores all accents in all languages.** Whether a difference is treated as primary or secondary depends on the locale's collation table and data version. Some letters regarded as distinct letters in a language may not be equivalent at `PRIMARY`.

Use cases: **low-sensitivity** sorting or matching within a defined linguistic context.

### SECONDARY: adds secondary differences, usually accents

`SECONDARY` additionally considers secondary differences, typically *accents/diacritics*:

```text
cafe != café
cafe ~ Cafe
```

In the US example, the acute accent makes the two strings non-equivalent; case differences still do not distinguish them.

Use cases: requiring accent distinction without necessarily treating uppercase and lowercase as distinct words.

### TERTIARY: adds tertiary differences, usually case

`TERTIARY` additionally considers tertiary differences; in many languages, this is the level associated with **case** or certain presentation variants:

```text
cafe != café
cafe != Cafe
```

In the US example, both differences are treated as significant. `TERTIARY` is also the common default strength for JDK collators, though applications should **set the level explicitly** rather than implicitly relying on defaults.

Do not assume this level **always matches `String.equals()`**. Collation still applies linguistic rules, normalization/decomposition, and special handling of text components.

### IDENTICAL: highest distinction within Collator

`IDENTICAL` considers remaining differences when all lower levels cannot distinguish the strings. It is useful when wanting a comparison closer to character representation while staying within the Collator mechanism.

**Subtle point:** `IDENTICAL` results are also affected by **decomposition**. For example, precomposed `café` and `e` + combining mark `cafe\u0301` may:

- Compare as **different** at `IDENTICAL` under `NO_DECOMPOSITION`.
- Compare as **equal** at `IDENTICAL` when `CANONICAL_DECOMPOSITION` is enabled, because the two canonically equivalent representations are handled consistently.

Hence, never say "IDENTICAL is always String.equals" or "IDENTICAL always distinguishes every pair of Unicode strings with different bytes." If business logic requires **exact String content match**, use `String.equals()`; if it requires **byte match**, compare the exact bytes in the chosen encoding/protocol.

## 4. Meaning and Usage Scope Table

| Strength | Differences typically distinguished | Typical use case | Watch out for |
|---|---|---|---|
| `PRIMARY` | Base letter differences per language | Relatively lenient sorting/matching | Can collapse many distinct strings |
| `SECONDARY` | Adds diacritic differences | Want to distinguish `e`/`é` while possibly ignoring case | Accents are not ranked identically in every locale |
| `TERTIARY` | Adds case and tertiary variants | High-distinction display sorting | Not equivalent to `String.equals` |
| `IDENTICAL` | Adds remaining differences per Collator mechanism | High-sensitivity tie-breaking/collation | Depends on decomposition; does not replace byte equality |

Going from `PRIMARY` up to `IDENTICAL` increases sensitivity, yet **each locale's specific rules** decide which pairs return 0. Never hardcode a rule-of-thumb table claiming "accents are always secondary" for all languages worldwide.

## 5. Java 17+ Program Verifying All Four Levels

Create `CollationStrengthDemo.java`:

```java
import java.text.Collator;
import java.util.Locale;

public class CollationStrengthDemo {
    public static void main(String[] args) {
        Collator collator =
                Collator.getInstance(Locale.US);

        collator.setDecomposition(
                Collator.CANONICAL_DECOMPOSITION);

        String plain = "cafe";
        String accented = "caf\u00E9";
        String upper = "Cafe";
        String decomposed = "cafe\u0301";

        int[] strengths = {
                Collator.PRIMARY,
                Collator.SECONDARY,
                Collator.TERTIARY,
                Collator.IDENTICAL
        };

        String[] labels = {
                "PRIMARY",
                "SECONDARY",
                "TERTIARY",
                "IDENTICAL"
        };

        for (int i = 0; i < strengths.length; i++) {
            collator.setStrength(strengths[i]);

            boolean sameAccent =
                    collator.compare(plain, accented) == 0;
            boolean sameCase =
                    collator.compare(plain, upper) == 0;
            boolean sameCanonical =
                    collator.compare(accented, decomposed) == 0;

            System.out.printf(
                    "%s accent=%s case=%s canonical=%s%n",
                    labels[i],
                    sameAccent,
                    sameCase,
                    sameCanonical);
        }
    }
}
```

Compile/run:

```bash
javac CollationStrengthDemo.java
java CollationStrengthDemo
```

Verified JDK output for `Locale.US`:

```text
PRIMARY accent=true case=true canonical=true
SECONDARY accent=false case=true canonical=true
TERTIARY accent=false case=false canonical=true
IDENTICAL accent=false case=false canonical=true
```

Here:

- `accent` compares `cafe` with precomposed `café`.
- `case` compares `cafe` with `Cafe`.
- `canonical` compares precomposed `café` with `cafe` + combining acute accent.
- `CANONICAL_DECOMPOSITION` is explicitly set, so the canonically equivalent pair still compares equal even at `IDENTICAL` in this example.

**Read the table column by column**, without interpreting `true` as "the two strings are completely identical": it only means "the Collator does not distinguish that pair under the active configuration."

When an application uses another locale or runtime, verify the rules against real datasets. The general meaning of the levels is stable, while per-character classification is the responsibility of locale collation data.

## 6. Strength and Decomposition Are Two Independent Settings

`setStrength` answers: **which levels of difference are considered?**

`setDecomposition` answers: **before matching, to what extent does the collation parser process Unicode combining forms?**

Java has three options:

| Decomposition mode | Meaning |
|---|---|
| `Collator.NO_DECOMPOSITION` | Do not perform decomposition before comparison |
| `Collator.CANONICAL_DECOMPOSITION` | Handle canonical decomposition |
| `Collator.FULL_DECOMPOSITION` | Also handle compatibility decomposition |

Unicode example:

```text
U+00E9       -> é (precomposed character)
U+0065 U+0301 -> e + combining acute (decomposed characters)
```

These two representations can resolve to the same form under canonical decomposition. With `FULL_DECOMPOSITION`, the system can also unify certain compatibility representations such as full-width letters and their ASCII counterparts, depending on collation rules.

**Do not equate "IDENTICAL" with "no decomposition."** `IDENTICAL` is a strength, whereas `NO_DECOMPOSITION` is a decomposition mode. The two settings use separate methods and describe two orthogonal axes of behavior.

### Which Decomposition Should You Use?

- `NO_DECOMPOSITION` can be useful in scenarios where data is already guaranteed to be in the right form and avoiding decomposition inside the collator is preferred; however, you must understand `IDENTICAL` outcomes across canonically equivalent forms.
- `CANONICAL_DECOMPOSITION` is suitable if inputs may mix precomposed and combining forms and the application wants them treated as canonically equivalent.
- `FULL_DECOMPOSITION` can additionally fold compatibility characters. **Choose it only if the application accepts losing distinction** between those character forms during comparison.

Decomposition does not replace a normalization policy when **persisting data**. `Collator.compare` compares; it does not modify the contents of the two `String`s.

## 7. Java 17+ Example: IDENTICAL Still Changes When Decomposition Changes

Create `CollationDecompositionDemo.java`:

```java
import java.text.Collator;
import java.util.Locale;

public class CollationDecompositionDemo {
    public static void main(String[] args) {
        Collator collator =
                Collator.getInstance(Locale.US);

        String composed = "caf\u00E9";
        String decomposed = "cafe\u0301";

        collator.setStrength(Collator.IDENTICAL);
        collator.setDecomposition(Collator.NO_DECOMPOSITION);
        System.out.println("identical_no_decomp=" +
                (collator.compare(composed, decomposed) == 0));

        collator.setDecomposition(Collator.CANONICAL_DECOMPOSITION);
        System.out.println("identical_canonical=" +
                (collator.compare(composed, decomposed) == 0));

        String asciiA = "A";
        String fullWidthA = "\uFF21";

        collator.setDecomposition(Collator.FULL_DECOMPOSITION);
        collator.setStrength(Collator.IDENTICAL);
        System.out.println("identical_full_compat=" +
                (collator.compare(asciiA, fullWidthA) == 0));

        collator.setDecomposition(Collator.NO_DECOMPOSITION);
        System.out.println("identical_no_compat=" +
                (collator.compare(asciiA, fullWidthA) == 0));
    }
}
```

Run:

```bash
javac CollationDecompositionDemo.java
java CollationDecompositionDemo
```

JDK-verified output:

```text
identical_no_decomp=false
identical_canonical=true
identical_full_compat=true
identical_no_compat=false
```

Explanation:

1. At `NO_DECOMPOSITION` + `IDENTICAL`, the two spellings of `é` differ at the representation level.
2. Enabling `CANONICAL_DECOMPOSITION` handles canonical equivalence in the example.
3. Enabling `FULL_DECOMPOSITION` allows normal `A` and full-width `Ａ` to be treated as equivalent under the active collation mechanism.
4. Switching back to `NO_DECOMPOSITION`, the difference of the full-width pair reappears at `IDENTICAL`.

These specific results reflect the tested `Locale.US` collator and JDK dataset; do not generalize them as a universal rule for every locale/provider and every compatibility character.

**Note on Unicode forms:** `Normalizer.Form.NFC/NFD/NFKC/NFKD` is a different API (`java.text.Normalizer`). It transforms or checks string content; `Collator` only applies matching rules. Collator decomposition modes are conceptually related but are not synonymous with replacing input strings via `Normalizer.normalize(...)` before storing them.

## 8. Why IDENTICAL Should Not Be Called "Binary Comparison"

Three concepts must be kept distinct:

| Comparison | Property |
|---|---|
| `String.equals(a)` | Compares exact UTF-16 contents of two `String`s |
| `Collator.compare(a,b) == 0` | Compares by locale + strength + decomposition |
| Byte sequence comparison after encoding, e.g., UTF-8 | Compares by bytes, appropriate when protocols require exactness |

A `Collator` can treat two strings as equivalent at `IDENTICAL` because decomposition folded representation differences. Conversely, `String.equals()` will never treat two different UTF-16 sequences as equal.

This matters for:

- Tokens/secrets and identifiers requiring exact matching.
- Digital signatures and hashed data.
- Identifiers that must remain byte-for-byte per protocol.
- Database uniqueness, where DB collation may differ from JVM collation.

For data such as *secrets* or *canonical bytes*, never use Collator to "relax" equality. If a contract requires Unicode normalization before comparison, do so explicitly at a defined layer rather than turning strength into an implicit identity mutator.

`Collator.IDENTICAL` is the **highest sensitivity level of Collator**, not an API for verifying byte integrity.

## 9. Locale Is a Mandatory Part of Comparison Rules

Two languages can place accented letters, digraphs, and word orders differently. Therefore:

```java
Collator vietnamese = Collator.getInstance(
        Locale.forLanguageTag("vi-VN"));

Collator french = Collator.getInstance(
        Locale.FRENCH);
```

Both collators have four strengths, yet **do not guarantee the same ordering relation for every pair of words**. The purpose of `Locale` is for the application to declare the linguistic rules of the data.

In multi-user environments, avoid calling zero-arg `Collator.getInstance()` and assuming it fits all records. `getInstance()` uses the JVM default locale; the default locale can differ between developer machines, containers, and production.

A clean approach is accepting `Locale` as a parameter from the business/UI contract:

```java
static Collator createDisplayCollator(Locale locale) {
    Collator collator = Collator.getInstance(locale);
    collator.setStrength(Collator.TERTIARY);
    collator.setDecomposition(
            Collator.CANONICAL_DECOMPOSITION);
    return collator;
}
```

This is a **code snippet** used inside a class that imports `Collator` and `Locale`. It does not claim `TERTIARY` is always the right level; it is **one concrete policy** to agree upon before use.

For data aggregated from multiple locales, the application must answer: **sort by the viewer's locale, each record's source language, or a designated shared locale?** Mixing per-record comparators within a single sort pass can break the consistency of the ordering relation.

## 10. Sorting Lists with Collator

A common usage pattern is:

```java
List<String> names = new ArrayList<>(...);
Collator collator = Collator.getInstance(Locale.US);
collator.setStrength(Collator.SECONDARY);

names.sort((a, b) -> collator.compare(a, b));
```

The snippet above shows how to pass Collator to `List.sort`. In production code, the list must hold valid `String`s; handle `null` separately if the data domain allows `null`.

At `SECONDARY`, some case differences may be treated as equal. For elements where the comparator returns `0`, a stable sort may keep their relative input order. If the application requires a completely deterministic secondary order when two strings are collation-equal, add an explicit tie-breaker:

```java
names.sort((a, b) -> {
    int order = collator.compare(a, b);
    return order != 0 ? order : a.compareTo(b);
});
```

Then:

1. Configured linguistic order takes priority.
2. Only when Collator treats two strings as equivalent is `String.compareTo` order used for a consistent secondary order.

**Important:** this tie-breaker changes the definition of "equal" for the overall comparator. If application logic expects `cafe` and `café` to share the same key at `PRIMARY`, you cannot both add a tie-breaker that distinguishes them and expect `TreeSet` to merge them. Display sorting and uniqueness checking should remain two separate policies.

## 11. Collator in TreeSet/TreeMap: Risk of Losing Keys

`TreeSet` and `TreeMap` determine duplicate keys via the comparator, not solely via `String.equals()`. If the comparator returns `0` for two distinct strings, the structure may treat them as **the same key**.

For example, with `Locale.US` at `PRIMARY`, `cafe`, `café`, and `Cafe` can all be collation-equivalent.

Create `CollationTreeSetDemo.java`:

```java
import java.text.CollationKey;
import java.text.Collator;
import java.util.Locale;
import java.util.TreeSet;

public class CollationTreeSetDemo {
    public static void main(String[] args) {
        Collator collator =
                Collator.getInstance(Locale.US);
        collator.setStrength(Collator.PRIMARY);
        collator.setDecomposition(
                Collator.CANONICAL_DECOMPOSITION);

        TreeSet<String> set = new TreeSet<>(collator);
        set.add("cafe");
        set.add("caf\u00E9");
        set.add("Cafe");

        System.out.println("treeSize=" + set.size());
        System.out.println("stringEquals=" +
                "cafe".equals("caf\u00E9"));

        CollationKey first =
                collator.getCollationKey("cafe");
        CollationKey second =
                collator.getCollationKey("caf\u00E9");
        System.out.println("keysEqual=" +
                (first.compareTo(second) == 0));
    }
}
```

Compile/run:

```bash
javac CollationTreeSetDemo.java
java CollationTreeSetDemo
```

Verified output:

```text
treeSize=1
stringEquals=false
keysEqual=true
```

**Important explanation:** `TreeSet` retains only one element because the `PRIMARY` comparator treats all three representations as equivalent; yet `String.equals` still shows at least two different raw strings.

Therefore:

- If you want to sort a list **while keeping every row**, use `List.sort`.
- If you want to deduplicate records by collation policy, `TreeSet` can do that, but it must be an **intentional** decision.
- If you want uniqueness by raw content, use `HashSet<String>` or a `TreeSet` with a comparator consistent with that equality.
- If you want uniqueness by canonicalized key, design a dedicated key and enforce the constraint in the database.

Never use a `TreeMap` with `PRIMARY` to store accounts by name and assume collisions will never happen. When two keys compare equal to 0, the map can overwrite or return the same entry's value depending on the update operation.

## 12. CollationKey: Optimizing Repeated Comparisons

`Collator.compare(a,b)` executes the collation process over the strings. When sorting many strings or comparing the same strings repeatedly, consider `CollationKey`:

```java
CollationKey key = collator.getCollationKey("café");
```

This key represents precomputed collation information. Two `CollationKey`s can be compared via `compareTo`, and the order typically matches `Collator.compare` **if generated from the same collation rules**.

When using it:

- Generate keys with the **same locale, strength, and decomposition**, with the same rule set and compatible version.
- Never mix keys generated from differently configured collators.
- Never use `CollationKey.toByteArray()` bytes as a stable ID across JVMs/versions, because collation formats/orderings can change when providers or locale data are upgraded.
- If the collator configuration changes, previously generated keys must be rebuilt for consistent sorting.

`CollationKey` is a tool for **more efficient comparison in appropriate workloads**, not a database normalization key or a canonical username in a security sense.

Do not optimize prematurely before measuring: for very small lists, generating keys for all elements may not justify the memory overhead; for large datasets, benchmark and consider database or search engine indexing/sorting capabilities.

## 13. Collator Is Not Equivalent to a Text Search Engine

`Collator.compare(a,b)` compares **two complete strings** under collation rules. It does not automatically solve all of these needs:

- Finding a word inside a long paragraph.
- Tokenization for Vietnamese and other languages.
- Analyzing abbreviations, typos, and transliteration.
- Selective accent stripping or relevance ranking.
- Prefix/suffix filtering and highlighting with accurate Unicode offsets.

For instance, `Collator.PRIMARY` may treat `cafe` and `café` as equivalent when comparing two strings, yet it **does not turn `String.contains("cafe")` into accent-insensitive search**. `String.contains` does not accept a `Collator`.

When building a search index, define the analyzer, normalization, collation, tokenization, and locale. Collation ideas can inform matching conditions, while full search requires a dedicated pipeline and data structures.

An easy mistake: if `Normalizer.normalize` changes UTF-16 length, search offsets on the normalized string do not automatically match offsets on the original string. Highlighting features must build and maintain an appropriate offset mapping.

## 14. Relationship to Unicode Normalization

`java.text.Normalizer` and `Collator` are related but do not replace each other:

| Tool | Question it answers |
|---|---|
| `Normalizer.normalize(text, NFC)` | Which canonical form is the string converted into? |
| `Collator.setDecomposition(CANONICAL_DECOMPOSITION)` | During matching, how are combining representation differences handled? |
| `Collator.setStrength(PRIMARY...)` | Which level of difference is considered in the ordering relation? |
| `String.equals` | Do two `String`s contain the exact same UTF-16 content? |

An application can pick a **canonical key** for stored data using `Normalizer`, while using `Collator` for **sorting display lists**. They do not need the same definition of when two strings are "equivalent."

Example policy:

```text
original_title  -> kept intact for display
canonical_code  -> normalized per identity contract
search_text     -> indexed by a dedicated analyzer
sort_order      -> uses Collator per user locale
```

If compare returns 0 at `PRIMARY`, do not infer that two data rows share the same identity. Do not merge customers, accounts, or transactions merely because the collator ignores accents or case.

## 15. Differences Due to Providers and JDK Upgrades

`Collator.getInstance(locale)` returns an implementation from the Java runtime. Locale rules and datasets can differ by:

- JDK version.
- Locale provider configured on the JVM.
- Actual requested locale and level of data support.
- Unicode/CLDR updates and deployment settings.

The `Locale.US` examples above were verified on the JDK used for this lesson. When changing locale/provider, do not hardcode **the sign of compare** for complex character pairs without testing.

If you persist sort orders or collation keys in a cache/index, runtime upgrades may require reindexing or consistency testing. Especially for multinational products, test with real user language data rather than relying solely on English.

### Locale.US Does Not Represent All Languages

Many languages have distinct letters, diacritics, and special casing rules. For instance, classifying a letter's accent or character group in one language may be primary rather than secondary. Thus, "PRIMARY = accent-insensitive" is only a **rough mnemonic in some cases**, not Java's formal definition.

Do not use a single `cafe`/`café` test to prove a system correctly handles all of Vietnamese or other alphabets.

## 16. Thread Safety and Configuration Mutation

`Collator` holds stateful configuration (`strength`, `decomposition`). Do not share a single mutable instance across requests/threads while repeatedly calling `setStrength`:

```java
sharedCollator.setStrength(Collator.PRIMARY);
sharedCollator.compare(a, b);
```

If another thread modifies strength between the two operations, results can deviate from the intended policy. In multithreaded environments, create per-context instances or use `clone()` copies under a clear strategy, and thereafter **never mutate configuration while comparing**. If state is shared, synchronize appropriately.

Likewise, never mutate a `TreeSet/TreeMap` comparator after data has been inserted. With a mutable comparator, the ordering relation can shift while the tree structure is not rebuilt, causing inconsistent lookup results. To change locale/strength, create a new structure and reload the data.

## 17. Essential Test Cases

With `Locale.US` and `CANONICAL_DECOMPOSITION`, you can start with these pairs:

| Pair | PRIMARY | SECONDARY | TERTIARY | IDENTICAL |
|---|---|---|---|---|
| `cafe` / `café` | Equivalent | Different | Different | Different |
| `cafe` / `Cafe` | Equivalent | Equivalent | Different | Different |
| `café` / `cafe\u0301` | Equivalent | Equivalent | Equivalent | Equivalent |

These are verified results from one specific configuration, not a rule for all locales. Also test:

1. The same canonically equivalent pair with `IDENTICAL + NO_DECOMPOSITION` to observe decomposition's impact.
2. Full-width/compatibility characters with `FULL_DECOMPOSITION`, testing whether the application accepts folding them.
3. Accented letters and distinct letters in the locales your product supports, such as Vietnamese.
4. The same list before/after sorting to verify ordering criteria and tie-breakers.
5. `TreeSet`/`TreeMap` with a comparator returning 0 for two distinct raw strings to ensure data is not accidentally dropped.
6. Cross-script visually similar character pairs to confirm collator is not relied upon as spoofing security.
7. Pre/post JDK upgrade outcomes if the system stores collation-dependent sort keys or indexes.
8. Concurrency tests if the application caches Collators, preventing configuration mutation while formatting/comparing.

A good test does not merely assert "compare throws no exception," but states **which conditions should be treated as equivalent** and **which cases must never merge data**.

## 18. Common Mistakes

**1. Assuming `PRIMARY` simply strips all accents in all languages.** In reality, difference ranking depends on locale collation rules.

**2. Assuming `SECONDARY` guarantees ignoring all case differences.** This is a common rule of thumb, but details must be verified against the actual rule set.

**3. Assuming `TERTIARY` equals `String.equals()`.** Collator is still affected by locale/decomposition.

**4. Assuming `IDENTICAL` is byte comparison.** `IDENTICAL` is the highest strength level, yet `CANONICAL_DECOMPOSITION` can still treat two different UTF-16 representations as equivalent.

**5. Forgetting to configure decomposition.** `IDENTICAL` results on precomposed vs. decomposed forms can differ under `NO_DECOMPOSITION`.

**6. Enabling `FULL_DECOMPOSITION` without understanding compatibility mappings.** Some visually styled characters may become equivalent.

**7. Using `collator.compare(a,b)==0` as proof of duplicate accounts.** Linguistic comparison does not define identity unless business rules explicitly specify it.

**8. Using `TreeSet` with PRIMARY and wondering why elements disappear.** Returning 0 from the comparator makes the structure treat them as one key.

**9. Mixing CollationKeys from different collators.** Keys only compare meaningfully under the same configuration rules.

**10. Using the JVM default locale uncontrolled.** Results can vary across environments or users.

**11. Mutating a mutable comparator after populating a TreeMap.** Changing the ordering relation leaves the tree structure inconsistent.

**12. Equating Collator with full-text search.** It is string collation, not tokenization, ranking, or substring matching.

**13. Treating compare results as strictly -1/0/1.** Only negative/zero/positive sign is guaranteed.

**14. Assuming Collator always defeats confusables/homographs.** A string can be visually spoofed without having the expected collation relation; identity security needs a separate solution.

**15. Storing CollationKey bytes as durable IDs across all versions.** Collation rules and JDK data can change; a reindexing strategy is required.

## 19. Self-Check Questions

**Question 1.** How do `Collator.PRIMARY`, `SECONDARY`, and `TERTIARY` differ?

**Answer:** They progressively include more levels of difference: from base letter differences, adding secondary differences typically including accents, up to tertiary differences typically including case/variants. Details depend on locale.

**Question 2.** With `Locale.US` and canonical decomposition, does `cafe` equal `café` at PRIMARY?

**Answer:** Yes in the verified example; at SECONDARY and above, they differ.

**Question 3.** From which strength level do `cafe` and `Cafe` differ in the example?

**Answer:** TERTIARY and above.

**Question 4.** Can precomposed and decomposed `é` compare equal at IDENTICAL?

**Answer:** Yes, if configured with appropriate `CANONICAL_DECOMPOSITION`. With `NO_DECOMPOSITION`, the verified example produces a different result.

**Question 5.** Can using PRIMARY as a `TreeSet` comparator drop two distinct raw strings?

**Answer:** Yes, if the comparator returns 0 for them. `TreeSet` treats the two strings as the same element according to the comparator.

**Question 6.** Is `String.equals()` affected by calling `collator.setStrength(PRIMARY)`?

**Answer:** No. Collator only changes comparisons performed by that object; it does not alter `String` or the meaning of `equals()`.

**Question 7.** Why should `CollationKey.toByteArray()` not be used as a long-term database key?

**Answer:** It is tied to collation rules, configuration, and implementation; it is not an identifier independent of locale/provider/version.

**Question 8.** What must an application do if users should find `café` when querying `cafe`?

**Answer:** Define an accent-insensitive/locale search policy and use an appropriate search pipeline. `Collator.PRIMARY` expresses a lenient comparison between two strings, but does not automatically make `String.contains()` search flexibly.

## 20. Takeaways

- **PRIMARY:** base distinction level.
- **SECONDARY:** adds second-level differences such as accents in many locales.
- **TERTIARY:** adds third-level differences such as case in many locales.
- **IDENTICAL:** highest distinction level **within Collator**, still affected by decomposition.

Choose `Locale`, `strength`, and `decomposition` **explicitly** according to the sorting or matching task. Never use collation equivalence to replace identity rules, data keys, digital signatures, or byte comparison. For lists, `Collator` is great for linguistic ordering; for uniqueness or security, design a separate policy.

**Official documentation:** [Java SE 17 — Collator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Collator.html) · [Java SE 17 — RuleBasedCollator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/RuleBasedCollator.html) · [Java SE 17 — CollationKey](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/CollationKey.html) · [Java SE 17 — Normalizer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html).
