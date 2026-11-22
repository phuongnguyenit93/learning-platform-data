# Limitations of Slicing or Reversing Strings by `char` Index in Java

## 1. The Problem: A User-Perceived Character Does Not Necessarily Equal One `char`

In multilingual applications, slicing strings to build previews, limiting display names, reversing strings, or taking "the first n characters" easily introduces bugs if you assume **one character = one Java `char`**.

Example string:

```text
A🌍B
```

It looks like three characters: `A`, the Earth icon `🌍`, and `B`. Yet Java uses **UTF-16** in the `String` API; the character `🌍` (U+1F30D) requires **two UTF-16 code units**, so:

```text
String.length()                        = 4
String.codePointCount(...)             = 3
Visible character clusters in example  = 3
```

If you call `substring(0, 2)`, the slice retains `A` and **half of the emoji's surrogate pair**, producing an invalid UTF-16 string in the sense that the pair is no longer intact. If you use a loop swapping individual `char`s to reverse the string, you can swap high/low surrogates and corrupt non-BMP characters.

However, **moving from `char` to Unicode code points is still not enough for every UI operation**: the letter `é` can consist of `e` + combining acute accent, while an emoji like `👩‍💻` consists of multiple code points joined by ZERO WIDTH JOINER (ZWJ). Users typically treat that entire cluster as **one visible character (a grapheme cluster)**.

### Objectives

After this lesson, you will:

- Clearly distinguish **UTF-16 code unit**, **Unicode code point**, and **extended grapheme cluster**.
- Understand why `String.length()`, `charAt()`, `substring()`, and `StringBuilder.reverse()` have different limitations.
- Slice by **code point count** using `offsetByCodePoints` without splitting valid surrogate pairs.
- Slice or reverse by **visible character clusters** using `java.util.regex.Pattern` with `\X` on Java 17+.
- Know the JDK-dependent limitations of `java.text.BreakIterator` and cases involving emojis, combining marks, flags, and skin tones.
- Separate **Unicode string processing** from **visual reordering of right-to-left languages**.
- Design clear tests and storage/validation policies for localized applications.

## 2. Three Different Counting Units

| Unit | Definition | Related APIs | Used for |
| --- | --- | --- | --- |
| **UTF-16 code unit** | A 16-bit unit, Java type `char` | `length()`, `charAt(i)`, `substring(begin,end)` | Memory indices/positions in `String`, Java APIs |
| **Unicode code point** | Unicode character value from U+0000 to U+10FFFF | `codePointAt(i)`, `codePoints()`, `codePointCount(...)`, `offsetByCodePoints(...)` | Iterating Unicode characters, classifying code points, slicing without splitting surrogates |
| **Extended grapheme cluster (EGC)** | A code point sequence treated as a character unit close to user perception per Unicode UAX #29 | Regex `\X`, grapheme boundaries; `BreakIterator` in newer JDKs | UI cursors, truncating by visible characters, reversing clusters without tearing emojis apart |

Examples:

| String | UTF-16 units | Code points | Typical grapheme clusters |
| --- | ---: | ---: | ---: |
| `ABC` | 3 | 3 | 3 |
| `🌍` | 2 | 1 | 1 |
| `e◌́` (letter `e` + acute accent U+0301) | 2 | 2 | 1 |
| `👩‍💻` (woman technologist) | 5 | 3 | 1 |
| `🇻🇳` (pair of regional indicators) | 4 | 2 | 1 |
| `👍🏽` (emoji + skin tone) | 4 | 2 | 1 |

The emoji clusters in the table illustrate modern Unicode grapheme rules; fonts/renderers may draw a cluster as one shape, one cell, or multiple glyphs. **Grapheme count is not pixel count, not terminal width, and not a glyph count guaranteed to match across every device.**

### Why Does Java Have a 16-Bit `char`?

A Java `char` represents **one UTF-16 code unit**. For code points in the Basic Multilingual Plane (BMP) outside the surrogate range, one `char` is usually sufficient to represent one code point. However, for code points outside the BMP, like the emoji `🌍` U+1F30D, UTF-16 requires:

```text
U+1F30D
   ↓
high surrogate = U+D83C
low surrogate  = U+DF0D
```

The two individual code units **are not two valid emoji characters**. Retaining only the high surrogate and dropping the low surrogate can turn the output into replacement character `�` or be rejected by an encoder depending on error handling.

## 3. A `char` Index Can Land in the Middle of an Emoji

For the string `A🌍B`:

| UTF-16 index | `charAt(index)` | Role |
| ---: | --- | --- |
| 0 | U+0041 | `A` |
| 1 | U+D83C | High surrogate of `🌍` |
| 2 | U+DF0D | Low surrogate of `🌍` |
| 3 | U+0042 | `B` |

`substring(beginIndex, endIndex)` takes indices in **UTF-16 code units**, with `endIndex` exclusive. Therefore:

```java
String value = "A🌍B";
String broken = value.substring(0, 2);
```

`broken` contains `A` and the high surrogate; it does **not** hold the complete emoji. A Java `String` can hold an unpaired surrogate, so `substring` is not guaranteed to throw an exception. The issue only surfaces later when encoding, rendering, comparing, or transmitting to another system.

### Java 17+ Example Verifying by Code Point

Create the file `Utf16IndexDemo.java`:

```java
import java.util.Locale;

public class Utf16IndexDemo {
    static String points(String s) {
        return s.codePoints()
                .mapToObj(cp -> String.format(
                        Locale.ROOT, "U+%04X", cp))
                .toList().toString();
    }

    public static void main(String[] args) {
        String s = "A" + new String(Character.toChars(0x1F30D))
                + "B";

        System.out.println("utf16 length: " + s.length());
        System.out.println("code points: "
                + s.codePointCount(0, s.length()));

        for (int i = 0; i < s.length(); i++) {
            System.out.printf(Locale.ROOT,
                    "char[%d]=U+%04X%n", i, (int) s.charAt(i));
        }

        String broken = s.substring(0, 2);
        System.out.println("broken length: " + broken.length());
        System.out.println("dangling high: "
                + Character.isHighSurrogate(broken.charAt(1)));

        int safeEnd = s.offsetByCodePoints(0, 2);
        System.out.println("safe points: "
                + points(s.substring(0, safeEnd)));
        System.out.println("reverse points: "
                + points(new StringBuilder(s).reverse().toString()));
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 Utf16IndexDemo.java
java Utf16IndexDemo
```

Stdout (using Unicode codes so it does not depend on console emoji font support):

```text
utf16 length: 4
code points: 3
char[0]=U+0041
char[1]=U+D83C
char[2]=U+DF0D
char[3]=U+0042
broken length: 2
dangling high: true
safe points: [U+0041, U+1F30D]
reverse points: [U+0042, U+1F30D, U+0041]
```

Two distinct takeaways here:

1. **Slicing by `char` index can tear a surrogate pair**; `offsetByCodePoints` helps pick a boundary after a given code point count.
2. **`StringBuilder.reverse()` actually preserves valid surrogate pairs** (reversing `B🌍A` properly at the code point level). Do not claim that every reversal with `StringBuilder.reverse()` breaks emojis; the more important limitation is that it does not preserve **multi-code-point grapheme clusters**.

## 4. Using `offsetByCodePoints` to Slice by Code Point

When the business requirement is "take n Unicode code points", convert the **code point count** into a **UTF-16 offset** and then call `substring`:

```java
public static String prefixCodePoints(String s, int count) {
    if (s == null) {
        throw new NullPointerException("s");
    }
    int total = s.codePointCount(0, s.length());
    if (count < 0 || count > total) {
        throw new IllegalArgumentException("Invalid count");
    }
    int end = s.offsetByCodePoints(0, count);
    return s.substring(0, end);
}
```

This is an **illustrative method**, placed inside a Java class. For `"A🌍B"`, `prefixCodePoints(s, 2)` returns `"A🌍"` without slicing between the two surrogates.

APIs to distinguish:

- `s.length()` returns **UTF-16 code units**, not Unicode character count.
- `s.charAt(index)` returns **one `char`**, which may be half of a surrogate pair.
- `s.codePointAt(charIndex)` returns the code point starting at the given **UTF-16 index**; the index is still measured in `char`s.
- `s.codePointBefore(charIndex)` returns the code point preceding the UTF-16 position.
- `s.codePointCount(startChar, endChar)` counts code points in a range specified by **two UTF-16 indices**.
- `s.offsetByCodePoints(startChar, delta)` converts a code point offset into a valid UTF-16 index starting from an appropriate boundary.
- `s.codePoints()` returns an `IntStream` of code points (`int`); `s.chars()` returns code units (`int` widened from `char`).
- `Character.charCount(codePoint)` indicates whether a valid code point is represented by 1 or 2 UTF-16 code units.
- `StringBuilder.appendCodePoint(int)` appends a complete code point.

Do not call `codePointAt(index)` with `index` as a "code point ordinal" without converting: that parameter is still a **UTF-16 index**. Nor should you assume `offsetByCodePoints` validates that every UTF-16 string has valid surrogates; **unpaired surrogates** in a `String` can be counted as one unit each, since the API operates even on UTF-16 strings with malformed data.

### Slicing by Code Point Is Still Not Equivalent to Slicing by Visible Character

With `e` + U+0301 (combining acute accent), slicing **one code point** keeps only `e` and drops the accent. With `👩‍💻`, slicing one or two code points can produce an emoji that loses its original meaning. That is why the grapheme level is needed for UIs.

## 5. String Reversal Problem: `char[]` and `StringBuilder.reverse()` Differ

A common hand-written algorithm:

```java
static String reverseChars(String s) {
    char[] chars = s.toCharArray();
    for (int i = 0, j = chars.length - 1; i < j; i++, j--) {
        char tmp = chars[i];
        chars[i] = chars[j];
        chars[j] = tmp;
    }
    return new String(chars);
}
```

With `🌍` having UTF-16 pair `D83C DF0D`, reversing char by char turns them into `DF0D D83C`, an invalid **low-high** pair. If a string holds international text, do not use this `char[]`-swap style to reverse Unicode.

`new StringBuilder(s).reverse().toString()` is a better solution **at the code point level** because the JDK specifically handles valid surrogate pairs as a single unit when reversing. However, it **does not** guarantee preserving multi-code-point sequences representing **one grapheme**.

For example, `e\u0301` (e + combining acute) has two code points:

```text
Before:           [U+0065, U+0301]
After reverse():  [U+0301, U+0065]
```

The combining mark now precedes the base letter. With the emoji `👩‍💻` consisting of three code points:

```text
Before: [U+1F469, U+200D, U+1F4BB]
After:  [U+1F4BB, U+200D, U+1F469]
```

Surrogate pairs remain valid, yet the **internal order of components in the cluster is reversed**, altering the emoji's appearance/meaning.

### Java 17+ Example: Reverses Code Points Yet Does Not Preserve Graphemes

File `ReverseLimitsDemo.java`:

```java
import java.util.Locale;

public class ReverseLimitsDemo {
    static String points(String s) {
        return s.codePoints()
                .mapToObj(cp -> String.format(
                        Locale.ROOT, "U+%04X", cp))
                .toList().toString();
    }

    public static void main(String[] args) {
        String accent = "e\u0301";
        String technologist = new String(
                new int[] {0x1F469, 0x200D, 0x1F4BB}, 0, 3);

        System.out.println("accent: " + points(accent));
        System.out.println("accent reversed: "
                + points(new StringBuilder(accent).reverse().toString()));
        System.out.println("emoji: " + points(technologist));
        System.out.println("emoji reversed: "
                + points(new StringBuilder(technologist).reverse().toString()));
    }
}
```

```bash
javac -encoding UTF-8 ReverseLimitsDemo.java
java ReverseLimitsDemo
```

```text
accent: [U+0065, U+0301]
accent reversed: [U+0301, U+0065]
emoji: [U+1F469, U+200D, U+1F4BB]
emoji reversed: [U+1F4BB, U+200D, U+1F469]
```

**Distinguish clearly:** `StringBuilder.reverse()` does not break the structure of valid high-low surrogate pairs, yet it reverses the **code point order of a multi-code-point cluster**, so it is not a "reverse user-perceived characters" operation for general text.

## 6. Extended Grapheme Clusters: A Better Unit for UIs

The **Unicode Standard Annex #29 (UAX #29)** rules define **extended grapheme cluster** boundaries to approximate the writing units humans perceive. These clusters can include:

1. **Base letter + combining mark**: `e` + U+0301 is treated as one cluster.
2. **Regional indicator pair**: two code points forming a national flag, e.g., `🇻🇳`.
3. **Emoji + modifier**: `👍🏽` consisting of a base emoji and skin-tone modifier.
4. **Emoji ZWJ sequence**: `👩‍💻` consisting of `U+1F469` + `U+200D` + `U+1F4BB`.
5. **Certain variation selector sequences**: `U+FE0F` requesting emoji style on eligible characters.
6. **Complex script sequences**: characters and vowel signs or joiners in many scripts can form a single cluster.
7. **CRLF**: the pair `\r\n` is treated as one cluster in the grapheme algorithm.

Therefore, **counting code points** is insufficient to determine the number of "characters" in a Unicode input field. At the same time, a grapheme cluster is still not a *word*, *syllable*, *glyph*, or *UI width*.

### Regex `\X` in Java 17+

`java.util.regex.Pattern` supports the regex **`\X`** (extended grapheme cluster), including in JDK 17. In a **Java string literal**, write `"\\X"` so the regex engine receives `\` per regex syntax.

Example:

```java
Pattern pattern = Pattern.compile("\\X");
Matcher matcher = pattern.matcher(text);
while (matcher.find()) {
    String cluster = matcher.group();
    // cluster is one extended grapheme cluster per the JDK's Unicode data.
}
```

This is an **illustrative snippet**, requiring `import java.util.regex.Pattern;` and `Matcher`, along with a declared variable `text`. Although `Pattern` follows the Unicode definition, grouping of newer emojis can change when the JDK updates its Unicode data version; critical tests should run on the target runtime.

### `BreakIterator` Can Also Be Used, with Version Caveats

`java.text.BreakIterator.getCharacterInstance(locale)` is a character boundary analysis API. However, **behavior is not uniform across JDK generations**:

- **JDK 17**: do not assume all ZWJ/flag emoji sequences will always be segmented per modern extended grapheme clusters; segmentation depends on implementation and Unicode data.
- **JDK 20 and later**: the default `BreakIterator` implementation was updated to conform to **Unicode UAX #29 extended grapheme cluster** rules, under **JDK-8291660**.

Because this lesson targets **Java 17+**, the grapheme-slicing examples use `Pattern.compile("\\X")`, which is documented in Java 17. If using `BreakIterator`, test on the exact JDK/provider, especially for family, flag, skin-tone, and ZWJ emojis.

## 7. Java 17+: Counting and Locating Grapheme Boundaries with `\X`

Create the file `GraphemeCountDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class GraphemeCountDemo {
    static String codePoints(String s) {
        return s.codePoints()
                .mapToObj(cp -> String.format(
                        Locale.ROOT, "U+%04X", cp))
                .toList().toString();
    }

    public static void main(String[] args) {
        String text = new String(new int[] {
                0x0065, 0x0301, 0x0020,
                0x1F469, 0x200D, 0x1F4BB, 0x0020,
                0x1F1FB, 0x1F1F3
        }, 0, 9);

        Matcher matcher = Pattern.compile("\\X").matcher(text);
        List<String> graphemes = new ArrayList<>();
        List<Integer> endOffsets = new ArrayList<>();

        while (matcher.find()) {
            graphemes.add(codePoints(matcher.group()));
            endOffsets.add(matcher.end());
        }

        System.out.println("UTF-16 units: " + text.length());
        System.out.println("code points: "
                + text.codePointCount(0, text.length()));
        System.out.println("graphemes: " + graphemes.size());
        System.out.println("clusters: " + graphemes);
        System.out.println("end offsets: " + endOffsets);
    }
}
```

Run:

```bash
javac -encoding UTF-8 GraphemeCountDemo.java
java GraphemeCountDemo
```

Output on a JDK with aligned grapheme rules:

```text
UTF-16 units: 13
code points: 9
graphemes: 5
clusters: [[U+0065, U+0301], [U+0020], [U+1F469, U+200D, U+1F4BB], [U+0020], [U+1F1FB, U+1F1F3]]
end offsets: [2, 3, 8, 9, 13]
```

The five clusters in order are:

- `e` + acute accent (one grapheme).
- Space.
- Technologist emoji consisting of three code points.
- Space.
- Regional indicator pair representing the Vietnam flag.

Notably, `matcher.start()` and `matcher.end()` are still **UTF-16 offsets** for use with `substring`. The advantage is that boundaries are chosen **after the entire grapheme**, never in the middle of a surrogate or combining mark sequence. Do not treat these offsets as code point indices and pass them directly assuming code points—those are two different unit systems.

## 8. Slicing Strings by Purpose: Code Points or Graphemes?

The same phrase "take at most N characters" has several meanings:

| Requirement | Unit to consider | Example |
| --- | --- | --- |
| Capacity limit of a Java API in UTF-16 units | UTF-16 code units, **while avoiding splitting surrogates** | Splitting strings into chunks for a storage protocol |
| Processing a list of Unicode code points | Code point | Unicode classification algorithms |
| Creating a preview of at most N user-perceived characters | Grapheme cluster | Usernames, titles |
| Maximum byte limit over network or DB | Encoded bytes, e.g., UTF-8 | Field limited to 255 bytes |
| Horizontal width in pixels/terminal cells | Font/layout measurement from renderer | Screen line wrapping, terminal UI |
| Limit of N words | Word boundaries, not graphemes | Word-based previews |

**Do not use `String.length()` to infer UTF-8 byte count**. A non-BMP code point can be four UTF-8 bytes and two UTF-16 code units; a multi-code-point grapheme can take even more bytes.

### Safe Slicing at the Grapheme Level

Create `SafeTruncateDemo.java`:

```java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class SafeTruncateDemo {
    static String firstGraphemes(String text, int max) {
        if (text == null) {
            throw new NullPointerException("text");
        }
        if (max < 0) {
            throw new IllegalArgumentException("max must be >= 0");
        }

        Matcher matcher = Pattern.compile("\\X").matcher(text);
        int end = 0;
        int matched = 0;

        while (matched < max && matcher.find()) {
            end = matcher.end();
            matched++;
        }
        return text.substring(0, end);
    }

    public static void main(String[] args) {
        String text = "e\u0301" + new String(
                new int[] {0x1F469, 0x200D, 0x1F4BB}, 0, 3)
                + "!";
        for (int n = 0; n <= 3; n++) {
            String prefix = firstGraphemes(text, n);
            System.out.println(n + ": utf16=" + prefix.length()
                    + ", codePoints="
                    + prefix.codePointCount(0, prefix.length()));
        }
    }
}
```

```bash
javac -encoding UTF-8 SafeTruncateDemo.java
java SafeTruncateDemo
```

```text
0: utf16=0, codePoints=0
1: utf16=2, codePoints=2
2: utf16=7, codePoints=5
3: utf16=8, codePoints=6
```

At `n=1`, the code does not slice between `e` and the acute accent. At `n=2`, it keeps the entire three-code-point ZWJ emoji (five UTF-16 units) intact. The result in terms of visible characters is far more appropriate than `substring(0, n)` or code-point-only prefixes.

**Implementation note:** `firstGraphemes` returns the intact string if the cluster count is less than `max`. If you need to append `…` when truncated, separate the logic of **detecting remaining content** and **appending the ellipsis**; also decide whether the ellipsis counts toward the N limit. The `…` character itself is one code point/grapheme in normal contexts.

## 9. Reversing by Grapheme Instead of by `char` or Code Point

If the business requirement genuinely is "reverse the order of character clusters" (not handling RTL text), you can split clusters with `\X`, reverse the list, and join them back:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class ReverseGraphemeDemo {
    static String reverseGraphemes(String input) {
        Matcher matcher = Pattern.compile("\\X").matcher(input);
        List<String> graphemes = new ArrayList<>();

        while (matcher.find()) {
            graphemes.add(matcher.group());
        }
        Collections.reverse(graphemes);
        return String.join("", graphemes);
    }

    static String points(String s) {
        return s.codePoints()
                .mapToObj(cp -> String.format(
                        Locale.ROOT, "U+%04X", cp))
                .toList().toString();
    }

    public static void main(String[] args) {
        String emoji = new String(
                new int[] {0x1F469, 0x200D, 0x1F4BB}, 0, 3);
        String input = "A" + emoji + "B";

        String byCodePoint = new StringBuilder(input)
                .reverse().toString();
        String byGrapheme = reverseGraphemes(input);

        System.out.println("input: " + points(input));
        System.out.println("code-point-like reverse: "
                + points(byCodePoint));
        System.out.println("grapheme reverse: " + points(byGrapheme));
    }
}
```

```bash
javac -encoding UTF-8 ReverseGraphemeDemo.java
java ReverseGraphemeDemo
```

```text
input: [U+0041, U+1F469, U+200D, U+1F4BB, U+0042]
code-point-like reverse: [U+0042, U+1F4BB, U+200D, U+1F469, U+0041]
grapheme reverse: [U+0042, U+1F469, U+200D, U+1F4BB, U+0041]
```

The grapheme reverse result preserves the **internal order** of the emoji `👩‍💻`; it only swaps the order of the clusters `A`, the emoji, and `B`. This is something `StringBuilder.reverse()` does not guarantee for multi-code-point clusters.

However, **grapheme reversal is not the right way to build RTL (Arabic/Hebrew) interfaces**. Visual display order of bidirectional text is governed by the Unicode Bidirectional Algorithm and the layout engine, not by reversing `String`. For RTL, use appropriate text/renderer APIs and set text direction properly; do not manually reorder Unicode data.

## 10. Unicode Normalization: Two Strings Looking Alike May Not Be `equals`

The character `é` has two classic representations:

- **Precomposed:** U+00E9, one code point and one UTF-16 unit.
- **Decomposed:** U+0065 (`e`) + U+0301 (combining acute), two code points and two UTF-16 units.

Both can render identically while `String.equals` returns `false`. Slicing by `char` or code point can easily strip accents in the decomposed case; slicing by grapheme is less prone to visual corruption, yet **does not automatically normalize** character storage.

Java provides `java.text.Normalizer`:

```java
import java.text.Normalizer;

String composed = "\u00E9";
String decomposed = "e\u0301";
boolean same = composed.equals(decomposed); // false

String normalized = Normalizer.normalize(
        decomposed, Normalizer.Form.NFC);
boolean equivalent = composed.equals(normalized); // true
```

This is a snippet **inside a method**. `NFC` is canonical composition; `NFD` is canonical decomposition; `NFKC`/`NFKD` also apply compatibility equivalence and can alter semantic/visual presentation in certain cases. Do not blindly apply normalization to identifiers, passwords, digital signatures, or legal data without a defined preservation contract.

**Normalization does not replace grapheme segmentation.** Even after NFC, many ZWJ emojis, modifier sequences, and script cases still consist of multiple code points in one grapheme. A normalized string can still be sliced improperly if relying on `char` indices.

### Java 17+ Example on Normalization

File `NormalizationDemo.java`:

```java
import java.text.Normalizer;

public class NormalizationDemo {
    public static void main(String[] args) {
        String a = "\u00E9";
        String b = "e\u0301";

        System.out.println("a utf16: " + a.length());
        System.out.println("b utf16: " + b.length());
        System.out.println("raw equal: " + a.equals(b));
        System.out.println("NFC equal: "
                + a.equals(Normalizer.normalize(
                        b, Normalizer.Form.NFC)));
    }
}
```

```bash
javac -encoding UTF-8 NormalizationDemo.java
java NormalizationDemo
```

```text
a utf16: 1
b utf16: 2
raw equal: false
NFC equal: true
```

## 11. Invalid UTF-16 Strings: Unpaired Surrogates and Encoding

A Java `String` can contain a **high surrogate without a low surrogate** or vice versa. APIs like `substring` do not necessarily throw an exception when producing such a string. However, converting to UTF-8 (or other standard Unicode systems) is where **malformed input** must be handled.

For example, `StandardCharsets.UTF_8.newEncoder()` configured with `CodingErrorAction.REPORT` can **reject** unpaired surrogates rather than silently substituting characters:

```java
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class SurrogateValidationDemo {
    public static void main(String[] args) {
        String text = "A"
                + new String(Character.toChars(0x1F30D)) + "B";
        String broken = text.substring(0, 2);

        try {
            StandardCharsets.UTF_8.newEncoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .encode(CharBuffer.wrap(broken));
            System.out.println("encoded");
        } catch (CharacterCodingException ex) {
            System.out.println("unpaired surrogate rejected");
        }
    }
}
```

```bash
javac SurrogateValidationDemo.java
java SurrogateValidationDemo
```

```text
unpaired surrogate rejected
```

Some other encoding paths may **replace** the invalid segment with a replacement character or `?` depending on encoder policy, leading to data loss or hard-to-diagnose logs. Do not treat the device displaying `�` as proof that the string is valid. For APIs, logs, or persistence requiring integrity, validate/encode under an explicit policy instead of slicing strings with indices that can tear surrogates.

Additionally, **byte count** after `UTF-8` does not equal `String.length()`. When a system limits byte count (e.g., a protocol field), measure on **encoded bytes** and slice on appropriate boundaries rather than blindly slicing inside UTF-8 or UTF-16 byte sequences. Counting graphemes for UI and limiting bytes for storage are two independent problems.

## 12. Watch Out for Other Subtle Traps

### 12.1. CRLF Is Two Code Points Yet Usually One Line Boundary

A line ending in CRLF has the sequence `\r\n` (U+000D U+000A). Reversing code points can turn the order into `\n\r`; line-break processors may interpret that differently. UAX #29 treats CRLF as one grapheme cluster. Yet for **reversing lines**, the proper approach is to parse lines/line terminators intentionally, not to reverse individual graphemes across the whole string.

### 12.2. Variation Selectors and Emoji Modifiers

Some emojis use U+FE0F (variation selector-16) to request emoji presentation; many others use modifiers like U+1F3FD. `StringBuilder.reverse()` keeps surrogate pairs of non-BMP code points intact yet can still move selectors/modifiers ahead of the base character. Grapheme cluster regex helps slice on proper boundaries. When testing, inspect code point lists to see invisible characters clearly.

### 12.3. Reversing Text Is Not Changing Writing Direction

Languages like Arabic, Hebrew, and strings mixing Latin with RTL scripts follow **bidi rules**. Reversing `char`s, code points, or graphemes to "fix visual order" usually corrupts the data. Keep content in logical order and delegate visual rendering to a bidi-aware renderer; Java provides `java.text.Bidi`, and platforms provide appropriate UI text engines.

### 12.4. A Code Point Is Not Necessarily a Valid Character in Every Context

`Character.isValidCodePoint(cp)` checks the Unicode code point range, yet a value inside the code point range is **not necessarily** an assigned character or valid in every data type. Unicode noncharacters, control codes, and unpaired surrogates must be evaluated against the schema and protocol in use. Do not interpret "one code point" as "one readable letter" or "one displayable character".

### 12.5. Differences Between Unicode Versions

Grapheme segmentation rules and emoji sets are updated across Unicode releases. If an application needs consistent grapheme limits between backend and frontend, pin/document the Unicode data version and test with real product examples. The JDK, browsers, and libraries may not use the exact same data version.

## 13. API Selection Table

| Scenario | Recommended | Avoid |
| --- | --- | --- |
| Iterating UTF-16 for legacy API integration | `charAt` per explicit contract | Calling every `char` a visible character |
| Slicing first N code points | `codePointCount` + `offsetByCodePoints` | `substring(0, N)` |
| Analyzing individual code points | `codePoints()` or `codePointAt` + `Character.charCount` | Counting `char`s as code points |
| Reversing a string at code point level | `StringBuilder.reverse()` for valid surrogate pairs or rebuilding by code point | Swapping individual `char`s manually |
| Slicing N grapheme clusters | `Pattern.compile("\\X")` and `Matcher.end()` | Slicing per code point and assuming emojis stay intact |
| Reversing character clusters | Split with `\X`, reverse **the clusters**, join | `StringBuilder.reverse()` if clusters must stay intact |
| Analyzing character boundaries with `BreakIterator` | Check JDK/provider; full EGC default since JDK 20 | Assuming JDK 17 handles all ZWJ emojis properly |
| Comparing Unicode-equivalent text | Appropriate `Normalizer` + business comparison/collation rules | Manually stripping accents or dropping code points |
| Enforcing UTF-8 byte limits | Encode and measure bytes, preserving valid sequences | Using `String.length()` as byte length |
| Rendering RTL | UI/layout supporting Unicode bidi | `reverse()` to flip characters |
| Finding cursor position in user text | Grapheme boundaries + text layout engine | Arbitrary `char` indices |

## 14. Testing Checklist for Multilingual Applications

Include at least the following input groups:

1. **Simple ASCII:** `ABC`; the case where `UTF-16 units = code points = graphemes`.
2. **One supplementary code point:** `A🌍B`; test `length=4`, `codePointCount=3`, avoiding boundaries between U+D83C and U+DF0D.
3. **Combining mark:** `e\u0301`; test slicing one code point vs one grapheme, clearly differing.
4. **NFC/NFD:** precomposed `é` vs `e + U+0301`; test comparison per normalization policy.
5. **ZWJ emoji:** `👩‍💻`; test keeping the entire cluster intact when slicing/reversing.
6. **Regional indicators:** `🇻🇳`; test not splitting the flag in half.
7. **Emoji modifier:** `👍🏽`; test keeping skin tone with the base emoji.
8. **Variation selector:** string with U+FE0F; test not detaching the selector from the preceding character.
9. **CRLF:** `\r\n`; test not breaking line structure.
10. **Unpaired surrogate:** test encoder `CodingErrorAction.REPORT` or controlled replacement policy.
11. **Empty string / limit 0 / limit exceeding cluster count:** verify APIs do not crash and do not produce malformed fragments.
12. **Right-to-left languages and complex scripts:** verify with an actual renderer, not just `String` output.
13. **Differences across JDK 17, 20+ and Unicode versions:** test emoji sequences actually used by the product.

**Question to turn into tests:** does business logic limit *N UTF-16 units*, *N code points*, *N grapheme clusters*, *N bytes*, or *N pixels*? Without picking the unit, an algorithm to "slice N characters" cannot be called correct.

## 15. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| `substring(0, n)` with user-provided n as character count | Can slice inside a surrogate or grapheme | Choose the unit and compute boundaries |
| `length()` equals visible emoji count | One emoji can take multiple code units/code points | Use `codePointCount` or grapheme segmentation |
| Reversing `char[]` by swapping | Can create invalid low-high surrogates | Use at least `StringBuilder.reverse()` |
| Thinking `StringBuilder.reverse()` always reverses "characters" properly | Combining marks and ZWJ emojis can reorder internally | Reverse grapheme clusters |
| Thinking `codePoints()` is a list of graphemes | One grapheme can have multiple code points | Use `\X` or a grapheme boundary engine |
| Using `BreakIterator` on JDK 17 and assuming all emojis are one cluster | Behavior is JDK-dependent, lacking JDK 20 upgrade | Test; choose `\X`/suitable library |
| Testing only ASCII | Misses Unicode bugs | Test emojis, combining marks, flags |
| Not distinguishing precomposed/decomposed letters | `equals` differs despite identical visual appearance | Normalize intentionally |
| Slicing UTF-8 bytes by byte count without preserving code points | Produces invalid byte sequences | Encode/segment at valid boundaries |
| Reversing strings to support RTL | Wrong logical and visual order | Use a bidi renderer |
| Treating EGC as screen width | Layout does not correspond to grapheme count | Use text measurement in the UI renderer |
| Silently replacing unpaired surrogates | Data loss, hard-to-diagnose logs | REPORT encoder or explicit replacement policy |

## 16. Self-Check

1. **For `"A🌍B"`, what does `String.length()` return?** 4, because `🌍` uses two UTF-16 code units.
2. **What does `codePointCount` return?** 3, because there are `A`, `🌍`, and `B`.
3. **Is `substring(0,2)` safe?** No; it can leave a high surrogate without a low surrogate.
4. **Which Java API gets the first two code points?** `offsetByCodePoints(0,2)` and then passing the returned UTF-16 index to `substring`.
5. **Does `StringBuilder.reverse()` always corrupt valid surrogate pairs?** No; it preserves surrogate pairs when reversing.
6. **Why can `StringBuilder.reverse()` still be wrong for `e\u0301`?** It moves the combining mark before the base letter.
7. **How many UTF-16 units, code points, and typical graphemes does `👩‍💻` have?** 5 units, 3 code points, 1 grapheme.
8. **Which regex matches one extended grapheme cluster in Java 17?** `\X`, written in a Java string literal as `"\\X"`.
9. **Are `Matcher.end()` values measured in code points or UTF-16?** UTF-16 offsets, directly compatible with `substring`.
10. **Since which JDK does `BreakIterator` support full EGC per JDK-8291660?** JDK 20, in the default implementation.
11. **Does NFC replace grapheme segmentation?** No; normalization does not turn every ZWJ emoji into one code point.
12. **Should RTL text be reversed via `String` to display properly?** No; use the bidi algorithm and an appropriate renderer.
13. **If a server limits to 255 UTF-8 bytes, can you use `s.length() <= 255`?** No; you must measure byte count after encoding with the chosen encoding.
14. **Why can text that looks "identical" still have `equals=false`?** It may differ in Unicode normalization form, such as precomposed `é` vs `e + U+0301`.
15. **To reverse "visible characters" while keeping ZWJ emojis intact, what should you do?** Split into grapheme clusters and reverse the clusters, without reversing code points inside a cluster.

## References

- [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): `length`, `charAt`, `substring`, `codePoints`, `codePointCount`, and `offsetByCodePoints`.
- [Java SE 17 — StringBuilder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuilder.html): `reverse` handles valid surrogate pairs as one unit.
- [Java SE 17 — Character](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html): surrogate pairs and Unicode code points.
- [Java SE 17 — Pattern](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html): regex `\X` for extended grapheme clusters.
- [Java SE 17 — BreakIterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/BreakIterator.html): APIs for character/word/sentence boundary analysis.
- [JDK 20 Release Notes — Grapheme Support in BreakIterator (JDK-8291660)](https://www.oracle.com/java/technologies/javase/20-relnote-issues.html): default implementation updated to extended grapheme clusters.
- [Java SE 17 — Normalizer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html): NFC/NFD/NFKC/NFKD.
- [Unicode Standard Annex #29 — Unicode Text Segmentation](https://www.unicode.org/reports/tr29/): extended grapheme cluster rules, ZWJ emojis, combining marks, regional indicators.
- [Unicode Standard Annex #15 — Unicode Normalization Forms](https://www.unicode.org/reports/tr15/): canonical and compatibility normalization.
