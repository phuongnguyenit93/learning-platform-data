# Limits of equalsIgnoreCase and Case-Insensitive Comparison in Java

## Objectives

`"Hello".equalsIgnoreCase("hello")` returns `true`, yet that **does not mean `equalsIgnoreCase` is the right character comparator for every language, every type of identifier, and every search requirement**. Unicode has letters whose casing depends on context or locale; some characters expand into multiple characters; the same accented letter can be stored in multiple normalization forms. Therefore, the concept of "case-insensitive" must be defined per problem.

After this lesson, you will:

- Understand the `String.equalsIgnoreCase` contract and how it differs from `equals`, `compareToIgnoreCase`, and `String.CASE_INSENSITIVE_ORDER`.
- Explain why this API is **independent of `Locale`**, yet does not perform **Unicode full case folding** or `NFC/NFD` normalization.
- Analyze cases in Turkish (`I/i/İ/ı`), German (`ß/ẞ/SS`), Greek (`Σ/σ/ς`), accented Vietnamese, and code points outside the BMP.
- Know when to use `String.toLowerCase(Locale.ROOT)`, `java.text.Normalizer`, or `java.text.Collator`.
- Design distinct rules for technical codes, display text, accent-insensitive search, personal names, and sensitive data.
- Test Java 17+ examples and avoid bugs when using a case-insensitive comparator as collection keys.

**Focus:** the limits of case-insensitive comparisons, rather than claiming every application needs the same rule.

## 1. Exact comparison vs. case-insensitive comparison

`String.equals` checks exact string content; `String.equalsIgnoreCase` allows corresponding letters to differ in case per Java's algorithm:

```java
System.out.println("Java".equals("java"));
System.out.println("Java".equalsIgnoreCase("java"));
System.out.println("Java".equalsIgnoreCase("JavaScript"));
System.out.println("Java".equalsIgnoreCase(null));
```

Stdout:

```text
false
true
false
false
```

These are illustrative statements inside a Java method. No `Locale` needs to be passed to `equalsIgnoreCase`; the method has no overload accepting a locale.

Important limitations:

1. The comparison **does not automatically call `Normalizer.normalize`**.
2. It does not treat every character with the same visual shape or pronunciation as equivalent.
3. It does not strip Vietnamese tone marks.
4. It does not apply rules specific to the current locale.
5. It does not perform full one-to-many character expansions from Unicode case folding.
6. It does not imply that two values belong to the same identity or are interchangeable in a security protocol.

String length and structure matter: converting `ß` to `SS` is a one-character-to-two-character transformation, completely different from comparing a simple uppercase/lowercase pair.

### Do not equate "character" with "one char"

In Java, `String` uses UTF-16; `length()` counts code units, while `codePointCount` counts code points. Some uppercase/lowercase letters outside the BMP take two code units. Modern Java can recognize some of their case pairs in `equalsIgnoreCase`; one should not claim this method works only on the ASCII alphabet.

However, recognizing case pairs in the supplementary planes **does not turn `equalsIgnoreCase` into a comprehensive processor of all Unicode and linguistic rules**.

## 2. Turkish I: does not follow the user's language

Turkish is a particularly famous example:

| Character | Code point | Meaning |
| --- | --- | --- |
| `I` | `U+0049` | Latin capital letter I |
| `i` | `U+0069` | Latin small letter i |
| `İ` | `U+0130` | Latin capital I with dot |
| `ı` | `U+0131` | Latin small dotless i |

Turkish rules pair `I↔ı` and `i↔İ`. Yet `equalsIgnoreCase` applies a locale-independent comparison.

```java
String dottedCapital = "\u0130";
String dotlessSmall = "\u0131";

System.out.println("I".equalsIgnoreCase("i"));
System.out.println("I".equalsIgnoreCase(dotlessSmall));
System.out.println("i".equalsIgnoreCase(dottedCapital));
System.out.println(dottedCapital.equalsIgnoreCase(dotlessSmall));
```

Stdout on Java 17+:

```text
true
true
true
true
```

All four pairs above are treated as equivalent by the method when ignoring case, even though that cannot be considered an accurate match specifically under Turkish rules.

**Lesson:** `equalsIgnoreCase` has no concept of "the reader's language". If users need word comparison/sorting according to a locale, choose a solution with a locale parameter and test those rules.

### toLowerCase also has the default locale problem

```java
Locale tr = Locale.forLanguageTag("tr-TR");
System.out.println("I".toLowerCase(tr).codePointAt(0) == 0x0131);
System.out.println("I".toLowerCase(Locale.ROOT).equals("i"));
```

This illustrative snippet inside a method has `import java.util.Locale;`, and both lines print `true`. That means for the same letter `I`, lowercasing under a Turkic locale can differ from ROOT. Do not call parameterless `toLowerCase()` and expect identical behavior on every machine: this overload depends on the JVM's default locale.

Do not call `Locale.setDefault` per request to "fix" the issue; default is JVM-wide shared state. Pass a specific locale when needed.

## 3. German sharp S: case conversion can change character count

The letter `ß` (`U+00DF`) and capital `ẞ` (`U+1E9E`) illustrate another case:

```java
String smallSharp = "\u00DF";
String capitalSharp = "\u1E9E";

System.out.println(smallSharp.equalsIgnoreCase("SS"));
System.out.println(smallSharp.equalsIgnoreCase(capitalSharp));
System.out.println(smallSharp.toUpperCase(Locale.ROOT));
```

Stdout:

```text
false
true
SS
```

`"ß".equalsIgnoreCase("SS")` returns `false`, yet when `toUpperCase(Locale.ROOT)` processes the whole string, `ß` can produce `SS`. Reason: **whole-string** case conversion can expand length, whereas `equalsIgnoreCase` does not implement full multi-character Unicode case folding.

This is why **you cannot unconditionally replace**:

```java
a.equalsIgnoreCase(b)
```

with:

```java
a.toUpperCase(Locale.ROOT)
        .equals(b.toUpperCase(Locale.ROOT))
```

The two expressions can yield different results for `ß` and `SS`. Do not use the uppercased result as a permanent canonical key if business logic requires distinguishing values that could merge upon case expansion.

### Full case folding is a different contract

Unicode has case-folding rules, including mappings that can produce multiple code points, along with Turkic-specific options. `equalsIgnoreCase` **does not publish a configurable Unicode full case folding profile** for applications to tune. If a system requires full folding per a defined standard, choose an appropriate library/profile, document the Unicode version and normalization policy, and do not claim `equalsIgnoreCase` is equivalent.

`String.toUpperCase(Locale.ROOT)` is not another name for full case folding either: it performs **whole-string uppercasing** under its own rules. When comparing IDs, length-changing transformations can create collisions.

## 4. Greek sigma and context-dependent casing

Greek has:

- `Σ` (`U+03A3`): uppercase sigma.
- `σ` (`U+03C3`): lowercase sigma.
- `ς` (`U+03C2`): word-final lowercase sigma.

`equalsIgnoreCase` can treat `Σ` and `ς` as equal:

```java
System.out.println("\u03A3".equalsIgnoreCase("\u03C2"));
```

Stdout:

```text
true
```

Meanwhile, changing case on **an entire word** may need to inspect the letter's position in the word. That is context-dependent linguistic behavior, not merely per-character mapping. When an application processes multilingual text, distinguish case-ignoring comparison, case conversion for display, and normalization for search.

## 5. Vietnamese: tone marks are not case differences

For precomposed Vietnamese letters, simple case comparison can return true:

```java
System.out.println("ĐẮK".equalsIgnoreCase("đắk"));
System.out.println("ma".equalsIgnoreCase("má"));
```

Typically outputs:

```text
true
false
```

The acute accent in `má` is not an uppercase variant of `a`. `ma`, `má`, `mà`, `mã`... carry linguistic differences. When designing systems, never equate "case-insensitive comparison" with "accent-insensitive comparison".

### NFC/NFD: two representations can look identical

An accented letter can be a precomposed code point or a base letter plus a combining mark:

```java
String composed = "\u00E9"; // é
String decomposed = "e\u0301"; // e + combining acute

System.out.println(composed.equalsIgnoreCase(decomposed));
```

Stdout:

```text
false
```

Two strings can look identical yet have different UTF-16 structures and code point counts; `equalsIgnoreCase` does not merge them automatically.

If the system contract requires **canonically equivalent representations to be treated as equal**, apply the same Unicode normalization form on both sides, such as `NFC`:

```java
import java.text.Normalizer;

String left = Normalizer.normalize(
        composed, Normalizer.Form.NFC);
String right = Normalizer.normalize(
        decomposed, Normalizer.Form.NFC);

System.out.println(left.equalsIgnoreCase(right));
```

Stdout:

```text
true
```

NFC is **canonical normalization**; it is not a diacritic-stripping rule and does not validate spelling. Distinguish it from `NFKC`, which can merge compatibility characters such as `①` and `1`.

### The letter đ does not automatically turn into d

`Normalizer.Form.NFD` does not decompose `đ` into `d`. Therefore, never assume that running NFD and removing Unicode combining marks will automatically treat `đ` and `d` as the same letter.

If accent-insensitive search wants to support `đ → d`, you must add a custom product-level mapping rule. Even then, the stripped result is only an **approximate search key**, not a replacement for original data or IDs requiring exactness.

## 6. equalsIgnoreCase and toLowerCase(Locale.ROOT) are not synonymous

A common strategy:

```java
String key = input.toLowerCase(Locale.ROOT);
```

`Locale.ROOT` avoids the JVM default locale, making it especially suitable for **technical codes with a restricted alphabet**, such as ASCII command names. Yet whole-string lowercasing does not share the same contract as `equalsIgnoreCase`.

Example:

```java
String dottedI = "\u0130";
String lowered = dottedI.toLowerCase(Locale.ROOT);

System.out.println(dottedI.equalsIgnoreCase("i"));
System.out.println(lowered.equals("i"));
System.out.println(lowered.codePointCount(0, lowered.length()));
```

Stdout:

```text
true
false
2
```

Here `İ` can be ROOT-lowercased into **`i + combining dot above`** — two code points. `equalsIgnoreCase` against `i` returns true. Those are two different criteria.

### A good policy for ASCII codes

If a protocol allows only ASCII characters, validate the **allowed character set** first, then convert case:

```java
String canonicalCommand(String input) {
    if (input == null || !input.matches("[A-Za-z][A-Za-z0-9_-]*")) {
        throw new IllegalArgumentException("Invalid ASCII command");
    }
    return input.toLowerCase(Locale.ROOT);
}
```

This is an illustrative method inside a class that has imported `Locale`. It is unsuitable for validating personal names because it rejects accented Vietnamese letters and characters from other scripts.

If you simply write `"LOGIN".equalsIgnoreCase(userInput)` without checking the character range, Unicode characters with special case relationships may be accepted even though the protocol intended ASCII only.

## 7. compareToIgnoreCase and CASE_INSENSITIVE_ORDER

Beyond equality checks, Java provides:

- `String.compareToIgnoreCase(other)`: compares string order ignoring case per String rules, not a locale's dictionary order.
- `String.CASE_INSENSITIVE_ORDER`: a comparator that can be passed to `TreeSet`, `TreeMap`, or sorting.

```java
import java.util.Set;
import java.util.TreeSet;

Set<String> files = new TreeSet<>(
        String.CASE_INSENSITIVE_ORDER);
files.add("File");
files.add("file");

System.out.println(files.size());
```

Stdout:

```text
1
```

A `TreeSet` considers two elements whose comparator returns 0 to be equivalent keys, so it keeps only one element. Yet `"File".equals("file")` is `false`.

This is an example of a **comparator inconsistent with `equals`**. Therefore:

- `HashSet`/`HashMap` rely on `equals/hashCode`.
- `TreeSet`/`TreeMap` rely on the comparator to determine order and key uniqueness.
- The two collection types can hold different numbers of entries from the same data.

If the design requires filenames, personal names, or identifiers to preserve case distinctions, using `CASE_INSENSITIVE_ORDER` can drop entries. If you want `"File"` and `"file"` to be one key, document that explicitly as policy and handle collisions per business rules.

`compareToIgnoreCase` is not a locale-based sorting API either, so it is not automatically suitable for Vietnamese directories or Turkish word lists.

## 8. Collator for locale-aware comparison and sorting

`java.text.Collator` is designed to compare strings according to a locale's conventions. Example:

```java
import java.text.Collator;
import java.util.Locale;

Collator collator = Collator.getInstance(
        Locale.forLanguageTag("vi-VN"));
collator.setStrength(Collator.SECONDARY);
collator.setDecomposition(
        Collator.CANONICAL_DECOMPOSITION);
```

`Collator` has strength levels:

| Strength | Differences considered | What to be cautious about |
| --- | --- | --- |
| `PRIMARY` | Base letter differences | May merge some accent/case differences |
| `SECONDARY` | Adds secondary differences such as accents | Often ignores case while distinguishing many accents |
| `TERTIARY` | Adds case/variant differences | Ordering depends on locale/provider |
| `IDENTICAL` | Very strict distinction at collation level | Should not automatically be treated as byte-level equality |

In the example using the tested provider/JDK:

```java
System.out.println(collator.compare("Mai", "mai") == 0);
System.out.println(collator.compare("ma", "má") == 0);
```

Stdout:

```text
true
false
```

At `SECONDARY` strength, the case of `Mai/mai` does not separate the two strings in this example, while the acute accent of `ma/má` is still distinguished.

**Note:** collation data and comparison details can depend on locale/provider/JDK. When a system requires accurate dictionary ordering for a market, test on the actual configuration and an appropriate dataset. `Collator` holds mutable configuration state, so do not arbitrarily share one and mutate `setStrength` across concurrent requests.

### Collator is neither full case folding nor authentication

`Collator.PRIMARY` can report "equal" for words differing in accents. That level of comparison may be helpful for search, yet insufficient for deciding whether two accounts or two individuals are the same.

`CollationKey` should also not be treated as a permanent string ID across JDK or provider versions. It serves comparisons under a specific collation configuration.

## 9. Normalizing to NFC then comparing: a policy with clear boundaries

If a system wants **canonical equivalence + simple case ignoring**, you can build a helper:

```java
import java.text.Normalizer;

public final class TextEquality {
    private TextEquality() {}

    public static boolean sameNfcIgnoringCase(String a, String b) {
        if (a == null || b == null) {
            return a == b;
        }

        String left = Normalizer.normalize(
                a, Normalizer.Form.NFC);
        String right = Normalizer.normalize(
                b, Normalizer.Form.NFC);

        return left.equalsIgnoreCase(right);
    }
}
```

This is a class compilable as `TextEquality.java`, without a `main` method to run. The function enforces **a specific policy**: two nulls are treated as equal; all other strings are normalized to NFC and then passed to `equalsIgnoreCase`.

Limitations:

- It helps compare canonically equivalent forms `é` and `e + ◌́`.
- It **does not** automatically merge `ß` with `SS`.
- It does not perform Unicode full case folding.
- It does not apply Turkic-specific rules.
- It does not strip Vietnamese tone marks or map `đ` to `d`.
- It does not make input safe, spelled correctly, or valid against a schema.

If the data is used as cache, DB, or search keys, apply the exact same policy on **every key-generation and key-lookup path**. When adding normalization to a system with existing data, two raw-distinct values may collide after NFC; plan collision handling before migration.

## 10. Which tool to choose for each requirement?

### Command codes and ASCII protocols

Permit an explicit alphabet, validate first, and then apply `Locale.ROOT` case conversion if the protocol is case-insensitive. If the protocol is case-sensitive, use `equals` and preserve verbatim.

### User text, names, and multilingual content

Preserve the original value per business requirements. Consider NFC to unify **canonically equivalent** representations, but do not strip accents or convert entire names to ASCII. `equalsIgnoreCase` is not a real-world identity check.

### Flexible search

A search may want `ca phe` to find `cà phê`. You can build a secondary search index using an accent-stripping, case-folding, or collation policy. However, multiple words with different meanings can collapse to the same search key. **Keep the original field** and do not use the search key as a unique ID without rules accepting collisions.

### Linguistic sorting

Use `Collator` with the appropriate locale and strength/decomposition instead of `compareToIgnoreCase` or `CASE_INSENSITIVE_ORDER` when natural dictionary order matters to users.

### Passwords, API tokens, and secret data

Do not use `equalsIgnoreCase` merely to make typing "easier". Doing so can treat distinct secret values as equal. For passwords, use an authentication flow based on salted password hashing and dedicated algorithms; for tokens or signatures, use byte/schema rules and appropriate comparison mechanisms, including timing considerations where needed. Only normalize Unicode if the authentication protocol consistently specifies that policy.

### Unicode usernames or identifiers

A system allowing Unicode IDs must **publish a specific profile**: allowed character set, normalization, case folding, confusable rules, collision handling, length, and Unicode version. `equalsIgnoreCase` alone cannot solve these issues.

## 11. Standalone runnable Java 17+ example

Create the file `CaseComparisonDemo.java`. The example uses Unicode escapes to avoid depending on a source editor's or terminal's ability to display special characters.

```java
import java.text.Collator;
import java.text.Normalizer;
import java.util.Locale;
import java.util.Set;
import java.util.TreeSet;

public class CaseComparisonDemo {
    public static void main(String[] args) {
        String dottedI = "\u0130";
        String dotlessI = "\u0131";

        System.out.println("HELLO: "
                + "HELLO".equalsIgnoreCase("hello"));
        System.out.println("I/dotless: "
                + "I".equalsIgnoreCase(dotlessI));
        System.out.println("i/dotted: "
                + "i".equalsIgnoreCase(dottedI));

        String sharpS = "\u00DF";
        String upperSharpS = "\u1E9E";
        System.out.println("sharp/SS: "
                + sharpS.equalsIgnoreCase("SS"));
        System.out.println("sharp/upperSharp: "
                + sharpS.equalsIgnoreCase(upperSharpS));
        System.out.println("uppercased sharp: "
                + sharpS.toUpperCase(Locale.ROOT));

        System.out.println("sigma: "
                + "\u03A3".equalsIgnoreCase("\u03C2"));

        String composed = "\u00E9";
        String decomposed = "e\u0301";

        System.out.println("raw NFC/NFD: "
                + composed.equalsIgnoreCase(decomposed));
        System.out.println("normalized NFC: "
                + Normalizer.normalize(
                    composed, Normalizer.Form.NFC)
                  .equalsIgnoreCase(
                    Normalizer.normalize(
                        decomposed, Normalizer.Form.NFC)));

        Collator vi = Collator.getInstance(
                Locale.forLanguageTag("vi-VN"));
        vi.setStrength(Collator.SECONDARY);
        vi.setDecomposition(
                Collator.CANONICAL_DECOMPOSITION);

        System.out.println("collator case: "
                + (vi.compare("Mai", "mai") == 0));
        System.out.println("collator accent: "
                + (vi.compare("ma", "m\u00E1") == 0));

        Set<String> names = new TreeSet<>(
                String.CASE_INSENSITIVE_ORDER);
        names.add("File");
        names.add("file");
        System.out.println("set size: " + names.size());
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 CaseComparisonDemo.java
java CaseComparisonDemo
```

Stdout under the tested JDK environment, with the two Collator checks depending on the provider as noted:

```text
HELLO: true
I/dotless: true
i/dotted: true
sharp/SS: false
sharp/upperSharp: true
uppercased sharp: SS
sigma: true
raw NFC/NFD: false
normalized NFC: true
collator case: true
collator accent: false
set size: 1
```

Explanation: the `I` lines show that ignoring case does not follow Turkish rules specifically; `sharp/SS` and `uppercased sharp` show the difference between simple comparison and whole-string conversion; NFC brings canonically equivalent code point sequences to the same form; `Collator` illustrates separating case and accents at an appropriate strength; `TreeSet` shows that the comparator can merge two keys.

The example uses an explicit `Locale`, does not call `Locale.setDefault`, and does not depend on system date/time. For specific collation ordering requirements, test the deployment environment's JDK/provider.

## 12. Common pitfalls

| Misconception | Consequence | Fix |
| --- | --- | --- |
| `equalsIgnoreCase` fits every language | Turkish I and special mappings can behave unexpectedly | Choose an explicit policy/locale |
| `equalsIgnoreCase` equals lowercasing both sides | Whole-string mapping can change length | Check how case mapping and folding differ |
| `ß` definitely equals `SS` | Simple comparison returns false | Use a full-folding profile if business logic needs it |
| Calling parameterless `toLowerCase()` for technical keys | Default locale can alter output | Use `Locale.ROOT` and validate alphabet |
| Case comparison handles NFC/NFD automatically | Two code point sequences still differ | Normalize both sides when needed |
| Ignoring case also ignores Vietnamese accents | `ma`/`má` differ by more than case | Do not strip accents unless required |
| NFC turns `đ` into `d` | No such canonical equivalence exists | Separate mapping only for search when needed |
| NFKC is always better than NFC | Can merge compatibility characters unintentionally | Pick form per data contract |
| `TreeSet` with CASE_INSENSITIVE_ORDER keeps all distinct values | Comparator returning 0 can drop entries | Define key/collision policy |
| `compareToIgnoreCase` sorts accurately for every locale | Has no locale parameter | Use `Collator` when needed |
| Collator PRIMARY proves two accounts are one | Can ignore accents/case | Do not use flexible collation as identity |
| Case-insensitive passwords are "convenient" | Weakens or breaks secret contract | Use proper authentication mechanisms |
| Testing only ABC/abc | Misses special Unicode cases | Test Turkic, German, NFC/NFD, Vietnamese diacritics |

## 13. Self-check exercises

**Exercise 1 — ASCII and Unicode.** Compare `HELLO/hello` and `I/ı`. Why can both be equal under `equalsIgnoreCase` even though the second case has different semantics when considering locale?

**Exercise 2 — German sharp S.** For `ß`, `ẞ`, and `SS`, print the results of `equalsIgnoreCase` and `toUpperCase(Locale.ROOT)`. What changes when one character expands into two characters?

**Exercise 3 — NFC/NFD.** Create `"\u00E9"` and `"e\u0301"`, calling `equalsIgnoreCase` before and after NFC. Why are normalization and case mapping two independent mechanisms?

**Exercise 4 — Vietnamese.** Compare `"ma"`, `"má"`, and `"MA"` across needs: original name, accent-free search key, and display. Which transformations can lose information?

**Exercise 5 — Collator.** Use `vi-VN` with strength SECONDARY to compare `Mai/mai` and `ma/má`. Change strength to PRIMARY and recheck. Why should this result not be used for identity verification?

**Exercise 6 — TreeSet.** Add `File` and `file` to a `HashSet` and a `TreeSet<>(String.CASE_INSENSITIVE_ORDER)`. Why can the sizes differ? Is this a bug or a feature depending on the contract?

**Exercise 7 — protocol codes.** An API permits case-insensitive ASCII IDs. Design a validation step followed by `Locale.ROOT` conversion. Which Unicode characters must be rejected to avoid expanding scope unintentionally?

**Exercise 8 — security.** Why should `equalsIgnoreCase` not be used for tokens or passwords? If a system allows Unicode usernames, what additional rules must be published regarding normalization, case folding, and collision handling?

## 14. Conclusion

`String.equalsIgnoreCase` is useful for **simple case-insensitive comparison**, yet **has no `Locale` parameter**, does not perform full Unicode case folding, does not automatically normalize NFC/NFD, does not strip Vietnamese diacritics, and does not replace language-aware collation or secure identity logic.

Choose the solution based on your goal: `equals` for exact data; ASCII validation + `Locale.ROOT` for restricted-alphabet protocols; `Normalizer` for canonical equivalence; `Collator` for linguistic comparison; separate search indices for approximate search. For IDs or secret data, normalization and comparison rules must be designed as part of the contract, not added as an ad-hoc utility.

**Takeaway:** *"Case-insensitive" is a requirement that must be defined, not a single toggle switch valid for all languages.*

### References

- [`String` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [`Collator` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Collator.html)
- [`Normalizer` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html)
- [Unicode Case Mappings – Unicode Standard](https://www.unicode.org/versions/latest/core-spec/chapter-4/)
- [Unicode Normalization (UAX #15)](https://unicode.org/reports/tr15/)
