# `length()`, `charAt()`, and `substring()` in Java 17+

The three most commonly used methods for reading and slicing a `String` in Java are:

- `length()`: returns the **number of UTF-16 code units** in the string.
- `charAt(index)`: retrieves one `char` value at the requested **UTF-16 index**.
- `substring(beginIndex)` and `substring(beginIndex, endIndex)`: extracts the content from a starting position, or from an **inclusive** start position to an **exclusive** end position.

All indices **start at 0**. These three operations **read or produce a string result** without modifying the original `String` content.

## 1. Quick reference table for syntax and bounds

Suppose:

~~~java
String text = "Java Core";
~~~

The string above has 9 UTF-16 code units, indexed as follows:

~~~text
Char    : J a v a   C o r e
Index   : 0 1 2 3 4 5 6 7 8
Boundary: 0 1 2 3 4 5 6 7 8 9
~~~

| Expression | Result | Rule |
| --- | --- | --- |
| `text.length()` | `9` | Total number of **UTF-16 code units** |
| `text.charAt(0)` | `'J'` | First element; return type is `char` |
| `text.charAt(5)` | `'C'` | 6th position |
| `text.substring(0, 4)` | `"Java"` | Takes indices 0, 1, 2, 3 |
| `text.substring(5)` | `"Core"` | Takes from 5 to the end |
| `text.substring(5, 9)` | `"Core"` | `endIndex = length()` is allowed |
| `text.substring(4, 4)` | `""` | Equal bounds produce an empty string |
| `text.substring(0, text.length())` | `"Java Core"` | Selects the entire string |

Important distinction: **`charAt(length())` is invalid**, whereas **`substring(length())` is valid and returns `""`**. That is because `charAt` must read an actual element, while `substring` is allowed to start at the **end boundary**.

## 2. Runnable Java 17+ example

Save a UTF-8 file named **`StringIndexDemo.java`**:

~~~java
public class StringIndexDemo {
    public static void main(String[] args) {
        String text = "Java Core";

        System.out.println("text=" + text);
        System.out.println("length=" + text.length());
        System.out.println("first=" + text.charAt(0));
        System.out.println("sixth=" + text.charAt(5));
        System.out.println("prefix=" + text.substring(0, 4));
        System.out.println("suffix=" + text.substring(5));
        System.out.println("middle=" + text.substring(5, 9));
        System.out.println("emptyLength=" + text.substring(4, 4).length());
        System.out.println("wholeSameContent="
                + text.substring(0, text.length()).equals(text));

        String unicode = "A🚀B";
        String rocket = unicode.substring(1, 3);

        System.out.println("codeUnits=" + unicode.length());
        System.out.println("codePoints="
                + unicode.codePointCount(0, unicode.length()));
        System.out.println("emojiSliceUnits=" + rocket.length());
        System.out.println("emojiSliceCodePoints="
                + rocket.codePointCount(0, rocket.length()));
        System.out.println("highSurrogate="
                + Character.isHighSurrogate(unicode.charAt(1)));
        System.out.println("lowSurrogate="
                + Character.isLowSurrogate(unicode.charAt(2)));
        System.out.printf("rocketPoint=U+%X%n", unicode.codePointAt(1));

        try {
            text.charAt(text.length());
        } catch (StringIndexOutOfBoundsException ex) {
            System.out.println("invalidCharAt=StringIndexOutOfBoundsException");
        }

        try {
            text.substring(6, 5);
        } catch (StringIndexOutOfBoundsException ex) {
            System.out.println(
                    "invalidSubstring=StringIndexOutOfBoundsException");
        }
    }
}
~~~

Open PowerShell (Windows) or Bash (Linux/macOS) in the directory containing the file and run with JDK 17+:

~~~bash
java -version
javac -version
javac -encoding UTF-8 StringIndexDemo.java
java StringIndexDemo
~~~

**Expected output:**

~~~text
text=Java Core
length=9
first=J
sixth=C
prefix=Java
suffix=Core
middle=Core
emptyLength=0
wholeSameContent=true
codeUnits=4
codePoints=3
emojiSliceUnits=2
emojiSliceCodePoints=1
highSurrogate=true
lowSurrogate=true
rocketPoint=U+1F680
invalidCharAt=StringIndexOutOfBoundsException
invalidSubstring=StringIndexOutOfBoundsException
~~~

Quick explanation: `"Java Core"` has 9 code units and position 5 is the letter `C`. `substring(5, 9)` does not include the element at index 9; it takes positions `5, 6, 7, 8`. `"A🚀B"` has **4 UTF-16 code units** even though it consists of only **3 Unicode code points**, because the emoji 🚀 (U+1F680) requires two code units.

The two errors are caught with `try/catch` so the program continues running. In real programming, prefer checking bounds before calling rather than relying on exceptions for normal control flow.

## 3. Understanding exact index bounds

Let `n = text.length()`.

| Method | Valid condition | Invalid |
| --- | --- | --- |
| `text.charAt(i)` | `0 <= i && i < n` | `i < 0` or `i >= n` |
| `text.substring(begin)` | `0 <= begin && begin <= n` | `begin < 0` or `begin > n` |
| `text.substring(begin, end)` | `0 <= begin && begin <= end && end <= n` | Any violation |

Java throws **`StringIndexOutOfBoundsException`** when invalid indices are passed to the methods above.

Common errors:

~~~java
String s = "Hi"; // length() = 2.

// s.charAt(2);       // Invalid: valid indices are only 0, 1.
// s.charAt(-1);      // Invalid: no negative indices.
// s.substring(-1);   // Invalid: negative begin.
// s.substring(1, 3); // Invalid: end exceeds length().
// s.substring(2, 1); // Invalid: begin is greater than end.

String empty = s.substring(2); // Valid: empty string.
~~~

**Getting the last character** when the string is guaranteed non-empty:

~~~java
char last = s.charAt(s.length() - 1);
~~~

If `s.isEmpty()`, the expression `length() - 1` equals `-1` and will cause an exception. You must check:

~~~java
if (!s.isEmpty()) {
    char last = s.charAt(s.length() - 1);
    System.out.println(last);
}
~~~

If `s == null`, none of the three methods can be called and any call will throw `NullPointerException`. This **differs** from the empty string `""`: an empty string is an existing object with `length() == 0`, and `substring(0)` is valid.

## 4. Why does `substring` use an exclusive upper bound?

The **`[begin, end)`** interval design has three benefits:

1. The length of the slice equals **`end - begin`** measured in UTF-16 code units.
2. Two adjacent intervals meet cleanly at the boundary: `substring(0, k)` and `substring(k, n)` neither overlap nor skip any code units.
3. To extract from the beginning to the end, simply use `text.substring(0, text.length())`.

Example splitting before/after a `':'`:

~~~java
String record = "id:42";
int colon = record.indexOf(':');

if (colon >= 0) {
    String key = record.substring(0, colon);     // "id"
    String value = record.substring(colon + 1); // "42"
}
~~~

`indexOf` returns `-1` when the character is not found. If you forget to check the result, the bound calculation for `substring` may violate your intent even when it happens to stay within valid index bounds.

Also distinguish **part of a string** from **a new string with an independent object**: `substring` returns an immutable `String` result, but you should not rely on an assumption that the JVM always allocates a distinct object for every slice. Check **content** with `equals`, not `==`.

## 5. Unicode pitfall: indices in Java are UTF-16 indices

`length()` counts **code units**, not necessarily Unicode code points or displayed characters.

With `"A🚀B"`:

~~~text
Visible value     : A       🚀          B
Code unit index   : 0       1, 2        3
String end bound  :                        4
~~~

- `charAt(0)` holds `'A'`.
- `charAt(1)` returns the **high surrogate**, while `charAt(2)` returns the **low surrogate**. Each value is a `char`, **not the whole emoji**.
- `substring(1, 3)` extracts the **entire surrogate pair**, so it is the slice containing the emoji.
- `substring(1, 2)` extracts only **half of the surrogate pair**, which can produce an undesirable string containing an unpaired surrogate. Never slice between the two code units of a supplementary code point.

If you need to work with Unicode code points, use `codePointAt`, `codePointCount`, `offsetByCodePoints`, and `codePoints()`. For example, extracting the first code point:

~~~java
String word = "🚀Launch";
int cp = word.codePointAt(0);              // 0x1F680.
int end = word.offsetByCodePoints(0, 1);    // 2 code units.
String firstCodePoint = word.substring(0, end); // "🚀".
~~~

Note: **a code point does not necessarily equal one user-perceived character** (*grapheme cluster*), for instance a letter with combining diacritics can consist of multiple code points. The `length`/`charAt`/`substring` methods are not a full grapheme breaker.

## 6. Choosing the right method for the goal

| Requirement | Approach | Notes |
| --- | --- | --- |
| Measure length in UTF-16 | `text.length()` | Not always the number of code points |
| Get code unit at index `i` | `text.charAt(i)` | Check `0 <= i < length()` |
| Get from `begin` to end | `text.substring(begin)` | `begin == length()` returns `""` |
| Get interval `[begin, end)` | `text.substring(begin, end)` | End bound is exclusive |
| Read one code point | `text.codePointAt(i)` | `i` is still a UTF-16 index |
| Count code points | `text.codePointCount(0, text.length())` | Not counting graphemes |
| Avoid `NullPointerException` | Check `text != null` | Empty string differs from null |

## 7. Self-check exercises

**Exercise 1.** `String s = "abcdef";`. What are the values of `s.length()`, `s.charAt(2)`, and `s.substring(2, 5)`?

*Answer:* `6`, `'c'`, and `"cde"`.

**Exercise 2.** Given `String s = "Java";`, how do `s.substring(4)` and `s.charAt(4)` differ?

*Answer:* `substring(4)` returns an empty string; `charAt(4)` throws `StringIndexOutOfBoundsException`.

**Exercise 3.** Why does `s.substring(1, 3)` have length 2 instead of 3?

*Answer:* It only takes indices 1 and 2; the end bound 3 is **exclusive**.

**Exercise 4.** Does `"A🚀B".length()` equal 4 or 3? What does `substring(1, 3)` extract?

*Answer:* `length()` equals 4 code units; `substring(1, 3)` contains the complete emoji 🚀.

**Exercise 5.** How do you retrieve the last character of a string without throwing an error when the string is empty?

*Answer:* Check `!s.isEmpty()` before calling `s.charAt(s.length() - 1)`. If `s` could be null, check `s != null` first.

## Memory checklist

- [ ] `length()` counts UTF-16 code units, not necessarily code points.
- [ ] `charAt(i)` only accepts `0 <= i < length()`.
- [ ] `substring(begin, end)` extracts the interval **`[begin, end)`**, so the length is `end - begin`.
- [ ] `substring(length())` is valid, whereas `charAt(length())` is invalid.
- [ ] Do not call `charAt(length() - 1)` before checking for an empty string.
- [ ] Do not slice `substring` between the two surrogates of a non-BMP emoji.
- [ ] Methods do not modify the original `String`; verify results by **content**.

**Conclusion:** Think of `length()` as the **exclusive upper bound** of UTF-16 indices, use `charAt` to read one code unit, and use `substring` to extract the interval `[begin, end)`. When manipulating non-BMP Unicode, remember that one visible character can occupy multiple index positions.
