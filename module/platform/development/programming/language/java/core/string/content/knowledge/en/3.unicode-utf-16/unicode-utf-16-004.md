# Length of Vietnamese Text, Combining Marks, and Emojis in Java

## 1. Why Is Counting Characters Hard?

When a user enters **“Việt”**, **“ắ”**, **“😊”**, or **“👩‍💻”**, each visual form seems to consist of clear letters or icons. However, a string can be measured in several different units. In Java, calling **String.length()** does not mean “counting how many letters the user sees”.

For example:

- The letter **“ắ”** precomposed as Unicode U+1EAF has **1 UTF-16 code unit**, **1 code point**, and **1 grapheme cluster**.
- A visually similar letter built from **a + breve + acute** (**a\u0306\u0301**) has **3 code units**, **3 code points**, yet is still **1 grapheme cluster**.
- The emoji **“😊”** consists of **1 code point** but requires **2 UTF-16 code units**.
- The emoji **“👩‍💻”** consists of **3 code points** joined into **1 icon**; in Java, this string is **5 UTF-16 code units** long.

Therefore, before limiting a username, truncating text, positioning a cursor, or measuring byte size, you must determine **which unit “length” refers to**.

## 2. Four Units to Distinguish

| Unit | Explanation | How to measure in Java | When to use? |
| --- | --- | --- | --- |
| **UTF-16 code unit** | A 16-bit unit in the Java string interface | **s.length()**; indices of **charAt()**, **substring()** | API compatibility, obtaining UTF-16 indices |
| **Unicode code point** | A Unicode code value, e.g., U+1F60A | **s.codePointCount(0, s.length())** or **s.codePoints().count()** | Iterating over/inspecting Unicode values |
| **Extended grapheme cluster** | A cluster of code points typically perceived by users as one character | Regex **\\X** or a Unicode segmentation library | Limiting displayed character count, slicing close to user input behavior |
| **Encoded bytes** | Number of bytes of the string in a specified charset | **s.getBytes(StandardCharsets.UTF_8).length** | Payload size, files, storage limits |

**A UTF-16 code unit is not a UTF-8 byte.** One Java **char** holds one UTF-16 code unit; for characters outside the Basic Multilingual Plane (BMP), a code point must use **two chars**, forming a *surrogate pair*. Conversely, a grapheme can contain multiple code points, such as a letter with combining marks or a combined emoji.

Since Java 9, the String implementation may use *compact strings* to optimize memory. That **does not change** the rules of APIs calculated in UTF-16 code units. Do not infer the physical object size of a String from **length()**.

### Illustrative Value Table

The examples below are concrete strings, with Vietnamese diacritics in the NFC column using their precomposed forms:

| String | UTF-16 units | Code points | Grapheme clusters | UTF-8 bytes |
| --- | ---: | ---: | ---: | ---: |
| **“Việt”** (NFC) | 4 | 4 | 4 | 6 |
| **“Việt”** (NFD: **ệ** decomposed into **e + dot below + circumflex**) | 6 | 6 | 4 | 8 |
| **“ắ”** (NFC) | 1 | 1 | 1 | 3 |
| **“a\u0306\u0301”** (NFD; a + two combining marks) | 3 | 3 | 1 | 5 |
| **“😊”** | 2 | 1 | 1 | 4 |
| **“👍🏽”** (thumbs up + skin tone) | 4 | 2 | 1 | 8 |
| **“👩‍💻”** (woman + ZWJ + laptop) | 5 | 3 | 1 | 11 |
| **“🇻🇳”** (two regional indicators) | 4 | 2 | 1 | 8 |

The grapheme counts in the table follow Unicode's **extended grapheme cluster** rules applied to the listed combinations. The Unicode data bundle in a specific JDK or library can affect recognition of newer emojis introduced after the supported version.

## 3. Vietnamese: Precomposed Marks and Combining Marks

### 3.1. Two Encodings That Can Look Identical

An accented Vietnamese letter is sometimes **one precomposed code point**, and sometimes **a base letter plus combining marks**.

For the letter **“ắ”**:

- Precomposed NFC form: **U+1EAF** — LATIN SMALL LETTER A WITH BREVE AND ACUTE.
- Decomposed NFD form: **U+0061** (a) + **U+0306** (COMBINING BREVE) + **U+0301** (COMBINING ACUTE).

Both are usually rendered as the same letter **ắ**. However:

~~~java
String composed = "\u1EAF";
String decomposed = "a\u0306\u0301";

System.out.println(composed.length());        // 1
System.out.println(decomposed.length());      // 3
System.out.println(composed.equals(decomposed)); // false
~~~

This is an **illustrative code snippet** to place inside a method. The **equals()** operation compares content by code units and does not automatically recognize that two encodings are canonically equivalent in Unicode.

In Vietnamese text, letters with stacked marks such as **ắ, ậ, ệ, ỡ, ự** can have precomposed and decomposed forms. For the word **“Việt”**, the NFC string has 4 code points; when converted to NFD, **ệ** becomes **e + dot below (U+0323) + circumflex (U+0302)**, bringing the total to 6 code points. The number of letters perceived by the reader remains 4.

Diacritics may look slightly different depending on the font, text rendering engine, and mark-positioning rules; visual appearance alone is not a way to verify Unicode content.

### 3.2. Unicode Normalization

The **java.text.Normalizer** class provides well-defined normalization operations:

- **NFC** (*Normalization Form C*): applies canonical decomposition followed by canonical composition, representing canonically equivalent strings in composed form when possible.
- **NFD** (*Normalization Form D*): decomposes characters that have a canonical decomposition into base components and combining marks, while ordering canonical combining marks according to Unicode rules.
- **NFKC/NFKD**: also performs compatibility normalization, which can transform differences that carry presentation or compatibility distinctions. Use only when the task genuinely requires it.

Example:

~~~java
import java.text.Normalizer;

String left = "\u1EAF";
String right = "a\u0306\u0301";

String normalizedLeft = Normalizer.normalize(left, Normalizer.Form.NFC);
String normalizedRight = Normalizer.normalize(right, Normalizer.Form.NFC);
System.out.println(normalizedLeft.equals(normalizedRight)); // true
~~~

**NFC does not strip Vietnamese accents.** Nor is normalization a Vietnamese accent-stripping operation (*transliteration*). If accent-insensitive comparison or search is needed, you must design dedicated business logic because deleting combining marks can lose information and does not handle every letter (for example, **đ** does not automatically become **d** via NFD alone).

**Do not normalize arbitrarily** on digital signatures, resource names requiring exact byte comparison, data that must preserve its original form, or API contracts with specific rules. If business logic chooses to normalize, do it consistently at input, storage, and comparison boundaries.

## 4. Emojis and Surrogate Pairs

### 4.1. An Emoji with One Code Point but Two Code Units

The emoji **“😊”** is code point **U+1F60A**, outside the BMP. In UTF-16, it is encoded by the surrogate pair **U+D83D U+DE0A**:

~~~java
String emoji = "😊";

System.out.println(emoji.length());                           // 2
System.out.println(emoji.codePointCount(0, emoji.length()));  // 1
System.out.println(Character.isHighSurrogate(emoji.charAt(0))); // true
System.out.println(Character.isLowSurrogate(emoji.charAt(1)));  // true
System.out.printf("U+%X%n", emoji.codePointAt(0));              // U+1F60A
~~~

Each statement above works when placed inside a Java method. **charAt(0)** returns the first half of the surrogate pair, **not the complete emoji**. Slicing **emoji.substring(0, 1)** creates a String containing only an unpaired high surrogate, which can cause rendering or transcoding errors.

To step through each code point, you can use **codePoints()**, **codePointAt(...)**, or **offsetByCodePoints(...)**. Still, stepping by code points does not guarantee you will not split an emoji composed of multiple joined code points.

### 4.2. Modifiers, ZWJ Joiners, and Flags

Some emojis consist of **multiple code points**:

- **“👍🏽”** consists of U+1F44D (thumbs up) and U+1F3FD (skin tone modifier). Two code points, four UTF-16 code units, usually displayed as one symbol.
- **“👩‍💻”** consists of U+1F469 (woman), U+200D (ZERO WIDTH JOINER, ZWJ), and U+1F4BB (laptop). Three code points, yet one extended grapheme cluster under the relevant rules.
- **“🇻🇳”** is a pair of regional indicators U+1F1FB and U+1F1F3. Two code points, four UTF-16 code units, usually displayed as one flag.
- Some emoji sequences also use variation selectors such as U+FE0F to request emoji presentation. A variation selector is also a code point and contributes to the length.

Therefore, even **codePointCount()** can return a larger result than the number of icons the user sees. Actual emoji appearance depends on font support, platform, and Unicode data version; a valid cluster may render as separate images if the environment does not support joining.

## 5. Grapheme Cluster: The Unit Closest to User Characters

Unicode Standard Annex #29 defines *grapheme cluster boundaries* rules. An **extended grapheme cluster** can consist of a base letter and combining marks, a base emoji plus a modifier, a ZWJ sequence, or a pair of regional indicators.

Java 17 supports the regex construct **\\X**, which matches one extended grapheme cluster according to the Unicode data used by the JDK. For example:

~~~java
import java.util.regex.Pattern;

Pattern grapheme = Pattern.compile("\\X");
String text = "A👩‍💻B";

long visibleUnits = grapheme.matcher(text).results().count();
System.out.println(visibleUnits); // 3
~~~

The **Matcher.results()** method returns a Stream of match results; each match for this regex corresponds to one grapheme cluster. This counting approach suits many UI character limits, yet a *grapheme cluster* is still a Unicode segmentation unit, **not** a guarantee that the displayed symbol has a one-column width or exactly one glyph. For width on a terminal/UI, font, shaping, layout, and grapheme rendering must still be considered.

**BreakIterator.getCharacterInstance(...)** is another segmentation API in Java. Its ability to segment complex emoji sequences and its Unicode data version should be tested against the actual JDK. When consistent results across web, mobile, and server are needed, or for the latest emojis, specify the Unicode version and consider a specialized library such as ICU4J; run test suites with real-world strings.

## 6. Complete Java 17+ Example: Comparing All Four Length Types

Save the following program as **UnicodeLengthDemo.java** with UTF-8 encoding.

~~~java
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;
import java.util.regex.Pattern;

public class UnicodeLengthDemo {
    private static final Pattern GRAPHEME = Pattern.compile("\\X");

    private static void describe(String label, String value) {
        int units = value.length();
        int points = value.codePointCount(0, units);
        long clusters = GRAPHEME.matcher(value).results().count();
        int bytes = value.getBytes(StandardCharsets.UTF_8).length;

        System.out.printf(
                "%s | units=%d | points=%d | clusters=%d | UTF8=%d%n",
                label, units, points, clusters, bytes);
    }

    public static void main(String[] args) {
        String vietnameseNfc = "Việt";
        String vietnameseNfd = Normalizer.normalize(
                vietnameseNfc, Normalizer.Form.NFD);

        String aNfc = "\u1EAF";
        String aNfd = "a\u0306\u0301";

        describe("VIET_NFC", vietnameseNfc);
        describe("VIET_NFD", vietnameseNfd);
        describe("A_NFC", aNfc);
        describe("A_NFD", aNfd);
        describe("SMILE", "😊");
        describe("TONE", "👍🏽");
        describe("ZWJ", "👩‍💻");
        describe("FLAG", "🇻🇳");

        System.out.println("plain equals: " + aNfc.equals(aNfd));
        String normalizedA = Normalizer.normalize(
                aNfc, Normalizer.Form.NFC);
        String normalizedB = Normalizer.normalize(
                aNfd, Normalizer.Form.NFC);
        System.out.println(
                "NFC equals: " + normalizedA.equals(normalizedB));

        String emoji = "😊";
        System.out.println(
                "emoji high surrogate: " +
                Character.isHighSurrogate(emoji.charAt(0)));
        System.out.printf("emoji point=U+%X%n", emoji.codePointAt(0));
    }
}
~~~

Compile and run with JDK 17 or newer:

~~~bash
javac -encoding UTF-8 UnicodeLengthDemo.java
java UnicodeLengthDemo
~~~

Stdout output for the sample strings under the grapheme rules described above:

~~~text
VIET_NFC | units=4 | points=4 | clusters=4 | UTF8=6
VIET_NFD | units=6 | points=6 | clusters=4 | UTF8=8
A_NFC | units=1 | points=1 | clusters=1 | UTF8=3
A_NFD | units=3 | points=3 | clusters=1 | UTF8=5
SMILE | units=2 | points=1 | clusters=1 | UTF8=4
TONE | units=4 | points=2 | clusters=1 | UTF8=8
ZWJ | units=5 | points=3 | clusters=1 | UTF8=11
FLAG | units=4 | points=2 | clusters=1 | UTF8=8
plain equals: false
NFC equals: true
emoji high surrogate: true
emoji point=U+1F60A
~~~

**Result explanation:**

1. **VIET_NFC** and **VIET_NFD** both keep four user-perceived letters; the NFD form increases code unit, code point, and byte counts because the diacritics on **ệ** are decomposed separately.
2. **A_NFC** and **A_NFD** render equivalently yet have different code unit lengths. **equals()** returns **false** before normalization and **true** after NFC.
3. The single emoji **😊** has 2 code units but 1 code point. **👍🏽**, **👩‍💻**, and **🇻🇳** have multiple code points, yet each sample string is 1 grapheme cluster.
4. **UTF8** is the data length *after UTF-8 encoding*, not **String.length()**; for the ZWJ sequence in the example, that is 11 bytes.
5. **codePointAt(0)** reads the full code point U+1F60A when position 0 is the start of a valid surrogate pair.

Note: the source file must be saved in UTF-8 so that Vietnamese and emoji literals in the program keep their exact values. The **-encoding UTF-8** flag tells the compiler how to read the source file.

## 7. Slicing Strings by Grapheme Instead of UTF-16 Position

Suppose the input is **“A👩‍💻B”**. The string has 7 UTF-16 code units: A (1) + ZWJ emoji (5) + B (1), yet **3 grapheme clusters**.

Slicing **substring(0, 2)** will not keep the emoji icon intact; it selects A and part of the surrogate pair of the first character in the sequence. Slicing by 2 code points also does not keep the entire “👩‍💻” emoji.

If the product requirement is “keep the first two user-perceived characters”, find grapheme boundaries instead. Save the snippet below in **GraphemeTruncateDemo.java**:

~~~java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class GraphemeTruncateDemo {
    private static final Pattern GRAPHEME = Pattern.compile("\\X");

    static String firstGraphemes(String value, int maxClusters) {
        if (value == null) {
            throw new IllegalArgumentException("value must not be null");
        }
        if (maxClusters < 0) {
            throw new IllegalArgumentException("negative limit");
        }

        Matcher matcher = GRAPHEME.matcher(value);
        int end = 0;

        for (int i = 0; i < maxClusters && matcher.find(); i++) {
            end = matcher.end();
        }

        return value.substring(0, end);
    }

    public static void main(String[] args) {
        String original = "A👩‍💻B";

        System.out.println(original.length());
        System.out.println(GRAPHEME.matcher(original).results().count());
        System.out.println(firstGraphemes(original, 2));
        System.out.println(firstGraphemes(original, 0).isEmpty());
        System.out.println(firstGraphemes(original, 99));
    }
}
~~~

~~~bash
javac -encoding UTF-8 GraphemeTruncateDemo.java
java GraphemeTruncateDemo
~~~

~~~text
7
3
A👩‍💻
true
A👩‍💻B
~~~

The **Matcher.end()** method returns the end position of the match as a **UTF-16 index** — the exact index type expected by **substring(0, end)**. Taking boundaries from segmentation results avoids splitting inside a cluster for strings properly recognized by the regex. If the limit is 0, an empty string is returned; if the limit exceeds the cluster count, the result is the original string.

This is a text segmentation technique, not a truncation strategy to fit a byte budget. For a byte-limited payload, you need a different algorithm that both respects grapheme boundaries and measures bytes after encoding.

## 8. Choosing the Right Length Unit for Business Requirements

| Problem | Usually appropriate unit | Notes |
| --- | --- | --- |
| Java APIs requiring positions for **substring**, **charAt** | UTF-16 code unit | Never pass code point indices to APIs as if they were UTF-16 offsets. |
| Iterating over Unicode scalars or analyzing code points | Code point | Java strings can hold unpaired surrogates; a policy for invalid data is required. |
| Input form “maximum 20 user-perceived characters” | Grapheme cluster | Synchronize segmentation rules between client/server and define the Unicode version. |
| HTTP body or storage column with a byte limit | Bytes in a specified charset | Count **getBytes(UTF_8).length** after deciding on normalization. |
| Searching Vietnamese names by canonical equivalence | Appropriate normalization, usually NFC | Normalize before comparison per contract; also consider case, locale, and diacritics. |
| UI excerpt truncation | Grapheme boundary + layout rules | Avoid slicing inside combining marks/emojis; display width is still determined by the renderer. |

A system may need **two limits at the same time**: at most 30 graphemes for input experience and at most 255 UTF-8 bytes for protocol compatibility. These limits are independent; one limit cannot be replaced by the other's measurement.

If an application stores data and validates length on both client and server, clearly define: whether to normalize to NFC before checking, which Unicode segmentation version to use, how joined emojis are counted, and which layer is responsible for byte checks.

## 9. Common Mistakes

**Mistake 1 — Using String.length() to limit the number of letters a user enters.** An NFD Vietnamese letter can take 2–3 code units; a multi-part emoji can take 4–11 code units or more. Limiting by **length()** can reject valid input or slice mid-cluster. Choose the unit of measurement based on the specific requirement.

**Mistake 2 — Assuming codePointCount() gives the number of displayed emojis.** **“👩‍💻”** is three code points yet typically renders as one icon. For input UIs, grapheme segmentation is needed.

**Mistake 3 — Slicing in the middle of a surrogate pair.** **substring()** takes UTF-16 offsets; arbitrary slice values can produce a String containing an unpaired surrogate. When operating by code points, use **offsetByCodePoints()**; when operating by display characters, use grapheme boundaries.

**Mistake 4 — Comparing two visually identical Vietnamese letters with equals() without considering normalization.** NFC and NFD can differ in code unit counts, so **equals()** returns **false**. Normalize only if the data policy requires it; preserve the original if exact bytes are required.

**Mistake 5 — Converting to NFD and deleting all marks to “normalize”.** That is **accent stripping**, which can lose Vietnamese word meaning. True Unicode NFC/NFD does not aim to delete accents; accent-insensitive matching requires separate specification.

**Mistake 6 — Treating String.length() as the UTF-8 byte count.** The emoji **😊** has **length()==2** yet **4 bytes** in UTF-8. To check transmission/storage limits, encode with the specified charset and then count bytes.

**Mistake 7 — Believing every environment renders emojis identically.** Unicode defines code points and many segmentation rules; final visuals depend on fonts, text shapers, and platform emoji support. Test ZWJ sequences, modifiers, flags, and combining characters on target environments.

**Mistake 8 — Equating code points with all valid Unicode scalars.** A Java String can contain **unpaired surrogates** from improper slicing or invalid data. **codePointCount()** still processes positions per the API, but that does not prove the Unicode string is validly encoded. When strict Unicode compliance is needed, validate input and define a replacement/rejection policy.

## 10. Self-Check Questions

1. Why can two representations of the letter **ắ** have **length()** equal to 1 and 3? — Because one form uses a precomposed code point, while the other consists of a base letter and two combining marks.
2. Why does **"😊".length() == 2** yet **codePointCount(...) == 1**? — Because a code point outside the BMP uses a surrogate pair in UTF-16.
3. Why does **"👩‍💻"** have 3 code points yet can be 1 grapheme? — Because the components are joined by ZWJ into one extended grapheme cluster.
4. When should **Normalizer.Form.NFC** be chosen? — When business logic needs to canonicalize to a consistent Unicode form before comparison/processing; the same policy must be specified for all related data.
5. Should a 200-byte UTF-8 limit use **s.length() <= 200**? — No. You must measure UTF-8 bytes after applying normalization (if the policy specifies it).
6. Which Java regex finds extended grapheme clusters? — **Pattern.compile("\\X")**, then iterate with **Matcher.find()** or use **results()**.
7. Why should you care about the JDK's Unicode version? — Because character property and segmentation data can change when Unicode updates, especially for new emojis.

## 11. Takeaways

- **length() = UTF-16 code units**, suitable for String API indices but not an accurate representation of visible character count.
- **codePointCount() = code points counted over the UTF-16 representation**, still not the number of emoji icons or graphemes.
- **Grapheme cluster** is a useful unit when handling Vietnamese diacritics, emoji modifiers, ZWJ sequences, and flags in input UIs.
- **NFC/NFD** can change the length of Vietnamese text while keeping representations canonically equivalent in Unicode.
- **UTF-8 byte length** is a separate measurement, required for transmission and storage limits.

Foundational technical documentation: **java.lang.String**, **java.text.Normalizer**, **java.util.regex.Pattern** in Java SE 17, and **Unicode Standard Annex #29 — Unicode Text Segmentation**.