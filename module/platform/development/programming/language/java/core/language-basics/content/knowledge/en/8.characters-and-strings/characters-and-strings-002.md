# UTF-16 Code Units, Code Points, and Supplementary Characters in Java

> **Java core — language-basics / Characters and Strings**  
> **Requirements:** Java 17+ with JDK; no external libraries required.  
> **Goal:** Distinguish `char`, UTF-16 code units, Unicode code points, and supplementary (non-BMP) characters; understand surrogate pairs, how `String` indexes characters, and use code point APIs to avoid splitting characters in half.

## 1. Three easily confused concepts

| Concept | Meaning in Java | Example |
| --- | --- | --- |
| **Unicode code point** | A numeric value identifying a position in the Unicode codespace, written `U+...` | `U+0041` (A), `U+1F600` (😀) |
| **UTF-16 code unit** | A **16-bit** code unit used to represent data inside a `String` | `0x0041`, `0xD83D` |
| **`char`** | A Java primitive type holding **one UTF-16 code unit**, not necessarily a complete code point | `char letter = 'A';` |

The **Unicode code point** space spans from `U+0000` to `U+10FFFF` and **includes** the surrogate range `U+D800`–`U+DFFF`. However, surrogate code points **are not valid Unicode scalar values**, so they cannot stand alone as a properly encoded Unicode character. A code point outside the BMP requires two `char`s in UTF-16.

- **BMP** (*Basic Multilingual Plane*): range `U+0000`–`U+FFFF`; valid code points in the BMP use **one** UTF-16 code unit.
- **Supplementary code points** (*non-BMP*): range `U+10000`–`U+10FFFF`; in UTF-16, each code point is represented by **two** code units (*surrogate pair*).
- The surrogate range lies numerically within the BMP, but surrogates are not Unicode scalar values and must not be used alone to encode characters in valid UTF-16.

For example, the letter `A` (U+0041) needs 1 `char`; the emoji 😀 (U+1F600) needs **2 `char`s** in a Java `String`.

## 2. How is a surrogate pair formed?

For supplementary code points outside the BMP, UTF-16 uses:

- **High surrogate**: a code unit in the range `0xD800`–`0xDBFF`.
- **Low surrogate**: a code unit in the range `0xDC00`–`0xDFFF`.
- A consecutive high-then-low pair encodes one code point outside the BMP.

Concrete example:

~~~text
Unicode code point: U+1F600 (😀)
High surrogate:      D83D
Low surrogate:       DE00
UTF-16 code units:   [D83D][DE00]
~~~

Formula if you want to compute it manually from a code point `cp >= 0x10000`:

~~~text
v    = cp - 0x10000
high = 0xD800 + (v >> 10)
low  = 0xDC00 + (v & 0x3FF)
~~~

Combining two surrogates back:

~~~text
cp = 0x10000 + ((high - 0xD800) << 10) + (low - 0xDC00)
~~~

**Do not** treat `0xD83D` or `0xDE00` individually as a complete emoji. They are simply two code units that must appear as a pair in the right order.

## 3. `String.length()` and `charAt()` count UTF-16 units

Consider a string of three code points: `A`, `U+1F600`, `B`. In UTF-16:

| UTF-16 index | Code unit | Belongs to code point |
| ---: | --- | --- |
| 0 | `0041` | `U+0041` (A) |
| 1 | `D83D` | First half of `U+1F600` |
| 2 | `DE00` | Second half of `U+1F600` |
| 3 | `0042` | `U+0042` (B) |

Therefore `length()` is **4**, while `codePointCount(0, length())` is **3**. `charAt(1)` returns the **high surrogate**, `charAt(2)` returns the **low surrogate**; `codePointAt(1)` combines the pair into the code point `0x1F600`.

| Java API | Unit processed | Usage |
| --- | --- | --- |
| `s.length()` | UTF-16 code unit | Storage length in UTF-16 |
| `s.charAt(index)` | **One** `char` | Read one code unit |
| `s.codePointAt(index)` | One code point starting at that UTF-16 index, if a valid pair exists | Read a code point at a proper boundary |
| `s.codePointCount(0, s.length())` | Code point | Count code points |
| `s.offsetByCodePoints(start, count)` | From a UTF-16 offset, advance by code points | Find index boundaries for slicing strings |
| `s.codePoints()` | `IntStream` of code points | Iterate by code point |
| `Character.toChars(cp)` | `char[]` array of length 1 or 2 | Encode a valid code point into UTF-16 |

The indices passed to `charAt`, `substring`, and `codePointAt` are still **UTF-16 offsets**, not pure code point positions. Calling `codePointAt(2)` in the middle of the pair above **does not** look backward to combine with the high surrogate at index 1; therefore you should iterate with `codePoints()` or valid offsets.

## 4. Runnable Java 17+ example: UnicodeUnitsDemo.java

Create the file **UnicodeUnitsDemo.java**:

~~~java
import java.nio.charset.StandardCharsets;

public final class UnicodeUnitsDemo {
    public static void main(String[] args) {
        int emoji = 0x1F600;
        String face = new String(Character.toChars(emoji));
        String sample = "A" + face + "B";

        System.out.println("utf16Units=" + sample.length());
        System.out.println("codePoints="
                + sample.codePointCount(0, sample.length()));
        System.out.println("utf8Bytes="
                + sample.getBytes(StandardCharsets.UTF_8).length);

        System.out.printf("unit1=%04X%n", (int) sample.charAt(1));
        System.out.printf("unit2=%04X%n", (int) sample.charAt(2));
        System.out.printf("point1=U+%X%n", sample.codePointAt(1));
        System.out.println("supplementary="
                + Character.isSupplementaryCodePoint(emoji));
        System.out.println("unitCount=" + Character.charCount(emoji));

        int afterTwoPoints = sample.offsetByCodePoints(0, 2);
        System.out.println("afterTwoPoints=" + afterTwoPoints);
        System.out.println("faceSlice="
                + sample.substring(1, afterTwoPoints).equals(face));
        System.out.println("splitPair="
                + Character.isHighSurrogate(sample.substring(1, 2).charAt(0)));

        StringBuilder labels = new StringBuilder();
        sample.codePoints().forEach(cp -> {
            if (labels.length() > 0) {
                labels.append(",");
            }
            labels.append(String.format("U+%X", cp));
        });
        System.out.println("sequence=" + labels);

        String combining = "e\u0301";
        System.out.println("combiningUnits=" + combining.length());
        System.out.println("combiningPoints="
                + combining.codePointCount(0, combining.length()));
    }
}
~~~

Compile/run in the directory containing the file using Bash, PowerShell, or Command Prompt:

~~~bash
javac -encoding UTF-8 UnicodeUnitsDemo.java
java UnicodeUnitsDemo
~~~

**Expected output (exact):**

~~~text
utf16Units=4
codePoints=3
utf8Bytes=6
unit1=D83D
unit2=DE00
point1=U+1F600
supplementary=true
unitCount=2
afterTwoPoints=3
faceSlice=true
splitPair=true
sequence=U+41,U+1F600,U+42
combiningUnits=2
combiningPoints=2
~~~

**How to read the output:**

1. The string `A + 😀 + B` consists of three code points but occupies 4 UTF-16 code units. When encoded as UTF-8, `A` and `B` are 1 byte each and this emoji is 4 bytes, totaling **6 bytes**.
2. The two `char`s at UTF-16 indices 1 and 2 have codes `D83D` and `DE00`. `codePointAt(1)` returns `U+1F600` as expected.
3. `offsetByCodePoints(0, 2)` equals **3**, because it steps past A (1 code unit) and the emoji (2 code units).
4. `substring(1, 3)` produces a complete emoji string. `substring(1, 2)`, on the other hand, **splits the surrogate pair in half**, leaving an isolated high surrogate.
5. `codePoints()` iterates through the three code points `U+41`, `U+1F600`, `U+42`. The string `"e\u0301"` has `e` and a combining acute accent: **2 code points**, even though a reader may see it as **one displayed character**.

## 5. Iterating and slicing strings safely at code point boundaries

**Do not assume** `for (int i = 0; i < s.length(); i++)` iterates over each code point: that loop iterates over **each code unit**.

Iterate by code point when Unicode analysis is needed:

~~~java
String s = "A" + new String(Character.toChars(0x1F600)) + "B";
s.codePoints().forEach(cp -> System.out.printf("U+%X%n", cp));
~~~

When you need to slice starting from the **1st code point** (0-based) and take **one code point**, compute the UTF-16 boundaries:

~~~java
int start = s.offsetByCodePoints(0, 1); // 1
int end = s.offsetByCodePoints(start, 1); // 3
String onlyEmoji = s.substring(start, end);
~~~

Do not slice arbitrarily with length 1 using `s.substring(start, start + 1)`: if the element is a supplementary code point, you only get half of a surrogate pair.

`Character.charCount(cp)` indicates whether a code point needs **1 or 2 code units**; `Character.toChars(cp)` produces the corresponding code units. The `String.codePointAt`/`codePoints` APIs help work at the code point level, but **do not replace validation for malformed Unicode data**: a Java `String` can contain lone surrogates, and those APIs have their own rules when encountering invalid pairs.

## 6. A code point is not necessarily a user-visible character

Three measurements must be distinguished:

| Unit | Example `A😀B` | Meaning |
| --- | ---: | --- |
| UTF-16 code unit | 4 | Result of `String.length()` |
| Unicode code point | 3 | Result of `codePointCount` |
| UTF-8 byte | 6 | Result of `getBytes(StandardCharsets.UTF_8).length` |

However, a **displayed character** (*grapheme cluster*) can consist of **multiple code points**: for example `"e\u0301"` (letter e plus combining acute accent), emoji with skin-tone modifiers, or emoji sequences using zero-width joiners. Thus counting code points **does not automatically mean counting user-visible characters**.

For cursor positioning, slicing displayed text, or limiting characters in a UI, you need a Unicode-compliant grapheme segmentation algorithm, not just `length()` or `codePointCount()`. For many data-processing operations based on Unicode codes, code point is the appropriate unit.

## 7. Common misconceptions

| Misconception | Explanation / fix |
| --- | --- |
| “One `char` is any Unicode character.” | False: `char` holds one 16-bit code unit; supplementary code points need **two** units. |
| “`String.length()` counts code points.” | False: it counts UTF-16 code units. |
| “`substring(i, i+1)` always extracts one character.” | False if `i` is at the high surrogate of a supplementary code point. Compute `end` with `offsetByCodePoints`. |
| “`charAt(1)` will return the whole emoji.” | False: it only returns one surrogate. Use `codePointAt` at a valid boundary. |
| “UTF-8 byte length equals `String.length()`.” | False: UTF-8 bytes and UTF-16 code units are two different measurement units. |
| “Counting code points is counting graphemes.” | False: one grapheme can combine multiple code points. |
| “`String.codePoints()` automatically repairs broken UTF-16.” | False: data containing lone surrogates must be checked/handled according to input policy. |

## 8. Self-practice exercises

**Exercise 1.** Explain why `"A" + new String(Character.toChars(0x1F600)) + "B"` has `length() == 4`, yet `codePointCount(...) == 3`.

**Exercise 2.** Predict the two values `(int) s.charAt(1)` and `(int) s.charAt(2)` in the sample string; convert them to hexadecimal to compare with `D83D` and `DE00`.

**Exercise 3.** Create `int cp = 0x1F680;` (🚀), use `Character.toChars(cp)` to create a string, then print `length()` and `codePointCount`. Are the two results the same?

**Exercise 4.** From the string `A😀B`, extract only the emoji without splitting the surrogate pair, using `offsetByCodePoints` and `substring`.

**Exercise 5.** For `"e\u0301"`, predict the number of code units, code points, and visible characters a reader might perceive. Explain why these three concepts are not always equivalent.

### Key takeaways

- **`char` = one UTF-16 code unit (16-bit)**, not every Unicode code point.
- **Supplementary (non-BMP) = two code units (high/low surrogate)**; e.g. `U+1F600` ↔ `D83D DE00`.
- `String.length()` and indices in `charAt`/`substring` operate on **UTF-16 code units**.
- Use `codePointAt`, `codePoints`, `codePointCount`, and `offsetByCodePoints` when working by code point.
- **Code point differs from grapheme cluster**, and UTF-8 byte count is yet another measurement.
