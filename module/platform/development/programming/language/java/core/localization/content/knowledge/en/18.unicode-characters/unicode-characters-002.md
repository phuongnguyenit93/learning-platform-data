# `char` Does Not Always Represent a Whole Character in Java

## 1. The Problem: A "Character" Is Not Necessarily One `char`

In a Java program, the snippet `String.valueOf('A')` holds one Latin letter and `"A".length()` equals `1`. Therefore, beginners often assume:

- `char` always represents one complete character;
- `String.length()` is the number of characters the user sees;
- `charAt(i)` always retrieves one Unicode character;
- `substring(i, i + 1)` always slices exactly one character.

These assumptions are **wrong when working with Unicode**. For example, the grinning face symbol **😀 (U+1F600)** is **one Unicode code point** yet requires **two UTF-16 code units** in a Java string. A visible letter like **é** can also be represented by **one code point** `U+00E9` or **two code points** `U+0065 U+0301` (letter `e` plus combining acute accent). Furthermore, family emojis and certain letter clusters are formed from **multiple code points** yet are usually perceived by users as a single character.

Therefore, at least three layers must be separated:

1. **UTF-16 code unit** — the 16-bit `char` unit Java uses for indexing inside a `String`.
2. **Unicode code point** — the numeric code of a Unicode element, typically handled with `int`.
3. **Extended grapheme cluster** — a sequence of code points forming one character unit according to Unicode text segmentation rules, close to what a user considers one "character".

This is essential foundational knowledge when traversing internationalized strings, counting input limits, truncating display names, handling emojis, comparing Vietnamese content, building APIs, and storing data.

## 2. `char` Is 16 Bits, While Unicode Has More Than 65,536 Code Points

`char` in Java is an **unsigned 16-bit integer type**, with values from `0` to `65535` (hex `U+0000` to `U+FFFF` in code unit notation). When working with `String`, each `char` is **one UTF-16 code unit**, not necessarily a complete character.

Unicode assigns **code points** in the range `U+0000` to `U+10FFFF`. They are divided into:

| Range | Name | UTF-16 representation |
| --- | --- | --- |
| `U+0000..U+FFFF`, excluding surrogate values | Basic Multilingual Plane (BMP) | One `char` / one code unit |
| `U+10000..U+10FFFF` | Supplementary planes | **Two `char`s / one surrogate pair** |
| `U+D800..U+DFFF` | Reserved UTF-16 surrogate range | Not standalone Unicode scalar values |

Examples:

- `'A'` is one `char` and one code point `U+0041`.
- `'é'` (precomposed `U+00E9`) is one `char` and one code point.
- `'中'` (`U+4E2D`) is one `char` and one code point.
- Emoji `😀` (`U+1F600`) **cannot fit inside a single `char`**; it requires two `char`s.
- A visible character formed from `e` + combining acute accent can contain **two BMP code points**, even though the human eye sees one letter.

Therefore, the claim "a Unicode character is always 16 bits" is false. Java still provides 16-bit `char` because its string model is based on UTF-16 units; code-point-aware APIs are required to fully handle codes outside the BMP.

**Implementation note:** since Java 9, `String` may use an optimized memory representation (compact strings), but the **API semantics** of `length()`, `charAt()`, indices, and `substring()` remain based on **UTF-16 units**. Do not infer from internal storage structures to decide how to count strings.

## 3. Surrogate Pairs: Why Does One Emoji Need Two `char`s?

UTF-16 represents a code point outside the BMP with a pair:

- **High surrogate** in the range `U+D800..U+DBFF`.
- **Low surrogate** in the range `U+DC00..U+DFFF`.

Two consecutive code units in the proper order form one supplementary code point. For example, `U+1F600` is encoded as `\uD83D\uDE00` in UTF-16.

```java
String emoji = new String(Character.toChars(0x1F600));

System.out.println(emoji.length()); // 2
System.out.println(emoji.codePointCount(0, emoji.length())); // 1
System.out.println(Character.isHighSurrogate(emoji.charAt(0))); // true
System.out.println(Character.isLowSurrogate(emoji.charAt(1)));  // true
```

This is a **snippet** placed inside a method. `Character.toChars(int)` returns a `char[]` of length 1 or 2 depending on the code point; `new String(...)` creates the corresponding string. `Character.isSurrogatePair(high, low)` indicates whether two code units form a structurally valid surrogate pair.

If you call `emoji.charAt(0)`, you only obtain the **high surrogate**, not the code point `U+1F600`. Similarly, `emoji.substring(0, 1)` produces a `String` containing only the first half of the surrogate pair. That string can still exist in Java, yet **is no longer a valid sequence of Unicode scalar values** when interpreted independently.

A **char literal** such as `'A'` or `'中'` is valid because it holds one code unit. You cannot use a single `char` literal to hold an entire non-BMP emoji. Use `String`, `int codePoint`, or code-point-aware APIs.

## 4. `length`, `codePointCount`, and Visible Character Count Are Three Different Quantities

Consider text composed of:

- `A` — `U+0041`;
- grinning face emoji — `U+1F600`;
- letter `e` — `U+0065`;
- combining acute accent — `U+0301`.

When displayed, you typically see **three character clusters**: `A`, the emoji, and `é`. However, different counts yield different results:

| Quantity | Result | Why |
| --- | ---: | --- |
| `text.length()` | **5** | `A` 1 + emoji 2 + `e` 1 + combining mark 1 code unit |
| `text.codePointCount(0, text.length())` | **4** | `A`, emoji, `e`, combining mark are four code points |
| Extended grapheme clusters count | **3** | `e` and acute accent form one cluster; this emoji is one cluster |
| `text.getBytes(UTF_8).length` | **8** | UTF-8 bytes: `A` 1 + emoji 4 + `e` 1 + combining mark 2 |

**There is no single `String.length()` method that automatically returns "the number of user-perceived characters"** in all situations. `String.length()` counts **UTF-16 code units**. `codePointCount` counts **code points** (a valid surrogate pair counts as one), while grapheme segmentation is a separate problem.

### API Reference Table

| API | Unit processed | Notes |
| --- | --- | --- |
| `String.length()` | UTF-16 code units | Not the number of code points or graphemes |
| `String.charAt(index)` | One `char` | May return half of a surrogate pair |
| `String.chars()` | Stream of `char` values widened to `int` | **Does not** merge surrogate pairs |
| `String.codePointAt(index)` | Code point at **UTF-16 index** | Merges a valid high+low surrogate starting at that index |
| `String.codePoints()` | `IntStream` of code points | Merges valid surrogate pairs; does not merge combining marks into graphemes |
| `String.codePointCount(begin, end)` | Code point count in **UTF-16 index** range | Indices are still measured in code units |
| `String.offsetByCodePoints(index, offset)` | Finds **UTF-16 index** shifted by a number of code points | Used to slice strings without splitting surrogate pairs |
| `Character.toChars(codePoint)` | Converts a code point to one or two `char`s | Useful when building strings from code points |
| `StringBuilder.appendCodePoint(int)` | Appends one code point | Avoids manual surrogate calculation |
| `Pattern.compile("\\X")` | Extended grapheme cluster | Suitable for segmentation close to visible "characters"; depends on Unicode/JDK rule versions |

Important note: `String` methods that accept an **index** still use **UTF-16 indices** even when the method name contains `codePoint`. For example, `codePointAt(1)` reads the code point starting at **code unit index 1**, not "the code point at ordinal 1 in the list of code points" for every string.

## 5. Standalone Java 17+ Example: Seeing Every Counting Layer Clearly

Create the file **`UnicodeUnitsDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.regex.Pattern;

public class UnicodeUnitsDemo {
    public static void main(String[] args) {
        String emoji = new String(Character.toChars(0x1F600));
        String text = "A" + emoji + "e\u0301";

        System.out.println("UTF-16 units: " + text.length());
        System.out.println("Code points: "
                + text.codePointCount(0, text.length()));
        System.out.println("UTF-8 bytes: "
                + text.getBytes(StandardCharsets.UTF_8).length);

        System.out.println("charAt(1) high surrogate: "
                + Character.isHighSurrogate(text.charAt(1)));
        System.out.println("codePointAt(1): U+"
                + Integer.toHexString(text.codePointAt(1))
                         .toUpperCase(Locale.ROOT));
        System.out.println("Index after 2 code points: "
                + text.offsetByCodePoints(0, 2));

        System.out.println("Grapheme clusters: "
                + Pattern.compile("\\X").matcher(text)
                         .results().count());
        System.out.println("Code points list: "
                + text.codePoints()
                      .mapToObj(cp -> String.format(
                              Locale.ROOT, "U+%04X", cp))
                      .toList());
    }
}
```

Run with **JDK 17 or higher**:

```bash
javac -encoding UTF-8 UnicodeUnitsDemo.java
java UnicodeUnitsDemo
```

**Stdout verified on JDK 24:**

```text
UTF-16 units: 5
Code points: 4
UTF-8 bytes: 8
charAt(1) high surrogate: true
codePointAt(1): U+1F600
Index after 2 code points: 3
Grapheme clusters: 3
Code points list: [U+0041, U+1F600, U+0065, U+0301]
```

Interpretation:

1. `text.length() == 5` because the emoji takes two code units.
2. `codePointCount(...) == 4` because the emoji is one code point, while the combining acute accent remains a separate code point.
3. `getBytes(StandardCharsets.UTF_8).length == 8` shows **byte length** is a fourth quantity. Do not use `length()` to predict exact data size after UTF-8 encoding.
4. `charAt(1)` returns the high surrogate, whereas `codePointAt(1)` combines it with the following low surrogate to return `0x1F600`.
5. `offsetByCodePoints(0, 2)` returns UTF-16 index `3`: the first code point `A` occupies index 0, and the second code point (the emoji) occupies indices 1 and 2.
6. The regex `\\X` in Java source creates the regex expression `\X`, meaning one **Unicode extended grapheme cluster**, so the sample string has three clusters.

The code intentionally prints **Unicode codes and counts in ASCII** rather than requiring the terminal to render emoji glyphs properly; this makes stdout easier to verify across environments.

## 6. Iterating Strings: When to Use `char`, When to Use Code Points?

### 6.1. Iterating by `char`: Only Correct When UTF-16 Units Are Needed

```java
for (int i = 0; i < text.length(); i++) {
    char unit = text.charAt(i);
    // One iteration corresponds to one UTF-16 code unit.
}
```

This is a snippet. It is appropriate for UTF-16-level tasks (buffer formatting, certain low-level algorithms), yet **it is not a loop that traverses each complete Unicode code point**. For a non-BMP emoji, the loop sees **two `char`s**.

If you use `Character.isLetter(text.charAt(i))` or single-`char` classification checks on international data, supplementary characters can be misanalyzed. `Character` provides many overloads taking `int codePoint`; choose the overload matching the unit you intend to process.

### 6.2. Iterating by Code Point with a Stream

```java
text.codePoints().forEach(cp -> {
    System.out.printf("U+%04X%n", cp);
});
```

`codePoints()` merges valid surrogate pairs into a single `int`. In the example, the line for the emoji is `U+1F600` rather than two lines `U+D83D` and `U+DE00`.

Unlike `codePoints()`, `text.chars()` returns an `IntStream` of **each `char`**. The two API names are fairly similar, but they are not interchangeable.

### 6.3. Iterating by Code Point Without Creating a Stream

```java
for (int i = 0; i < text.length(); ) {
    int codePoint = text.codePointAt(i);
    System.out.printf("U+%04X%n", codePoint);
    i += Character.charCount(codePoint);
}
```

For a **valid UTF-16** string, `charCount` returns 1 for a BMP code point and 2 for a supplementary one. Consequently, the index advances across two code units when encountering an emoji. Do not substitute `i++` in this loop: doing so would read the low surrogate again as a separate unit.

**Limitation:** a `String` in Java *can contain an isolated surrogate*. By the contract of `String.codePointAt`/`codePoints`, an unpaired surrogate can still be returned as its corresponding `int` value rather than the API automatically throwing an error or replacing it with a replacement character. If input must be valid Unicode text for a protocol or database, apply an appropriate validation/normalization step and a policy for handling invalid strings.

## 7. Safe String Slicing: `substring` Uses UTF-16 Indices

Suppose `String s = "A" + emoji + "B";` with emoji `U+1F600`. The string has:

```text
UTF-16 index:      0       1(high)  2(low)   3
Code/unit:         A       high      low      B
Code point index:  0       1         1       2
```

If you call `s.substring(1, 2)`, the result contains only the **high surrogate**, corrupting the emoji. To extract the emoji, you must slice from `1` to `3`. However, you should not hardcode that emojis always take two units when writing general slicing logic.

### Slicing Function by Code Point Index

Create the standalone program **`CodePointSliceDemo.java`**:

```java
import java.util.Locale;

public class CodePointSliceDemo {
    static String sliceByCodePoints(String text, int from, int to) {
        int count = text.codePointCount(0, text.length());
        if (from < 0 || to < from || to > count) {
            throw new IndexOutOfBoundsException("Invalid code-point range");
        }
        int begin = text.offsetByCodePoints(0, from);
        int end = text.offsetByCodePoints(begin, to - from);
        return text.substring(begin, end);
    }

    public static void main(String[] args) {
        String emoji = new String(Character.toChars(0x1F600));
        String text = "A" + emoji + "B";

        String selected = sliceByCodePoints(text, 1, 2);

        System.out.println("UTF-16 length: " + text.length());
        System.out.println("Code-point count: "
                + text.codePointCount(0, text.length()));
        System.out.println("Selected: U+"
                + Integer.toHexString(selected.codePointAt(0))
                         .toUpperCase(Locale.ROOT));
        System.out.println("Selected UTF-16 length: "
                + selected.length());

        String broken = text.substring(1, 2);
        System.out.println("Broken half is high surrogate: "
                + Character.isHighSurrogate(broken.charAt(0)));
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 CodePointSliceDemo.java
java CodePointSliceDemo
```

Stdout:

```text
UTF-16 length: 4
Code-point count: 3
Selected: U+1F600
Selected UTF-16 length: 2
Broken half is high surrogate: true
```

`sliceByCodePoints` avoids splitting a valid surrogate pair in half because it converts **code point indices** into **UTF-16 indices** using `offsetByCodePoints`. However, it **does not guarantee slicing on grapheme cluster boundaries**: taking only the letter `e` from `e + acute accent` can still leave behind the combining acute accent. To slice by "user-perceived characters", grapheme rules must also be handled.

## 8. A Code Point Is Still Not Equivalent to a Visible Character

### 8.1. Accented Letters and Combining Marks

There are at least two ways to represent the form of the letter `é`:

- **Precomposed:** `U+00E9`, one code point `é`.
- **Decomposed:** `U+0065` `U+0301`, two code points `e` + combining acute accent.

Both can render identically, yet:

```java
String precomposed = "\u00E9";
String decomposed = "e\u0301";

System.out.println(precomposed.length()); // 1
System.out.println(decomposed.length());  // 2
System.out.println(precomposed.equals(decomposed)); // false
```

**This is a difference in the Unicode code sequence**, not necessarily a difference in the visible letter. Vietnamese has many accented letters; some characters can exist in precomposed form, while text entered from different sources may use combining marks.

If a task requires comparison according to Unicode equivalence standards, you can use `java.text.Normalizer` and choose a form such as `Normalizer.Form.NFC`. However, normalization does not automatically solve all linguistic comparison issues such as case folding, synonyms, locale-specific sorting, or visually similar characters with different codes.

### 8.2. Emojis and Zero Width Joiner Clusters

Some emojis render as a single symbol yet consist of multiple code points linked by **Zero Width Joiner (ZWJ, U+200D)**. Flag emojis can use **two regional indicator symbols**. Some emojis also have skin-tone modifiers or variation selectors. Iterating with `codePoints()` still sees each component separately rather than yielding "one visible character".

The **extended grapheme cluster** concept in Unicode (segmentation rules UAX #29) is used when splitting clusters of characters that users tend to perceive as a single unit. In modern Java, the regex `\X` in `java.util.regex.Pattern` is one tool for this kind of segmentation.

### 8.3. Regex `\X`: Counting Extended Grapheme Clusters

```java
import java.util.regex.Pattern;

String text = "e\u0301";
long clusters = Pattern.compile("\\X")
        .matcher(text)
        .results()
        .count();

System.out.println(clusters); // 1
```

This is a **snippet**; the code needs to sit inside a method/class. On Java 17+, `Pattern` supports `\X`; when writing a Java string, escape it as `"\\X"` because the first backslash is for the Java literal and the second reaches the regex engine.

Do not equate a grapheme cluster with a **rendered glyph** or display width: fonts can produce ligatures, letter variants, or different presentations for multi-code-point sequences; Unicode rules are updated across versions. When building input limits or accurate cursor positioning for complex UIs, test with the actual rendering engine and real emoji/language sets, not just a single demo string.

One more note: `java.text.BreakIterator.getCharacterInstance(locale)` also performs character segmentation, though its level of support for emoji/ZWJ sequences may depend on the JDK and Unicode data. Do not assume every implementation/version returns identical boundaries for all new emojis.

## 9. Unicode Normalization with `Normalizer`: Looking Alike Does Not Mean `equals`

Standalone runnable example **`UnicodeNormalizationDemo.java`**:

```java
import java.text.Normalizer;
import java.util.regex.Pattern;

public class UnicodeNormalizationDemo {
    public static void main(String[] args) {
        String composed = "\u00E9";
        String decomposed = "e\u0301";

        System.out.println("Composed length: " + composed.length());
        System.out.println("Decomposed length: " + decomposed.length());
        System.out.println("Raw equals: " + composed.equals(decomposed));

        String normalizedA =
                Normalizer.normalize(composed, Normalizer.Form.NFC);
        String normalizedB =
                Normalizer.normalize(decomposed, Normalizer.Form.NFC);

        System.out.println("NFC equals: "
                + normalizedA.equals(normalizedB));
        System.out.println("Decomposed graphemes: "
                + Pattern.compile("\\X").matcher(decomposed)
                         .results().count());
    }
}
```

Run:

```bash
javac -encoding UTF-8 UnicodeNormalizationDemo.java
java UnicodeNormalizationDemo
```

Output:

```text
Composed length: 1
Decomposed length: 2
Raw equals: false
NFC equals: true
Decomposed graphemes: 1
```

Interpretation:

- `equals` compares strings by UTF-16 units; the precomposed and decomposed strings differ and therefore return `false`.
- `Normalizer.Form.NFC` normalizes to canonical composition; two canonically equivalent representations will compare equal.
- `Pattern.compile("\\X")` treats `e + acute accent` as one grapheme cluster in the example.
- Do not indiscriminately normalize identifiers, digital signatures, passwords, tokens, or data with exact byte contracts; define input/comparison conventions first. NFC is not a security measure replacing authentication and does not automatically eliminate all confusable characters.

## 10. When Should You Use `int` Code Point, `String`, and `char`?

| Scenario | Recommended API/type | Avoid |
| --- | --- | --- |
| Storing an ASCII character or a UTF-16 code unit | `char` | Believing `char` is always a complete character |
| Storing a Unicode code point (including outside BMP) | `int`, `Character.toChars`, `appendCodePoint` | Casting a supplementary code point down to `char` |
| Iterating over code points | `String.codePoints()` or `codePointAt` + `charCount` | `charAt(i)` with `i++` if you need to traverse each code point |
| Getting a position by code point count | `offsetByCodePoints` | Passing a code point index directly to `substring` |
| Counting characters close to user perception | Grapheme rules, `Pattern \X`, Unicode segmentation tools | Using `length()` or `codePoints().count()` as visible character count |
| Measuring UTF-8 byte count | `getBytes(StandardCharsets.UTF_8).length` | `length()` × 2 or × 4 |
| Comparing two equivalent accented representations | `Normalizer` with an agreed form | Believing visually identical rendering means `equals` is always `true` |
| Searching and sorting words linguistically | Appropriate collation/localization APIs | Raw code unit comparison for all languages |
| Calculating character width on screen | UI font/layout engine | Using code point/grapheme count as display column count |

### `StringBuilder` and `char[]`

When building a Unicode string, you can append code points safely:

```java
int point = 0x1F600;
StringBuilder sb = new StringBuilder();
sb.appendCodePoint(point);
String emoji = sb.toString();
```

Use `appendCodePoint` or `Character.toChars` instead of computing high/low surrogates manually from a code point unless you genuinely need to implement UTF-16 algorithms. Java's `StringBuilder.reverse()` handles valid surrogate pairs to avoid reversing their two halves, **yet that does not mean reversing a string by grapheme clusters**: combining marks and multi-code-point emoji sequences can still end up reversed incorrectly in terms of display meaning.

### Invalid Input and Lone Surrogates

A `String` can exist containing a high surrogate without a low surrogate or vice versa. `length`, `charAt`, and `codePointCount` still operate per their contracts; **do not infer that every Java `String` is a valid sequence of Unicode scalar values**.

When processing data from bytes, specify the charset explicitly, such as `StandardCharsets.UTF_8`, and choose a policy for detecting/replacing corrupted UTF-8 data. For integrity-sensitive data, validate at system boundaries; do not expect `codePoints()` to automatically fix lone surrogates.

## 11. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using `text.length()` as the number of user-perceived letters | Emojis are double-counted; combining marks are counted separately | Clarify whether the requirement is code units, code points, or graphemes |
| Calling `text.charAt(i)` and treating the result as a Unicode code point | May read only half of a surrogate | Use `codePointAt` or `codePoints` |
| Looping `for (i++)` with `codePointAt(i)` | Passing an emoji reads the low surrogate again | Increment `i += Character.charCount(cp)` |
| Using `substring(0, max)` to enforce "max characters" | Can split a surrogate pair or grapheme in half | Convert from code point/grapheme index to UTF-16 index before slicing |
| Using `codePointCount` as visible character count | `e + acute accent` still counts as two | Use grapheme rules for UI requirements |
| Thinking UTF-8 length equals `String.length()` | Wrong transmission/storage size | Count bytes after encoding with the chosen charset |
| Using `String.chars()` to get code points | Surrogate pairs are not merged | Use `String.codePoints()` |
| Using one `char` to store a non-BMP emoji | Lost code point or literal compilation error | Use `String` or `int` |
| Comparing raw accented text from multiple sources and seeing differences | NFC/NFD forms differ | Standardize normalization per contract |
| Thinking `Normalizer` resolves all linguistic equivalences | Case folding/collation/glyph similarity are separate problems | Use appropriate localization APIs and validation |
| Slicing on code point boundaries and assuming it is one visible character | Can split ZWJ/combining clusters | Consider extended grapheme clusters |
| Using an unpinned Java Unicode version and comparing very new emoji boundaries | Segmentation can change across Unicode/JDK versions | Pin versions and test real character sets |

## 12. Exercises and Knowledge Check

**Exercise 1.** If `String s = new String(Character.toChars(0x1F600));`, what are the values of `s.length()` and `s.codePointCount(0, s.length())`?

**Answer:** `2` UTF-16 code units, yet only `1` Unicode code point.

**Exercise 2.** What is the length of a string containing `A + emoji U+1F600 + B`, and why is `substring(1, 2)` wrong for extracting the emoji?

**Answer:** `length() == 4`. The emoji sits at code unit indices 1 and 2. `substring(1, 2)` only takes the high surrogate; you must take `substring(1, 3)` or slice via `offsetByCodePoints`.

**Exercise 3.** How many code points and how many extended grapheme clusters does `String s = "e\u0301";` have?

**Answer:** Two code points (`e` and combining acute accent), yet typically segmented into **one** extended grapheme cluster.

**Exercise 4.** Does `new String(Character.toChars(0x1F600)).chars().count()` equal `codePoints().count()`?

**Answer:** No. `chars().count() == 2` because it counts code units; `codePoints().count() == 1` because the surrogate pair is merged.

**Exercise 5.** Two strings `"\u00E9"` and `"e\u0301"` display nearly identically, yet `equals` returns `false`. What can you do if the application requires canonical equivalence?

**Answer:** Normalize both strings to a Unicode normalization form such as `Normalizer.Form.NFC` before comparing, following a consistent data policy.

**Exercise 6.** To limit a username to "20 visible characters", is `offsetByCodePoints` alone enough?

**Answer:** Not enough. It avoids splitting surrogate pairs, yet does not preserve every grapheme cluster made of combining marks or multi-code-point emojis. Grapheme segmentation rules and testing on target devices/Unicode versions are required.

**Exercise 7.** An API limits the body to a maximum of 1,024 UTF-8 bytes. Does `String.length() <= 1024` guarantee the byte length will not exceed 1,024?

**Answer:** No. UTF-8 has variable byte length, differing from the number of UTF-16 code units. You must encode in UTF-8 and measure the actual bytes, while also handling invalid UTF-16 data according to the encoding contract.

## 13. Summary

- `char` in Java is **a 16-bit UTF-16 code unit**, not always a Unicode code point or a user-perceived "letter".
- Code points outside the BMP (e.g., emoji `U+1F600`) are represented by a **surrogate pair**, occupying two `char`s.
- `String.length()`, `codePointCount`, `getBytes(UTF_8).length`, and the number of grapheme clusters are **four different quantities**.
- For code-point-level tasks, use `codePoints()`, `codePointAt`, `Character.charCount`, `offsetByCodePoints`, `Character.toChars`, or `appendCodePoint`.
- For operations on visible characters, consider **extended grapheme clusters**; Java supports regex `\X`, though real-world text still requires testing.
- With Vietnamese and multi-source data, recognize **combining marks**, **Unicode normalization**, and the limits of raw `String.equals` comparisons.
- Clarify whether you want to count **code units, code points, graphemes, or UTF-8 bytes** before designing length checks, string slicing, storage, or APIs.

Official documentation:

- [Java SE 21 — String](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html)
- [Java SE 21 — Character](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Character.html)
- [Java SE 21 — Pattern (`\X` and grapheme boundary)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/regex/Pattern.html)
- [Java SE 21 — Normalizer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/Normalizer.html)
- [Unicode UAX #29 — Text Segmentation](https://www.unicode.org/reports/tr29/)
