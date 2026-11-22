# `lastIndexOf` and Reverse Search Direction in Java

`String.lastIndexOf(...)` is used to find the **last occurrence** of a character or substring, measured by its index in a `String`. It is useful when you need the last separator, a file extension, the position of the final slash in a path, or when searching backward from a specified position.

The key difference from `indexOf` is the **search direction and which match position is chosen**. Both return a starting index counted from **0 at the start of the string**, not a distance counted from the end. If not found, `-1` is returned.

> Core rule: `lastIndexOf` chooses the starting position of the **rightmost match** within the search range; `fromIndex`, when provided, bounds the search from right to left.

## 1. The Four Overloads of `String.lastIndexOf`

Java's `String` provides four main overloads:

| Method | What does it search for? | Where does it start? |
| --- | --- | --- |
| `lastIndexOf(int ch)` | A Unicode code point represented as `int` | From the end of the string toward the start |
| `lastIndexOf(int ch, int fromIndex)` | Code point `ch` | From position `fromIndex` (inclusive) toward the start |
| `lastIndexOf(String str)` | The full substring `str` | Last occurrence in the source string |
| `lastIndexOf(String str, int fromIndex)` | The full substring `str` | Match whose **starting index** does not exceed `fromIndex` |

Each overload returns an `int`: the **first index of the matched segment** on the source string's UTF-16 position scale, or `-1` when there is no match.

The `int` overloads accept a Unicode code point. For ordinary characters in the Basic Multilingual Plane (BMP), you can pass a `char` literal because Java automatically widens `char` to `int`. For non-BMP code points (such as certain emojis), `int` lets you search for an entire surrogate pair as a single code point; this is explained in the Unicode section.

The overloads accepting `String str` require a non-`null` argument `str`. A `null` argument does not mean "not found": it throws `NullPointerException`. If you need to handle missing search strings, check and decide the policy on the caller side.

## 2. Finding the Last Occurrence While Returning a Start-Relative Index

Consider `"abracadabra"`:

```text
Value: a b r a c a d a b r a
Index: 0 1 2 3 4 5 6 7 8 9 10
```

The character `'a'` appears at positions `0`, `3`, `5`, `7`, and `10`. Therefore:

- `indexOf('a')` returns `0`: the first occurrence.
- `lastIndexOf('a')` returns `10`: the last occurrence.
- `lastIndexOf("bra")` returns `8`: the last `"bra"` segment starts at index 8.
- `lastIndexOf("missing")` returns `-1`: no matching segment.

The name `lastIndexOf` describes how the **result is selected**; the index is still a Java index counted from the start. Never compute `length() - result` thinking that is the method's return position. Only if your problem genuinely needs the distance to the end should you calculate it yourself from the returned index according to the problem definition.

### Example 1: Distinguishing `indexOf` and `lastIndexOf`

Create file `LastIndexOfBasicsDemo.java`:

```java
public class LastIndexOfBasicsDemo {
    public static void main(String[] args) {
        String text = "abracadabra";

        System.out.println(text.indexOf('a'));
        System.out.println(text.lastIndexOf('a'));
        System.out.println(text.indexOf("bra"));
        System.out.println(text.lastIndexOf("bra"));
        System.out.println(text.lastIndexOf("BRA"));
        System.out.println(text.lastIndexOf('z'));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac LastIndexOfBasicsDemo.java
java LastIndexOfBasicsDemo
```

Output:

```text
0
10
1
8
-1
-1
```

`"BRA"` does not match `"bra"` because these searches are **case-sensitive**. `lastIndexOf` does not automatically strip accents, normalize Unicode, split words, or apply natural-language rules.

## 3. `fromIndex`: Searching Backward from a Specified Position

The two overloads with `fromIndex` let you restrict the portion of the source considered:

```java
lastIndexOf(int ch, int fromIndex)
lastIndexOf(String str, int fromIndex)
```

Searching proceeds in **decreasing index order**, from around `fromIndex` to the left. For a BMP character, position `fromIndex` itself is **included in the check** if valid.

Example:

```text
String text = "abracadabra";

Index:   0 1 2 3 4 5 6 7 8 9 10
Text:    a b r a c a d a b r a
                 ^
           fromIndex = 6
```

`text.lastIndexOf('a', 6)` does not consider `'a'` at 7 or 10; it moves backward from index 6 and encounters `'a'` at 5, so it returns `5`. Likewise, `text.lastIndexOf('a', 3)` returns `3` because the starting position **is included in the search range**.

A subtler point applies to *substrings*: `fromIndex` bounds the **starting position of the match**, not necessarily keeping every character of the match to the left of `fromIndex`.

For example, `"abcd".lastIndexOf("bcd", 1)` returns `1` even though the match has characters at indices `2` and `3`. The matched segment starts at index 1, so it still satisfies the condition.

### Example 2: Starting Position Included in the Result

Create `LastIndexOfFromIndexDemo.java`:

```java
public class LastIndexOfFromIndexDemo {
    public static void main(String[] args) {
        String text = "abracadabra";

        System.out.println(text.lastIndexOf('a', 6));
        System.out.println(text.lastIndexOf('a', 3));
        System.out.println(text.lastIndexOf('a', -1));
        System.out.println(text.lastIndexOf('a', 99));

        System.out.println(text.lastIndexOf("bra", 8));
        System.out.println(text.lastIndexOf("bra", 7));

        System.out.println("abcd".lastIndexOf("bcd", 1));
        System.out.println("abcd".lastIndexOf("bcd", 0));
    }
}
```

```bash
javac LastIndexOfFromIndexDemo.java
java LastIndexOfFromIndexDemo
```

Output:

```text
5
3
-1
10
8
1
1
-1
```

Explanation:

1. When `fromIndex` is 6, the nearest `'a'` to the left is at 5.
2. When `fromIndex` is 3, the character `'a'` right at index 3 is counted.
3. When `fromIndex < 0`, there is no valid starting position, so the result is `-1`.
4. When `fromIndex` exceeds the last index, searching effectively starts from the last valid position; the result is 10.
5. For `"bra"`, starting position 8 is included in `lastIndexOf("bra", 8)`; when limited to `fromIndex = 7`, it finds the previous match at 1.
6. `"bcd"` starts at 1 so `lastIndexOf("bcd", 1)` succeeds, even though the match extends through index 3.

If your specification means "search only within the **prefix** ending at an index", control the end boundary of the match rather than assuming `fromIndex` truncates the input data.

## 4. A Substring Can Match Multiple Times, Including Overlapping Matches

`lastIndexOf(String)` matches the entire contiguous character sequence. Overlapping occurrences remain valid candidates.

For example, `"bananana"` has `"ana"` starting at indices `1`, `3`, and `5`:

```text
b a n a n a n a
0 1 2 3 4 5 6 7
  └─ana─┘
      └─ana─┘
          └─ana─┘
```

Therefore:

- `lastIndexOf("ana")` → `5`.
- `lastIndexOf("ana", 4)` → `3`.
- `lastIndexOf("ana", 2)` → `1`.
- `lastIndexOf("ana", 0)` → `-1`.

### Example 3: Searching Backward Multiple Times

Create `ReverseSearchDemo.java`:

```java
public class ReverseSearchDemo {
    public static void main(String[] args) {
        String text = "bananana";

        System.out.println(text.indexOf("ana"));
        System.out.println(text.lastIndexOf("ana"));
        System.out.println(text.lastIndexOf("ana", 4));
        System.out.println(text.lastIndexOf("ana", 2));
        System.out.println(text.lastIndexOf("ana", 0));

        int at = text.lastIndexOf("ana");
        while (at >= 0) {
            System.out.println("match = " + at);
            at = text.lastIndexOf("ana", at - 1);
        }
    }
}
```

```bash
javac ReverseSearchDemo.java
java ReverseSearchDemo
```

Output:

```text
1
5
3
1
-1
match = 5
match = 3
match = 1
```

In the loop, `at - 1` ensures the next search considers **starting positions smaller than** the one just found. Calling it again with `at` itself could return the current position and cause an infinite loop. The pattern above lists **overlapping** matches as well. If you want to skip overlapping matches, design the index update policy for that specific goal.

## 5. Special Boundaries: Empty Strings, Negative Positions, and Out-of-Bounds Positions

The easiest edge cases to overlook are in the overloads searching for an **empty substring**.

For a string `s` of length `n`:

- `s.lastIndexOf("")` returns `n`, because an empty string can match at the boundary right after the last character.
- `s.lastIndexOf("", fromIndex)` returns `min(fromIndex, n)` if `fromIndex >= 0`; if `fromIndex < 0`, it returns `-1`.
- For a **non-empty** search string, `fromIndex < 0` returns `-1`; an overly large `fromIndex` is clamped to possible matching start positions.
- `s.lastIndexOf("longer-than-source")` returns `-1` if the entire substring cannot fit inside `s`.
- `s.lastIndexOf((String) null)` throws `NullPointerException`, unlike returning `-1` when not found.

### Example 4: Intentionally Testing Boundaries

Create `LastIndexOfEdgeCasesDemo.java`:

```java
public class LastIndexOfEdgeCasesDemo {
    public static void main(String[] args) {
        String text = "abc";

        System.out.println(text.lastIndexOf(""));
        System.out.println(text.lastIndexOf("", 1));
        System.out.println(text.lastIndexOf("", 100));
        System.out.println(text.lastIndexOf("", -1));

        System.out.println(text.lastIndexOf("abcd"));
        System.out.println(text.lastIndexOf('b', 100));
        System.out.println(text.lastIndexOf('b', -1));

        String empty = "";
        System.out.println(empty.lastIndexOf(""));
        System.out.println(empty.lastIndexOf('a'));
    }
}
```

```bash
javac LastIndexOfEdgeCasesDemo.java
java LastIndexOfEdgeCasesDemo
```

Output:

```text
3
1
3
-1
-1
1
-1
0
-1
```

**Do not equate an empty string with "not found".** If an empty search argument is invalid in your business rules, check `needle.isEmpty()` before calling, rather than relying on `lastIndexOf` to return `-1`.

## 6. `lastIndexOf` Indices Are UTF-16, Not Visible Character Positions

`String` stores characters with **UTF-16 code unit** indexing semantics. A Unicode character outside the BMP (such as U+1F600) is represented by **two `char`s**—a surrogate pair. Consequently, the index returned by `lastIndexOf` is also a **code unit position**, not a position counted by code points or grapheme clusters.

There are two ways of searching worth distinguishing:

- `lastIndexOf(int ch)` can accept a valid non-BMP Unicode code point, such as `0x1F600`, and find the matching surrogate pair. The result is the UTF-16 index of the **high surrogate**, i.e., the start of the pair.
- `lastIndexOf(String str)` searches for the exact sequence of code units present in substring `str`. You can pass a string containing the full surrogate pair.
- `lastIndexOf(char)` is not a separate overload; passing a `char` invokes the `int` overload after widening. A single `char` cannot represent an entire non-BMP code point.

### Example 5: Searching for an Emoji by Unicode Code Point

Create `LastIndexOfUnicodeDemo.java`:

```java
public class LastIndexOfUnicodeDemo {
    public static void main(String[] args) {
        String text = "A\uD83D\uDE00B\uD83D\uDE00";
        int emoji = 0x1F600;

        System.out.println(text.length());
        System.out.println(text.lastIndexOf(emoji));
        System.out.println(text.lastIndexOf(emoji, 3));
        System.out.println(text.lastIndexOf("\uD83D\uDE00"));
        System.out.println(text.lastIndexOf('\uDE00'));
        System.out.println(text.codePointCount(0, text.length()));
    }
}
```

```bash
javac LastIndexOfUnicodeDemo.java
java LastIndexOfUnicodeDemo
```

Output:

```text
6
4
1
4
5
4
```

The displayed string is `A😀B😀`: four code points but six UTF-16 code units. The first emoji has its high surrogate at position 1; the last emoji is at position 4. `lastIndexOf(emoji, 3)` searches backward from around index 3 and finds the first emoji at 1. Searching specifically for the low surrogate `'\uDE00'` returns 5, which is only the **second half of the last surrogate pair**, not representative of the whole emoji.

Additional note: even when counting by code points, a character perceived by a user may consist of multiple code points (such as combining accent marks or composite emojis). If you need to search by **grapheme cluster** or natural-language rules, `lastIndexOf` does not provide that capability on its own.

## 7. Practical Scenario: Extracting the Part After the Last Separator

When data is known to have a simple structure with a fixed separator, `lastIndexOf` combined with `substring` is a direct solution.

Suppose the file name is `report.final.csv` and you need the final extension:

```java
String filename = "report.final.csv";
int dot = filename.lastIndexOf('.');
String extension = dot >= 0 ? filename.substring(dot + 1) : "";
```

The resulting `extension` is `"csv"`. `dot + 1` is right because `substring(beginIndex)` starts **after** the dot. If no dot appears, `lastIndexOf` returns `-1`. In the example above, we intentionally choose an empty value when there is no dot.

### Example 6: Handling Multiple File Names

Create `FileExtensionDemo.java`:

```java
public class FileExtensionDemo {
    static String extension(String filename) {
        int dot = filename.lastIndexOf('.');
        return dot < 0 ? "" : filename.substring(dot + 1);
    }

    public static void main(String[] args) {
        System.out.println(extension("report.final.csv"));
        System.out.println(extension("README"));
        System.out.println("[" + extension("notes.") + "]");
        System.out.println(extension(".env"));
    }
}
```

```bash
javac FileExtensionDemo.java
java FileExtensionDemo
```

Output:

```text
csv

[]
env
```

In the output there is **a blank line** after `csv` because `README` has no dot. `"notes."` has a trailing dot so `substring(dot + 1)` is an empty string printed as `[]`. For `".env"`, this simple function treats `"env"` as the extension; many hidden-file conventions treat `.env` as a **file name with no extension**.

**Limitation of this example:** this is a *file-name string* rule, not a full path parser. A dot in a directory name, a URL path, hidden files, or multi-part extensions may require different policies. In applications handling cross-platform paths, consider `java.nio.file.Path` to separate the file name from the path before applying extension logic.

## 8. Practical Scenario: Extracting the Segment After a Multi-Character Separator

When a separator has multiple characters, you must add **the length of the entire separator**, not just 1.

```java
String message = "region::team::member";
String separator = "::";
int at = message.lastIndexOf(separator);
String last = at < 0 ? message : message.substring(at + separator.length());
```

The resulting `last` is `"member"`. If you add `at + 1`, the result will contain an extra leading `':'`.

### Example 7: Finding the Last Segment and Validating Errors

Create `LastSegmentDemo.java`:

```java
public class LastSegmentDemo {
    static String lastSegment(String text, String separator) {
        if (separator.isEmpty()) {
            throw new IllegalArgumentException("separator must not be empty");
        }

        int at = text.lastIndexOf(separator);
        return at < 0 ? text : text.substring(at + separator.length());
    }

    public static void main(String[] args) {
        System.out.println(lastSegment("a::b::c", "::"));
        System.out.println(lastSegment("single", "::"));
        System.out.println("[" + lastSegment("a::", "::") + "]");
    }
}
```

```bash
javac LastSegmentDemo.java
java LastSegmentDemo
```

Output:

```text
c
single
[]
```

The function chooses to return the entire input when no separator is present, and returns an empty string if the separator is at the end. This is an explicit **business policy** written in code, not an automatic feature of `lastIndexOf`. The function also rejects an empty separator because `lastIndexOf("")` has special semantics generally unsuitable for splitting segments.

## 9. Comparing `indexOf` and `lastIndexOf` When Choosing a Search Method

| Need | Suitable choice |
| --- | --- |
| Find the **first** position of a character or substring | `indexOf(...)` |
| Find the **last** position of a character or substring | `lastIndexOf(...)` |
| Find the first occurrence at position ≥ `fromIndex` | `indexOf(..., fromIndex)` |
| Find the last occurrence whose starting position is ≤ `fromIndex` | `lastIndexOf(..., fromIndex)` |
| Check whether a specific substring is contained | `contains(...)` or `indexOf(...) >= 0` |
| Check a specific prefix/suffix | `startsWith(...)` / `endsWith(...)` |
| Search by regular expression, capture groups, character classes | `Pattern`/`Matcher` and an appropriate regex |

`lastIndexOf` searches for a **literal** character or substring. For example, `lastIndexOf(".")` searches for a literal period, not interpreting `"."` as "any character" as in regex. When you only need the last separator, regex is unnecessary.

`lastIndexOf` may be optimized by the JVM at the implementation level, but the API does not guarantee a single complexity or memory profile across all JVMs. Do not draw absolute performance conclusions without measuring on real data and runtime.

## 10. Common Pitfalls

**Pitfall 1 — thinking the result is counted from the end.** `lastIndexOf` returns a **start-relative index**. For `"abcabc"`, `lastIndexOf("abc") == 3`, not 0.

**Pitfall 2 — treating `fromIndex` as an exclusive index.** Unlike `endIndex` in `substring`, `fromIndex` in `lastIndexOf` is **inclusive**. To skip the current match position, you typically call again with `at - 1`.

**Pitfall 3 — thinking the entire substring must lie to the left of `fromIndex`.** `fromIndex` restricts the **starting position**, not necessarily the ending position of the matched segment. `"abcd".lastIndexOf("bcd", 1)` returns 1.

**Pitfall 4 — failing to check `-1`.** `substring(text.lastIndexOf("::") + 2)` can behave wrongly when the separator is absent because `-1 + 2 == 1`. Check the match position before slicing.

**Pitfall 5 — adding 1 for a multi-character separator.** With `"::"`, you must add `separator.length()` when taking the part after the match.

**Pitfall 6 — overlooking empty strings.** `lastIndexOf("")` returns the string length, not `-1`. Define explicitly whether empty search strings are allowed.

**Pitfall 7 — assuming case-insensitive search.** `"Java".lastIndexOf("java") == -1`. If case-insensitive handling is desired, implement dedicated comparison rules, especially with Unicode and locales.

**Pitfall 8 — treating `char` as every Unicode character.** A non-BMP code point takes two UTF-16 code units. Use the `int` overload with the right code point, or use a full substring, and understand the returned index.

**Pitfall 9 — using `lastIndexOf` as a semantic parser.** Finding the last `'.'` is just a string operation; it does not understand file extensions, URL formats, escape sequences, or path rules on its own.

**Pitfall 10 — forgetting that the source string is immutable.** `lastIndexOf` only reads the `String` and returns a position; it does not modify contents or shift an internal search cursor.

## 11. Self-Check

### Question 1: Reverse search with a starting index

Given:

```java
String text = "one-two-two";
System.out.println(text.lastIndexOf("two"));
System.out.println(text.lastIndexOf("two", 5));
System.out.println(text.lastIndexOf('-', 6));
```

Answer:

```text
8
4
3
```

`"two"` appears at 4 and 8; searching from position 5 can only pick the match starting at 4. The `'-'` character is at indices 3 and 7; searching backward from 6 finds index 3.

### Question 2: Empty search string

Given:

```java
String text = "xyz";
System.out.println(text.lastIndexOf(""));
System.out.println(text.lastIndexOf("", 1));
System.out.println(text.lastIndexOf("", -1));
```

Answer:

```text
3
1
-1
```

The boundary right after the last character is also a valid match position for an empty string.

### Question 3: Extracting the suffix after the last colon

Given `String text = "a:b:c";`, write the slice to obtain `"c"`.

Solution:

```java
int separator = text.lastIndexOf(':');
String tail = separator < 0 ? text : text.substring(separator + 1);
```

The variable `tail` has value `"c"`. This is an illustrative snippet placed inside a method where `text` is already declared.

### Question 4: Overlapping matches

In `"aaaa"`, the segment `"aa"` starts at indices `0`, `1`, and `2`. Thus `lastIndexOf("aa")` returns `2`, and `lastIndexOf("aa", 1)` returns `1`. Overlapping does not disqualify a valid match position.

## Takeaway

**`lastIndexOf` searches from right to left yet returns a starting index counted from left to right.** The overloads with `fromIndex` find matches whose starting position is no greater than that boundary; the boundary is **inclusive**. A result of `-1` means not found, while searching for an empty string is a special case with valid results. When using an index to slice text, check for `-1`, add the exact separator length, and remember that `String` indices use UTF-16 code units.