# Distinguishing Code Units, Code Points, and Grapheme Clusters

In Java, the word "character" can refer to three different levels: **UTF-16 code units**, **Unicode code points**, and **grapheme clusters**. For the letter `A`, all three counts are 1. For emojis, letters with combining marks, or flags, they can differ. This lesson builds a conceptual map so you choose the right unit from the start; later lessons dive deeper into `String` indexing, surrogate pairs, Vietnamese text, and code point operations.

## 1. Three Layers of the Same Text

| Layer | What Is It Exactly? | Corresponding Tools in Java | When Is It Needed? |
| --- | --- | --- | --- |
| **UTF-16 code unit** | A 16-bit value in a UTF-16 code sequence | `char`, `String.length()`, `charAt()`, `substring()` indices | Interfacing with string APIs or offsets |
| **Unicode code point** | A code value from `U+0000` to `U+10FFFF` | `int`, `codePointAt()`, `codePoints()`, `codePointCount()` | Classifying, iterating over, or processing individual code points |
| **Extended grapheme cluster** | One or more code points grouped according to Unicode segmentation rules | Regex `\\X` and `Matcher` | Slicing text by clusters that users typically perceive as a single character |

A `char` is **one code unit** and does not guarantee representing a full code point. A code point outside the BMP requires **two consecutive code units** (a surrogate pair). A grapheme cluster can contain **multiple code points**, even if each code point is read correctly. Conversely, the number of graphemes is not the number of glyphs or the display width in pixels: fonts and the text rendering system determine the final visual shape.

Unicode data reserves code points for surrogates (`U+D800`–`U+DFFF`), but each individual value is not a Unicode scalar value. Java can still hold unpaired surrogates in a `String`; therefore, Java's code point counting is not a validation check for well-formed Unicode text.

## 2. Looking at Some Examples

| Text sequence | UTF-16 units | Code points | Extended grapheme clusters | Reason |
| --- | ---: | ---: | ---: | --- |
| `A` | 1 | 1 | 1 | A standard BMP character |
| `😊` (`U+1F60A`) | 2 | 1 | 1 | A non-BMP code point with a surrogate pair |
| `é` (`U+00E9`) | 1 | 1 | 1 | Precomposed character |
| `e\u0301` | 2 | 2 | 1 | Base letter and combining mark |
| `🇻🇳` | 4 | 2 | 1 | Two regional indicators |
| `👩‍💻` | 5 | 3 | 1 | Two emojis joined by `U+200D` (ZWJ) |

The table describes **specific sample sequences** under extended grapheme cluster rules; the numbers are not a formula for every emoji. New emojis or segmentation rules across versions may require testing on the actual JDK.

The two strings `"\u00E9"` and `"e\u0301"` may look like the same letter "é" but have different code unit sequences. `String.equals()` does not automatically normalize Unicode. If business logic requires comparison by canonical equivalence, consider `java.text.Normalizer`, such as NFC, with a consistent policy for inputs. Normalization does not turn every grapheme cluster into a single code point.

## 3. Java API Contracts Before Choosing How to Count

- `String.length()` returns the **number of UTF-16 code units**; the positions in `charAt(index)` and `substring(begin, end)` are also measured in UTF-16.
- `codePointCount(0, s.length())` counts the code points recognized by Java APIs when scanning the UTF-16 sequence; unpaired surrogates are still counted as individual units.
- `s.codePoints()` gives an `int` stream of code points, combining valid surrogate pairs; `s.chars()` gives a stream of code units.
- `Pattern.compile("\\X")` matches each extended grapheme cluster in Java regex; `Matcher.start()` and `Matcher.end()` return **UTF-16 offsets**, which can be used as `substring` boundaries.
- `s.getBytes(StandardCharsets.UTF_8).length` is the number of **bytes after encoding**, not any of the three counts above.

Distinguish "length" from "position": the argument to `codePointAt(2)` is a **UTF-16 offset**, not "the third code point". If you need to convert a code point index to a UTF-16 offset, use `offsetByCodePoints`. If you need to slice by display characters, code point boundaries are not enough: you must perform grapheme segmentation.

## 4. Program Comparing the Three Units

Save as `UnicodeLevelsOverview.java` (JDK 17+):

~~~java
import java.util.regex.Pattern;

public class UnicodeLevelsOverview {
    private static final Pattern CLUSTERS = Pattern.compile("\\X");

    private static void show(String label, String text) {
        int units = text.length();
        int points = text.codePointCount(0, units);
        long clusters = CLUSTERS.matcher(text).results().count();
        System.out.printf("%s: units=%d, points=%d, clusters=%d%n",
                label, units, points, clusters);
    }

    public static void main(String[] args) {
        show("A", "A");
        show("smile", "\uD83D\uDE0A");
        show("composed", "\u00E9");
        show("decomposed", "e\u0301");
        show("flag", "\uD83C\uDDFB\uD83C\uDDF3");
    }
}
~~~

~~~bash
javac -encoding UTF-8 UnicodeLevelsOverview.java
java UnicodeLevelsOverview
~~~

Expected output with segmentation rules supporting the sample sequences:

~~~text
A: units=1, points=1, clusters=1
smile: units=2, points=1, clusters=1
composed: units=1, points=1, clusters=1
decomposed: units=2, points=2, clusters=1
flag: units=4, points=2, clusters=1
~~~

In `smile`, the difference occurs **between code units and code points**. In `decomposed`, two code points are grouped into **one grapheme cluster**. In `flag`, both mechanisms appear together: two non-BMP code points become four UTF-16 units, yet segmentation rules group them into one cluster.

## 5. Choose the Unit Based on Requirements, Not Visual Shape

If an API requires an offset to call `substring`, use **UTF-16 offsets**. If the problem requires inspecting each Unicode value, use **code points** while accounting for unpaired surrogates. If an input field limits text to "at most 20 user-perceived characters", use **grapheme clusters**, with a consistent Unicode/version policy on both client and server. If storing a payload limited to 255 bytes, you must **encode with the exact charset and then count bytes**. On-screen box width still requires UI text-measuring tools.

An application can enforce both a maximum grapheme count and a maximum byte size at the same time. Using `length()` for both will be wrong for many multilingual texts.

### Self-Check

For `String s = "A\uD83D\uDE0Ae\u0301";`, predict the three counts. Answer: **5 UTF-16 units**, **4 code points**, **3 grapheme clusters** (A, 😊, e + acute accent). `s.substring(1, 2)` takes only the emoji's high surrogate and breaks the pair. `s.substring(1, 3)` extracts the whole emoji, yet a code-point-based slice can still split a letter from its combining mark. Choosing boundaries always depends on the unit the requirement actually refers to.

Subsequent lessons will clarify UTF-16 indexing, BMP and surrogate pairs, Vietnamese normalization, malformed data, the `Character` API, file charsets, and policies for display-character operations.