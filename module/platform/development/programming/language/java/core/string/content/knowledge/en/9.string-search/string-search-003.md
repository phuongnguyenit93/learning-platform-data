# `indexOf` with a Character or Unicode Code Point in Java String

In Java, **String.indexOf(int ch)** finds the first occurrence of a character or a Unicode code point in a string; **String.indexOf(int ch, int fromIndex)** searches starting from a specified UTF-16 position. Both methods return the **starting position in the UTF-16 code unit sequence** or **-1 if not found**.

A common point of confusion is that the argument has type **int**, not just `char`. Because of that, they can search for Unicode code points outside the BMP (Basic Multilingual Plane) that occupy **two UTF-16 code units**, such as the emoji 😀 (U+1F600). However, the returned position is still a **UTF-16 index**, not a code point ordinal or a user-perceived character count.

## 1. Syntax and Meaning

Java provides two directly related overloads:

~~~java
int indexOf(int ch)
int indexOf(int ch, int fromIndex)
~~~

These are **API signatures for learning**, not methods you need to define yourself. Both overloads return `int`:

- **indexOf(ch)**: searches for the value `ch` from the start of the string; if it appears multiple times, returns the starting position of the first occurrence.
- **indexOf(ch, fromIndex)**: only considers occurrences whose starting position is **from `fromIndex` onward**.
- **Found**: returns the UTF-16 index of the match.
- **Not found**: returns **-1**; this is a sentinel value indicating no result, not a valid index.
- **Does not modify the string**: `String` is immutable; `indexOf()` only reads its contents.

When `ch` is in the BMP, the behavior is essentially searching for a `char` code unit equal to `ch`. When `ch` is a supplementary code point from **U+10000 to U+10FFFF**, the method searches for the corresponding **high surrogate + low surrogate pair** and returns the index of the high surrogate. For a negative `ch` or a value greater than **U+10FFFF**, there is no valid code point to match, so the result is `-1`.

## 2. Searching for a BMP Character with `char`

In Java, literals like **'a'**, **'J'**, **'?'**, **'7'** have type `char`. When passed to `indexOf(int)`, Java automatically widens the `char` value to `int`. You do not need to cast.

~~~java
String text = "Java Java";

System.out.println(text.indexOf('J'));     // 0
System.out.println(text.indexOf('a'));     // 1
System.out.println(text.indexOf('v'));     // 2
System.out.println(text.indexOf('z'));     // -1
System.out.println(text.indexOf('J', 1));  // 5
~~~

Explanation: the letter `'J'` appears at positions 0 and 5; `indexOf('J')` picks position 0, while `indexOf('J', 1)` skips position 0 and finds position 5. If the target value does not appear, `-1` is returned.

**There is no difference in result between the `char` value `'J'` and the `int` `74`** when searching this string:

~~~java
String text = "Java";
System.out.println(text.indexOf('J')); // 0
System.out.println(text.indexOf(74));  // 0
~~~

`74` is the code point U+004A of the letter `J`. Still, prefer a `char` literal when representing an easily recognizable BMP character and an `int` code point when handling Unicode in general.

### Case Sensitivity

`indexOf()` searches for the **exact character/code point value**; it does not automatically ignore case:

~~~java
String text = "Java";
System.out.println(text.indexOf('J')); // 0
System.out.println(text.indexOf('j')); // -1
~~~

If business logic requires case-insensitive searching, an appropriate processing rule must be defined. Converting the entire string to lowercase/uppercase can be affected by locale or change the number of characters; you should not assume such conversion preserves UTF-16 indices in all cases.

## 3. Why Is the Result a UTF-16 Index, Not a Code Point Ordinal?

Java `String` uses **UTF-16 code units**. A code point in the BMP normally occupies one code unit; a supplementary code point outside the BMP occupies **two** code units: a high surrogate followed by a low surrogate.

Consider the string:

~~~java
String text = "A😀B😀";
~~~

The content consists of four Unicode code points in order: `A`, `😀`, `B`, `😀`.

| UTF-16 index | Code unit | Meaning |
|---:|---|---|
| 0 | U+0041 | A |
| 1 | U+D83D | High surrogate of the first 😀 |
| 2 | U+DE00 | Low surrogate of the first 😀 |
| 3 | U+0042 | B |
| 4 | U+D83D | High surrogate of the second 😀 |
| 5 | U+DE00 | Low surrogate of the second 😀 |

Therefore:

- **text.length() = 6**: six UTF-16 code units.
- **text.codePointCount(0, text.length()) = 4**: four Unicode code points.
- **text.indexOf('B') = 3**: `B` is the third code point if counting from 1, yet it starts at UTF-16 index 3.
- **text.indexOf(0x1F600) = 1**: the first emoji starts at high surrogate index 1.
- **text.indexOf(0x1F600, 2) = 4**: starting position 1 is less than `fromIndex` 2, so the first emoji is skipped and the second emoji is found at index 4.

Code point ordinal, UTF-16 position, and visible character cluster (grapheme cluster) are different concepts. `indexOf()` returns a **UTF-16 offset**.

## 4. Searching for Non-BMP Code Points with `int`

An emoji like 😀 corresponds to **U+1F600** and has decimal value 128512. That value exceeds the range of `char`, so it must be represented as an **int**.

~~~java
String text = "A😀B😀";
int smile = 0x1F600;

System.out.println(text.indexOf(smile));      // 1
System.out.println(text.indexOf(smile, 2));   // 4
System.out.println(text.indexOf(smile, 4));   // 4
System.out.println(text.indexOf(smile, 5));   // -1
~~~

In the final search, `fromIndex=5` points to the low surrogate of the second emoji. The **starting positions** of both emoji pairs are 1 and 4, both smaller than 5; therefore no pair starting at or after index 5 is found.

A `char` literal only stores one 16-bit code unit, so you **cannot write** a supplementary emoji directly as `char '😀'`. Use `int 0x1F600`, `Character.toCodePoint(high, low)` when you already have a surrogate pair, or an API that returns a code point as `int`.

Example obtaining the search value from the string itself:

~~~java
String text = "A😀B";
int emojiCodePoint = text.codePointAt(1);
System.out.printf("U+%X%n", emojiCodePoint); // U+1F600
System.out.println(text.indexOf(emojiCodePoint)); // 1
~~~

**Key point:** `codePointAt(1)` returns U+1F600 by properly combining the surrogate pair; `indexOf(emojiCodePoint)` searches for the entire pair. Distinguish this from `text.charAt(1)`, which only returns the high surrogate.

## 5. `fromIndex`: Inclusive Starting Position

With **indexOf(ch, fromIndex)**, Java finds the first occurrence whose starting index is **greater than or equal to `fromIndex`**. The position `fromIndex` itself is included in the search range.

~~~java
String text = "ABABA";

System.out.println(text.indexOf('A'));      // 0
System.out.println(text.indexOf('A', 0));   // 0
System.out.println(text.indexOf('A', 1));   // 2
System.out.println(text.indexOf('A', 2));   // 2
System.out.println(text.indexOf('A', 3));   // 4
System.out.println(text.indexOf('A', 5));   // -1
~~~

Boundary notes:

- **Negative `fromIndex`**: searching starts as if from position 0.
- **`fromIndex` equal to 0**: equivalent to searching from the beginning of the string.
- **`fromIndex >= length()`**: for the `ch` overloads, there is no valid starting position left, so `-1` is returned.
- **Empty string**: has no code units to match, so `indexOf(int ch)` always returns `-1`.
- **`fromIndex` is a UTF-16 offset**, not a Unicode code point ordinal.

Searching for a supplementary code point requires two adjacent code units. If `fromIndex` lands in the middle of a pair (on the low surrogate), the pair whose high surrogate precedes `fromIndex` will **not** count as a new match starting at `fromIndex`.

## 6. A Valid Code Point Differs from a Surrogate Code Unit

The `int` argument to `indexOf()` is handled in two ways depending on its value range:

| Argument `ch` | How Java searches |
|---|---|
| 0 to U+FFFF | Matches a single UTF-16 code unit equal to `ch` |
| U+10000 to U+10FFFF | Matches the valid UTF-16 surrogate pair representing `ch` |
| Negative `ch` or `ch` > U+10FFFF | No match: `-1` |

In the range **U+D800 to U+DFFF**, values are surrogate code units, **not standalone Unicode scalar values**. However, because they fall within 0 to U+FFFF, `indexOf(int)` can still locate an individual high/low surrogate in the string.

~~~java
String text = "A😀B";

System.out.println(text.indexOf(0xD83D));   // 1: high surrogate
System.out.println(text.indexOf(0xDE00));   // 2: low surrogate
System.out.println(text.indexOf(0x1F600));  // 1: complete pair
System.out.println(text.indexOf(0x110000)); // -1: outside Unicode range
~~~

This is a useful distinction when debugging UTF-16:

- Searching **0xD83D** only identifies a high surrogate code unit and does not prove it is a complete 😀 emoji.
- Searching **0x1F600** requires **both** the high surrogate U+D83D and low surrogate U+DE00 adjacent to each other.
- On a `String` with unpaired surrogates or an invalid pair, searching for a single surrogate code unit may still succeed; searching for the corresponding supplementary code point will not match an invalid pair.

To check whether a supplementary value is a valid code point, you can use `Character.isValidCodePoint(int)`; if business logic requires a **Unicode scalar value**, you must also exclude the surrogate range U+D800–U+DFFF.

## 7. Complete Java 17+ Program

Save the file **StringIndexOfCodePointDemo.java** as UTF-8:

~~~java
public class StringIndexOfCodePointDemo {
    public static void main(String[] args) {
        String text = "A😀B😀";
        int emoji = 0x1F600;

        System.out.println("length=" + text.length());
        System.out.println("codePoints="
                + text.codePointCount(0, text.length()));

        System.out.println("A=" + text.indexOf('A'));
        System.out.println("B=" + text.indexOf('B'));
        System.out.println("missing=" + text.indexOf('X'));

        System.out.println("emoji-first=" + text.indexOf(emoji));
        System.out.println("emoji-from-2=" + text.indexOf(emoji, 2));
        System.out.println("emoji-from-4=" + text.indexOf(emoji, 4));
        System.out.println("emoji-from-5=" + text.indexOf(emoji, 5));

        System.out.println("high=" + text.indexOf(0xD83D));
        System.out.println("low=" + text.indexOf(0xDE00));
        System.out.println("invalid=" + text.indexOf(0x110000));

        int found = text.indexOf(emoji);
        if (found >= 0) {
            System.out.printf("found=U+%X%n", text.codePointAt(found));
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 StringIndexOfCodePointDemo.java
java StringIndexOfCodePointDemo
~~~

Exact output:

~~~text
length=6
codePoints=4
A=0
B=3
missing=-1
emoji-first=1
emoji-from-2=4
emoji-from-4=4
emoji-from-5=-1
high=1
low=2
invalid=-1
found=U+1F600
~~~

**Output explanation:**

1. `length=6` because there are two emojis, each occupying two UTF-16 code units.
2. `codePoints=4` because the content consists of `A`, emoji, `B`, emoji.
3. `'B'` is at UTF-16 index 3, even though it is the third code point from the start.
4. The indices of the two emojis are 1 and 4, which are the positions at the **start of each surrogate pair**.
5. `fromIndex=2` skips the pair starting at 1; `fromIndex=5` skips the pair starting at 4 as well.
6. `0xD83D` and `0xDE00` are handled as individual code unit values; `0x110000` is outside the Unicode range.
7. Only after ensuring `found >= 0` does the program call `codePointAt(found)` to read the matched code point, avoiding using `-1` as an index.

The program does not rely on how the console renders emojis to verify the result: the code point is printed as `U+1F600`.

## 8. Finding All Occurrences of a Code Point

When you need every position, you can call `indexOf(ch, fromIndex)` in a loop and update **fromIndex** after each match. For supplementary code points, advance past the entire matched UTF-16 pair to avoid repetition and clearly mark the next search starting point.

Standalone example, save **AllCodePointMatches.java**:

~~~java
public class AllCodePointMatches {
    public static void main(String[] args) {
        String text = "😀x😀y😀";
        int target = 0x1F600;
        int fromIndex = 0;

        while (true) {
            int found = text.indexOf(target, fromIndex);
            if (found == -1) {
                break;
            }
            System.out.println("match at UTF-16 index " + found);
            fromIndex = found + Character.charCount(target);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 AllCodePointMatches.java
java AllCodePointMatches
~~~

Output:

~~~text
match at UTF-16 index 0
match at UTF-16 index 3
match at UTF-16 index 6
~~~

Because each emoji takes two code units, the string `"😀x😀y😀"` has starting positions 0, 3, 6. `Character.charCount(0x1F600)` returns 2; after each match, `fromIndex` moves past the matched emoji.

If the goal is **all potentially overlapping occurrences** of a string pattern, the cursor advancement policy can differ. The example above only handles a single code point and retrieves subsequent occurrences.

### When You Only Need to Iterate Over Every Code Point, Not Search for One Value

`String.codePoints()` provides an `IntStream` of code points; it is suitable for processing **all** code points without needing to determine UTF-16 positions. If you need the exact matching start position in `String`, `indexOf(int)` or a loop over UTF-16 indices is more appropriate.

## 9. Distinguishing `indexOf(int)` from `indexOf(String)`

`String` also has the overloads **indexOf(String str)** and **indexOf(String str, int fromIndex)** to search for **an entire substring**, unlike searching for a single code point via `int`.

Example:

~~~java
String text = "abcabc";

System.out.println(text.indexOf('a'));     // 0: single character
System.out.println(text.indexOf("ab"));    // 0: substring
System.out.println(text.indexOf("bc", 3)); // 4: substring from index 3
~~~

For a non-BMP emoji, you can create a `String` representing the code point with:

~~~java
int cp = 0x1F600;
String emoji = new String(Character.toChars(cp));
String text = "A😀B";

System.out.println(text.indexOf(cp));    // 1
System.out.println(text.indexOf(emoji)); // 1
~~~

The result is the same in the example, yet the **parameter type determines the overload**: `int` searches for one code point (or one BMP code unit), while `String` searches for a sequence of code units. Do not accidentally search for the digit character string `"128512"` when your target is the emoji whose code point is 128512.

**Note the difference regarding empty strings:** searching for `""` with the `indexOf(String)` overload has a rule for matching an empty string at a valid position; searching by `int` has no concept of an "empty code point". The rules above for `fromIndex >= length()` apply to **indexOf(int ch, int fromIndex)**; do not transfer them verbatim to the `indexOf(String, int)` overload.

## 10. Common Mistakes and How to Avoid Them

1. **Using `'😀'` as a `char` literal:** a `char` holds only one UTF-16 code unit; emoji U+1F600 requires two code units. Use `int 0x1F600`.
2. **Interpreting the result as a code point ordinal:** the return value of `indexOf()` is a UTF-16 index. In `"A😀B"`, `'B'` is at position 3.
3. **Confusing `fromIndex` with code point ordinal:** `fromIndex=2` starts searching from UTF-16 index 2; it does not mean skipping two Unicode code points.
4. **Treating `-1` as a normal position:** before passing the result to `charAt()`, `codePointAt()`, or `substring()`, check `result >= 0`.
5. **Assuming `indexOf(0xD83D)` means searching for the full 😀 emoji:** that only searches for the high surrogate; to match the full code point, use `0x1F600`.
6. **Expecting `indexOf()` to ignore case, strip accents, or normalize Unicode:** it searches by code unit sequence; extended matching rules must be designed explicitly.
7. **Seeing `String.indexOf('x')` and `String.indexOf("x")` and assuming all rules are identical:** a `char` argument is widened to `int`, whereas `"x"` is a `String`; the overloads differ, especially for empty-string matching rules.
8. **Computing indices by visible character count:** emojis can combine multiple code points and combining marks; UTF-16 indices do not map directly to display positions.
9. **Slicing a string at an index assumed to be a code point boundary:** if `indexOf(int)` returns the start of a surrogate pair, capturing the full supplementary code point requires ending at `start + Character.charCount(ch)`, not assuming `start + 1`.
10. **Using a Unicode string search result as an index for another system:** other libraries or protocols may measure offsets in UTF-8 bytes, code points, or grapheme clusters; convert explicitly before exchanging indices.

## 11. Self-Check Exercises

Given:

~~~java
String s = "x😀y😀";
~~~

Predict the results:

1. What are `s.length()` and `s.codePointCount(0, s.length())`?
2. What is `s.indexOf('y')`?
3. What is `s.indexOf(0x1F600)`?
4. What is `s.indexOf(0x1F600, 2)`?
5. What is `s.indexOf(0x1F600, 5)`?
6. Does `s.indexOf(0xD83D)` necessarily verify a complete 😀 emoji?

**Answers and explanations:**

1. **6 and 4**: `x`, emoji, `y`, emoji have 4 code points but 6 UTF-16 code units.
2. **3**: `x` is at 0; the first emoji occupies 1–2; `y` starts at 3.
3. **1**: the first emoji has its high surrogate at 1.
4. **4**: skips the pair starting at 1 and finds the second pair at 4.
5. **-1**: `fromIndex` 5 lies after the last starting point 4.
6. **No**: `0xD83D` only checks for a single high surrogate code unit and does not confirm the full `U+D83D U+DE00` pair.

**Conclusion:** use **indexOf(int ch)** to find a BMP character or Unicode code point; use **indexOf(int ch, int fromIndex)** when continuing a search from an offset. When searching for supplementary code points, Java matches the **surrogate pair**, yet **every returned index and `fromIndex` is still measured in UTF-16 code units**. Always check for **-1** and be careful with surrogate pair boundaries.
