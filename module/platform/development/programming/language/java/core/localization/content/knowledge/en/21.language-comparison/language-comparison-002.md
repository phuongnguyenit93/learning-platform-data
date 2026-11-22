# `Collator.getInstance` by `Locale`: Language-Aware String Comparison and Sorting in Java

## 1. Why Alphabetical Order Differs Across Languages

When displaying lists of personal names, place names, product categories, or terms to international users, sorting by Unicode code value is usually **not equivalent to the sorting order native speakers expect**.

For example, in Swedish, the letters `å`, `ä`, `ö` have their own positions at the end of the alphabet, after `z`; in standard German comparison, `ä` is usually sorted near `a`, before `z`. Given the same two strings `"ä"` and `"z"`, the result can differ depending on language:

```text
Swedish Locale (sv-SE):  z < ä
German Locale  (de-DE):  ä < z
```

Therefore, `String.compareTo()` or `Collections.sort(list)` using default Unicode order cannot be treated as the sole definition of **natural language sorting**.

Java provides `java.text.Collator`: a comparator (*collation*) capable of applying rules by `Locale`. Common creation pattern:

```java
Collator collator =
        Collator.getInstance(Locale.forLanguageTag("vi-VN"));
```

Then:

```java
int result = collator.compare("a", "ă");
```

The sign of `result` indicates the order according to **that collator's collation rules**. Exact behavior depends on the locale, distinction level, accent handling, and runtime locale data.

**Core point:** `Collator.getInstance(locale)` obtains a comparator **for the requested locale**. It does not translate text, does not normalize all data, does not guarantee identical order across all JDKs, and does not implicitly turn comparison into an identity equality check.

## 2. What Is `Collator` and How Does It Differ from `String.compareTo()`?

| Feature | `String.compareTo(...)` | `Collator.compare(...)` |
| --- | --- | --- |
| Basis of comparison | UTF-16 code unit order, per `String` rules | `Locale` collation rules and `Collator` configuration |
| Depends on `Locale` | No | Yes |
| Accents and uppercase/lowercase | Different codes may differ in order without linguistic semantics | Distinction level is configurable |
| Sorting names and words in UI | Not always appropriate | Usually more appropriate when the right locale is chosen |
| Order stability across new locale data | Fixed by `String` rules, independent of CLDR data | May change across JDK, data provider, and collation rules |
| Used for identifiers/signatures/hashes? | Still requires its own contract | **Should not** replace byte equality or security identifiers |

`Collator` is an abstract class in the `java.text` package implementing `Comparator<Object>` and `Cloneable`. Concrete implementations, such as `RuleBasedCollator`, execute the comparison policy. Most application code only needs the `getInstance` factory rather than defining all rules manually.

`compare(a,b)` returns an `int`:

- **Negative** value: `a` comes before `b`.
- **`0`**: `a` and `b` are considered **equivalent under the current collation configuration**.
- **Positive** value: `a` comes after `b`.

**Do not compare strictly against `-1` or `1`**: the `Comparator` contract only requires negative/0/positive sign. Use `Integer.signum(result)` if you want to display a normalized sign in examples.

`compare(a,b)==0` **does not mean** `a.equals(b)`. For example, when configured to ignore accents, `"resume"` and `"résumé"` can be collation-equal while remaining two distinct Java strings.

## 3. The `getInstance` Factory and Selecting a `Locale`

There are two main overloads:

```java
Collator.getInstance()
Collator.getInstance(Locale desiredLocale)
```

- `getInstance()` retrieves a comparator for the **JVM's default locale**.
- `getInstance(locale)` requests a comparator for an explicit locale, e.g. `Locale.US`, `Locale.GERMANY`, `Locale.forLanguageTag("sv-SE")`, `Locale.forLanguageTag("vi-VN")`.

In multi-user applications, pass **the locale of the sorting operation** instead of implicitly relying on the server's default locale:

```java
Locale locale = Locale.forLanguageTag("vi-VN");
Collator collator = Collator.getInstance(locale);
```

This is an illustrative snippet requiring imports of `java.util.Locale` and `java.text.Collator`.

**How to determine the locale:** if sorting a list for a user in a Vietnamese UI, `vi-VN` can be used. However, data may span multiple languages, or the product may require a sorting locale independent of the UI locale (e.g., a global reference catalog). In that case, **explicitly define the list's sorting locale**, rather than inferring it from IP address, timezone, or server language.

### Is the Locale Supported?

`Collator.getAvailableLocales()` returns the list of locales advertised as supported by the runtime and installed collation providers. However:

- The list may differ across runtimes/vendors and providers.
- `getInstance(locale)` may use appropriate fallback data if the exact requested variant is not found, rather than guaranteeing a unique rule set for every language tag.
- Do not treat the ability to construct `Locale.forLanguageTag("xx-YY")` as proof that Java has dedicated collation data for that locale.
- Some Unicode locale extensions (e.g., collation identifier) may be recognized by a provider; do **not** assume every JDK/provider understands and applies every extension. Test the actual supported locale tags.

`Locale.getDefault()` is environment state that can be mutated and make sort results unstable. For protocol/API data requiring a fixed order, do not implicitly depend on `Locale.getDefault()`.

## 4. Runnable Example: Same Letters, Swedish vs. German Order

Create **`CollatorLocaleDemo.java`**:

```java
import java.text.Collator;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public class CollatorLocaleDemo {
    private static void show(Locale locale, List<String> source) {
        Collator collator = Collator.getInstance(locale);
        List<String> sorted = new ArrayList<>(source);

        sorted.sort((a, b) -> collator.compare(a, b));

        System.out.println(locale.toLanguageTag() + ": " + sorted);
        System.out.println("compare(ä,z)=" +
                Integer.signum(collator.compare("ä", "z")));
    }

    public static void main(String[] args) {
        List<String> words = List.of("z", "ä", "a", "ö");

        show(Locale.forLanguageTag("sv-SE"), words);
        show(Locale.GERMANY, words);
    }
}
```

Compile/run on JDK 17+ with a UTF-8 source file:

```bash
javac -encoding UTF-8 CollatorLocaleDemo.java
java -cp . CollatorLocaleDemo
```

**Reference output** with typical modern JDK collation data:

```text
sv-SE: [a, z, ä, ö]
compare(ä,z)=1
de-DE: [a, ä, ö, z]
compare(ä,z)=-1
```

**Why do they differ?** `Collator.getInstance` selects linguistic rules. With `sv-SE`, `ä` comes **after** `z`; with `de-DE`, it is placed **before** `z`. Even though both runs use the exact same four source strings, the sorted order differs.

This is an example of **language-based collation rules**, not a contract for exact ordering across all locales/JDKs. Collation data typically depends on linguistic rule sets and can change between runtime versions. When defining storage order or durable pagination, pin or version the comparison rules.

### Avoid Mutating the Original Data Order

The example copies `source` into `new ArrayList<>(source)` before sorting because `List.of(...)` is an unmodifiable list. Calling `sort` directly on a list that does not support modification will fail. Additionally, copying lets us display two locales without affecting the source list.

## 5. `Collator.setStrength`: "Equality" Depends on Level

In addition to locale, `Collator` has a **strength** property: the level of difference considered significant.

| Level | General idea | Typical example |
| --- | --- | --- |
| `PRIMARY` | Distinguishes only primary differences at the base-letter level | May treat `e` and `é`, `a` and `A` as equivalent in some locales |
| `SECONDARY` | Adds secondary differences, usually including accents | May distinguish `e` and `é`, while not yet distinguishing case |
| `TERTIARY` | Adds tertiary differences, usually including case | May distinguish `a` from `A` |
| `IDENTICAL` | Checks the finest differences between strings when previous levels are equal | May distinguish Unicode representations under certain decomposition modes |

**Note:** how a linguistic feature is assigned to primary/secondary/tertiary **depends on the locale and provider**. The table above is a general intuition and does **not** mean every accent or letter pair across all languages falls at the same level. For instance, an accented letter in Vietnamese may belong to a different class depending on collation rules.

Configuration:

```java
Collator c = Collator.getInstance(Locale.US);
c.setStrength(Collator.PRIMARY);
```

Calling `setStrength` mutates the state of the **existing instance**. Therefore **`Collator` is not immutable**, unlike `DateTimeFormatter`.

### Program Verifying Each Strength Level

Create **`CollatorStrengthDemo.java`**:

```java
import java.text.Collator;
import java.util.Locale;

public class CollatorStrengthDemo {
    private static void show(String name, int level) {
        Collator collator = Collator.getInstance(Locale.US);
        collator.setStrength(level);

        System.out.println(name
                + ": e_vs_é="
                + Integer.signum(collator.compare("e", "é"))
                + ", a_vs_A="
                + Integer.signum(collator.compare("a", "A")));
    }

    public static void main(String[] args) {
        show("PRIMARY", Collator.PRIMARY);
        show("SECONDARY", Collator.SECONDARY);
        show("TERTIARY", Collator.TERTIARY);
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 CollatorStrengthDemo.java
java -cp . CollatorStrengthDemo
```

Reference result under typical US data:

```text
PRIMARY: e_vs_é=0, a_vs_A=0
SECONDARY: e_vs_é=-1, a_vs_A=0
TERTIARY: e_vs_é=-1, a_vs_A=-1
```

At `PRIMARY`, the example treats strings differing in accents or case as equivalent. As strength increases, those differences become significant. Do not use `PRIMARY` to check duplicate **account identifiers** if business rules require distinguishing these strings.

`Collator.getInstance(locale)` can create a collator with runtime-determined default settings. For predictable application behavior, **set strength explicitly** when required by the domain; never assume the default suits search, sorting, filtering, or duplicate checking alike.

## 6. `setDecomposition`: Canonical Normalization and Comparison

Unicode allows certain characters to have multiple canonically equivalent representations. For example:

```text
"é"       = U+00E9
"é"  = U+0065 U+0301
```

`Collator` has a **decomposition** property controlling how composed/decomposed strings are handled during collation:

- `Collator.NO_DECOMPOSITION`: does not perform canonical decomposition during comparison.
- `Collator.CANONICAL_DECOMPOSITION`: handles canonical decomposition when comparing.
- `Collator.FULL_DECOMPOSITION`: additionally handles compatibility decomposition forms, which may affect matching.

Changed via `setDecomposition(...)`. This setting is independent of `setStrength(...)` in the API, though the two settings work together to determine the `compare` outcome.

**Distinguishing `Collator` from `Normalizer`:**

```java
Collator collator = Collator.getInstance(Locale.US);
collator.setDecomposition(Collator.CANONICAL_DECOMPOSITION);
```

`Collator` compares **two strings** using linguistic rules; it does not return a normalized string for storage. `Normalizer.normalize(text, Normalizer.Form.NFC)` produces a **new string** in the chosen normal form; it does not replace locale-based collation.

A runnable example:

Create **`CollatorDecompositionDemo.java`**:

```java
import java.text.Collator;
import java.util.Locale;

public class CollatorDecompositionDemo {
    public static void main(String[] args) {
        String a = "\u00E9";
        String b = "e\u0301";

        Collator collator = Collator.getInstance(Locale.US);
        collator.setStrength(Collator.TERTIARY);
        collator.setDecomposition(
                Collator.CANONICAL_DECOMPOSITION);

        System.out.println("String.equals=" + a.equals(b));
        System.out.println("Collator.equal=" +
                (collator.compare(a, b) == 0));
    }
}
```

Commands:

```bash
javac -encoding UTF-8 CollatorDecompositionDemo.java
java -cp . CollatorDecompositionDemo
```

Output:

```text
String.equals=false
Collator.equal=true
```

This illustrates the difference between **exact string value** and **collation comparison equivalence**. Do not use `collator.compare(a,b)==0` to infer that two strings match code-unit-for-code-unit, byte-for-byte, code-point-for-code-point, or have the same hash value.

## 7. Using `Collator` to Sort a `List<String>`

Direct approach:

```java
Locale locale = Locale.forLanguageTag("vi-VN");
Collator collator = Collator.getInstance(locale);

List<String> names = new ArrayList<>(
        List.of("An", "Bình", "Ánh", "Dũng"));

names.sort((a, b) -> collator.compare(a, b));
```

This is an **illustrative snippet**, not a standalone program; it requires importing `Collator`, `Locale`, `List`, `ArrayList`.

Equivalent options depending on the API:

```java
names.sort(collator::compare);
Collections.sort(names, collator::compare);
```

`Collator` implements `Comparator<Object>`, so a lambda or method reference can clarify the `String` type. `List.sort` sorts **in place**, so the list must support modification.

**Do not do this:**

```java
// Not natural language sorting rules:
names.sort(String::compareTo);
```

The snippet above may be valid for protocol data or system keys requiring Unicode code order, but must not be treated as a substitute for sorting user names by locale.

### Defining a Tie-Breaker When Two Values Are Collation-Equal

If at low strength two strings yield `compare(...) == 0`, Java's `List.sort` is a **stable sort**: comparator-equal elements preserve their relative order. In a UI with input from multiple sources, achieving a deterministic overall sort across reloads may require a secondary criterion.

Example:

```java
Comparator<String> comparator = (a, b) -> {
    int byLocale = collator.compare(a, b);
    return byLocale != 0 ? byLocale : a.compareTo(b);
};
names.sort(comparator);
```

This snippet assumes `collator` and `names` have been created and requires importing `Comparator`. It selects code-unit order as the **tie-breaker**. However, use a tie-breaker only when **the goal is deterministic sorting**; if business rules want two strings treated as the same name for lookup, do not mix this rule into the definition of "equality" without documenting it.

## 8. Warning About `TreeSet`, `TreeMap`, and the Meaning of `compare == 0`

This is a very common design mistake.

`TreeSet` and `TreeMap` use the comparator to decide whether two keys are **equivalent in the sorted structure**. If the comparator returns `0`, two strings can be treated as **the same key**, even when `String.equals` returns `false`.

Runnable example—create **`CollatorSetDemo.java`**:

```java
import java.text.Collator;
import java.util.Locale;
import java.util.Set;
import java.util.TreeSet;

public class CollatorSetDemo {
    public static void main(String[] args) {
        String first = "resume";
        String second = "résumé";

        Collator collator = Collator.getInstance(Locale.US);
        collator.setStrength(Collator.PRIMARY);

        Set<String> set = new TreeSet<>(
                (a, b) -> collator.compare(a, b));

        set.add(first);
        set.add(second);

        System.out.println("equals=" + first.equals(second));
        System.out.println("collationEqual=" +
                (collator.compare(first, second) == 0));
        System.out.println("setSize=" + set.size());
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 CollatorSetDemo.java
java -cp . CollatorSetDemo
```

Illustrative result with the US locale:

```text
equals=false
collationEqual=true
setSize=1
```

**Explanation:** `TreeSet` uses the comparator to determine uniqueness. Because `PRIMARY` considers the two words equivalent in this example, the set retains only **one element**, not two.

This can be intentional if building a word list merged by pronunciation/spelling; however, it is usually **wrong** if each user identifier or exact data string must be kept. When building set/map structures, explicitly decide whether "equal" means linguistically equal or identity-equal. If both concepts are needed simultaneously, store identity under a separate key and use collator only to sort the display layer.

**Never change the comparator's strength or decomposition after inserting it into a populated `TreeSet`/`TreeMap`.** Changing comparison ordering while the structure holds elements can break ordering and lookup invariants.

## 9. `CollationKey`: When Comparing Many Times

Each call to `Collator.compare(a,b)` may have to process multiple linguistic rules. If a large list is sorted repeatedly or the same strings participate in many comparisons, Java provides `CollationKey`:

```java
CollationKey key = collator.getCollationKey(text);
```

Keys generated from the **same collation configuration** can be compared via `keyA.compareTo(keyB)`. This pattern is useful when converting each string to a key once and reusing those keys during sorting.

Standalone example **`CollationKeyDemo.java`**:

```java
import java.text.CollationKey;
import java.text.Collator;
import java.util.Locale;

public class CollationKeyDemo {
    public static void main(String[] args) {
        Collator collator = Collator.getInstance(Locale.US);
        collator.setStrength(Collator.TERTIARY);

        CollationKey apple = collator.getCollationKey("apple");
        CollationKey banana = collator.getCollationKey("banana");

        System.out.println("appleBeforeBanana=" +
                (apple.compareTo(banana) < 0));
        System.out.println("sameLocale=" +
                apple.getSourceString().equals("apple"));
    }
}
```

Run:

```bash
javac -encoding UTF-8 CollationKeyDemo.java
java -cp . CollationKeyDemo
```

Output:

```text
appleBeforeBanana=true
sameLocale=true
```

**Never compare `CollationKey`s from two different collators**—especially if locale, strength, decomposition, or provider data differs. `CollationKey` applies within a single consistent **collation profile**, not as a universal classification key across locales.

Do not treat collation key bytes as a durable version-independent storage format. If used as a sort index in a database/cache, you need an invalidation or rebuild policy when collation rules, CLDR data, JDK, or strength change.

### When to Choose `compare` vs. `CollationKey`?

- **One or a few comparisons:** call `collator.compare(a,b)` directly; it is simpler.
- **Many comparisons over the same string set:** consider building `CollationKey` once; measure performance and memory cost.
- **Large datasets in a database:** examine DB collation and how to align it with Java; avoid generating all Java keys in memory when a DB query already supports language-accurate sorting and consistent rules.

## 10. Distinguishing Linguistic Comparison from Unicode Normalization

`Normalizer` handles Unicode representations in canonical or compatibility forms: `NFC`, `NFD`, `NFKC`, `NFKD`. Meanwhile, `Collator` performs **locale-based comparison ordering**, which may treat strings with different code points as equivalent at a given strength.

| Need | API or mechanism to consider |
| --- | --- |
| Bring precomposed `é` and `e + acute` to a single canonical form | `Normalizer.normalize(..., NFC)` or NFD per contract |
| Sort Vietnamese names per language rules | `Collator.getInstance(Locale.forLanguageTag("vi-VN"))` |
| Ignore certain accents/case during matching | Locale-based collation strength, or a specialized search index |
| Compare IDs exact per Java character | `String.equals` along with a documented canonicalization/validation contract |
| Compare cryptographic data, signatures, tokens | Specific byte/encoding/protocol rules; do not use collator |
| Word segmentation, fuzzy search, selective accent stripping | Dedicated search engine/algorithm, not just `Collator` |

`Collator` **does not sanitize input, does not remove control characters, does not prevent homograph attacks**, and does not verify identity. Two visually similar letters from different scripts may have different comparison rules; do not derive security policy from a `compare` result.

For heterogeneous Unicode data, define a normalization profile before storage/indexing; use locale-based collation when **displaying or searching by language**. The two steps complement rather than replace each other.

## 11. Using `Collator` in Multithreaded Applications

`Collator` has setters such as `setStrength` and `setDecomposition`, making it a **mutable object**. Do not keep a singleton `Collator` and mutate strength/locale per request.

Some JDK implementations may synchronize internal comparison to allow concurrent execution, yet multiple threads sharing a single `RuleBasedCollator` can still cause significant **contention**; nor does that make concurrent configuration mutation a safe design. A prudent strategy:

- Create a separate `Collator.getInstance(locale)` per task/thread or use `clone()` from a **fully configured template collator**.
- Do not change strength/decomposition while other threads are comparing with the same instance.
- If caching, keep **configuration immutable at the application level**: do not allow callers to mutate a shared cached object directly; consider cloning per task.
- Use a comparator with a stable configuration throughout an **entire sort operation**; do not alter properties mid-sort.
- Measure performance on realistic workloads under high request volume; do not choose a shared cache merely to save instantiation cost only to introduce a bottleneck.

Technical example:

```java
Collator template = Collator.getInstance(locale);
template.setStrength(Collator.TERTIARY);

// Each task gets its own copy, never mutating template:
Collator local = (Collator) template.clone();
```

This is an **illustrative snippet**, assuming `locale` exists; it requires importing `Collator`. If `template` is published to other threads, prevent callers from mutating it while used as a template.

Unlike `java.time.DateTimeFormatter`, `Collator` **has no immutability contract** merely because it is stored in a `static final` field.

## 12. Implications for Pagination, Database Storage, and File Export

Distinguish two scenarios:

**Displaying a list to one user:** using a collator with the appropriate locale and strength can produce natural ordering.

**Persisting durable order / consistent server-client pagination:** if the server uses database collation while the Java application uses `Collator` with different rules, `ORDER BY` results, page boundaries, or tie ordering can diverge. When that happens:

1. Establish **a single authoritative source of sort rules** for paginated data.
2. Record locale, version, and strength if results must be reproducible.
3. Have a stable secondary criterion (e.g., ID) to break ties when multiple strings are collation-equivalent.
4. Do not use a runtime's collation key as a permanent key without a versioning strategy.
5. Re-test when upgrading the JDK, locale provider, CLDR data, or database collation.

If a system supports multiple locales yet relies on **a single index** for all users, weigh performance, user choice of sorting locale, and business consistency requirements. There is no single "universal" alphabetical order optimal for all languages.

## 13. Common Mistakes and How to Avoid Them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using `String.compareTo` to sort multilingual names | Order follows UTF-16 instead of linguistic convention | Use `Collator.getInstance(locale)` |
| Using `Collator.getInstance()` on the server without managing default locale | Results may depend on environment | Pass `Locale` explicitly |
| Assuming `getInstance(locale)` translates data | No translation occurs | Separate resource localization from collation |
| Assuming every `Locale` has full dedicated rules | May fall back to other/provider rules | Check the actual runtime and `getAvailableLocales` |
| Treating `compare()==0` as `String.equals` | Accidentally merges data or accounts | Pick the right notion of equality per domain |
| Using `PRIMARY` in `TreeSet` to store accent-differing strings | May drop elements such as `resume`/`résumé` | Use a separate identity key or appropriate comparator |
| Calling `setStrength` after `TreeMap` holds data | Corrupts tree ordering/lookup | Freeze comparator upon creating structure |
| Persisting collation keys permanently | No guarantee across versions/locales | Manage versions and rebuild on policy change |
| Comparing `CollationKey`s from two different collators | Results have no meaning under a single profile | Compare only keys from the same profile |
| Assuming `setDecomposition` replaces `Normalizer.normalize` | Does not produce a normalized string for storage | Use `Normalizer` when data normalization is needed |
| Sharing a mutable singleton and mutating strength per user | Configuration cross-talk across requests | Per-task clone/instance with stable configuration |
| Trusting sort snapshots across all JDK/versions | Locale data and collation may change | Test target environment, version when needed |
| Using collation for authentication/security | May conflate differently encoded strings | Security must follow identity profiles and byte/canonical rules |

## 14. Implementation and Testing Workflow

When adding locale-aware sorting to a feature:

1. **Define scope:** list of person names, cities, dictionary, categories; display result or storage key?
2. **Choose Locale explicitly:** from user settings or product policy; never implicitly use the JVM locale for multi-user features.
3. **Choose strength/decomposition:** determine whether accents, case, or all differences must be distinguished; test against the supported language set.
4. **Create a collator per sort operation:** finish configuring before sorting, never mutate while the comparator is in use.
5. **Distinguish equality from ordering:** if using `TreeSet`/`TreeMap` or duplicate checks, clarify the impact of `compare()==0`.
6. **Unicode data:** maintain a separate storage/normalization policy as needed; do not use collation instead of validation.
7. **Pagination/DB:** align sort rules between Java, queries, and APIs; include a stable tie-breaker.
8. **Test across locales:** Swedish/German for `ä`, Vietnamese with tone marks, multi-script mixed data, words differing only in case or accents.
9. **Test runtime changes:** JDK/CLDR/provider updates can change ordering; document locale data and avoid overly rigid snapshots when unnecessary.
10. **Benchmark performance:** when sorting large volumes repeatedly, compare direct cost against `CollationKey`; do not assume key caching is always faster.

A short contract test for locale rules (without asserting an entire alphabet order) might look like:

```java
import java.text.Collator;
import java.util.Locale;

public class CollatorAssertions {
    private static void require(boolean condition) {
        if (!condition) {
            throw new AssertionError("Collation assertion failed");
        }
    }

    public static void main(String[] args) {
        Collator swedish = Collator.getInstance(
                Locale.forLanguageTag("sv-SE"));
        Collator german = Collator.getInstance(Locale.GERMANY);

        require(swedish.compare("ä", "z") > 0);
        require(german.compare("ä", "z") < 0);

        Collator us = Collator.getInstance(Locale.US);
        us.setStrength(Collator.PRIMARY);
        require(us.compare("resume", "résumé") == 0);

        require(!"resume".equals("résumé"));
        System.out.println("4 checks passed");
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 CollatorAssertions.java
java -cp . CollatorAssertions
```

Result on a JDK with matching collation rules as in the example:

```text
4 checks passed
```

Because sort outcomes depend on locale data, these assertions work well as **regression tests for a chosen runtime**, and should not be treated as proof independent of all versions and providers. If the provider changes, evaluate whether the collation change is acceptable for product requirements.

## 15. Summary

- Use **`Collator.getInstance(Locale)`** when comparing/sorting strings for a specific language; avoid relying on the server's default locale.
- `Collator.compare(a,b)` returns **negative, 0, or positive** per locale rules and configuration, not per `String.compareTo`.
- `setStrength` controls the level of difference deemed significant; `setDecomposition` affects Unicode decomposition handling during comparison.
- `compare()==0` can occur for strings **not equal under `String.equals`**. Be especially careful with `TreeSet`, `TreeMap`, and identity validation.
- Use `CollationKey` for many repeated comparisons with the same profile, but never mix keys across collators or use them as unversioned persistent storage.
- `Collator` is **mutable**; stabilize configuration before sorting, and consider per-task instances/clones in multithreaded environments.
- **Locale, strength, decomposition, provider, and runtime data** can all influence ordering. For pagination and durable data, design consistent sort rules between Java and the storage system.
