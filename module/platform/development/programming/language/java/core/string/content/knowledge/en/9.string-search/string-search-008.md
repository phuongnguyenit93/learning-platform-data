# `String.indexOf` with `beginIndex` and `endIndex` Starting in Java 21

In Java 21, `java.lang.String` added two `indexOf` overloads that **restrict searching to a range of the source string**. This lets you search for a character/code point or substring within `[beginIndex, endIndex)` without creating a `substring` just to bound the region. The result is still the **position in the original string**, not a relative position inside the searched range.

The two new overloads:

```java
// Available since Java 21:
int indexOf(int ch, int beginIndex, int endIndex);
int indexOf(String str, int beginIndex, int endIndex);
```

These are **method signatures for reference**, not declarations you can place standalone in an arbitrary class. Calling them requires **compiling and running with JDK 21 or later**. The older forms `indexOf(int ch, int fromIndex)` and `indexOf(String str, int fromIndex)` only specify a starting point; they have no parameter to bound the end point.

## 1. Understanding the `[beginIndex, endIndex)` Range Correctly

The **half-open** interval convention is used consistently across these search APIs:

- `beginIndex`: starting position, **inclusive**.
- `endIndex`: ending position, **exclusive**.
- A valid range satisfies `0 <= beginIndex <= endIndex <= s.length()`.
- Indices use **UTF-16 code unit** units (just like `String.length()` and `substring()`), not Unicode code point counts or visible character counts.
- Returns the first matching position within the range, or `-1` if not found; the match result is an **absolute index in `s`**.

Example with `"cat|dog|cat|owl"` of length 15:

```text
Content:        c a t | d o g | c a t | o w l
UTF-16 index:   0 1 2 3 4 5 6 7 8 9 10 11 12 13 14
                                                  end = 15

Range [4, 11):  d o g | c a t       (positions 4..10)
Range [4, 10):  d o g | c a         (missing letter t at index 10)
```

Therefore:

```java
String s = "cat|dog|cat|owl";

System.out.println(s.indexOf("cat", 4, 11)); // 8
System.out.println(s.indexOf("cat", 4, 10)); // -1
System.out.println(s.indexOf('|', 4, 11));   // 7
System.out.println(s.indexOf('|', 8, 11));   // -1
```

On the first line, `"cat"` at positions 8–10 lies **completely** within `[4, 11)`, so the result is `8`. On the second line, the range stops before index 10 and does not contain all of `"cat"`, so the result is `-1`. The separator character at position 11 also lies outside a range with `endIndex = 11`.

## 2. Substring Search: `indexOf(String str, beginIndex, endIndex)`

Use this overload when you want to find **a complete substring** inside a window of the string.

```java
String s = "abc---abc---xyz";

System.out.println(s.indexOf("abc", 0, 3));   // 0
System.out.println(s.indexOf("abc", 3, 9));   // 6
System.out.println(s.indexOf("abc", 3, 8));   // -1
System.out.println(s.indexOf("xyz", 9, 15));  // 12
```

The third call returns `-1` because the window `[3,8)` only covers positions `3,4,5,6,7`; `"abc"` starts at 6, but its last character is at index 8, outside the range.

### Exact Matching Rule

For `s.indexOf(str, beginIndex, endIndex)`, if `str` is **non-empty**, Java finds the smallest index `k` satisfying:

- `k >= beginIndex`;
- `k + str.length() <= endIndex`;
- `s.startsWith(str, k)` returns `true`.

If no valid `k` exists, `-1` is returned. Thus, the **entire substring** must fit inside the window.

According to the Java 21 API, the result is equivalent in value to:

```java
String window = s.substring(beginIndex, endIndex);
int local = window.indexOf(str);
int result = local < 0 ? -1 : beginIndex + local;
```

The snippet above is **illustrative code inside a method body** where the variables already exist; it intentionally creates `window` to clarify the index conversion. The three-parameter overload lets you write directly:

```java
int result = s.indexOf(str, beginIndex, endIndex);
```

Per the API documentation, this overload avoids creating an intermediate `substring` object just to search. That is an advantage in clarity and avoids unnecessary temporary string creation; do not infer that every scenario is guaranteed to be faster or free of any internal allocations.

### The Result Is a Position in the Original String

```java
String s = "0123Java789";
System.out.println(s.indexOf("Java", 4, 8)); // 4
```

`Java` is the content of the window `[4,8)`, yet the result is `4`, **not 0**. This is a very common point of confusion when switching from `s.substring(begin,end).indexOf(...)`.

## 3. Character / Unicode Code Point Search: `indexOf(int ch, beginIndex, endIndex)`

The overload whose first parameter is `int ch` searches for a character/code point value. Java also accepts ordinary `char` expressions because `char` widens automatically to `int`:

```java
String s = "alpha|beta|gamma";

System.out.println(s.indexOf('|', 0, 10)); // 5
System.out.println(s.indexOf('|', 6, 10)); // -1
System.out.println(s.indexOf('a', 6, 10)); // 9
```

In this example, the first `'a'` in `[6,10)` is at index 9.

For `ch` in the BMP range (`0x0000` to `0xFFFF`), Java compares against each code unit via `charAt(k)`. For values outside the BMP, Java searches for the code point via `codePointAt(k)`. In both cases, the **returned index is the starting UTF-16 position of the occurrence**, not the code point ordinal.

Example with emoji 😀 (`U+1F600`) occupying two UTF-16 code units:

```java
String emoji = new String(Character.toChars(0x1F600));
String s = "A" + emoji + "B"; // UTF-16 length = 4

System.out.println(s.length());                       // 4
System.out.println(s.indexOf(0x1F600, 0, s.length())); // 1
System.out.println(s.indexOf(emoji, 0, s.length()));    // 1
```

Both searches on the same string return `1`, the position of the emoji's high surrogate. **Boundary note:** the `int ch` overload checks the code point at a starting index within the range; the `String str` overload requires the entire substring to lie within the range. When an `endIndex` cuts across a surrogate pair, do not assume the two overloads share the exact same "pattern length" rule—to bound a **complete Unicode character**, set the window along valid code point boundaries first (which can be computed with `offsetByCodePoints`).

## 4. Comparing Old and New Overloads

| Call | How it searches | Java |
| --- | --- | --- |
| `s.indexOf("cat")` | Searches the entire string | Before Java 21 |
| `s.indexOf("cat", fromIndex)` | Searches from a position to the end, no `endIndex` | Before Java 21 |
| `s.indexOf("cat", beginIndex, endIndex)` | Searches for substring **completely inside the window** | Since Java 21 |
| `s.indexOf('c')` | Searches for the first character in the entire string | Before Java 21 |
| `s.indexOf('c', fromIndex)` | Searches for character from `fromIndex` onward | Before Java 21 |
| `s.indexOf('c', beginIndex, endIndex)` | Only considers starting positions inside the window | Since Java 21 |

The one-parameter or two-parameter `fromIndex` forms handle out-of-range indices quite "leniently": negative indices are treated as searching from the start, and indices past the length normally yield `-1` for non-empty patterns. Meanwhile, the **three-parameter overloads validate strictly**:

```java
String s = "abc";

System.out.println(s.indexOf("a", -3)); // 0
System.out.println(s.indexOf("a", 99)); // -1

// s.indexOf("a", -3, 3); // Throws StringIndexOutOfBoundsException
// s.indexOf("a",  0, 4); // Throws StringIndexOutOfBoundsException
// s.indexOf("a",  2, 1); // Throws StringIndexOutOfBoundsException
```

Thus, the new overloads clearly distinguish **"pattern not found in a valid window"** (`-1`) from **"caller passed invalid boundaries"** (exception).

## 5. Complete Java 21+ Program You Can Compile and Run

Save the following full program into `BoundedIndexOfDemo.java`:

```java
public class BoundedIndexOfDemo {
    public static void main(String[] args) {
        String s = "cat|dog|cat|owl";

        System.out.println("length = " + s.length());
        System.out.println("cat in [4,11) = " + s.indexOf("cat", 4, 11));
        System.out.println("cat in [4,10) = " + s.indexOf("cat", 4, 10));
        System.out.println("dog in [4,7) = " + s.indexOf("dog", 4, 7));
        System.out.println("pipe in [4,11) = " + s.indexOf('|', 4, 11));
        System.out.println("pipe in [8,11) = " + s.indexOf('|', 8, 11));
        System.out.println("empty in [6,6) = " + s.indexOf("", 6, 6));
        System.out.println("empty in [15,15) = " + s.indexOf("", 15, 15));
        System.out.println("missing = " + s.indexOf("fox", 0, 15));

        try {
            s.indexOf("cat", -1, 5);
            System.out.println("unexpected success");
        } catch (StringIndexOutOfBoundsException expected) {
            System.out.println("invalid range rejected");
        }

        String emoji = new String(Character.toChars(0x1F600));
        String unicode = "A" + emoji + "B";
        System.out.println("UTF-16 length = " + unicode.length());
        System.out.println("emoji code point index = "
                + unicode.indexOf(0x1F600, 0, unicode.length()));
        System.out.println("emoji string index = "
                + unicode.indexOf(emoji, 0, unicode.length()));
    }
}
```

Compile/run with **JDK 21 or newer**:

```bash
javac BoundedIndexOfDemo.java
java BoundedIndexOfDemo
```

Expected output:

```text
length = 15
cat in [4,11) = 8
cat in [4,10) = -1
dog in [4,7) = 4
pipe in [4,11) = 7
pipe in [8,11) = -1
empty in [6,6) = 6
empty in [15,15) = 15
missing = -1
invalid range rejected
UTF-16 length = 4
emoji code point index = 1
emoji string index = 1
```

Pay special attention to `indexOf("", 6, 6)` returning `6`. An empty pattern can match right at the start of an empty window. Conversely, searching for a non-empty pattern or an ordinary character inside an empty window returns `-1`.

## 6. Boundary Rules, Errors, and Confusing Cases

### 6.1. Empty Ranges and Empty Patterns

When `String str` is the **empty string**, there is a valid match at `beginIndex`, even when `beginIndex == endIndex`, or when both equal `s.length()`:

```java
String s = "abc";
System.out.println(s.indexOf("", 0, 0)); // 0
System.out.println(s.indexOf("", 2, 2)); // 2
System.out.println(s.indexOf("", 3, 3)); // 3
System.out.println(s.indexOf("a", 2, 2)); // -1
System.out.println(s.indexOf('a', 2, 2)); // -1
```

There is no "character position" inside `[2,2)`, yet an empty pattern can match at a valid boundary. Do not accidentally call `indexOf("", ...)` when the intent is to search for a non-empty delimiter.

### 6.2. Invalid Boundaries

Both Java 21 three-parameter overloads throw `StringIndexOutOfBoundsException` if:

- `beginIndex < 0`;
- `endIndex > s.length()`;
- `beginIndex > endIndex`.

When validating inputs, you must also ensure `s` itself is not `null`. For the overload taking `String str`, `str == null` throws `NullPointerException`; an `int ch` argument has no `null` state. Choose a clear policy for `null` arguments rather than turning access errors into "not found".

Illustrative example showing upfront validation inside an application method:

```java
static int boundedSearch(String text, String needle, int begin, int end) {
    java.util.Objects.requireNonNull(text, "text");
    java.util.Objects.requireNonNull(needle, "needle");

    if (begin < 0 || begin > end || end > text.length()) {
        throw new IllegalArgumentException("Invalid search window");
    }
    return text.indexOf(needle, begin, end); // Requires Java 21+
}
```

This is an **illustrative method to place inside a class**, not a standalone program. Here we intentionally convert boundary errors into `IllegalArgumentException` per a custom API contract; if you want to keep the standard exception from `String.indexOf`, you can omit that check.

### 6.3. Case-Sensitive Matching and No Automatic Unicode Normalization

The new overloads only **narrow the search window**. They do not strip spaces, turn `"A"` into `"a"`, normalize Unicode, or perform natural-language matching:

```java
String s = "Java java";
System.out.println(s.indexOf("java", 0, s.length())); // 5
System.out.println(s.indexOf("JAVA", 0, s.length())); // -1
```

If an application needs case-insensitive search or complex Unicode handling, that is a separate requirement requiring appropriate normalization/collation rules. Do not blindly call `toLowerCase()` without choosing a locale and assume it works for every language.

## 7. Practical Application: Searching Within a Field or Message Segment

Consider a message with fields separated by `;`:

```text
id=7;role=user;token=abc
```

Problem: check whether the field `role=user` appears **inside the segment between the first and second semicolons**, avoiding false matches from another field.

Standalone program `FieldWindowDemo.java`:

```java
public class FieldWindowDemo {
    public static void main(String[] args) {
        String input = "id=7;role=user;token=abc";

        int firstSeparator = input.indexOf(';'); // 4
        int secondSeparator = input.indexOf(';', firstSeparator + 1); // 14

        int begin = firstSeparator + 1; // 5
        int end = secondSeparator;       // 14

        int role = input.indexOf("role=user", begin, end);
        int token = input.indexOf("token", begin, end);
        System.out.println("role offset = " + role);
        System.out.println("token offset = " + token);
    }
}
```

Run:

```bash
javac FieldWindowDemo.java
java FieldWindowDemo
```

Output:

```text
role offset = 5
token offset = -1
```

`role` lies inside `[5,14)` and is returned as the original string index `5`. The keyword `token` lies **outside the window**, so it returns `-1` even though it appears elsewhere in the full message.

In this example, we knew for sure there were two `;` characters. If real-world input may lack delimiters, **you must check for `-1` before constructing the search range**, and define behavior for malformed data. Do not hardcode the numbers from this example for arbitrary records.

This is only an example of searching a string slice; when parsing complex formats—especially with escaping, nested delimiters, or structured representations—use a proper parser matching the format specification instead of simple string searching.

## 8. When Should You Use the New Overloads?

**Worth considering** when you already have a defined `[beginIndex, endIndex)` region and only want to search inside it: content between two delimiters, a section of a document, a token in a header, or verifying a pattern appears completely within a segment.

Writing:

```java
int found = text.indexOf(needle, beginIndex, endIndex);
```

makes intent clearer than creating a temporary substring to search a window and then adding back the offset. For the `String str` overload, it also prevents a match starting inside the window from **extending past `endIndex`**.

**Not strictly necessary** if you need to search from a point all the way to the end of the string: `indexOf(str, fromIndex)` remains simpler and compatible with older JDKs. If a project still must compile/run on **Java 17**, the three-parameter overloads **do not exist yet**, so they cannot be used directly. A Java 17-compatible alternative can use `substring` on a validated range or a custom bounded search algorithm; if you write an alternative, remember to translate local indices back to original indices.

### Notes on UTF-16 Indices and Code Points

An emoji outside the BMP takes two code units; therefore `endIndex` and `beginIndex` are not code point ordinals. If you receive code point positions from another API, convert them to UTF-16 indices with `offsetByCodePoints` before calling `indexOf`. Also remember that a Unicode grapheme cluster can contain multiple code points; the `indexOf` overloads do not segment text by display clusters automatically.

## 9. Common Mistakes

1. **Assuming the returned index is relative to `beginIndex`.** False: `indexOf` returns a UTF-16 index on the original string; you do not add `beginIndex`.
2. **Treating `endIndex` as inclusive.** False: the right boundary is exclusive. A substring pattern must fit completely inside the region.
3. **Passing code point indices to UTF-16 index parameters.** Fails on strings with surrogate pairs; convert index units first.
4. **Equating the `int ch` and `String str` overloads in all Unicode cases.** For non-BMP code points, understand the starting-position check of `int ch` vs. the full-pattern-length check of `String str`.
5. **Ignoring exceptions on invalid ranges.** The three-parameter overloads do not silently accept negative indices, `endIndex` exceeding `length()`, or `beginIndex > endIndex`.
6. **Expecting an empty pattern to return `-1`.** `""` matches at `beginIndex`, even for a valid empty window.
7. **Using them on JDK 17 and thinking it is a logic bug in `indexOf`.** These APIs were added in Java 21; the right JDK and build/runtime configuration are required.
8. **Forgetting to check `-1` from delimiter searches before computing a window.** This can produce an invalid range or throw unexpected exceptions.
9. **Assuming the method automatically performs case-insensitive search.** It matches exact contents; language-aware matching requires a separate solution.

## 10. Self-Check

Given `String s = "red|blue|red";`, compute the results:

| Expression | Result | Explanation |
| --- | --- | --- |
| `s.indexOf("red", 0, 8)` | `0` | First occurrence found within the region |
| `s.indexOf("red", 4, 12)` | `9` | Only the second occurrence lies completely in the region |
| `s.indexOf("red", 4, 11)` | `-1` | Second pattern needs character at index 11, but right bound is exclusive |
| `s.indexOf('|', 4, 8)` | `8`? | **Check trap:** index 8 is excluded, so the right answer is `-1` |
| `s.indexOf("", 8, 8)` | `8` | Empty pattern matches at a valid boundary |

In the table, the row with a question mark is a self-check trap; **the actual result is `-1`**. Do not treat the decoy answer `8` as program output.

**Takeaway:** Java 21 adds three-parameter `indexOf` overloads to search within `[beginIndex, endIndex)`. For `String str`, the pattern must lie completely inside the range; for `int ch`, the occurrence index is checked by character/code point value. The result is a **UTF-16 index in the original string**, and invalid ranges are rejected with an exception.

**Official documentation:** [Java SE 21 — `String` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html).