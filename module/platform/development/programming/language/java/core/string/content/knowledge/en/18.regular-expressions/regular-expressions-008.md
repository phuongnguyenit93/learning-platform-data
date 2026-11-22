# Unicode Characters, Word Boundaries, and Grapheme Clusters in Java Regex

## 1. Why Does Regex with Unicode Differ from ASCII-Only Regex?

A `Java String` stores a sequence of **UTF-16 code units** (`char`). In Unicode, three concepts must be distinguished:

| Concept | Meaning | Example |
| --- | --- | --- |
| **Code unit** | One UTF-16 unit, which is what `String.length()` counts. | Emoji `😀` (U+1F600) requires **2** `char`s (a surrogate pair). |
| **Code point** | One Unicode character value, which may take 1 or 2 UTF-16 code units. | `e` + combining acute accent U+0301 is **2** code points. |
| **Extended grapheme cluster** | A sequence of code points typically perceived by a reader as a single character unit. | `e` + U+0301 is typically **1** cluster; emoji `👩‍💻` is one cluster joined with ZWJ. |

A character visible on screen **does not necessarily correspond to one `char` or one code point**. Even a grapheme cluster is not guaranteed to occupy a single display cell, because width and rendering depend on fonts and UI.

In `java.util.regex.Pattern`, regex understands Unicode properties via `\p{...}` and `\P{...}`; identifies word boundaries via `\b` and `\B`; and supports **extended grapheme clusters** via `\X` and the boundary `\b{g}` (Java 9+). These are distinct concepts serving different purposes.

## 2. Writing Regexes in Java Strings: Two Escaping Layers

Regex is a language embedded **inside** a Java string. When written directly as a Java string literal, backslashes in the regex must be escaped a second time:

| Intent | Regex | Java string literal |
| --- | --- | --- |
| One Unicode letter | `\p{L}` | `"\\p{L}"` |
| Word boundary | `\b` | `"\\b"` |
| One grapheme cluster | `\X` | `"\\X"` |
| Grapheme boundary | `\b{g}` | `"\\b{g}"` |
| Code point U+1F600 | `\x{1F600}` | `"\\x{1F600}"` |

**Careful:** `"\b"` in Java code represents a **backspace character**, not a regex word boundary. Likewise, `"\p{L}"` is not a valid Java string literal because `\p` is not a Java escape.

`Pattern.compile(regex).matcher(text).find()` finds a matching span; `matcher.matches()` requires the **entire search region** to match. For frequently used expressions, compile `Pattern` once and reuse it.

## 3. Selecting Characters by Unicode Property

### 3.1. General Categories and Unicode Labels

`\p{...}` matches a character that has the property; `\P{...}` matches a character that **does not** have the corresponding property.

| Expression | Meaning | Use case |
| --- | --- | --- |
| `\p{L}` | **Letter** category: letters across many scripts. | Matching letters instead of limiting to `[A-Za-z]`. |
| `\p{Lu}`, `\p{Ll}` | Uppercase / lowercase letters by Unicode category. | Checking letter casing. |
| `\p{M}` | **Mark**, including combining marks (`Mn`, `Mc`, `Me`). | Preserving diacritics when processing decomposed strings. |
| `\p{N}`, `\p{Nd}` | Numbers in general / decimal digits. | Distinguishing `Ⅳ` (a numeric character) from decimal digits. |
| `\p{Sc}` | Currency symbols. | Detecting symbols such as `€` or `$`. |
| `\p{IsAlphabetic}` | Binary Alphabetic property. | Broader definition than certain `L` category characters. |
| `\P{L}` | A code point outside the Letter category. | Finding non-letter characters. |

Example:

```java
Pattern letters = Pattern.compile("\\p{L}+");
Pattern lettersAndMarks = Pattern.compile("\\p{L}[\\p{L}\\p{M}]*");

System.out.println(letters.matcher("Việt").matches());       // true
System.out.println(letters.matcher("e\u0301").matches());     // false
System.out.println(lettersAndMarks.matcher("e\u0301").matches()); // true
```

`"Việt"` in the first example contains **precomposed** accented letters. By contrast, `"e\u0301"` contains the letter `e` and a **combining acute accent**. With `\p{L}+` alone, the combining mark is not in the Letter category, so `matches()` returns `false`. The pattern `\p{L}[\p{L}\p{M}]*` requires starting with a letter and allows marks afterward; this is a technical illustration rather than a complete natural-language word definition.

### 3.2. Script vs. Block

- **Script** (`\p{IsLatin}`, `\p{sc=Greek}`, `\p{script=Hiragana}`) indicates the writing system assigned to a character.
- **Block** (`\p{InGreek}`, `\p{blk=Greek}`) is a Unicode **code point range**, which can contain characters from other scripts or unassigned code points.
- **Category** (`\p{L}`, `\p{Lu}`) classifies by character nature, independent of script.

For example, `\p{sc=Greek}+` expresses the **Greek script**; `\p{InGreek}+` expresses code points within the **Greek block**. The two sets are not interchangeable in every situation. When filtering Vietnamese text, `\p{IsLatin}` also does not automatically guarantee all accompanying combining marks are included, since marks can carry the `Inherited` script.

Java regex supports set intersection/subtraction inside character classes, such as `[\p{L}&&[^\p{Lu}]]` for Letter characters that are not in the Uppercase Letter category.

## 4. `\w`, `\d`, `\s`, and Unicode Mode

By default in Java 17, predefined classes are mainly ASCII-based: `\w` is equivalent to `[a-zA-Z_0-9]`, `\d` is `[0-9]`, and `\s` covers standard ASCII whitespace. Hence `\w+` **does not** automatically recognize all Vietnamese letters.

Enable `Pattern.UNICODE_CHARACTER_CLASS` (inline `(?U)`) when you want predefined and POSIX classes to use Unicode rules:

```java
Pattern asciiWord = Pattern.compile("\\w+");
Pattern unicodeWord = Pattern.compile("\\w+", Pattern.UNICODE_CHARACTER_CLASS);
Pattern inlineUnicodeWord = Pattern.compile("(?U)\\w+");

System.out.println(asciiWord.matcher("đèn").matches());        // false
System.out.println(unicodeWord.matcher("đèn").matches());      // true
System.out.println(inlineUnicodeWord.matcher("đèn").matches()); // true
```

In Unicode mode, `\w` includes alphabetic letters, decimal digits, combining marks, connector punctuation, and certain join controls (`Join_Control`). Therefore `\w` is **not synonymous** with "letters", "valid Java identifier", or "meaningful word". Depending on requirements:

- Only letters by category: `\p{L}+`.
- Letters with combining marks: `\p{L}[\p{L}\p{M}]*`.
- Word-like tokens, possibly containing digits, underscores, and marks: `(?U)\w+`.
- Validating actual Java identifiers: consider `Character.isJavaIdentifierStart`/`isJavaIdentifierPart` on **code points**, or an appropriate parser; regex `\w+` is insufficient.

Enabling `UNICODE_CHARACTER_CLASS` also implies `UNICODE_CASE`. Conversely, `Pattern.UNICODE_CASE` (inline `(?u)`) only adjusts **case-insensitive** matching when combined with `CASE_INSENSITIVE`; `(?u)` by itself does not turn `\w` into a Unicode class. Distinguish lowercase `u` from uppercase `U`.

## 5. Word Boundaries `\b` and `\B`

`\b` is a **zero-width assertion**: it checks a *position* at a word boundary without consuming characters. `\B` checks a position that is **not** a word boundary.

```java
String text = "café_42, đèn!";
Matcher words = Pattern.compile("(?U)\\b\\w+\\b").matcher(text);
while (words.find()) {
    System.out.println(words.group());
}
```

Output:

```text
café_42
đèn
```

Explanation: `(?U)` selects Unicode semantics for `\w`; `\b` at both ends checks boundaries, while `\w+` **consumes** the token's characters. Underscores and digits can appear inside the same token, so `café_42` is a single match. To extract only letters and marks, specify a separate character set rather than wrapping `\w+` in `\b`.

**Do not confuse `\b` with a natural-language word tokenizer**: hyphens, apostrophes, hashtags, emojis, unspaced languages like Thai, or multisyllabic Vietnamese words all need appropriate segmentation rules. `\b` does not define a dictionary or grammatical "word". Using `(?U)` consistently helps avoid unintended ASCII assumptions when pairing `\b` with `\w`; do not rely on JDK-version-specific boundary details behaving identically to a language tokenizer.

## 6. Grapheme Clusters with `\X` and `\b{g}`

An **extended grapheme cluster** may consist of one or more code points: base letter + combining marks, emoji sequences joined by zero-width joiners (ZWJ), or regional indicator pairs forming a flag.

| Regex | Role | Consumes characters? |
| --- | --- | --- |
| `\X` | Matches **one extended grapheme cluster**. | Yes |
| `\b{g}` | Checks a **boundary between grapheme clusters**. | No |
| `\b` | Checks a **word** boundary. | No |
| `.` | Matches one regex unit; **not** a reliable way to count grapheme clusters. | Yes |

For example, the string `"e\u0301👩‍💻"` has **7 UTF-16 code units**, **5 code points**, yet only **2 grapheme clusters**: the `e + U+0301` cluster and the `woman technologist` emoji cluster. With regex `\X`, two `find()` calls return two clusters. `\b{g}` identifies the UTF-16 boundary positions at offsets `0`, `2`, and `7`. In contrast, `\b` expresses word boundaries and does not replace `\b{g}`.

You can use `\X` to step through a string in character units that users typically perceive, such as enforcing a *grapheme cluster count* limit or slicing strings at cluster boundaries. Even so, Unicode clustering does not replace font/rendering logic, nor does it guarantee a cluster equals a linguistic "letter".

### 6.1. `Matcher.start()`/`end()` Positions Are Still UTF-16

Even when regex `\X` groups an entire emoji into one cluster, `Matcher.start()`, `Matcher.end()`, and `String.substring(...)` indices are still measured in **UTF-16 code units**, with `end()` being *exclusive*. Do not increment an offset by 1 assuming you have stepped past one code point or one grapheme.

To count code points: `s.codePointCount(0, s.length())`. To iterate over code points: `s.codePoints()` or `s.offsetByCodePoints(...)`. To iterate over **graphemes**: use `Pattern.compile("\\X").matcher(s)` with `find()`. Do not slice a string in the middle of a surrogate pair or a mark/emoji cluster when the goal is to keep user-visible characters intact.

## 7. Standalone Runnable Java 17+ Example

Save the **entire program** below as `UnicodeRegexDemo.java`. The code uses Unicode escapes in special strings to clearly show character structure and run consistently even when a terminal cannot easily type emojis.

```java
import java.text.Normalizer;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class UnicodeRegexDemo {
    public static void main(String[] args) {
        String decomposed = "e\u0301";
        String womanTechnologist = "\uD83D\uDC69\u200D\uD83D\uDCBB";
        String sample = decomposed + womanTechnologist;

        System.out.println("UTF-16 units: " + sample.length());
        System.out.println("Code points: "
                + sample.codePointCount(0, sample.length()));

        Matcher clusters = Pattern.compile("\\X").matcher(sample);
        while (clusters.find()) {
            System.out.printf("Grapheme: [%d,%d)%n",
                    clusters.start(), clusters.end());
        }

        Matcher boundaries = Pattern.compile("\\b{g}").matcher(sample);
        System.out.print("Grapheme boundaries:");
        while (boundaries.find()) {
            System.out.print(" " + boundaries.start());
        }
        System.out.println();

        System.out.println("ASCII word đ: "
                + Pattern.compile("\\w+").matcher("\u0111").matches());
        System.out.println("Unicode word đ: "
                + Pattern.compile("(?U)\\w+").matcher("\u0111").matches());
        System.out.println("NFD all letters: "
                + Pattern.compile("\\p{L}+").matcher(decomposed).matches());
        System.out.println("NFD letters and marks: "
                + Pattern.compile("\\p{L}[\\p{L}\\p{M}]*")
                        .matcher(decomposed).matches());

        Matcher words = Pattern.compile("(?U)\\b\\w+\\b")
                .matcher("caf\u00e9_42, \u0111\u00e8n!");
        while (words.find()) {
            System.out.println("Word: " + words.group());
        }

        String normalized = Normalizer.normalize(
                decomposed, Normalizer.Form.NFC);
        System.out.println("NFC equals é: "
                + normalized.equals("\u00e9"));
    }
}
```

Compile/run:

```bash
javac UnicodeRegexDemo.java
java UnicodeRegexDemo
```

Standard output (UTF-8 output):

```text
UTF-16 units: 7
Code points: 5
Grapheme: [0,2)
Grapheme: [2,7)
Grapheme boundaries: 0 2 7
ASCII word đ: false
Unicode word đ: true
NFD all letters: false
NFD letters and marks: true
Word: café_42
Word: đèn
NFC equals é: true
```

The three counts **7 / 5 / 2** refer respectively to code units, code points, and grapheme clusters. The offsets `[0,2)` and `[2,7)` represent two clusters, not two `char`s. The Vietnamese token output demonstrates Unicode mode for `\w` in this regex; the two NFD checks demonstrate why combining marks must be accounted for.

## 8. Unicode Normalization, Case Matching, and Limitations

### NFC and NFD: Two Representations of the Same Letter Shape

`"é"` can be U+00E9 (precomposed) or U+0065 + U+0301 (decomposed). Those two strings may look identical yet not be equal under `String.equals()` and not necessarily match the same literal pattern. When consistent matching is required, **normalize both the data and the search criteria**:

```java
import java.text.Normalizer;

String a = "\u00E9";
String b = "e\u0301";
String left = Normalizer.normalize(a, Normalizer.Form.NFC);
String right = Normalizer.normalize(b, Normalizer.Form.NFC);
System.out.println(left.equals(right)); // true
```

`Normalizer.Form.NFC` is usually suitable when normalizing to composed form. `NFD` performs canonical decomposition. Java also has `Pattern.CANON_EQ` to match canonical equivalence, but that flag can incur significant overhead; normalize inputs upfront if the goal is to match text in a unified storage form.

### Unicode Case Folding

`Pattern.CASE_INSENSITIVE` alone defaults to ASCII preference; add `Pattern.UNICODE_CASE` (or `(?iu)`) for Unicode case-insensitive matching. This is **case-insensitive matching**, not NFC/NFD normalization and not a guarantee of every locale-specific casing rule. Normalization/case-folding operations can change string contents and positions, so pick a consistent processing order before recording offsets.

### Common Mistakes

1. Using `String.length()` to limit "visible character count"; in reality it counts UTF-16 code units. If the product requires a grapheme limit, count `\X`.
2. Using default `\w+` and concluding accented letters are "invalid"; replace with `(?U)\w+` or a policy-appropriate `\p{...}` expression.
3. Using `\p{L}+` on decomposed text while forgetting `\p{M}`; this drops or rejects combining marks.
4. Using `\b` as a Vietnamese/Thai word splitter or as an emoji boundary; those goals need linguistic logic or `\b{g}`/`\X` respectively.
5. Treating `Matcher.start()` as a code point or grapheme index; in reality it is UTF-16.
6. Assuming NFC, `(?U)`, or `(?iu)` eliminates **confusables** or all zero-width characters; identifier/identity checks require separate policies.
7. Concatenating user input directly into a regex; when searching literally, use `Pattern.quote(userInput)` to avoid unintended metacharacter behavior.

## 9. Choosing the Right Tool for the Goal

| Goal | Suggested approach |
| --- | --- |
| Check whether one code point is a letter/digit/mark | `\p{L}`, `\p{Nd}`, `\p{M}`, or `Character` APIs. |
| Find tokens of letters, digits, combining marks, and underscores | `(?U)\b\w+\b` plus business rules. |
| Iterate over each code point | `String.codePoints()`; keeps surrogate pairs intact. |
| Iterate over each extended grapheme cluster | `Matcher` with `\X`. |
| Identify boundaries between grapheme clusters | Assertion `\b{g}`. |
| Match strings that may differ in combining-mark composition | Normalize with `Normalizer` to the same NFC/NFD form first. |
| Break words by specific language rules | `BreakIterator.getWordInstance(locale)` to start, or NLP/ICU4J libraries when accurate language segmentation is needed. |

**Takeaway:** **Unicode properties** answer "which category does a character belong to?", **word boundaries** answer "is this position a token boundary under regex rules?", and **grapheme clusters** answer "which code points combine into one character unit?". Selecting the right layer lets regex handle accented Vietnamese, emojis, and other writing systems accurately.

### References

- [Java SE 17 — `java.util.regex.Pattern`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html): Unicode Support, character classes, boundary matchers, `UNICODE_CHARACTER_CLASS`, `UNICODE_CASE`.
- [Java SE 17 — `java.text.Normalizer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html): NFC/NFD and canonical equivalence matching.
- [Java SE 17 — `java.lang.String`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): UTF-16, `codePointCount`, and code-point offsets.
