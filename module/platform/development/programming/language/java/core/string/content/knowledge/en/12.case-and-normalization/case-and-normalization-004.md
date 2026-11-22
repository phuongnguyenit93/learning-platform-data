# Case Conversion Can Change String Length in Java

Many developers are familiar with `"java".toUpperCase()` returning `"JAVA"` and assume that changing case simply replaces each character with another at the same position. **That is not true for Unicode.** When using `String.toUpperCase(Locale)` or `String.toLowerCase(Locale)`, a single Unicode character can map to **multiple characters/code points**, or the result can depend on context and language. Therefore, `length()` and UTF-16 indices of the resulting string can differ from the original string.

A striking example on JDK 17 or later:

```java
String before = "Straße";
String after = before.toUpperCase(java.util.Locale.ROOT);

System.out.println(before);           // Straße
System.out.println(after);            // STRASSE
System.out.println(before.length());  // 6
System.out.println(after.length());   // 7
```

The `ß` in `Straße` can map to two `S` letters when uppercased. As a result, both the content **and the length** change. This is intentional Unicode conversion behavior, not a memory bug or in-place `String` mutation.

## 1. What does `String.length()` actually count?

In Java, `String.length()` returns the number of **UTF-16 code units** (`char`), which is not guaranteed to equal the number of Unicode code points or the number of characters a human perceives on screen.

Three concepts to separate:

| Unit | Meaning | Relation to Java |
| --- | --- | --- |
| UTF-16 code unit | A 16-bit unit | `String.length()` and `charAt(index)` use this unit |
| Unicode code point | A Unicode scalar/code value, occupying one or two UTF-16 code units | `codePointCount(...)` and `codePoints()` |
| Grapheme cluster | A character cluster a reader typically perceives as one displayed character | Can consist of multiple code points, e.g., a base letter plus combining marks; `length()` does not count these clusters |

A code point outside the BMP such as U+1F600 (😀) takes **two** UTF-16 code units. Conversely, the combining mark U+0307 is its own code point, usually rendered together with a preceding base letter. Thus, a change in UTF-16 length can come from one code point turning into multiple code points, or from how new characters are represented.

`String` case conversion operates on Unicode text and has no contract to preserve length under any of the units above. When evaluating results, inspect the **resulting value** rather than predicting size solely from source data.

## 2. Why can one letter turn into multiple letters?

Unicode supports both **simple case mapping** and **full case mapping**. In simple mapping, one code point typically maps to at most one corresponding code point. Full mapping can produce **sequences of multiple code points**, and some rules also depend on locale or surrounding characters.

The whole-string methods `String.toUpperCase(Locale)` and `String.toLowerCase(Locale)` can apply full case mapping. Therefore, you should not imagine the result is always built by iterating `char` by `char` and replacing one-for-one.

A clear case is the German **sharp s** (`ß`, U+00DF):

```text
"Straße"                  : 6 UTF-16 code units
"Straße".toUpperCase(ROOT): "STRASSE", 7 UTF-16 code units
                                 ^^
                             ß -> SS
```

Note that the Unicode capital sharp S `ẞ` (U+1E9E) also exists. That does not change the specific result of `"ß".toUpperCase(Locale.ROOT)` in the example above: Java applies the string mapping to `"SS"`. An application with specific linguistic rules should clarify requirements before applying this transformation.

### Example 1: observing code unit counts before and after

Create `UppercaseExpansionDemo.java`:

```java
import java.util.Locale;

public class UppercaseExpansionDemo {
    public static void main(String[] args) {
        String original = "Straße";
        String upper = original.toUpperCase(Locale.ROOT);

        System.out.println(original);
        System.out.println(upper);
        System.out.println(original.length());
        System.out.println(upper.length());
        System.out.println(original.codePointCount(0, original.length()));
        System.out.println(upper.codePointCount(0, upper.length()));
        System.out.println("ß".toUpperCase(Locale.ROOT));
    }
}
```

Compile as UTF-8 and run with JDK 17+:

```bash
javac -encoding UTF-8 UppercaseExpansionDemo.java
java UppercaseExpansionDemo
```

Output:

```text
Straße
STRASSE
6
7
6
7
SS
```

In this example, each letter in the source string is represented by one UTF-16 code unit. Uppercasing replaces `ß` with two `S` code points, increasing both code unit count and code point count from 6 to 7. The new `String` result does not modify `original`.

## 3. Lowercasing can also make a string longer

It is not only `toUpperCase` that can expand length. The Latin capital letter I with dot above `İ` (U+0130, *LATIN CAPITAL LETTER I WITH DOT ABOVE*) is a classic example.

Under the language-neutral mapping of `Locale.ROOT`:

```text
U+0130 (İ) -> U+0069 (i) + U+0307 (COMBINING DOT ABOVE)
```

The source string has **one** UTF-16 code unit; the resulting string has **two** UTF-16 code units. On screen, `i` plus a combining mark can look almost like a normal dotted lowercase letter, yet the two Unicode representations do not necessarily have the same number of code points.

### Example 2: verifying with code points instead of just looking at glyphs

Create `LowercaseExpansionDemo.java`:

```java
import java.util.Locale;
import java.util.stream.Collectors;

public class LowercaseExpansionDemo {
    static String codePoints(String text) {
        return text.codePoints()
                .mapToObj(cp -> String.format("U+%04X", cp))
                .collect(Collectors.joining(", "));
    }

    public static void main(String[] args) {
        String original = "\u0130";
        String lower = original.toLowerCase(Locale.ROOT);

        System.out.println(original.length());
        System.out.println(lower.length());
        System.out.println(codePoints(original));
        System.out.println(codePoints(lower));
        System.out.println(original.equals(lower));
    }
}
```

```bash
javac -encoding UTF-8 LowercaseExpansionDemo.java
java LowercaseExpansionDemo
```

Output:

```text
1
2
U+0130
U+0069, U+0307
false
```

Using `codePoints()` lets you inspect the exact data and avoid confusion from fonts or combining-mark rendering. `String.equals` returns `false` because the two strings have different code unit sequences; naturally, changing case is not a content-preserving operation.

## 4. `Locale` can determine both output and length

Uppercasing/lowercasing rules depend on language. Turkish is the classic example with four related characters:

- `I`: Latin capital I without dot.
- `i`: Latin small i with dot.
- `İ`: Latin capital I with dot.
- `ı`: Latin small i without dot.

In Turkish, `I` lowercases to `ı`, and `İ` lowercases to `i`. With `Locale.ROOT`, the default Unicode rule for `İ` produces `i` + combining dot, so the length differs from converting under the Turkish locale.

### Example 3: same input, different locale

Create `LocaleCaseMappingDemo.java`:

```java
import java.util.Locale;

public class LocaleCaseMappingDemo {
    public static void main(String[] args) {
        Locale turkish = Locale.forLanguageTag("tr");
        String capitalDottedI = "\u0130";

        String rootLower = capitalDottedI.toLowerCase(Locale.ROOT);
        String trLower = capitalDottedI.toLowerCase(turkish);

        System.out.println(rootLower.length());
        System.out.println(trLower.length());
        System.out.println("I".toLowerCase(Locale.ROOT).equals("i"));
        System.out.println("I".toLowerCase(turkish).equals("\u0131"));
        System.out.println("title".toUpperCase(Locale.ROOT));
        System.out.println("title".toUpperCase(turkish)
                .codePoints()
                .mapToObj(cp -> String.format("%04X", cp))
                .toList());
    }
}
```

```bash
javac -encoding UTF-8 LocaleCaseMappingDemo.java
java LocaleCaseMappingDemo
```

Output:

```text
2
1
true
true
TITLE
[0054, 0130, 0054, 004C, 0045]
```

`Locale.ROOT` is an intentional choice for rules independent of user language (for instance, certain internal key codes designed that way). When processing **natural language**, you must select the locale matching the data. There is no single "correct" locale for all text and all requirements.

The two overloads without a locale parameter are:

```java
text.toUpperCase()
text.toLowerCase()
```

By `String`'s contract, they use the environment's default locale. Therefore, a program can produce different results if the default locale changes. If output needs to be consistently reproducible across servers and CI environments, **pass `Locale` explicitly** instead of relying on system configuration.

## 5. Surrounding character context also affects conversion

Unicode mapping is not merely a lookup table from one input character to one output character. Some lowercasing rules must examine **context within a word**. For instance, the Greek capital letter Sigma (Σ, U+03A3) can convert to standard lowercase sigma (σ, U+03C3) or word-final lowercase sigma (ς, U+03C2), depending on position.

Conceptual example:

```java
String word = "\u039F\u03A3"; // Two Greek capital letters.
String lower = word.toLowerCase(java.util.Locale.ROOT);
```

The result contains code points U+03BF (ο) and U+03C2 (ς); the trailing sigma receives the context-appropriate form. This is an **illustrative snippet** without `main`. Even though this example does not change length, it proves that case-conversion algorithms cannot always be replaced by independent operations on each `char`.

Therefore, avoid automatically writing a loop with `Character.toLowerCase(text.charAt(i))` when you need **full string Unicode case conversion**: processing one code unit at a time misses both multi-code-point mappings and whole-string context.

## 6. `Character.toUpperCase(char)` is not equivalent to `String.toUpperCase(Locale)`

`Character.toUpperCase(char)` takes a `char` and returns a `char`. That return type can hold only **one UTF-16 code unit**, so it cannot return the two-letter sequence `"SS"` for input `'ß'`. The `Character.toUpperCase(int)` overload works on code points, yet still returns a single `int` value and cannot represent variable-length string mappings.

`String.toUpperCase(Locale)` is allowed to return a longer result to represent the full mapping.

### Example 4: replacing `char` by `char` can yield different output

Create `CharacterVsStringDemo.java`:

```java
import java.util.Locale;

public class CharacterVsStringDemo {
    public static void main(String[] args) {
        char sharpS = '\u00DF';

        char charMapped = Character.toUpperCase(sharpS);
        String stringMapped = String.valueOf(sharpS).toUpperCase(Locale.ROOT);

        System.out.println(charMapped == sharpS);
        System.out.println(stringMapped);
        System.out.println(stringMapped.length());

        String text = "Straße";
        StringBuilder naive = new StringBuilder();
        for (int i = 0; i < text.length(); i++) {
            naive.append(Character.toUpperCase(text.charAt(i)));
        }

        System.out.println(naive);
        System.out.println(text.toUpperCase(Locale.ROOT));
    }
}
```

```bash
javac -encoding UTF-8 CharacterVsStringDemo.java
java CharacterVsStringDemo
```

Output:

```text
true
SS
2
STRAßE
STRASSE
```

In Java 17+, `Character.toUpperCase('ß')` cannot expand to two characters and keeps the same code unit, whereas `String.toUpperCase(Locale.ROOT)` expands it to `SS`.

When complete text transformation is required, use the `String` API with an appropriate locale. `Character` is suited for algorithms intentionally operating on a single code point or code unit after understanding the mapping limitations.

## 7. Length changes make old indices unreliable

In Java, `substring`, `charAt`, `indexOf`, and `lastIndexOf` all use UTF-16 indices in the **string being operated on**. If case conversion produces a longer or shorter string, character positions in the result can shift left or right.

Consider:

```text
Before: S t r a ß e
Index : 0 1 2 3 4 5

After : S T R A S S E
Index : 0 1 2 3 4 5 6
```

The letter `e` is at index `5` before uppercasing; after `ß` becomes `SS`, `E` is at index `6`. **Do not store an index from the original string and reuse it to slice or index the case-converted string.**

### Example 5: bug from using a pre-conversion index

Create `CaseMappingIndexDemo.java`:

```java
import java.util.Locale;

public class CaseMappingIndexDemo {
    public static void main(String[] args) {
        String original = "Straße";
        int oldE = original.indexOf('e');

        String upper = original.toUpperCase(Locale.ROOT);

        System.out.println(oldE);
        System.out.println(upper.charAt(oldE));
        System.out.println(upper.indexOf('E'));
        System.out.println(upper.substring(upper.indexOf('E')));
    }
}
```

```bash
javac -encoding UTF-8 CaseMappingIndexDemo.java
java CaseMappingIndexDemo
```

Output:

```text
5
S
6
E
```

The character at index 5 after conversion is the second `S` in `SS`, no longer `E`. If you use the old index to slice the new string, the result is silently wrong without throwing an exception.

**Safer approach:** recompute positions on the **post-transformation string**, or parse/split data before transforming if the boundaries truly belong to the original string. If you must maintain bidirectional position mapping (for example, highlighting search matches on normalized text), design an explicit *offset mapping* mechanism. You cannot simply add or subtract a fixed offset in the general case.

## 8. `String` remains immutable even when result length changes

`String.toUpperCase(...)` and `String.toLowerCase(...)` do not mutate the source `String`'s content. They return the converted result. When conversion does not change the content, an implementation may return the original instance; do not rely on reference identity of the result in business logic.

```java
String source = "Straße";
String alias = source;
String changed = source.toUpperCase(java.util.Locale.ROOT);

// source and alias still have content "Straße".
// changed has content "STRASSE".
```

This is an illustrative snippet, not a class with `main`. Immutability explains why both before and after versions can coexist; it does **not** guarantee that the result has the same `length()`.

When you need the length to allocate buffers, enforce field limits, check UI bounds, or compute indices, **compute it on the actual resulting string**:

```java
String normalizedCase = source.toUpperCase(java.util.Locale.ROOT);
int finalLength = normalizedCase.length();
```

Do not preallocate a character array using the source length and assume the converted result will fit. For many international text inputs, that assumption fails.

## 9. Do not equate case conversion with Unicode normalization

Two concepts often appear side by side but solve different problems:

- **Case conversion:** uppercasing/lowercasing according to Unicode and locale, which can change the number of code points.
- **Unicode normalization:** bringing equivalent code point sequences into a canonical form such as NFC or NFD (per canonical equivalence rules), which can change the number of code points and code units.
- **Case-insensitive comparison / case folding:** a policy for comparing or matching letters without case sensitivity, with its own rules—not simply a guarantee of `toLowerCase` across all languages.

For example, `é` can be represented by a single code point U+00E9, or by `e` (U+0065) combined with acute accent U+0301. They can look identical yet are unequal under `String.equals` before normalization:

### Example 6: normalization is a separate step

Create `UnicodeNormalizationDemo.java`:

```java
import java.text.Normalizer;

public class UnicodeNormalizationDemo {
    public static void main(String[] args) {
        String composed = "\u00E9";
        String decomposed = "e\u0301";

        System.out.println(composed.length());
        System.out.println(decomposed.length());
        System.out.println(composed.equals(decomposed));

        String fixed = Normalizer.normalize(decomposed, Normalizer.Form.NFC);
        System.out.println(composed.equals(fixed));
        System.out.println(fixed.length());
    }
}
```

```bash
javac UnicodeNormalizationDemo.java
java UnicodeNormalizationDemo
```

Output:

```text
1
2
false
true
1
```

This example illustrates **Unicode representation**, not a case-conversion scenario. It shows that length can change in different text-processing steps. Do not use `Normalizer` as a substitute for `toUpperCase` or `toLowerCase`: each operation has its own contract and purpose. When business logic requires both normalization and case-insensitive comparison, clearly define the order and the accepted comparison standard.

## 10. Case conversion can break comparison assumptions

`equalsIgnoreCase` is useful when you want to compare two `String` values case-insensitively according to Java's own contract. However, it is **not equivalent** to all multi-character Unicode mappings or locale-sensitive natural-language comparison.

Example:

```java
String a = "straße";
String b = "STRASSE";

System.out.println(a.toUpperCase(java.util.Locale.ROOT));
System.out.println(a.equalsIgnoreCase(b));
```

The illustrative snippet produces:

```text
STRASSE
false
```

Two strings may turn into the same uppercase text under a specific transformation, yet `equalsIgnoreCase` is not designed to treat every one-to-many expansion as equal; it also requires matching lengths. Using `equalsIgnoreCase` is a decision based on **the API's comparison contract**, not a general way to implement full Unicode case folding or language-aware collation.

When handling user-facing search, language sorting, proper names, or international Unicode text, clarify all factors: locale, accent sensitivity, case sensitivity, normalization, expanding mappings, and matching policy. Depending on the problem, you may need `Collator`, a dedicated Unicode library, or domain-specific rules. Do not automatically treat any `toLowerCase(Locale.ROOT)` string as the canonical search key for every business domain.

Especially for sensitive identifiers or security policies, a careless canonicalization rule can cause two distinct values to be treated as identical, or the same value to be recognized differently across environments. Define rules consistently across all places where data is ingested, stored, and compared.

## 11. Common mistakes

**Mistake 1 — Assuming `upper.length() == original.length()`.** False for Unicode. `"Straße".toUpperCase(Locale.ROOT)` grows from 6 to 7 UTF-16 code units.

**Mistake 2 — Thinking only uppercasing expands strings.** `"\u0130".toLowerCase(Locale.ROOT)` turns one code point into two code points: `i` and a combining dot.

**Mistake 3 — Using `Character.toUpperCase(char)` instead of `String.toUpperCase(Locale)`.** A function returning a single `char` cannot represent one-to-many mappings, and looping per `char` ignores whole-string context.

**Mistake 4 — Ignoring locale.** Results for `I`/`İ`/`ı`/`i` in Turkish differ from general rules. Pass locale intentionally; do not let machine settings implicitly decide a stable business rule.

**Mistake 5 — Trusting old indices after transformation.** A letter can expand into multiple units, shifting subsequent positions. Recompute indices or maintain an offset map.

**Mistake 6 — Thinking UTF-16 length equals visible character count.** An emoji outside the BMP uses two code units; a base letter with combining marks can contain multiple code points. `String` indices are not grapheme cluster indices.

**Mistake 7 — Assuming NFC normalization is case conversion.** Normalization and case conversion are separate operations. Do not interchange them merely because both can change length.

**Mistake 8 — Assuming `equalsIgnoreCase` supports all Unicode rules.** This API does not perform all one-to-many expansions and is not locale-aware language comparison.

**Mistake 9 — Assuming case conversion is reversible.** When `ß` becomes `SS`, the result does not retain enough information to determine with certainty how many original characters existed or their original casing. Mapping is not necessarily one-to-one or invertible.

**Mistake 10 — Forgetting `String` is immutable.** Case conversion creates a resulting value and does not modify text held by other references.

## 12. Self-check questions

### Question 1: length after uppercasing

Given:

```java
String word = "Straße";
String upper = word.toUpperCase(java.util.Locale.ROOT);

System.out.println(word.length());
System.out.println(upper.length());
System.out.println(upper);
```

Output:

```text
6
7
STRASSE
```

Explanation: the `ß` in the source string maps to two consecutive `S` letters when uppercased.

### Question 2: what is the length of the letter İ?

Given:

```java
String s = "\u0130";
String lowerRoot = s.toLowerCase(java.util.Locale.ROOT);
String lowerTr = s.toLowerCase(java.util.Locale.forLanguageTag("tr"));

System.out.println(lowerRoot.length());
System.out.println(lowerTr.length());
```

Output:

```text
2
1
```

`Locale.ROOT` produces `i` + combining dot, while Turkish rules produce a single `i`.

### Question 3: can old indices be reused?

If `original = "Straße"` and `upper = original.toUpperCase(Locale.ROOT)`, the index of the original `e` is 5. The position of `E` in the result is **6**. Therefore, `upper.charAt(5)` returns `'S'`, not `'E'`.

### Question 4: handling multilingual strings

An application stores text in multiple locales and needs to find matches on case-converted text. What should it do?

**Approach:** choose the appropriate locale/canonicalization rules, transform data under a consistent contract, compute indices on the **transformed version**, and if highlighting on the original text is required, maintain an explicit offset mapping. Do not use old indices or lengths to infer new positions.

## Conclusion

**Case conversion in Java is a Unicode transformation, not simply replacing each `char` with another `char`.** `String.toUpperCase(Locale)` and `String.toLowerCase(Locale)` can expand one character into multiple code points; results can also depend on locale and context. Therefore, compute `length()` and indices on the resulting string itself, choose locales explicitly, distinguish case conversion from Unicode normalization, and never assume the transformation is one-to-one or reversible.
