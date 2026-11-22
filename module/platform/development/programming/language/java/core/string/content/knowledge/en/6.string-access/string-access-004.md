# codePointCount over a UTF-16 Range in Java

## 1. Purpose and meaning

The method **String.codePointCount(int beginIndex, int endIndex)** counts the number of **Unicode code points** represented in **a range of a Java string**. The easiest point to confuse: both **beginIndex** and **endIndex** are **UTF-16 code unit indices**, not code point indices or visible character indices.

Syntax:

~~~java
int count = text.codePointCount(beginIndex, endIndex);
~~~

The illustrative statements in this lesson can be placed inside a Java method. API conventions:

- **beginIndex**: start position in the String, **inclusive**.
- **endIndex**: end position, **exclusive**; the range is written **[beginIndex, endIndex)**.
- Valid indices satisfy **0 <= beginIndex <= endIndex <= text.length()**.
- If **beginIndex == endIndex**, the result is **0**.
- If begin is less than 0, end is greater than **length()**, or begin is greater than end, the method throws **IndexOutOfBoundsException**.
- Each **valid surrogate pair completely inside the range** is counted as **1 code point**.
- Each **unpaired surrogate** in the range, including one half of a pair split by a boundary, is counted as **1**.

**Important:** the method counts over the UTF-16 slice **exactly as passed in**. It does not expand the range to keep surrogate pairs intact, does not normalize Unicode, does not count grapheme clusters, and does not automatically convert parameters into code point positions.

## 2. Three concepts to distinguish

| Concept | In Java | How to understand it |
| --- | --- | --- |
| **UTF-16 code unit** | **char**, **String.length()**, indices of **charAt()**/**substring()** | A 16-bit unit; code points outside the BMP need two units |
| **Unicode code point** | **codePointAt()**, **codePoints()**, **codePointCount()** | A Unicode value; a high surrogate + low surrogate pair represents one supplementary code point |
| **Extended grapheme cluster** | Can be segmented with regex **\\X** | A cluster usually perceived by the user as one character, which may contain multiple code points |

The **Basic Multilingual Plane (BMP)** consists of code points from U+0000 to U+FFFF, excluding the surrogate range which are not standalone Unicode scalar values. Supplementary code points from U+10000 to U+10FFFF are encoded using **two UTF-16 code units**: a **high surrogate** followed by a **low surrogate**.

Therefore:

- An ordinary Latin letter **A**: typically 1 code unit and 1 code point.
- The emoji **😊** (U+1F60A): 2 code units, 1 code point.
- The letter **a** plus a combining acute accent **a\u0301**: 2 code units, 2 code points, yet usually 1 grapheme cluster.
- The emoji **👩‍💻**: 5 code units, 3 code points, usually 1 grapheme cluster.

**codePointCount()** answers the question about **code points in a UTF-16 range**; it does not necessarily answer “how many letters, emoji, or visible characters are there?”.

## 3. Core illustration: "A😊B"

Consider the string:

~~~java
String text = "A😊B";
~~~

Layout of the string by **UTF-16** index:

| Code unit position | Content | Role |
| ---: | --- | --- |
| 0 | **A** | BMP letter, 1 code unit |
| 1 | **U+D83D** | High surrogate of **😊** |
| 2 | **U+DE0A** | Low surrogate of **😊** |
| 3 | **B** | BMP letter, 1 code unit |
| 4 | End-of-string boundary | Valid **endIndex** position, not a character |

So **text.length() == 4**, yet the entire string has only **3 code points**: **A**, **😊**, **B**.

Typical ranges:

| UTF-16 range | Portion taken | **codePointCount** | Explanation |
| --- | --- | ---: | --- |
| **[0, 4)** | **A😊B** | 3 | A (1) + surrogate pair of 😊 (1) + B (1) |
| **[1, 3)** | **😊** | 1 | Two code units combined into one code point |
| **[0, 1)** | **A** | 1 | One BMP letter |
| **[3, 4)** | **B** | 1 | One BMP letter |
| **[1, 1)** | Empty | 0 | No code units |
| **[0, 2)** | A + lone high surrogate | 2 | Boundary 2 splits the surrogate pair in half |
| **[2, 4)** | Lone low surrogate + B | 2 | Boundary 2 splits the surrogate pair in half |

This leads to a property that requires caution:

~~~java
int whole = text.codePointCount(0, 4);   // 3
int left = text.codePointCount(0, 2);    // 2
int right = text.codePointCount(2, 4);   // 2
~~~

**left + right == 4**, which differs from **whole == 3**, because the split point **2** lies **between the two halves of the surrogate pair**. Adding the code point counts of subranges only matches the count of the whole range if every split boundary **does not break** a valid surrogate pair.

If you change the split point to **3**, right after the emoji, the result is:

~~~java
int left = text.codePointCount(0, 3);    // 2 (A, 😊)
int right = text.codePointCount(3, 4);   // 1 (B)
~~~

Then **left + right == 3**, matching the code point count of the whole string.

## 4. Standalone Java 17+ example

Save as **CodePointCountRangeDemo.java** (UTF-8 encoding):

~~~java
public class CodePointCountRangeDemo {
    public static void main(String[] args) {
        String text = "A😊B";

        System.out.println("UTF16 units: " + text.length());
        System.out.println("All: " +
                text.codePointCount(0, text.length()));
        System.out.println("Emoji: " +
                text.codePointCount(1, 3));
        System.out.println("Left split: " +
                text.codePointCount(0, 2));
        System.out.println("Right split: " +
                text.codePointCount(2, 4));
        System.out.println("Empty: " +
                text.codePointCount(1, 1));

        System.out.println("High surrogate: " +
                Character.isHighSurrogate(text.charAt(1)));
        System.out.println("Low surrogate: " +
                Character.isLowSurrogate(text.charAt(2)));

        int endAfterTwoPoints = text.offsetByCodePoints(0, 2);
        System.out.println("Index after 2 points: " +
                endAfterTwoPoints);
        System.out.println("Prefix: " +
                text.substring(0, endAfterTwoPoints));
    }
}
~~~

Run with JDK 17 or newer:

~~~bash
javac -encoding UTF-8 CodePointCountRangeDemo.java
java CodePointCountRangeDemo
~~~

Stdout:

~~~text
UTF16 units: 4
All: 3
Emoji: 1
Left split: 2
Right split: 2
Empty: 0
High surrogate: true
Low surrogate: true
Index after 2 points: 3
Prefix: A😊
~~~

The numbers are calculated based on the surrogate pair of the emoji **😊**: high surrogate U+D83D and low surrogate U+DE0A.

Key takeaways from the program:

1. **length()** measures code units; **codePointCount(0, length())** measures code points in the entire String.
2. **[1, 3)** contains the complete surrogate pair, so the result is 1.
3. **[0, 2)** and **[2, 4)** produce ranges with an unpaired surrogate; each unpaired surrogate is counted as 1.
4. **offsetByCodePoints(0, 2)** returns **UTF-16 index 3** after the first two code points, suitable for passing into **substring()**.

**Important:** **charAt(1)** yields the high surrogate, not the complete emoji character. To read the code point starting at that position, use **text.codePointAt(1)**; the result is U+1F60A.

## 5. beginIndex/endIndex bounds and empty ranges

Ranges in Java are **half-open**:

\[
[beginIndex,endIndex)
\]

Examples with **"Java"** (each character in this example is one code unit):

| Call | Result | Why |
| --- | ---: | --- |
| **"Java".codePointCount(0, 4)** | 4 | Counts the whole string |
| **"Java".codePointCount(1, 3)** | 2 | Contains the characters at positions 1 and 2 |
| **"Java".codePointCount(0, 0)** | 0 | Empty range at the start of the string |
| **"Java".codePointCount(4, 4)** | 0 | Empty range at the end of the string |

The following statements are invalid:

~~~java
String text = "Java";
text.codePointCount(-1, 2); // negative beginIndex
text.codePointCount(1, 5);  // endIndex exceeds length()
text.codePointCount(3, 2);  // beginIndex > endIndex
~~~

This is an **error-demonstration** snippet; you should not run all three statements consecutively if you want to observe each error individually, because the first statement throws **IndexOutOfBoundsException** and can halt the program. Valid boundaries must simultaneously satisfy **0 <= beginIndex <= endIndex <= text.length()**.

Do not confuse **endIndex == length()** (valid) with accessing **charAt(length())** (invalid, because that is the position immediately after the last element).

If a method only receives a code point range from a user or from another API, **do not** pass those indices directly into **codePointCount(beginIndex, endIndex)**. First convert the code point offsets into UTF-16 offsets.

## 6. Converting between UTF-16 positions and code point positions

**codePointCount(begin, end)** returns a **number of code points**, not an index. When you need a UTF-16 offset corresponding to a number of code points, Java provides:

~~~java
int endUtf16 = text.offsetByCodePoints(startUtf16, numberOfCodePoints);
~~~

Example:

~~~java
String text = "A😊B";
int endUtf16 = text.offsetByCodePoints(0, 2); // 3
String firstTwo = text.substring(0, endUtf16); // "A😊"
~~~

Because the supplementary character **😊** occupies two code units, the offset after the first two code points is **3**, not **2**.

A prefix count is also useful when converting a **UTF-16 offset** into a code point ordinal:

~~~java
String text = "A😊B";
int utf16Index = 3; // start of letter B
int codePointsBeforeB = text.codePointCount(0, utf16Index); // 2
~~~

The condition to watch out for is that **utf16Index** must lie on a code point boundary when you intend to interpret the result as the number of code points **before an intact character**. If you use **utf16Index == 2** (middle of the emoji), **codePointCount(0, 2)** still returns **2**, but that is not a valid position to place a cursor “after two code points” in the original string.

**offsetByCodePoints()** also requires a valid starting point and code point count. It can move from an arbitrary UTF-16 position, including a position in the middle of a surrogate pair; if you want to guarantee not splitting code points, **the input must be a valid boundary**.

### Helper function to check surrogate boundaries

A **valid code point boundary** must not lie between an adjacent high surrogate and low surrogate. The following method checks that condition:

~~~java
static boolean isCodePointBoundary(String text, int index) {
    if (index < 0 || index > text.length()) {
        return false;
    }
    if (index == 0 || index == text.length()) {
        return true;
    }
    return !(Character.isHighSurrogate(text.charAt(index - 1))
            && Character.isLowSurrogate(text.charAt(index)));
}
~~~

This is a **method snippet**; it must be placed inside a Java class. For example with **"A😊B"**: indices **1** and **3** are boundaries, while **2** is not. Both ends **0** and **4** are also boundaries.

This method only ensures **not splitting inside a surrogate pair**, and **does not validate that the entire String is valid UTF-16**. A Java String can contain lone surrogates that already exist in the data.

## 7. Java 17+ example: checking boundaries before counting

The following example is suitable when your API wants to count **complete code points** and needs to reject ranges that split a surrogate pair. Save as **SafeCodePointRangeDemo.java**:

~~~java
public class SafeCodePointRangeDemo {
    static boolean isBoundary(String text, int index) {
        if (index < 0 || index > text.length()) {
            return false;
        }
        if (index == 0 || index == text.length()) {
            return true;
        }
        return !(Character.isHighSurrogate(text.charAt(index - 1))
                && Character.isLowSurrogate(text.charAt(index)));
    }

    static int countOnBoundaries(String text, int begin, int end) {
        if (text == null) {
            throw new IllegalArgumentException("text is null");
        }
        if (begin > end ||
                !isBoundary(text, begin) ||
                !isBoundary(text, end)) {
            throw new IllegalArgumentException(
                    "range splits a surrogate pair or is invalid");
        }
        return text.codePointCount(begin, end);
    }

    public static void main(String[] args) {
        String text = "A😊B";

        System.out.println(isBoundary(text, 1));
        System.out.println(isBoundary(text, 2));
        System.out.println(isBoundary(text, 3));
        System.out.println(countOnBoundaries(text, 0, 3));

        try {
            System.out.println(countOnBoundaries(text, 0, 2));
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected a split surrogate pair");
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 SafeCodePointRangeDemo.java
java SafeCodePointRangeDemo
~~~

Stdout:

~~~text
true
false
true
2
Rejected a split surrogate pair
~~~

The method **countOnBoundaries** chooses the policy of **rejecting a range that falls in the middle of a surrogate pair**. This is a **custom constraint**, not the default behavior of **String.codePointCount()**. The standard API allows counting ranges like **[0, 2)** and counts an unpaired surrogate as one code point.

Applications that require strict Unicode data integrity must also have a step validating that **there are no unpaired surrogates anywhere in the data region**. Boundary checking is not a substitute for that validation.

## 8. Vietnamese accents and composite emoji: counting code points differs from counting graphemes

A Vietnamese accent can be encoded using a **combining mark**; for example:

~~~java
String composed = "\u00E1";     // á, a precomposed code point
String decomposed = "a\u0301"; // a + combining acute accent

System.out.println(composed.codePointCount(0, composed.length()));     // 1
System.out.println(decomposed.codePointCount(0, decomposed.length())); // 2
~~~

The two values usually **render** identically, yet **codePointCount()** yields different results. The reason is that this method **does not automatically normalize** NFC/NFD. If business logic needs to compare two canonically equivalent forms, you can apply **java.text.Normalizer** consistently:

~~~java
import java.text.Normalizer;

// The following statements go inside a method:
String a = Normalizer.normalize("\u00E1", Normalizer.Form.NFC);
String b = Normalizer.normalize("a\u0301", Normalizer.Form.NFC);
System.out.println(a.equals(b)); // true
~~~

The code above is an **illustrative snippet with an import**, not a standalone program. Normalization does not strip Vietnamese accents, whereas removing accents is a separate business requirement.

Similarly:

- Emoji **😊**: 2 UTF-16 code units, 1 code point.
- Emoji **👍🏽**: 4 UTF-16 code units, 2 code points, usually rendered as one symbol.
- Emoji **👩‍💻**: 5 UTF-16 code units, 3 code points, usually rendered as one symbol thanks to ZERO WIDTH JOINER.
- Flag emoji **🇻🇳**: 4 UTF-16 code units, 2 code points, usually rendered as one flag.

Therefore, even when passing the whole string into **codePointCount(0, length())**, the number returned can **differ from the number of characters seen by the user**. If the requirement is to truncate or limit visible characters, **extended grapheme cluster** segmentation is needed; you can use the Java regex **Pattern.compile("\\X")** in JDKs that support it or a dedicated Unicode library when control over the Unicode version is needed.

## 9. Comparing codePointCount with related APIs

| API | Returns | Indices/input | Notes |
| --- | --- | --- | --- |
| **length()** | Number of UTF-16 code units in the whole String | No parameters | Not the number of code points for emoji outside the BMP |
| **charAt(i)** | One **char** (one code unit) | **i** is a UTF-16 index | May return half of a surrogate pair |
| **codePointAt(i)** | Code point starting at **i**, if a valid pair exists | **i** is a UTF-16 index | If starting at a lone low surrogate, returns that code unit value |
| **codePointBefore(i)** | Code point immediately before **i** | **i** is a UTF-16 index, starting from 1 | Checks surrogate pairs looking backward |
| **codePointCount(begin, end)** | Number of code points in the half-open UTF-16 slice | Two UTF-16 offsets | Lone surrogates in the slice count as 1 |
| **offsetByCodePoints(i, delta)** | UTF-16 offset after moving by code points | **i** is a UTF-16 index; delta is a signed number of code points | Can be used to find the appropriate end index for substring |
| **codePoints().count()** | Number of code points in the whole String as a **long** | No direct slice indices | If you only need the whole-string total, you can use **codePointCount(0, length())** |
| **substring(begin, end)** | Substring over a UTF-16 range | Two UTF-16 offsets | Can split a surrogate pair if wrong offsets are used |

**codePoints()** returns an **IntStream** of code point values. The total code point count for the **entire string** obtained via **text.codePoints().count()** and **text.codePointCount(0, text.length())** will match for the same String; **codePoints().count()** returns **long**, whereas **codePointCount()** returns **int**.

In terms of cost, counting code points in a range must scan the relevant code units to detect surrogate pairs; it should not be assumed to be an **O(1)** length operation like reading the String's **length()**. For large datasets and frequent queries, consider storing precomputed indices at **valid boundaries** or changing to an appropriate data structure, rather than repeatedly rescanning ranges.

## 10. Applying to real-world scenarios

### Scenario 1: Counting content between two known Java positions

If **begin** and **end** come from **Matcher.start()/end()**, **String.indexOf()**, or a Java API that returns UTF-16 offsets, you can call:

~~~java
int codePoints = text.codePointCount(begin, end);
~~~

Before interpreting the result as a count of complete characters, check whether the boundaries split a surrogate pair. Not every substring or application-computed position is guaranteed to lie on a code point boundary.

### Scenario 2: Taking the first 10 code points

Do not use **substring(0, 10)** if emoji might appear, because 10 code points may require more than 10 UTF-16 code units.

~~~java
int amount = Math.min(10, text.codePointCount(0, text.length()));
int endIndex = text.offsetByCodePoints(0, amount);
String prefix = text.substring(0, endIndex);
~~~

This snippet keeps at most 10 code points from the beginning of the String, without automatically guaranteeing preservation of a multi-code-point grapheme. For a “10 visible characters” requirement, substitute grapheme segmentation.

### Scenario 3: Counting what has been typed from the start to the caret position

If the caret is measured in UTF-16 offsets **and** points to a valid code point boundary:

~~~java
int pointsBeforeCaret = text.codePointCount(0, caretUtf16Index);
~~~

If the cursor could sit in the middle of a surrogate pair, adjust it to a valid boundary before interpreting the result. If the UI counts by graphemes instead of code points, use an independent grapheme index.

### Scenario 4: Splitting chunks for parallel processing or pagination

When splitting at UTF-16 offsets, a split point must not pass through a surrogate pair if the chunks will be processed as intact Unicode text. If you cut between a pair, the sum of the chunks' **codePointCount** values can exceed the true total of the original range. Determine split boundaries using **offsetByCodePoints()** or check boundaries before cutting; if visible characters must be preserved, use grapheme boundaries.

## 11. Common mistakes and how to avoid them

1. **Assuming beginIndex/endIndex are code point indices.** They are UTF-16 offsets. Convert indices with **offsetByCodePoints()** before calling methods that expect UTF-16 offsets.
2. **Assuming counting chunks and summing always equals the total.** This fails if a split point cuts a surrogate pair; split at valid code point boundaries.
3. **Treating beginIndex == endIndex as an error.** An empty range is valid and returns 0.
4. **Using endIndex = length() - 1 to count the whole string.** Because the range is half-open, to count everything you must pass **endIndex = length()**.
5. **Thinking unpaired surrogates automatically throw an exception.** The **codePointCount()** API counts them as 1; validating well-formed UTF-16 is a separate responsibility.
6. **Treating the code point count as the number of visible letters.** Combining marks and joined emoji can be multiple code points within one grapheme.
7. **Slicing with substring at arbitrary offsets.** That can produce lone surrogates, causing unpredictable results when displaying or encoding to UTF-8.
8. **Thinking codePointCount automatically normalizes Vietnamese letters.** NFC and NFD can differ in code point count; normalization must be an explicit step per business rules.
9. **Using codePointCount to deduce storage byte count.** Byte length depends on the charset; for UTF-8 bytes, use **text.getBytes(StandardCharsets.UTF_8).length**.

## 12. Self-check

**Question 1.** Given **String s = "A😊B"**, what are the results of **s.length()** and **s.codePointCount(0, s.length())**?

**Answer:** 4 code units and 3 code points.

**Question 2.** Why does **s.codePointCount(0, 2) + s.codePointCount(2, 4)** equal 4 instead of 3?

**Answer:** The UTF-16 boundary at position 2 lies between the high and low surrogates of the emoji; each half standing alone inside a range is counted as 1.

**Question 3.** What does the range **[1, 1)** return?

**Answer:** 0 because it is a valid empty range.

**Question 4.** To get the first two code points of **"A😊B"**, which UTF-16 end index do you use?

**Answer:** **s.offsetByCodePoints(0, 2)** returns 3; use **s.substring(0, 3)** to get **"A😊"**.

**Question 5.** Does **codePointCount** automatically reject lone surrogates or automatically count the emoji **👩‍💻** as one character?

**Answer:** No. A lone surrogate counts as one unit in the count; this ZWJ emoji consists of 3 code points and is typically 1 grapheme cluster.

**Question 6.** For the letter **"á"** in NFC and **"a\u0301"** in NFD, why can the results differ?

**Answer:** NFC has one precomposed code point, whereas the decomposed form consists of two code points. The method does not normalize automatically.

## 13. Remember

- **String.codePointCount(beginIndex, endIndex)** counts **Unicode code points** over the **half-open UTF-16 range [beginIndex, endIndex)**.
- **Both indices are UTF-16 offsets**; the return value is a **code point count**, not a position or a grapheme count.
- **A complete surrogate pair is counted once; lone surrogates within the range are counted once per piece**.
- **Do not split surrogate pairs** when separating a string into intact Unicode text regions; when summing across multiple chunks, every split boundary must be checked.
- **offsetByCodePoints()** steps by code points and returns the right kind of UTF-16 offset for use with **substring()**.
- Vietnamese with combining marks and multi-component emoji clearly show that **a code point is not equivalent to a visible character**.

API reference: **Java SE 17, java.lang.String#codePointCount(int,int)**, **String#offsetByCodePoints(int,int)**, **Character#isHighSurrogate(char)**, **Character#isLowSurrogate(char)**, and Unicode rules for UTF-16.