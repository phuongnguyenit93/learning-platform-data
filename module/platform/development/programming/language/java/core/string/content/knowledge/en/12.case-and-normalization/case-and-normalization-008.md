# `Collator` in Java: Comparing Strings by Language Rules

When users view a list of names, words, or product labels, they usually expect **alphabetical order according to their language**. That order can differ from the UTF-16 order used by `String.compareTo()`. Java provides **`java.text.Collator`** to compare and sort strings according to `Locale`-dependent *collation* rules, such as Vietnamese, German, or Swedish.

**Main idea:** `String.equals()` checks identical content; `String.compareTo()` compares by string code unit order; **`Collator.compare(a, b)`** determines order (and equivalence level during comparison) according to language and configuration. `Collator` is very useful for user-facing UIs or lists, but is not automatically the right tool for validating tokens, identifiers, or access permissions.

## 1. Why do we need `Collator`?

Alphabets do not always treat accented letters the same way. For example, in common German sorting, `ä` is typically sorted near `a`; whereas in Swedish, `ä` comes after `z`. Therefore, an ordering based on UTF-16 values cannot represent every language.

Java has four familiar comparison approaches:

| API | Basic rule | Appropriate use case |
| --- | --- | --- |
| `a.equals(b)` | Compares **entire `String` content**; sensitive to case and code units | Checking codes, exact strings |
| `a.compareTo(b)` | Lexicographical order based on **UTF-16 code units**, `Locale`-independent | Fixed technical sorting conventions |
| `collator.compare(a, b)` | Compares by **`Locale` collation rules and configuration** | Sorting names, words, and display labels |
| `a.compareToIgnoreCase(b)` | Case-insensitive comparison per `String`'s rules, **not `Locale`-based collation** | Simple comparisons when linguistic rules are unnecessary |

Example of using `Collator`:

```java
import java.text.Collator;
import java.util.Locale;

Collator collator = Collator.getInstance(Locale.forLanguageTag("vi-VN"));
int result = collator.compare("An", "Bình");
```

This is an **illustrative code snippet placed inside a method**. `Locale.forLanguageTag("vi-VN")` specifies the desired language and region. The JDK's locale data provider determines the actual rules applied; when specialized data is missing, the runtime may fall back to default rules. Therefore, test on your target JDK and deployment locale, especially for accented names.

## 2. Obtaining a `Collator` by `Locale` and interpreting results

`Collator` is an abstract class. Typically you do not call `new Collator()` directly, but obtain an instance via:

```java
Collator collator = Collator.getInstance(Locale.US);
```

Several ways to create a `Locale`:

```java
Locale vietnamese = Locale.forLanguageTag("vi-VN");
Locale swedish = Locale.forLanguageTag("sv-SE");
Locale german = Locale.GERMAN;
```

The examples above are declarations used within scope of `import java.util.Locale;`.

The return value of `collator.compare(a, b)` is an integer:

- **Negative**: `a` comes before `b` according to the collator.
- **Zero**: `a` and `b` are considered **equivalent at the configured comparison level**.
- **Positive**: `a` comes after `b`.

Do not rely on exact values like `-1` or `1` in all cases. Check `< 0`, `== 0`, and `> 0`; for demonstrations that want to print the comparison sign, you can use `Integer.signum(...)` to normalize the result to `-1`, `0`, or `1`.

### Example: same characters, different order across locales

Save as `LocaleOrderDemo.java`:

```java
import java.text.Collator;
import java.util.Locale;

public class LocaleOrderDemo {
    public static void main(String[] args) {
        Collator german = Collator.getInstance(Locale.GERMAN);
        Collator swedish = Collator.getInstance(
                Locale.forLanguageTag("sv-SE"));

        String aUmlaut = "\u00E4"; // ä

        System.out.println(Integer.signum(
                german.compare(aUmlaut, "z")));
        System.out.println(Integer.signum(
                swedish.compare(aUmlaut, "z")));
    }
}
```

Compile and run with Java 17+:

```bash
javac -encoding UTF-8 LocaleOrderDemo.java
java LocaleOrderDemo
```

With the OpenJDK locale data used in the example, output:

```text
-1
1
```

`-1` on the first line indicates `ä` sorts before `z` in the German example; `1` on the second line indicates `ä` sorts after `z` in the Swedish example. **Rule sets can vary by JDK version, locale provider configuration, and linguistic data**, so do not treat one example output as an immutable ranking across every environment. When reproducibility across systems is required, pin the runtime environment and collation version.

## 3. Adjusting sensitivity with `setStrength()`

`Collator` lets you set the comparison **strength**. Higher levels examine finer differences between strings.

| Strength | Main idea | Differences that typically take effect |
| --- | --- | --- |
| `Collator.PRIMARY` | Compares primary base-letter differences | In many locales, accented vs. unaccented and uppercase vs. lowercase may be treated as equivalent |
| `Collator.SECONDARY` | Also considers secondary differences | Usually adds differences in accents or character variants |
| `Collator.TERTIARY` | Also considers tertiary differences | Usually adds uppercase/lowercase differences and other variants |
| `Collator.IDENTICAL` | Recognizes even finer distinctions | Useful when distinguishing nearly at the representation level; affected by decomposition mode |

**Note:** These are directional descriptions; exactly how an accent, letter variant, or ligature rule is weighed depends on **`Locale` and collation data**. For instance, do not assert that every locale ignores every accent at `PRIMARY`. If you need "accent-free" filtering or Vietnamese search with special rules, test against the actual dataset.

### Example: case and accents

Save as `CollatorStrengthDemo.java`:

```java
import java.text.Collator;
import java.util.Locale;

public class CollatorStrengthDemo {
    public static void main(String[] args) {
        Collator collator = Collator.getInstance(Locale.US);

        collator.setStrength(Collator.PRIMARY);
        System.out.println(collator.compare(
                "resume", "r\u00E9sum\u00E9") == 0);
        System.out.println(collator.compare(
                "Java", "java") == 0);

        collator.setStrength(Collator.SECONDARY);
        System.out.println(collator.compare(
                "resume", "r\u00E9sum\u00E9") == 0);
        System.out.println(collator.compare(
                "Java", "java") == 0);

        collator.setStrength(Collator.TERTIARY);
        System.out.println(collator.compare(
                "Java", "java") == 0);
    }
}
```

Run:

```bash
javac -encoding UTF-8 CollatorStrengthDemo.java
java CollatorStrengthDemo
```

Output with the tested locale data:

```text
true
true
false
true
false
```

Explanation:

1. At `PRIMARY` with `Locale.US`, `resume` and `résumé` are treated as equivalent; `Java` and `java` are also equivalent.
2. At `SECONDARY`, the acute accent difference makes `resume` and `résumé` no longer equivalent; the case difference between `Java` and `java` is still ignored in this example.
3. At `TERTIARY`, `Java` and `java` are no longer equivalent in this example.

Because `setStrength()` changes the comparison policy, **do not mutate a collator's configuration while a collection sorted or indexed by that collator is in active use**; comparison order must stay consistent throughout operations.

### `compare(a, b) == 0` differs from `a.equals(b)`

`String.equals()` returns `true` only when string contents match according to `String`'s rules. `Collator.compare(a, b) == 0` only reports that two strings do not differ **under the current strength/locale/decomposition**. At lower strength, distinct strings can be treated as equivalent.

This also affects `TreeSet` or `TreeMap`: if a collator is used as the comparator, two keys with `compare() == 0` are treated by the collection as the same key for ordering, even though `String.equals()` returns `false`. Do not use a low-strength collator to store a key set that must distinguish every character exactly.

## 4. `setDecomposition()`: precomposed characters and combining marks

Unicode allows certain text to be represented by different yet **canonically equivalent** code point sequences:

- `"\u00E9"`: precomposed `é` (U+00E9).
- `"e\u0301"`: letter `e` and combining acute accent U+0301.

`String.equals()` compares code unit contents and therefore usually returns `false` for these two representations. Meanwhile, linguistic comparison often wants to treat them as equivalent.

`Collator` provides decomposition modes:

- `Collator.NO_DECOMPOSITION`: does not require canonical decomposition before comparing; usually faster, but requires care with equivalent Unicode forms.
- `Collator.CANONICAL_DECOMPOSITION`: accounts for canonically equivalent decompositions; appropriate when handling precomposed letters and combining marks consistently.
- `Collator.FULL_DECOMPOSITION`: broader compatibility decomposition, which can treat additional representations as collation-equivalent; **do not pick this level if business rules require distinguishing compatibility characters**.

### Complete example for Unicode forms

Save as `CanonicalDemo.java`:

```java
import java.text.Collator;
import java.util.Locale;

public class CanonicalDemo {
    public static void main(String[] args) {
        String composed = "Caf\u00E9";
        String decomposed = "Cafe\u0301";

        Collator collator = Collator.getInstance(Locale.US);
        collator.setStrength(Collator.TERTIARY);
        collator.setDecomposition(
                Collator.CANONICAL_DECOMPOSITION);

        System.out.println(composed.equals(decomposed));
        System.out.println(
                collator.compare(composed, decomposed) == 0);
    }
}
```

Run:

```bash
javac -encoding UTF-8 CanonicalDemo.java
java CanonicalDemo
```

Output:

```text
false
true
```

Both strings render similarly as `Café`. However, `equals()` compares differing code sequences; `Collator` with canonical decomposition treats them as equivalent in this example configuration.

**Distinction:** `Normalizer.normalize(text, Normalizer.Form.NFC)` is an operation that *transforms content* into a canonical form. In contrast, `collator.compare(...)` is a rule-based *comparison*; it neither replaces nor modifies the two input `String`s.

## 5. Using `Collator` to sort lists

`Collator` implements `Comparator`, so it can be passed directly to `List.sort(...)` or `Collections.sort(...)`. Standalone example `CollatorSortDemo.java`:

```java
import java.text.CollationKey;
import java.text.Collator;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.TreeSet;

public class CollatorSortDemo {
    public static void main(String[] args) {
        Collator collator = Collator.getInstance(Locale.US);

        List<String> names = new ArrayList<>(
                List.of("Zoe", "Alice", "Bob"));
        names.sort(collator);
        System.out.println(names);

        List<String> fromKeys = names.stream()
                .map(collator::getCollationKey)
                .sorted()
                .map(CollationKey::getSourceString)
                .toList();
        System.out.println(fromKeys);

        collator.setStrength(Collator.PRIMARY);
        TreeSet<String> unique = new TreeSet<>(collator);
        unique.add("resume");
        unique.add("r\u00E9sum\u00E9");
        System.out.println(unique.size());
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 CollatorSortDemo.java
java CollatorSortDemo
```

Output with the tested `Locale.US` configuration:

```text
[Alice, Bob, Zoe]
[Alice, Bob, Zoe]
1
```

The first two lines demonstrate sorting directly with `Collator` and using `CollationKey` keys. The last line shows that `TreeSet` at `PRIMARY` retains only **one key under the comparison relation**, because `resume` and `résumé` are treated as equivalent by the collator. It does **not** prove the two `String`s have identical content under `equals()`.

### When to use `CollationKey`?

`CollationKey` stores a comparison key derived from a `Collator`. For a set of strings compared repeatedly (such as sorting the same data multiple times), computing keys once can reduce the work of analyzing each string on every comparison.

Usage rules:

1. Generate keys using the **same collator with the same `Locale`, strength, and decomposition settings**.
2. Compare/sort keys with `CollationKey.compareTo(...)`.
3. Use `getSourceString()` to retrieve the original string when needed.
4. Weigh key creation/storage overhead against comparing just a few strings; do not default to `CollationKey` in every case.

Do not compare keys created by collators with different rules, because their orderings may be incompatible. When changing strength or decomposition, **regenerate the keys** if consistent comparison must continue.

## 6. Safety rules and practical limitations

### 6.1. Fixed locale or user locale?

- **Sorting data for display:** choose the `Locale` matching the language/environment the user wants to view. For instance, `Locale.forLanguageTag("vi-VN")` when sorting Vietnamese names.
- **Need consistent results across servers:** pin the locale, JDK version, collation data, and configuration; document changes during runtime upgrades. Even with the same locale tag, collation data across different systems can differ.
- **Do not use the default blindly:** `Collator.getInstance()` uses the host's default locale, so results can depend on the environment. Once business rules are defined, pass `Locale` explicitly.

### 6.2. Do not use linguistic collation to verify identity or security

Lower strength levels can treat distinct strings as equivalent; this is helpful for **display sorting** but inappropriate for:

- Tokens, API keys, session IDs, passwords.
- Case-sensitive identifiers.
- Keys that must match strictly by byte/code unit.
- Authorization rules or data signatures.

For those cases, apply comparisons matching the data specification. `String.equals()` compares exact `String` content, while sensitive secrets may require constant-time comparison and protocol-specific data protection.

### 6.3. `Collator` holds mutable configuration state

`setStrength()` and `setDecomposition()` modify how the instance compares. If multiple threads share an instance and one mutates configuration while another compares, results can be inconsistent. A simple approach is to create/configure a separate collator per task or per thread, or manage synchronization appropriately.

`Collator` supports `clone()` to create an independently configurable copy when you need to avoid modifying a shared instance directly. Never change a comparator's configuration while sorting or storing elements in a collection backed by that comparator.

### 6.4. Only compare strings with valid data

For example, the standard `compare(String, String)` API requires both strings to be non-`null`. If you want to sort a list that may contain `null`, specify an explicit rule such as `Comparator.nullsFirst(collator)` or `Comparator.nullsLast(collator)`. That is an application policy; collation itself does not define `null` as a word or character.

With Unicode, proper decomposition/strength helps compare accented letters, yet it **does not automatically solve** tokenization, fuzzy matching, accent stripping, transliteration, or product-specific rules.

## 7. Common mistakes to avoid

1. **Using `String.compareTo()` on a list of names and assuming it is standard alphabetical order for all languages.** It compares UTF-16 code units without using local collation rules.
2. **Calling `Collator.getInstance()` without actively choosing a `Locale`.** Use the default locale only when that is the actual requirement.
3. **Believing `compare()` always returns exactly `-1`, `0`, or `1`.** Check only negative/0/positive sign; use `Integer.signum` when normalizing.
4. **Assuming `compare(a, b) == 0` implies `a.equals(b)`.** Strength-based equivalence can be broader than content equality.
5. **Using `PRIMARY` in a `TreeSet` of identifier keys** without anticipating that keys with different contents can merge into a single entry.
6. **Interpreting `PRIMARY`/`SECONDARY`/`TERTIARY` as identical accent-stripping rules across all locales.** Rules depend on language and provider.
7. **Forgetting normalization/decomposition** when data contains both precomposed characters and base-letter + combining-mark sequences.
8. **Changing strength after creating `CollationKey`s or inserting the comparator into a sorted structure** without rebuilding the corresponding keys/structures.
9. **Comparing collation keys created under different configurations.** Keys have consistent meaning only when produced from the same rule set.
10. **Using collation order in place of Unicode analysis, word matching, search ranking, or authorization.** `Collator` solves language-based comparison/sorting, not those other concerns.

## 8. Self-check

- **Question 1:** To display a list of Vietnamese names following linguistic rules, what should you use?  
  **Answer:** `Collator.getInstance(Locale.forLanguageTag("vi-VN"))` as the comparator; verify the rules and JDK data in the deployment environment.
- **Question 2:** What does `collator.compare(a, b) < 0` mean?  
  **Answer:** `a` comes before `b` under the current collator configuration.
- **Question 3:** Does `PRIMARY` guarantee that all accents in every language are ignored?  
  **Answer:** No. The weight of each accent depends on the locale and collation data.
- **Question 4:** Can two strings that differ under `String.equals()` be equal under `Collator.compare()`?  
  **Answer:** Yes, if strength/decomposition rules treat them as equivalent.
- **Question 5:** When should you create `CollationKey`s?  
  **Answer:** When comparing the same set of strings repeatedly and the benefit outweighs key creation/storage cost; all keys must share the same configuration.
- **Question 6:** Should `Collator` be used to verify an API key?  
  **Answer:** No. Use exact matching rules and security mechanisms appropriate to the protocol.

**Key takeaway:** `Collator` is for **`Locale`-aware comparison and sorting**. Choose strength and decomposition based on how the application wants to treat letter, accent, and Unicode representation differences; check `compare` by negative/0/positive sign; and keep **linguistic equivalence** separate from **exact equality** of strings or business keys.
