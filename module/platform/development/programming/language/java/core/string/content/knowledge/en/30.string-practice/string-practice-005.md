# Counting Characters by `char`, Code Point, and Grapheme Cluster in Java

In Java, the question **"how many characters does a string have?"** does not have a single answer without specifying how you count. A Vietnamese accented letter can be written with one code point or multiple combining code points; an emoji can lie outside the Unicode BMP and require two **UTF-16 code units**; a multi-part emoji can be joined into **one grapheme cluster**.

This practice guides counting, comparing, and slicing strings at three levels:

1. **`char` / UTF-16 code unit**: the unit that APIs like **`String.length()`** and **`charAt()`** operate on.
2. **Unicode code point**: a Unicode scalar/code point, counted with **`codePointCount()`** or **`codePoints()`**.
3. **Display cluster (extended grapheme cluster)**: a group of code points usually treated as a single character when a user moves the cursor or selects text; can be segmented using regex **`\X`** in Java.

## 1. Foundations: `char` does not mean "one visible character"

### UTF-16 code units and `String.length()`

In Java, each **`char`** is 16 bits wide and represents **one UTF-16 code unit**. **`String.length()`** returns the number of code units in the string, not the number of UTF-8 bytes and not always the number of visible characters.

Example:

~~~java
System.out.println("ABC".length());           // 3
System.out.println("Vi\u1EC7t".length());      // 4
System.out.println("\uD83D\uDE42".length());  // 2
~~~

This code is a snippet to place inside a method, where **`Vi\u1EC7t`** equals **`Việt`** and **`\uD83D\uDE42`** equals **`🙂`**.

Why does **`🙂`** have **`length() = 2`**? Unicode code point U+1F642 lies outside the **Basic Multilingual Plane (BMP)**; UTF-16 represents it with **two consecutive `char`s**: a *high surrogate* and a *low surrogate*. Calling **`charAt(0)`** only retrieves the first half of the pair, not the entire emoji.

In modern JVMs, `String` may use **Compact Strings** to store `byte[]` more efficiently. This **does not change** the meaning of **`String.length()`**: the API still returns the number of UTF-16 code units.

### Unicode code points

A **code point** is a value defined by Unicode, for example:

- **A**: U+0041.
- **ệ**: U+1EC7.
- **🙂**: U+1F642.
- Joiner character **ZWJ**: U+200D.

A code point inside the BMP usually corresponds to one UTF-16 code unit. A code point outside the BMP uses **two** UTF-16 code units. Thus **`codePointCount`** can be smaller than **`length`**.

**`String.codePointCount(beginIndex, endIndex)`** takes **UTF-16 code unit indices**, not code point indices; its value is the number of code points within the selected UTF-16 range:

~~~java
String smile = "\uD83D\uDE42";
System.out.println(smile.length());                             // 2
System.out.println(smile.codePointCount(0, smile.length()));     // 1
System.out.println(smile.codePoints().count());                 // 1
~~~

**Note on malformed data:** for an unpaired lone surrogate, Java APIs may count it as one code point under **`codePointCount`** rules even though it is not a valid Unicode scalar value. Never assume every arbitrary `String` contains only valid surrogate pairs.

### Display clusters / grapheme clusters

An **extended grapheme cluster** is a sequence of one or more code points per Unicode segmentation rules, usually close to "one character" in a user interface. For example:

- **e + combining acute accent**: two code points, usually displayed as **é** as a single cluster.
- **👩‍💻**: **👩** + **ZWJ** + **💻**; three code points, usually **one emoji cluster**.
- **🇻🇳**: two *regional indicator* code points forming one flag cluster.
- **👍🏽**: hand emoji and skin-tone modifier forming one cluster.

**One grapheme cluster is not guaranteed to be exactly one physical glyph on screen.** Rendering also depends on fonts, shaping engines, operating systems, and Unicode/emoji versions. Counting grapheme clusters is a text-segmentation rule, not a count of rendered glyph images on screen.

## 2. Java APIs suited for each counting level

| Goal | API / approach | Unit |
| --- | --- | --- |
| Count UTF-16 code units | **`s.length()`** | `char` / code unit |
| Count code points | **`s.codePointCount(0, s.length())`** | code point |
| Iterate code points | **`s.codePoints()`** | stream of `int` values |
| Get code point at UTF-16 index | **`s.codePointAt(index)`** | code point |
| Advance `n` code points | **`s.offsetByCodePoints(index, n)`** | result is a UTF-16 index |
| Count graphemes | **`Pattern.compile("\\X").matcher(s)`** and count matches | extended grapheme cluster |
| Iterate graphemes | On each **`Matcher.find()`**, use **`group()`**, **`start()`**, **`end()`** | `String` slice / UTF-16 index pair |

In Java regex, **`\X`** represents a **Unicode extended grapheme cluster**. Because the regex is inside a Java `String` literal, you must write **`"\\X"`**, not **`"\X"`**; the latter is not a valid Java `String` escape.

Either **`Matcher.results().count()`** (Java 9+) or a **`while (matcher.find())`** loop can count **`\X`** matches. **`Pattern`** can be reused across multiple strings; create a new **`Matcher`** for each string processed. Do not share a stateful `Matcher` concurrently across multiple threads.

## 3. Complete Java 17+ practice program

Save as **`CharacterCountingDemo.java`**:

~~~java
import java.text.Normalizer;
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class CharacterCountingDemo {
    private static final Pattern GRAPHEME = Pattern.compile("\\X");

    private static void report(String label, String text) {
        int codeUnits = text.length();
        int codePoints = text.codePointCount(0, codeUnits);
        long clusters = GRAPHEME.matcher(text).results().count();

        System.out.println(label + ": units=" + codeUnits
                + ", points=" + codePoints
                + ", clusters=" + clusters);
    }

    public static void main(String[] args) {
        String precomposed = "Vi\u1EC7t";
        String decomposed = "Vie\u0323\u0302t";
        String smile = "\uD83D\uDE42";
        String zwj = "\uD83D\uDC69\u200D\uD83D\uDCBB";

        report("ASCII", "ASCII");
        report("Vietnamese NFC", precomposed);
        report("Vietnamese NFD", decomposed);
        report("Emoji", smile);
        report("Emoji ZWJ", zwj);
        report("Flag", "\uD83C\uDDFB\uD83C\uDDF3");
        report("Skin tone", "\uD83D\uDC4D\uD83C\uDFFD");
        report("CRLF", "A\r\nB");
        report("Empty", "");

        System.out.println("equal before NFC: "
                + precomposed.equals(decomposed));
        System.out.println("equal after NFC: "
                + precomposed.equals(
                        Normalizer.normalize(
                                decomposed, Normalizer.Form.NFC)));

        System.out.println("smile high surrogate: "
                + Character.isHighSurrogate(smile.charAt(0)));
        System.out.println("smile code point: U+"
                + Integer.toHexString(smile.codePointAt(0))
                        .toUpperCase(Locale.ROOT));

        int onePointEnd = zwj.offsetByCodePoints(0, 1);
        System.out.println("ZWJ first code point units: "
                + zwj.substring(0, onePointEnd).length());

        Matcher matcher = GRAPHEME.matcher(zwj);
        if (matcher.find()) {
            System.out.println("ZWJ first cluster units: "
                    + matcher.group().length());
        }
    }
}
~~~

The program uses **Unicode escapes** to represent Vietnamese data and emoji accurately, avoiding editor or terminal font/encoding dependencies. Sample labels and messages are ASCII, making console output easy to compare.

Compile and run:

~~~bash
javac -encoding UTF-8 CharacterCountingDemo.java
java CharacterCountingDemo
~~~

Sample stdout verified on a JDK supporting grapheme rules for the chosen cases:

~~~text
ASCII: units=5, points=5, clusters=5
Vietnamese NFC: units=4, points=4, clusters=4
Vietnamese NFD: units=6, points=6, clusters=4
Emoji: units=2, points=1, clusters=1
Emoji ZWJ: units=5, points=3, clusters=1
Flag: units=4, points=2, clusters=1
Skin tone: units=4, points=2, clusters=1
CRLF: units=4, points=4, clusters=3
Empty: units=0, points=0, clusters=0
equal before NFC: false
equal after NFC: true
smile high surrogate: true
smile code point: U+1F642
ZWJ first code point units: 2
ZWJ first cluster units: 5
~~~

Meaning of the three columns:

- **units** = number of UTF-16 code units, also **`String.length()`**.
- **points** = number of code points per the Java API.
- **clusters** = number of regex **`\X`** matches, according to the running JDK's Unicode rule implementation.

Results depend on the JDK's Unicode tables for newer Unicode/emoji clusters; the common examples above were verified in the test Java environment. When targeting newer emoji sets or another JDK release, re-run to confirm compatibility.

## 4. Analyzing each case in the table

### 4.1. ASCII: all three quantities are equal

**"ASCII"** has five characters: A, S, C, I, I. Each character occupies one UTF-16 code unit, is one code point, and forms one grapheme cluster on its own.

Therefore: **units=5, points=5, clusters=5**.

This case often leads developers to think **`length()` is always the character count**, because on simple ASCII data all three counts coincide. That conclusion does not hold for general Unicode.

### 4.2. Precomposed Vietnamese: mostly still one unit

**"Việt"** with precomposed **ệ** (U+1EC7) has four letters and four code points, all inside the BMP; each code point uses one UTF-16 unit. Under the chosen segmentation, each letter is one grapheme cluster.

Result: **units=4, points=4, clusters=4**.

**Do not infer** from this that all Vietnamese text always has all three counts equal. The same accented letter can be written with multiple combining code points, as in the next example.

### 4.3. Decomposed Vietnamese: multiple code points for one letter

The string **Việt** is declared as:

~~~java
String decomposed = "Vie\u0323\u0302t";
~~~

It has six code points: **V**, **i**, **e**, combining dot below, combining circumflex, and **t**. The dot below and circumflex combine with the letter `e`, so the grapheme segmenter produces four clusters.

- **units=6** because all six code points lie in the BMP.
- **points=6** because there are no surrogate pairs.
- **clusters=4** because `e` together with the two marks forms **one cluster**, not three separate clusters.

In the same program:

~~~java
String composed = "Vi\u1EC7t";
String decomposed = "Vie\u0323\u0302t";
System.out.println(composed.equals(decomposed)); // false
System.out.println(
        composed.equals(Normalizer.normalize(
                decomposed, Normalizer.Form.NFC))); // true
~~~

This is a snippet to place inside a method and import **`java.text.Normalizer`**. Java `String.equals` compares raw encoded content, so before normalization the two strings are unequal; NFC normalization converts the combining form to the equivalent precomposed form when one exists.

**Equal grapheme counts do not imply `equals` returns `true`.** If business requirements treat canonically equivalent Unicode forms as the same data, normalize before comparing or using as collection keys.

### 4.4. Single emoji: two `char`s, one code point

For **🙂** (U+1F642):

- **units=2**: a surrogate pair of two UTF-16 units.
- **points=1**: one code point.
- **clusters=1**: one grapheme cluster.

**`smile.charAt(0)`** returns the high surrogate; **`smile.codePointAt(0)`** returns U+1F642. For a valid string at the proper index, `codePointAt` combines the two `char`s of the surrogate pair to yield the complete code point.

### 4.5. ZWJ emoji: multiple code points forming one cluster

The string **👩‍💻** consists of:

1. **👩**: U+1F469, two UTF-16 units.
2. **ZWJ**: U+200D, one UTF-16 unit.
3. **💻**: U+1F4BB, two UTF-16 units.

Total: **5 units, 3 points, 1 cluster**.

This example shows that **counting by code point** is still insufficient when the requirement is "one user-perceived character." Taking only the first code point yields **👩**, not the whole **👩‍💻** cluster.

### 4.6. Flags and skin-tone emoji

**🇻🇳** consists of two non-BMP regional indicator code points, so **4 UTF-16 units**, **2 code points**, and usually **1 grapheme cluster**.

**👍🏽** consists of a hand emoji and a skin-tone modifier emoji, so **4 units**, **2 points**, and **1 cluster** in this case.

Not all emoji share the same structure. There are single-code-point emoji, emoji with variation selectors, modifiers, flags, ZWJ sequences, and longer sequences. You cannot assume "one emoji = two `char`s" or "one emoji = one code point."

### 4.7. CRLF newlines and empty strings

**"A\r\nB"** consists of A, CR, LF, B:

- **`length() = 4`**.
- **`codePointCount() = 4`**.
- **`\X`** groups CRLF into **one grapheme cluster** per segmentation rules, giving **3** clusters in total: A, CRLF, B.

CRLF is not a visible symbol, illustrating that **a grapheme cluster is a text-segmentation unit**, not necessarily one visible glyph image per cluster.

An empty string has **0** units, **0** code points, and **0** grapheme clusters. Do not call **`charAt(0)`** on an empty string.

## 5. Do not slice in the middle of a surrogate pair

A classic mistake when handling emoji:

~~~java
String smile = "\uD83D\uDE42";
String broken = smile.substring(0, 1);
~~~

**`broken`** contains only the high surrogate, an incomplete fragment of the emoji. When encoded to UTF-8, APIs may emit a replacement character for the invalid code; do not expect the original emoji to be recoverable.

If the requirement is **taking `n` code points**, use **`offsetByCodePoints`** to convert from a code point count to a UTF-16 index:

~~~java
String smile = "\uD83D\uDE42";
int end = smile.offsetByCodePoints(0, 1);
String firstPoint = smile.substring(0, end);

// end == 2; firstPoint contains the entire 🙂.
~~~

**`substring`** still accepts UTF-16 offsets; **`offsetByCodePoints`** simply computes the exact end offset by code points. This avoids splitting valid surrogate pairs, though it can still split a multi-code-point grapheme.

For example with **👩‍💻**, taking the first code point only extracts **👩** (2 UTF-16 units), leaving behind the ZWJ and 💻 emoji.

## 6. Slicing strings by grapheme cluster

If the requirement is **taking the first grapheme cluster**, use **`Matcher.find()`**:

~~~java
Pattern grapheme = Pattern.compile("\\X");
String value = "\uD83D\uDC69\u200D\uD83D\uDCBB";

Matcher matcher = grapheme.matcher(value);
if (matcher.find()) {
    String firstCluster = matcher.group();
    int begin = matcher.start();
    int end = matcher.end();

    // firstCluster is the entire 👩‍💻 sequence in this case.
    // begin == 0, end == 5 (UTF-16 offsets).
}
~~~

This is a snippet; import **`java.util.regex.Pattern`**, **`Matcher`**, and place inside a method.

**`Matcher.start()`** and **`end()`** also return **UTF-16 indices**, not code point counts. You can therefore pass those indices directly to **`substring`** to extract the entire cluster according to segmentation.

To take at most the **first `n` clusters**, loop while counting `find()` calls, capture **`end()`** of the `n`-th cluster, and slice there. Handle empty input separately so you do not assume `Matcher` finds a first cluster.

A utility method (snippet to place inside a class):

~~~java
static String takeClusters(String text, int limit) {
    if (limit < 0) {
        throw new IllegalArgumentException("limit must be >= 0");
    }
    if (limit == 0 || text.isEmpty()) {
        return "";
    }

    Matcher matcher = Pattern.compile("\\X").matcher(text);
    int end = 0;
    int taken = 0;

    while (taken < limit && matcher.find()) {
        end = matcher.end();
        taken++;
    }
    return text.substring(0, end);
}
~~~

If there are fewer than **`limit`** clusters, the loop runs to completion and returns the entire string. In frequently called code, reuse the compiled **`Pattern`** rather than compiling it on every call.

**Important limitation:** a grapheme cluster under Unicode rules / JDK version is not guaranteed to correspond to a single glyph rendered by an actual font. It is still a much better way to truncate text than `char`-based `substring` when avoiding splitting parts of a grapheme.

## 7. Which problems do `String.length`, `codePointCount`, and grapheme count serve?

| Problem | Preferred counting method | Reason |
| --- | --- | --- |
| Java APIs needing `char` indices for `substring`/`charAt` | UTF-16 unit | Most `String` indices use UTF-16 offsets |
| Logging **`char`** indices or analyzing UTF-16 code | **`length()`** | Matches the exact unit of the inspected data |
| Iterating Unicode scalars/code points of valid text | **`codePoints()`** / **`codePointCount()`** | Does not split valid surrogate pairs |
| UI limit on user-perceived characters | Grapheme cluster | Combining marks / ZWJ emoji must count together as one cluster |
| Truncating a ZWJ emoji string without breaking clusters | Regex **`\X`** `Matcher` | Avoids cutting between cluster components |
| Enforcing HTTP/file UTF-8 byte size limits | **`getBytes(UTF_8).length`** | Encoded bytes differ from all three "character" counts above |
| Comparing two ways of writing accented text | Normalize Unicode then compare content | Equal counts do not guarantee equal strings |
| Drawing glyphs in a UI | Shaping/rendering engine | One grapheme can render as multiple glyphs and depends on fonts |

None of the three counts solves every Unicode problem by itself. Choose the unit matching the data or UI requirement.

## 8. Unicode versions and Java `BreakIterator`

**`Pattern "\\X"`** is a built-in Java regex solution for **extended grapheme clusters**. It avoids external library dependencies in many exercises and works with the common Unicode examples in this lesson.

However, the Unicode/emoji rule tables implemented by the JDK can differ across versions. New emoji sequences, complex combining sequences, and new ZWJ sequences must be re-tested on your production JDK. Do not hardcode a cluster count from one example and assume every JDK segments every emoji identically.

**`BreakIterator.getCharacterInstance()`** also provides character segmentation, but you should not assume its results across all JDK versions/locales match **`Pattern "\\X"`** or always handle every ZWJ emoji sequence properly. For systems requiring strict Unicode UAX #29 compliance or the newest emoji sets, use an appropriate grapheme segmentation library such as ICU4J and test against your target dataset.

Also do not confuse **having one cluster** with *the user certainly seeing one picture*. Font support and text-shaping engines can vary across browsers and operating systems.

## 9. Performance of the three counts

**`String.length()`** directly returns the number of UTF-16 units stored in the `String`; this is a length lookup, typically constant-time.

**`codePointCount()`** must scan content to identify surrogate pairs within the requested range; cost depends on the number of UTF-16 units scanned.

**Counting graphemes with regex `\X`** runs the segmentation engine over the string; it is generally more expensive than simply reading length. If operating repeatedly on the same immutable text, consider caching the count or cluster indices rather than recomputing on every render.

Do not compare a single **`length()`** call against a single **`Matcher.find()`** and draw firm conclusions about application latency. To benchmark methods on large data:

1. Prepare inputs covering ASCII, precomposed Vietnamese, combining marks, single emoji, and ZWJ emoji with defined sample sizes and proportions.
2. Specify whether comparisons are normalized per **UTF-16 unit**, **code point**, or **grapheme**.
3. Use JMH with warm-up, multiple forks, and result consumption (`Blackhole`) so JIT does not eliminate the work.
4. Record Java version, Unicode version, JVM flags, string sizes, and units (`ns/op` or `ops/s`).
5. Also measure allocations if creating `Matcher`/streams in a tight loop is a concern for the application.

**Reuse `Pattern`** when counting many strings with the same regex. `Pattern` can be shared across threads; `Matcher` should be created per operation because it holds state during `find`.

## 10. Common mistakes

| Mistake | Why it is wrong | Fix |
| --- | --- | --- |
| **`"🙂".length()` is 1** | Non-BMP emoji needs two code units | Verify **`length=2`**, **`codePointCount=1`** |
| **`substring(0, 1)` always takes the first character** | Can cut right through a surrogate pair | Use `offsetByCodePoints` or slice by grapheme |
| **One code point is always one displayed letter** | Combining marks and ZWJ emoji combine multiple code points | Segment graphemes with **`\X`** |
| **`codePointCount(0, n)`** where `n` is a code point count | Start/end indices are UTF-16 offsets | Use **`s.length()`** as upper bound when counting the whole string |
| Typing **`"\\X"`** as **`"\X"`** | Java strings require escaping backslashes | Write **`"\\X"`** in Java source code |
| Visually identical Vietnamese strings give **`equals=false`** | Precomposed vs decomposed Unicode forms | Normalize to NFC when business rules require |
| Counting graphemes and treating CRLF as two visible letters | CRLF is segmented as one cluster despite not being a glyph | Understand a grapheme is a segmentation unit, not a glyph |
| Counting graphemes then passing cluster count as `substring` offset | `substring` uses UTF-16 offsets | Use **`Matcher.start()/end()`** or convert offsets properly |
| Cluster counts of new emoji change across JDKs | Unicode data versions / segmentation rules differ | Test specific emoji samples on the target JDK |
| Using `length` to cap upload byte size | UTF-8 bytes differ from UTF-16 units | Measure **`getBytes(UTF_8).length`** |

## 11. Reinforcement exercises

**Exercise 1: Distinguishing units**

Predict the three counts for **`"A🙂B"`**: **`String.length()`**, **`codePointCount()`**, and regex **`\X`**. Answer: **4 UTF-16 units**, **3 code points**, **3 grapheme clusters** (A, 🙂, B). Calling **`substring(0, 2)`** produces A plus the leading surrogate half of the emoji, invalid to treat as a complete two-character string.

**Exercise 2: Combining marks**

For **`"a\u0301"`** (`a` followed by combining acute accent), the unit count is **2**, code point count is **2**, yet the grapheme cluster count is **1**. Try comparing it with **`á`** U+00E1 using `equals` before and after **`Normalizer.Form.NFC`**.

**Exercise 3: Taking the first cluster of a joined emoji**

For **`"👩‍💻"`**, **`offsetByCodePoints(0, 1)`** returns the end offset after the first code point as **2** UTF-16 units, whereas one **`\X`** match gives the first cluster spanning **5** UTF-16 units. Explain why these two ways of slicing serve different requirements.

**Exercise 4: Testing real data**

Create strings containing NFC/NFD Vietnamese, flags, modifier emoji, ZWJ emoji, and CRLF. Run the program in Section 3, adding a **`report`** line for each string. Record the JDK version, all three counts, and note where unit counts differ.

**Exercise 5: 10-UI-character limit**

Write an input check enforcing at most **10 grapheme clusters** instead of **10 `char`s**, using regex **`\X`** `Matcher` as in Section 6. Test at least one ZWJ emoji sequence to ensure clusters are not split mid-sequence.

## 12. Summary

When handling Unicode in Java, always ask **which unit am I counting?**

- **`String.length()`** counts UTF-16 code units, matching `String`'s indexing model.
- **`codePointCount()`** counts Unicode code points, avoiding treating a valid surrogate pair as two code points.
- **`Pattern "\\X"`** counts extended grapheme clusters, usually better aligned with user-perceived characters, especially for Vietnamese with combining marks and ZWJ emoji.

A piece of text that looks like **one** emoji can require **multiple `char`s and multiple code points**. Choosing the right unit for counting, slicing, and testing prevents bugs that corrupt Unicode data.