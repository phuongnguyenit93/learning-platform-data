# StringBuilder.reverse(): Preserves Surrogate Pairs, Not Character Clusters

## 1. Key Points to Remember

`StringBuilder.reverse()` reverses the order of content **in place within the current builder** and returns the builder itself. By Java's contract, the method **preserves the high surrogate – low surrogate order within a valid UTF-16 surrogate pair** when reversing. As a result, emojis or supplementary Unicode characters represented by a surrogate pair do not turn into two misordered surrogates merely from calling `reverse()`.

However, preserving **surrogate pairs** is completely different from preserving **grapheme clusters** — character clusters that readers typically perceive as one character. Many grapheme clusters consist of two or more Unicode code points, such as letters with combining diacritics, emojis with ZWJ joiners, symbols with variation selectors, or flags represented by two regional indicators.

Two important cases:

~~~text
"A😀B"  -> reverse() -> "B😀A"
Emoji U+1F600 still consists of high surrogate U+D83D and low surrogate U+DE00 in order.

"a" + U+0301 + "b"
Initial code points: U+0061 U+0301 U+0062
After reverse():     U+0062 U+0301 U+0061
The acute accent may attach to letter b instead of letter a.
~~~

**Conclusion:** `reverse()` is appropriate when you want **Java's UTF-16 reversal contract**; it is not automatically suitable when a problem requires reversing by **visible character** and keeping complex emojis or combining marks intact.

## 2. UTF-16 Code Units, Unicode Code Points, and Grapheme Clusters

Before reading the code, clearly separate these three units:

| Unit | Definition | Typical Java APIs |
| --- | --- | --- |
| UTF-16 code unit | A 16-bit wide unit, which is Java's `char` | `length()`, `charAt(i)` |
| Unicode code point | A Unicode value, such as `U+0041` or `U+1F600` | `codePointAt(i)`, `codePoints()`, `appendCodePoint(cp)` |
| Extended grapheme cluster | A group of code points recognized by Unicode rules as a single character unit in text | Requires a UAX #29-compliant grapheme segmentation algorithm |

In UTF-16, Unicode code points in supplementary planes (`U+10000..U+10FFFF`) require **two** code units:

- High surrogate in `U+D800..U+DBFF`.
- Low surrogate in `U+DC00..U+DFFF`.
- The pair must be ordered **high first, low second**.

Example:

~~~java
int smile = 0x1F600;
char[] pair = Character.toChars(smile);
System.out.printf("U+%04X U+%04X%n", (int) pair[0], (int) pair[1]);
// U+D83D U+DE00
~~~

`new StringBuilder("😀").length()` equals `2` (two code units), while `codePointCount(0, length())` equals `1`. This is also typically **one** grapheme cluster.

Another example: the letter `á` can be `U+00E1`, or `U+0061 U+0301` (letter `a` plus combining acute accent). The second form has **two code points** yet still usually displays as a single character cluster. Therefore, reversing by code point is still not guaranteed to reverse by grapheme cluster.

## 3. Exact Contract of StringBuilder.reverse()

Signature:

~~~java
public StringBuilder reverse()
~~~

The method replaces the current content with the reversed sequence and **returns `this`**, allowing method chaining:

~~~java
StringBuilder sb = new StringBuilder("abc");
StringBuilder returned = sb.reverse();

System.out.println(sb);             // cba
System.out.println(returned == sb); // true
~~~

`returned == sb` is an **identity comparison of two builder references**, used here to show that `reverse()` does not return a new builder.

Guarantees and limitations:

1. **Valid surrogate pairs are treated as a single unit during reversal**. The high–low order within each pair is kept intact.
2. Code units not belonging to a valid pair are reversed according to the method's mechanism.
3. The method does not segment **extended grapheme clusters** per UAX #29.
4. **Lone** surrogates standing apart can **form a valid pair** after reversal if they were previously in low–high order. This is specified behavior, not a general Unicode repair step.
5. A `String` obtained via `toString()` before mutating the builder keeps its original content because `String` is immutable.

What matters is the **output contract**, not assumptions about internal algorithms or the backing array of a specific OpenJDK release.

### Simple Example

~~~java
StringBuilder sb = new StringBuilder("A");
sb.appendCodePoint(0x1F600).append('B');

String original = sb.toString();
sb.reverse();

System.out.printf("U+%X%n", sb.codePointAt(1)); // U+1F600
System.out.println(original.codePointCount(0, original.length())); // 3
~~~

After `reverse()`, the builder represents `B`, emoji `U+1F600`, `A`. Viewed at the UTF-16 code unit level:

~~~text
Before: [0041] [D83D] [DE00] [0042]
                 high    low
After:  [0042] [D83D] [DE00] [0041]
                 high    low
~~~

The emoji's surrogate pair **does not become** `[DE00][D83D]`. If you write your own loop reversing each `char`, you risk producing that broken low–high order.

## 4. Combining Marks: The Clear Example of a Split Grapheme

Consider the Unicode sequence:

~~~text
U+0061 U+0301 U+0062
    a   acute    b
~~~

Text renderers typically display `a + U+0301` as a single accented letter `á`. However, `StringBuilder.reverse()` only enforces surrogate rules, with no contract to keep a base letter and its combining mark together as a cluster:

~~~java
String input = "a\u0301b";
String reversed = new StringBuilder(input).reverse().toString();
~~~

`input` is the code point sequence `U+0061 U+0301 U+0062`; `reversed` is `U+0062 U+0301 U+0061`. The acute accent has moved right after `b`, so rendering can turn into `b́a`.

If the goal is to **reverse two grapheme clusters** `[a + acute]` and `[b]`, the desired order would be:

~~~text
[b] [a + U+0301]
Code points: U+0062 U+0061 U+0301
~~~

This difference shows that reversing individual **code points** is still not enough; you need **cluster boundaries** to keep the internal structure of each cluster intact.

### Does NFC Normalization Solve It?

`java.text.Normalizer` with `NFC` can combine `a + acute` into a single precomposed code point `U+00E1`. That makes **this particular example** easier to reverse. However, NFC does not turn every ZWJ emoji, variation selector, or other cluster into one code point. **Normalization** and **grapheme segmentation** are two separate problems; NFC does not turn `reverse()` into a valid cluster reversal algorithm for all Unicode text.

## 5. ZWJ-Joined Emojis: Surrogates Stay Intact, Emoji Can Still Change

The **woman technologist** emoji can be encoded as the sequence:

~~~text
U+1F469  WOMAN
U+200D   ZERO WIDTH JOINER (ZWJ)
U+1F4BB  PERSONAL COMPUTER
~~~

Both outer code points are supplementary, so each is stored as a **surrogate pair**. On supporting platforms, the three code points can render as one combined emoji.

~~~java
String womanTechnologist = new StringBuilder()
        .appendCodePoint(0x1F469)
        .appendCodePoint(0x200D)
        .appendCodePoint(0x1F4BB)
        .toString();

String reversed = new StringBuilder(womanTechnologist)
        .reverse()
        .toString();
~~~

After reversal, the sequence is:

~~~text
U+1F4BB U+200D U+1F469
~~~

The surrogate pairs inside U+1F469 and U+1F4BB remain valid, yet **the order of components in the emoji cluster has changed**. The screen may display a different cluster or render them separately, depending on the text shaper and font. `reverse()` **does not** treat the entire ZWJ emoji cluster as a single element to keep together.

## 6. Variation Selectors and Flags

**Variation selector:** The sequence `U+2764 U+FE0F` contains a heart symbol plus VARIATION SELECTOR-16. After reversal:

~~~text
Before: U+2764 U+FE0F
After:  U+FE0F U+2764
~~~

The selector precedes the base instead of following it, so its visual rendering can change. `U+FE0F` is not a surrogate pair and is not kept attached to its base by `reverse()`'s contract.

**Flags via regional indicators:** For example, the Vietnam flag has two code points in order:

~~~text
Before: U+1F1FB U+1F1F3
After:  U+1F1F3 U+1F1FB
~~~

Each supplementary regional indicator remains validly UTF-16 encoded, yet the pair **is no longer in the same order**. Consequently, the flag meaning and visual rendering are not preserved.

Similar phenomena can involve emoji modifiers, stacked combining marks, or script-specific shaping structures. Test suites using only ASCII or single-code-point emojis often miss cluster-level bugs.

## 7. Lone Surrogates: A Special Case You Must Understand

Java `String` and `StringBuilder` can hold an isolated surrogate `char`. For example, a string intentionally containing two code units in **low first, high second** order:

~~~java
char low = '\uDE00';
char high = '\uD83D';
String malformed = new String(new char[] {low, high});

String after = new StringBuilder(malformed).reverse().toString();
~~~

Before reversing:

~~~text
U+DE00 U+D83D  // low then high: does not form a valid pair
~~~

After reversing:

~~~text
U+D83D U+DE00  // high then low: valid pair, code point U+1F600
~~~

This illustrates an interesting detail: `reverse()` can turn two previously **unpaired** surrogates into **a valid pair**. Reversal is not guaranteed to be a permutation that preserves every code point grouping on malformed UTF-16 data.

As a consequence, you should not claim that calling `reverse()` **twice** always restores the exact original code unit sequence for arbitrary data containing lone surrogates. Once a pair forms on the first reversal, the second reversal can preserve that pair under the surrogate-pair rule instead of restoring the old malformed layout.

If data must conform to Unicode scalar values, check/reject/replace lone surrogates with an explicit policy. `reverse()` is not a repair API for corrupted UTF-16.

## 8. Complete Java 17+ Program and Verified Output

The program below prints code points and code units in `U+XXXX` form for objective verification, independent of fonts or console emoji support.

Save as **`ReverseUnicodeDemo.java`**:

~~~java
import java.util.stream.Collectors;

public class ReverseUnicodeDemo {
    private static String cps(String s) {
        return s.codePoints()
                .mapToObj(cp -> String.format("U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    private static String units(String s) {
        StringBuilder result = new StringBuilder();
        for (int i = 0; i < s.length(); i++) {
            if (i > 0) result.append(' ');
            result.append(String.format("U+%04X", (int) s.charAt(i)));
        }
        return result.toString();
    }

    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder("A")
                .appendCodePoint(0x1F600)
                .append('B');
        String original = builder.toString();
        StringBuilder returned = builder.reverse();
        System.out.println("sameBuilder=" + (returned == builder));
        System.out.println("original=" + cps(original));
        System.out.println("reversed=" + cps(builder.toString()));
        System.out.println("reversedUnits=" + units(builder.toString()));
        System.out.println("originalStill=" + cps(original));

        String accent = "a\u0301b";
        System.out.println("accentBefore=" + cps(accent));
        System.out.println("accentAfter=" + cps(new StringBuilder(accent).reverse().toString()));

        String womanTechnologist = new StringBuilder()
                .appendCodePoint(0x1F469)
                .appendCodePoint(0x200D)
                .appendCodePoint(0x1F4BB).toString();
        System.out.println("zwjBefore=" + cps(womanTechnologist));
        System.out.println("zwjAfter=" + cps(new StringBuilder(womanTechnologist).reverse().toString()));

        String heart = "\u2764\uFE0F";
        System.out.println("heartAfter=" + cps(new StringBuilder(heart).reverse().toString()));

        String flag = new StringBuilder()
                .appendCodePoint(0x1F1FB)
                .appendCodePoint(0x1F1F3).toString();
        System.out.println("flagBefore=" + cps(flag));
        System.out.println("flagAfter=" + cps(new StringBuilder(flag).reverse().toString()));

        String malformed = new String(new char[]{'\uDE00', '\uD83D'});
        System.out.println("malformedUnits=" + units(malformed));
        System.out.println("malformedReversed=" + cps(
                new StringBuilder(malformed).reverse().toString()));
    }
}
~~~

Compile/run commands:

~~~bash
javac --release 17 -encoding UTF-8 ReverseUnicodeDemo.java
java ReverseUnicodeDemo
~~~

`stdout` directly verified by the compiler/JVM:

~~~text
sameBuilder=true
original=U+0041 U+1F600 U+0042
reversed=U+0042 U+1F600 U+0041
reversedUnits=U+0042 U+D83D U+DE00 U+0041
originalStill=U+0041 U+1F600 U+0042
accentBefore=U+0061 U+0301 U+0062
accentAfter=U+0062 U+0301 U+0061
zwjBefore=U+1F469 U+200D U+1F4BB
zwjAfter=U+1F4BB U+200D U+1F469
heartAfter=U+FE0F U+2764
flagBefore=U+1F1FB U+1F1F3
flagAfter=U+1F1F3 U+1F1FB
malformedUnits=U+DE00 U+D83D
malformedReversed=U+1F600
~~~

**Reading the output:**

- `sameBuilder=true`: `reverse` mutates in place and returns `this`.
- `reversedUnits`: the emoji's surrogate pair stays `D83D DE00`, not flipped to `DE00 D83D`.
- `originalStill`: the `String` created earlier still keeps its original content.
- `accentAfter`: the combining mark shifted position between letters.
- `zwjAfter`: the order within the ZWJ emoji sequence was reversed.
- `heartAfter` and `flagAfter`: the variation selector and regional indicators were reversed in order.
- `malformedReversed`: two lone surrogates became a valid supplementary code point.

Thus, thorough testing needs to inspect **code points** and sometimes **UTF-16 code units**, not just visually compare rendered output.

## 9. Does Manual Reversal by Code Point Solve It?

A better solution than **naive `char` reversal** when working with Unicode code points is reading `String.codePoints()` and calling `appendCodePoint()` in reverse order:

~~~java
static String reverseCodePoints(String input) {
    int[] points = input.codePoints().toArray();
    StringBuilder result = new StringBuilder(input.length());

    for (int i = points.length - 1; i >= 0; i--) {
        result.appendCodePoint(points[i]);
    }
    return result.toString();
}
~~~

This is an **illustrative method** to place inside a Java class; the input is assumed non-null.

It preserves each valid supplementary code point, yet still **reverses** combining marks, ZWJs, variation selectors, and each regional indicator individually. `reverseCodePoints` is **not** a grapheme-cluster-preserving reversal algorithm.

For invalid UTF-16 data, `String.codePoints()` can also emit a lone surrogate as a separate `int` value; `appendCodePoint` does not automatically enforce a policy stripping all lone surrogates. If canonical Unicode scalar values are required, validate inputs separately.

For simple requirements that do not need grapheme awareness, use `new StringBuilder(input).reverse().toString()` instead of writing `charAt` reversal logic that easily breaks surrogates.

## 10. What Must Be Done to Reverse by Character Cluster?

If a specification requires reversing **characters as perceived by readers**, you must **segment extended grapheme clusters first, reverse the order of the clusters afterward**, and **keep the order of code points inside each cluster unchanged**.

Logical example:

~~~text
Input:
[a U+0301] [b] [woman U+200D laptop]

Grapheme segmentation:
cluster 1 = a + acute accent
cluster 2 = b
cluster 3 = emoji woman-ZWJ-laptop

Reverse cluster order:
[woman U+200D laptop] [b] [a U+0301]
~~~

At the design level, the algorithm consists of:

1. Choosing a grapheme segmenter appropriate for the Unicode version and real-world language/data.
2. Obtaining `[start,end)` ranges in **UTF-16 indices** or substrings representing each cluster.
3. Reversing **the order of the ranges**, preserving the code unit sequence inside each range.
4. Joining the ranges with `StringBuilder.append` and returning `toString()`.
5. Testing with base+combining marks, ZWJ emojis, flags, variation selectors, and multilingual data.

In Java, `java.text.BreakIterator.getCharacterInstance(...)` provides character boundary detection, though its support for **complex extended grapheme clusters**, especially newer emojis and Unicode rules, must be verified against the **JDK version**. For strict UAX #29 compliance, consider a dedicated Unicode segmentation library such as ICU4J at an appropriate version; do not assume every "character boundary" tool handles all emojis identically.

**Important:** reversing by grapheme cluster is also not necessarily equivalent to *reversing visual rendering on screen*. RTL/LTR text, the Unicode bidirectional algorithm (bidi), and contextual shaping require support from the typesetting system. To display text in the right reading direction, usually adjust layout/text direction rather than calling `reverse()` on the logical string.

## 11. Common Mistakes

1. **Thinking `char` is a complete Unicode character.** A supplementary code point takes two `char`s.
2. **Writing a loop reversing each `charAt` from end to start.** Can split a valid surrogate pair into broken low–high order.
3. **Thinking preserving surrogate pairs keeps every emoji intact.** Many emojis consist of multiple code points.
4. **Thinking `reverse()` preserves combining marks.** `a + U+0301` can move the accent onto a different letter.
5. **Thinking `String.codePoints()` is grapheme segmentation.** One cluster can contain multiple code points.
6. **Thinking NFC turns every character cluster into one code point.** Many ZWJ/variation selector emojis remain multi-code-point.
7. **Judging output visually in the console.** Fonts and rendering vary; print `U+XXXX` during QA.
8. **Ignoring lone surrogates.** `reverse()` can form new pairs from malformed input; double reversal is not guaranteed to restore the original malformed sequence.
9. **Thinking `reverse()` creates a new builder.** It mutates the receiver builder itself; capture a `String` before modifying if the original value is needed.
10. **Using `reverse()` to fix RTL display direction.** Logical order, bidi, and grapheme order are distinct concepts.
11. **Skipping JDK-specific evaluation of the segmenter.** Unicode data/implementations change across versions; test with real application data.

## 12. Self-Check Exercises

**Question 1.** Does `reverse()` turn the surrogate pair of `U+1F600` into low–high order?

**Answer:** no. Valid pairs preserve high–low order.

**Question 2.** What does the sequence `U+0061 U+0301 U+0062` become after `reverse()`?

**Answer:** `U+0062 U+0301 U+0061`; the acute accent changes position relative to `a`.

**Question 3.** Is `U+1F469 U+200D U+1F4BB` guaranteed to remain the same unified emoji after `reverse()`?

**Answer:** no. The result reverses order to `U+1F4BB U+200D U+1F469`.

**Question 4.** Why is reversing by code point still insufficient to reverse by "visible character"?

**Answer:** a grapheme cluster can contain multiple code points. Reversing code point by code point breaks cluster structure.

**Question 5.** Should you use `new StringBuilder(text).reverse().toString()` for an application that must preserve Vietnamese combining diacritics and complex emojis?

**Answer:** not by default. You must segment and reverse by grapheme cluster according to application requirements.

**Question 6.** What can low surrogate followed by high surrogate turn into after reverse?

**Answer:** a valid high–low pair; therefore reverse must not be treated as an always-reversible transformation on malformed UTF-16 data.

**Question 7.** If you need to change the display direction of an Arabic text segment, should you reverse the `String` content?

**Answer:** normally no. Use proper layout / Unicode bidi mechanisms instead of mutating logical order with `reverse()`.

## 13. Official References

- [Java SE 17 — StringBuilder.reverse()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuilder.html#reverse()): reversal contract, surrogate pair preservation, and pair formation from lone surrogates.
- [Java SE 17 — Character](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html): UTF-16, high/low surrogates, `toChars`, `charCount`, and code points.
- [Java SE 17 — String.codePoints()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#codePoints()): reading code point sequences and lone surrogate cases.
- [Unicode Standard Annex #29 — Unicode Text Segmentation](https://www.unicode.org/reports/tr29/): extended grapheme cluster segmentation rules.
- [Unicode Technical Standard #51 — Unicode Emoji](https://www.unicode.org/reports/tr51/): emoji ZWJ sequences, variation selectors, emoji modifiers, and regional indicators.

**Key takeaway:** `StringBuilder.reverse()` preserves valid **UTF-16 surrogate pair** structure, yet knows nothing about **grapheme cluster** boundaries. To reverse "user-perceived characters", segment clusters using appropriate Unicode rules and reverse **each cluster as a whole**.
