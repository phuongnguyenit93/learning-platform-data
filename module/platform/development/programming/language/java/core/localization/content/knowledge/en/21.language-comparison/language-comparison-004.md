# Case, Accents, and Language Rules in Java String Comparison

## 1. "Two Strings Are Equal" Is Not a Clear Enough Requirement

Multilingual Java applications often need to search person names, sort dictionaries, validate identifiers, and match content. Each goal requires a **different comparison policy**.

| Text pair | Difference | Why does it matter? |
| --- | --- | --- |
| `Java` / `java` | Case | May be ignored in search, but not necessarily in identifiers |
| `cafe` / `café` | Accent | French search may allow fuzzy match, while the original stays distinct |
| `ma` / `má` / `mã` / `mạ` | Vietnamese tone marks | Stripping accents can collapse **words with different meanings** |
| `I` / `ı` / `İ` / `i` | Turkish casing | Matching rules differ from English |
| `Straße` / `Strasse` | German `ß` and `ss` | May be equivalent at one collation level yet unequal under `String.equals` |
| `café` / `cafe\u0301` | Two Unicode representations of `é` | Canonically equivalent, yet `String.equals` is not necessarily true |

Before reaching for an API, decide: do you need **character-by-character equality**, **case-insensitive**, **linguistic rule comparison**, or **accent-tolerant search**? Never use the same transformation for all four.

**Core principle:** case and accent differences are not merely presentation. In many languages, they change a word's meaning or spelling. Collation (locale-based comparison) is a **sorting/matching rule**, not proof that two entities are identical.

## 2. String.equals, equalsIgnoreCase, and compareTo

Core `String` methods have specific contracts:

| API | What does it compare? | Locale-aware? |
| --- | --- | --- |
| `a.equals(b)` | Two strings with identical UTF-16 code units at each position | No |
| `a.compareTo(b)` | Lexicographic order by UTF-16 | No |
| `a.equalsIgnoreCase(b)` | Case-insensitive comparison per `String` algorithm | **No** |
| `a.compareToIgnoreCase(b)` | Case-ignoring order of `String` | **No** |
| `String.CASE_INSENSITIVE_ORDER` | Comparator following `compareToIgnoreCase` | **No** |
| `Collator.getInstance(locale).compare(a,b)` | Collation order of a language | **Yes** |

`equalsIgnoreCase` is convenient for simple technical keyword names, but is **not a comprehensive linguistic matcher**. It does not strip accents or perform multi-character expansions like `ß → ss`.

### Standalone Java 17+ Example

Create `StringComparisonDemo.java`:

~~~java
public class StringComparisonDemo {
    public static void main(String[] args) {
        String first = "Java";
        String second = "java";

        System.out.println("equals: " + first.equals(second));
        System.out.println("equalsIgnoreCase: "
                + first.equalsIgnoreCase(second));
        System.out.println("compareTo zero: "
                + (first.compareTo(second) == 0));
        System.out.println("Accent ignored: "
                + "cafe".equalsIgnoreCase("café"));
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 StringComparisonDemo.java
java StringComparisonDemo
~~~

Output:

~~~text
equals: false
equalsIgnoreCase: true
compareTo zero: false
Accent ignored: false
~~~

`compareTo` is not the rule for sorting names in Vietnamese, French, or German. It uses UTF-16 unit values. When sorting according to the reader's language, use `Collator`.

## 3. Collator: Comparing Strings by Locale

`java.text.Collator` provides locale-aware text comparison and sorting:

~~~java
Locale locale = Locale.forLanguageTag("fr-FR");
Collator col = Collator.getInstance(locale);
int result = col.compare("cafe", "café");
~~~

This is a **code snippet inside a method**, requiring imports of `java.text.Collator` and `java.util.Locale`.

Return conventions match `Comparator`:

- Negative: the first string comes before.
- `0`: the two strings are equivalent **under the current collator configuration**.
- Positive: the first string comes after.

Do not interpret `compare(a,b)==0` as `a.equals(b)`. In a less sensitive comparison mode, `cafe` and `café` can be equal even though they are two distinct strings.

### Strength: Distinction Level

| Property | Typical meaning | Use case |
| --- | --- | --- |
| `Collator.PRIMARY` | Considers base letter differences; many locales ignore case and some accents | Fuzzy comparison / locale-based search |
| `Collator.SECONDARY` | Also considers secondary differences, typically accents | Distinguishing accents when required by the language |
| `Collator.TERTIARY` | Also considers differences such as case | More detailed sorting |
| `Collator.IDENTICAL` | Highest distinction level in the collation mechanism | Must not be confused with `String.equals` |

These levels do not mean "PRIMARY strips all accents, SECONDARY checks only accents, TERTIARY checks only case" in **every locale**. Actual sensitivity and rules depend on language, provider, and JDK data.

### Standalone Example

Create `CollatorStrengthDemo.java`:

~~~java
import java.text.Collator;
import java.util.Locale;

public class CollatorStrengthDemo {
    public static void main(String[] args) {
        Collator fr = Collator.getInstance(Locale.FRENCH);

        fr.setStrength(Collator.PRIMARY);
        System.out.println("PRIMARY cafe/café: "
                + (fr.compare("cafe", "café") == 0));

        fr.setStrength(Collator.SECONDARY);
        System.out.println("SECONDARY cafe/café: "
                + (fr.compare("cafe", "café") == 0));

        fr.setStrength(Collator.TERTIARY);
        System.out.println("TERTIARY Cafe/cafe: "
                + (fr.compare("Cafe", "cafe") == 0));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 CollatorStrengthDemo.java
java CollatorStrengthDemo
~~~

Result in common French collation data:

~~~text
PRIMARY cafe/café: true
SECONDARY cafe/café: false
TERTIARY Cafe/cafe: false
~~~

These are comparison policy results. They **do not modify** characters in `"café"` and do not mean all accent-differing words are identical.

## 4. Turkish: Rules for I, İ, i, ı

Turkish is a prominent example of the difference between generic case-insensitivity and locale-aware comparison:

- `I`: uppercase **dotless** I.
- `ı`: lowercase **dotless** i.
- `İ`: uppercase **dotted** I.
- `i`: lowercase **dotted** i.

In Turkish case conversion, `I/ı` pair together, while `İ/i` pair together.

### Complete Java 17+ Example

Create `TurkishCaseDemo.java`:

~~~java
import java.text.Collator;
import java.util.Locale;

public class TurkishCaseDemo {
    public static void main(String[] args) {
        Locale tr = Locale.forLanguageTag("tr-TR");

        System.out.println("ROOT I lower: "
                + "I".toLowerCase(Locale.ROOT));
        System.out.println("TR I lower: "
                + "I".toLowerCase(tr));
        System.out.println("TR i upper: "
                + "i".toUpperCase(tr));

        System.out.println("equalsIgnoreCase I/i: "
                + "I".equalsIgnoreCase("i"));
        System.out.println("equalsIgnoreCase I/ı: "
                + "I".equalsIgnoreCase("ı"));

        Collator col = Collator.getInstance(tr);
        col.setStrength(Collator.PRIMARY);
        System.out.println("TR PRIMARY I/ı: "
                + (col.compare("I", "ı") == 0));
        System.out.println("TR PRIMARY I/i: "
                + (col.compare("I", "i") == 0));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 TurkishCaseDemo.java
java TurkishCaseDemo
~~~

Common JDK output:

~~~text
ROOT I lower: i
TR I lower: ı
TR i upper: İ
equalsIgnoreCase I/i: true
equalsIgnoreCase I/ı: true
TR PRIMARY I/ı: true
TR PRIMARY I/i: false
~~~

**Significance:** `String.equalsIgnoreCase` does not know the Turkish locale, whereas `Collator(tr-TR, PRIMARY)` applies linguistic comparison rules. Thus, the two methods can reach **different conclusions** on the same pair of strings.

In a system with multilingual users, do **not** call zero-arg `String.toLowerCase()` to generate technical keys: it uses the JVM default locale. If a technical field is defined by neutral rules, use `Locale.ROOT` **when matching the contract**; if processing natural language, account for the user's locale.

## 5. German: ß and ss

`"Straße"` and `"Strasse"` are not equal under `String.equals`. Nor does `equalsIgnoreCase` turn one `ß` character into two `ss` characters to make them equal.

However, a German collator at PRIMARY may consider them equivalent per collation rules.

Create `GermanCollationDemo.java`:

~~~java
import java.text.Collator;
import java.util.Locale;

public class GermanCollationDemo {
    public static void main(String[] args) {
        String a = "Straße";
        String b = "Strasse";

        System.out.println("equals: " + a.equals(b));
        System.out.println("equalsIgnoreCase: "
                + a.equalsIgnoreCase(b));

        Collator de = Collator.getInstance(Locale.GERMAN);
        de.setStrength(Collator.PRIMARY);

        System.out.println("DE PRIMARY: "
                + (de.compare(a, b) == 0));
    }
}
~~~

Run command:

~~~bash
javac -encoding UTF-8 GermanCollationDemo.java
java GermanCollationDemo
~~~

Result with common German data:

~~~text
equals: false
equalsIgnoreCase: false
DE PRIMARY: true
~~~

The takeaway is that **the algorithms serve different goals**, not that `Collator` fixed the original data. Do not replace `Straße` with `Strasse` in the database just to support fuzzy search.

## 6. Accents and Unicode Normalization Are Not the Same Problem

Two strings can contain the same accented letter in **two canonically equivalent Unicode forms**:

~~~text
"café"       : c a f U+00E9
"cafe\u0301" : c a f e U+0301
~~~

`U+0301` is *COMBINING ACUTE ACCENT*. `String.equals` compares UTF-16 code units and does not automatically normalize both forms to NFC.

Java provides `java.text.Normalizer`:

~~~java
String aNfc = Normalizer.normalize(a, Normalizer.Form.NFC);
String bNfc = Normalizer.normalize(b, Normalizer.Form.NFC);
boolean sameCanonicalText = aNfc.equals(bNfc);
~~~

This is a snippet inside a method requiring import of `java.text.Normalizer` with variables `a` and `b`.

### Standalone Java 17+ Example

Create `CanonicalComparisonDemo.java`:

~~~java
import java.text.Normalizer;

public class CanonicalComparisonDemo {
    public static void main(String[] args) {
        String composed = "caf\u00E9";
        String decomposed = "cafe\u0301";

        System.out.println("Raw equals: "
                + composed.equals(decomposed));
        System.out.println("Raw lengths: "
                + composed.length() + " / " + decomposed.length());

        String left = Normalizer.normalize(
                composed, Normalizer.Form.NFC);
        String right = Normalizer.normalize(
                decomposed, Normalizer.Form.NFC);

        System.out.println("NFC equals: " + left.equals(right));
        System.out.println("Accent retained: "
                + left.equals("café"));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 CanonicalComparisonDemo.java
java CanonicalComparisonDemo
~~~

Output:

~~~text
Raw equals: false
Raw lengths: 4 / 5
NFC equals: true
Accent retained: true
~~~

**NFC preserves accents**: after normalization, `café` still differs from `cafe`. NFC/NFD addresses **equivalent representations**, not stripping semantic information.

### Collator Strength and Decomposition

Besides `setStrength`, `Collator` has `setDecomposition`:

- `NO_DECOMPOSITION`: does not require decomposition prior to collation.
- `CANONICAL_DECOMPOSITION`: enables canonical decomposition handling.
- `FULL_DECOMPOSITION`: also considers compatibility decomposition in the collation mechanism.

Example:

~~~java
Collator fr = Collator.getInstance(Locale.FRENCH);
fr.setStrength(Collator.SECONDARY);
fr.setDecomposition(Collator.CANONICAL_DECOMPOSITION);
~~~

This is a snippet inside a method requiring imports of `java.text.Collator` and `java.util.Locale`.

**Decomposition differs from strength**: one controls how Unicode representations are interpreted, while the other controls the difference sensitivity during matching. `FULL_DECOMPOSITION` does not mean "strip all accents"; nor is `Collator.IDENTICAL` another name for `String.equals`.

## 7. Accent Stripping Is a Lossy Transformation

A common way to build an accent-tolerant search key:

~~~java
String searchKey = Normalizer
        .normalize(source, Normalizer.Form.NFD)
        .replaceAll("\\p{M}+", "")
        .toLowerCase(Locale.ROOT);
~~~

This is a snippet inside a method requiring imports of `java.text.Normalizer` and `java.util.Locale`.

It consists of **three transformations**:

1. Unicode canonical decomposition (NFD).
2. Removing characters with Unicode general category Mark (`\p{M}`).
3. Lowercasing with `Locale.ROOT`.

This is **not neutral**: `ma`, `má`, `mà`, `mả`, `mã`, and `mạ` can all become `ma`, despite having different meanings in Vietnamese. Moreover, removing Marks can destroy essential components of many other scripts, and does **not** guarantee ASCII output: `Đ/đ` or `ß` are not automatically turned into base Latin letters.

| Mechanism | Role | Modifies source text? |
| --- | --- | --- |
| `Normalizer.Form.NFC` | Unifies canonical equivalence | Produces another form while preserving meaningful accent distinctions |
| `Collator.PRIMARY` | Compares at locale-appropriate collation level | Does not alter source strings |
| `NFD + strip \p{M}` | Creates an approximate accentless form | **Yes, lossy** |
| Transliteration | Converts script by rules | Can lose information; not normalization |
| Case mapping | Upper–lower conversion | May change characters/length depending on locale |

**Safe practice:** keep the accented original; if tolerant search is needed, generate a **secondary** search key or use the collation capabilities of a search engine/database. Keep a separate ID to resolve collisions.

## 8. Comparing to Sort and Comparing for Identity Are Two Different Jobs

`List.sort(collator)` lets you sort a list of names by locale. However, the comparator may regard two strings as **equal** at low strength.

This affects collections that rely on the comparator for uniqueness, such as `TreeSet` and `TreeMap`.

### Complete Java 17+ Example on TreeSet

Create `CollationCollisionDemo.java`:

~~~java
import java.text.Collator;
import java.util.Locale;
import java.util.TreeSet;

public class CollationCollisionDemo {
    public static void main(String[] args) {
        Collator fr = Collator.getInstance(Locale.FRENCH);
        fr.setStrength(Collator.PRIMARY);

        String first = "cafe";
        String second = "café";

        TreeSet<String> set = new TreeSet<>(fr);
        set.add(first);
        set.add(second);

        System.out.println("String equals: "
                + first.equals(second));
        System.out.println("Collator equals: "
                + (fr.compare(first, second) == 0));
        System.out.println("TreeSet size: " + set.size());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 CollationCollisionDemo.java
java CollationCollisionDemo
~~~

Common French output:

~~~text
String equals: false
Collator equals: true
TreeSet size: 1
~~~

`TreeSet` uses the comparator to determine whether two elements are duplicates, so two strings differing in UTF-16 can be treated as the same key. This is **not a TreeSet bug**, but a consequence of the comparison policy you chose.

### How to Keep Both Values When Sorting

If only display order is needed, use `List.sort(collator)` and keep each record with an independent ID. If a comparator must distinguish raw values, add a tie-breaker:

~~~java
Comparator<String> displayOrder = (left, right) -> {
    int result = collator.compare(left, right);
    return result != 0 ? result : left.compareTo(right);
};
~~~

This is a snippet inside a method requiring import of `java.util.Comparator` and a configured `Collator` variable `collator`. The `String.compareTo` tie-breaker is used **only when the collator treats them as equal** to keep a stable/distinguishable order, without replacing primary collation rules. For records sharing the same name but different IDs, tie-breaking by ID is more reliable.

## 9. Locale-Aware Sorting with List.sort

A Java 17+ example that does not pin provider-dependent order:

Create `LocaleSortDemo.java`:

~~~java
import java.text.Collator;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public class LocaleSortDemo {
    public static void main(String[] args) {
        List<String> words = new ArrayList<>(
                List.of("été", "eclair", "École", "eleve")
        );
        Collator fr = Collator.getInstance(Locale.FRENCH);
        fr.setStrength(Collator.TERTIARY);

        words.sort(fr);

        boolean sorted = true;
        for (int i = 1; i < words.size(); i++) {
            if (fr.compare(words.get(i - 1), words.get(i)) > 0) {
                sorted = false;
                break;
            }
        }
        System.out.println("Count: " + words.size());
        System.out.println("Sorted using French collation: " + sorted);
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 LocaleSortDemo.java
java LocaleSortDemo
~~~

Output:

~~~text
Count: 4
Sorted using French collation: true
~~~

The program checks the **invariant of being sorted according to the active collator**, rather than relying on a fixed character sequence that could change when the JDK updates CLDR/provider data.

`Collator` holds mutable state via `setStrength` and `setDecomposition`. Do not share one instance across multiple threads while constantly changing configuration per request. Create/copy configurations per task or synchronize properly.

## 10. CollationKey for Many Comparisons

If a large set of strings must be compared very many times, you can generate `CollationKey`s from a configured collator:

~~~java
Collator fr = Collator.getInstance(Locale.FRENCH);
fr.setStrength(Collator.PRIMARY);

CollationKey first = fr.getCollationKey("cafe");
CollationKey second = fr.getCollationKey("café");

int result = first.compareTo(second);
~~~

This is a snippet inside a method requiring imports of `java.text.Collator`, `java.text.CollationKey`, and `java.util.Locale`.

### Complete Example

Create `CollationKeyDemo.java`:

~~~java
import java.text.CollationKey;
import java.text.Collator;
import java.util.Locale;

public class CollationKeyDemo {
    public static void main(String[] args) {
        Collator fr = Collator.getInstance(Locale.FRENCH);
        fr.setStrength(Collator.PRIMARY);
        fr.setDecomposition(Collator.CANONICAL_DECOMPOSITION);

        CollationKey a = fr.getCollationKey("cafe");
        CollationKey b = fr.getCollationKey("café");

        System.out.println("Direct equivalent: "
                + (fr.compare("cafe", "café") == 0));
        System.out.println("Key equivalent: "
                + (a.compareTo(b) == 0));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 CollationKeyDemo.java
java CollationKeyDemo
~~~

Result in common French data:

~~~text
Direct equivalent: true
Key equivalent: true
~~~

**Only compare CollationKeys created from compatible configurations**, i.e., the same locale, strength, decomposition, and related rules. Do not use `CollationKey.toByteArray()` bytes as identifiers, signatures, or long-term storage keys without a version management contract: collation data can change when upgrading the JDK/provider.

## 11. Case Is More Than Swapping Individual chars

`String.toLowerCase(Locale)` and `String.toUpperCase(Locale)` are **string transformations**, distinct from `equalsIgnoreCase`. A Unicode case mapping can alter string length: for example, `İ` in certain lowercasing contexts can be represented as `i` + combining dot.

Mistakes to avoid:

- Using `Character.toLowerCase(char)` and assuming all multi-code-point case transformations are handled.
- Using default `toLowerCase()` for system keys and being surprised when the server locale changes.
- Using `Locale.ROOT` for comparing personal names and assuming those rules work for every language.
- Using `equalsIgnoreCase` to conclude two official names or two accounts are always equivalent.

When linguistic comparison is needed, use a tool with an explicit locale policy. When handling **technical codes**, define a schema: whether ASCII case matters, whether Unicode is allowed, what normalization applies, and whether confusable characters are permitted. `Collator` and accent stripping are **not security validators**.

## 12. Data Design: Preserve Originals and Support Reasonable Search

Suppose a directory has three names: `Ma`, `Má`, `Mã`. If the system retains only a single stripped key `ma`, it loses distinguishing information.

A better design:

~~~text
Records:
  id = 101, displayName = "Ma"
  id = 102, displayName = "Má"
  id = 103, displayName = "Mã"

Search engine:
  query "ma"
       |
       +--> exact match against original
       +--> case-equivalent match
       +--> approximate match per accent-insensitive policy

UI:
  displays exact "Ma", "Má", "Mã"
  keeps IDs independent
~~~

Accent-insensitive search can be a good feature when users expect it, provided there is ranking and collision handling. Do not base account uniqueness or legal documents on it.

For passwords, tokens, protocol keys, verification codes, digital signatures, and access-controlled paths, follow **the comparison rules of that protocol**. Linguistic collation is usually inappropriate and can conflate distinct strings.

## 13. Default Locale, Provider, and Reproducibility

Zero-arg `Collator.getInstance()` can use the JVM default locale. If the development machine's default locale differs from production, sort order can diverge. For multi-user systems:

~~~java
Locale viewer = Locale.forLanguageTag("vi-VN");
Collator collator = Collator.getInstance(viewer);
collator.setStrength(Collator.TERTIARY);
collator.setDecomposition(Collator.CANONICAL_DECOMPOSITION);
~~~

This is a snippet inside a method requiring imports of `java.util.Locale` and `java.text.Collator`.

A reliable collation test must specify **locale**, **strength**, **decomposition**, **JDK/provider**, and **goal**. A newer Java release may update language data, changing item ordering without any bug in the program.

If a product maintains legal dictionary orderings or persisted search indexes, have a versioning/rebuild strategy when upgrading collation data. Never hardcode Unicode sort outputs to UTF-16 order or the host machine's default.

## 14. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Treating `equalsIgnoreCase` as locale-aware comparison | Wrong for Turkish `I/i/ı/İ` relations | Use `Collator(locale)` when the goal is linguistic |
| Using `compareTo` to sort Vietnamese names | UTF-16 order instead of dictionary order | Use a collator with the appropriate locale |
| Thinking `PRIMARY` only strips accents | Can also collapse case and secondary differences | Understand it as a collation equivalence level |
| Thinking `IDENTICAL` is `String.equals` | Confuses normalization and collation rules | Use dedicated exact comparison per schema |
| Thinking NFC removes accents | Unintended data changes | NFC only normalizes Unicode representation |
| Stripping `\p{M}` on original text | Loss of meaning and collisions | Keep original, use secondary search key if needed |
| Treating accent stripping as universal transliteration | Misses `Đ/ß/ł` and many scripts | Define a language-specific transliteration policy |
| Not passing a locale | Results depend on server host | Pass `Locale` explicitly |
| Using Collator.PRIMARY for uniqueness in TreeSet | Merges and drops distinct items | Use appropriate ID/tie-breaker |
| Persisting CollationKey as an identifier | May be unstable across providers | Regenerate keys per rule version |
| Sharing a mutable Collator across threads | State may change between requests | Create instance per task or synchronize |

## 15. Testing Checklist and Exercises

### Checklist

1. Test `Java/java` with `String.equals` and `equalsIgnoreCase`.
2. Test `cafe/café` with `fr-FR` at PRIMARY, SECONDARY, TERTIARY.
3. Test `I/ı` and `I/i` with `tr-TR`, compared against `equalsIgnoreCase`.
4. Test `Straße/Strasse` with `de-DE`.
5. Test precomposed/decomposed Unicode via NFC.
6. Test `ma/má/mã` to verify distinct items remain preserved in source data.
7. Test `TreeSet`/`TreeMap` when the comparator returns 0 for two distinct strings.
8. Test CollationKeys created with the **same configuration**.
9. Test on the actual Java/provider version when ordering must be reproducible.
10. Test multithreading if caching mutable collators.

### Exercises

1. For `cafe` and `café`, explain why `equalsIgnoreCase` returns false while `Collator(fr-FR, PRIMARY)` can treat them as equivalent.
2. For `tr-TR`, print the lowercasing of `I` and uppercasing of `i`. Explain the dotted/dotless I rule.
3. Compare `Straße` and `Strasse` using `equals`, `equalsIgnoreCase`, and a German `Collator` at PRIMARY. Why must the original not be overwritten based on the comparator?
4. Construct `"caf\u00E9"` and `"cafe\u0301"`. Check before/after `Normalizer.Form.NFC`.
5. Create a `TreeSet<String>` with a PRIMARY Collator and add `cafe` and `café`. Explain why the element count can be 1.
6. Find a way to sort a list of names while retaining every record by ID, even when names are collation-equivalent.
7. Design accent-insensitive search for `Ma/Má/Mã` with ranking but without merging IDs.
8. Distinguish `Collator.setStrength` from `setDecomposition`.
9. Why should `CollationKey.toByteArray()` not be used as a durable identifier?
10. For a multilingual application, identify where **exact** comparison is required, where **locale-aware** comparison is needed, and where **accent-insensitive** matching is permitted.

**Takeaway:** case, accents, and sorting rules belong to **different layers**. `String.equals`/`equalsIgnoreCase` have no locale policy; `Collator` compares by locale at PRIMARY/SECONDARY/TERTIARY/IDENTICAL levels; `Normalizer` handles Unicode equivalence but does **not** strip accents. Choose the API by intent, preserve original content, pass locale explicitly, and never equate "equivalent in search" with "same identity."

### References

- [Java SE 17 — Collator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Collator.html) — locale-based comparison, strength, and decomposition.
- [Java SE 17 — CollationKey](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/CollationKey.html) — efficiency in repeated comparisons and key usage rules.
- [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html) — equals, equalsIgnoreCase, compareTo, case conversion.
- [Java SE 17 — Normalizer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html) — Unicode NFC/NFD/NFKC/NFKD.
- [Unicode Technical Standard #10](https://www.unicode.org/reports/tr10/) — Unicode Collation Algorithm.
- [Unicode Standard Annex #15](https://www.unicode.org/reports/tr15/) — Unicode Normalization Forms.