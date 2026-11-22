# Empty Search Strings and Boundary Cases When Searching `String` in Java

When searching for a substring with `String.indexOf()`, `lastIndexOf()`, `contains()`, `startsWith()`, or `endsWith()`, it is easy to overlook the case where **the search string is `""` (empty string)**. Yet Java treats this as a **valid input**, and the results follow specific rules. Boundary indices such as `0`, `length()`, negative indices, or indices greater than the length can also yield results different from initial intuition.

This lesson focuses on three questions:

1. Why does searching for `""` still succeed even though it contains no characters?
2. How do search APIs handle **empty search strings, empty source strings, and out-of-range `fromIndex` values**?
3. How do you write safe code when the search string comes from user input or when iterating over multiple occurrences?

Examples apply to **Java 17+** and are based on the contract of `java.lang.String`.

## 1. Distinguishing Source String, Search String, and Search Position

In the expression:

```java
int position = text.indexOf(keyword);
```

- `text` is the **source string** (*haystack*).
- `keyword` is the **search string** (*needle*).
- `position` is the starting index of the first occurrence, or `-1` if not found.

`String` indices in Java start at `0`, use **UTF-16 code units**, and the end-of-string position (right after the last code unit) is `text.length()`.

For example, `"Java"` has length `4`:

```text
       J   a   v   a
Index  0   1   2   3
Positions where an empty string can be inserted:
       0   1   2   3   4
```

A helpful way to think about it: **an empty string fits at a boundary position without consuming any characters**. Therefore, you should not automatically interpret the result of searching for `""` as "not found".

Distinguish three values clearly:

- `""`: a valid `String` object with `length() == 0`.
- `" "`: a string containing a space, with `length() == 1`. Searching for a space is completely different from searching for an empty string.
- `null`: no reference to a `String` object; not a zero-length string.

## 2. Basic Results When the Search String Is `""`

Consider:

```java
String text = "Java";
System.out.println(text.indexOf(""));
System.out.println(text.lastIndexOf(""));
System.out.println(text.contains(""));
System.out.println(text.startsWith(""));
System.out.println(text.endsWith(""));
```

These lines print:

```text
0
4
true
true
true
```

Explanation by API:

| Call with `text = "Java"` | Result | Meaning |
| --- | --- | --- |
| `text.indexOf("")` | `0` | The first empty match position is right before `J`. |
| `text.lastIndexOf("")` | `4` | The last empty match position is right after the final `a`. |
| `text.contains("")` | `true` | The empty string is considered a substring of every `String`. |
| `text.startsWith("")` | `true` | Every string has an empty prefix. |
| `text.endsWith("")` | `true` | Every string has an empty suffix. |

This is **API-contracted behavior**, not a bug or a coincidence of a specific JVM version. In particular, `indexOf("")` returns `0` and `lastIndexOf("")` returns `length()`, not `-1`.

Conversely, when searching for a **non-empty string** that the source does not contain, `indexOf()` or `lastIndexOf()` returns `-1`:

```java
"Java".indexOf("Python")      // -1
"Java".lastIndexOf("Python")  // -1
"Java".contains("Python")     // false
```

The lines above are illustrative expressions inside a method, not a standalone Java file.

## 3. What If the Source String Itself Is Empty?

Given `String empty = "";`, the answers still follow the same rules:

```java
String empty = "";

System.out.println(empty.length());        // 0
System.out.println(empty.indexOf(""));     // 0
System.out.println(empty.lastIndexOf("")); // 0
System.out.println(empty.contains(""));    // true
System.out.println(empty.startsWith(""));  // true
System.out.println(empty.endsWith(""));    // true
System.out.println(empty.indexOf("a"));    // -1
System.out.println(empty.contains("a"));   // false
```

An empty source string has **one single boundary position**, namely position `0`, so searching for `""` succeeds there. However, it **contains no non-empty substrings**.

Cases worth remembering:

| Source string | Search string | `indexOf` | `lastIndexOf` | `contains` |
| --- | --- | ---: | ---: | --- |
| `""` | `""` | 0 | 0 | `true` |
| `""` | `"a"` | -1 | -1 | `false` |
| `"abc"` | `""` | 0 | 3 | `true` |
| `"abc"` | `"bc"` | 1 | 1 | `true` |
| `"abc"` | `"x"` | -1 | -1 | `false` |

Do not use `text.contains("")` to confirm that `text` is **non-empty**. Both `"abc".contains("")` and `"".contains("")` are `true`. To check for an empty source, use `text.isEmpty()` after ensuring the reference is not `null`.

## 4. `indexOf("", fromIndex)`: Forward Empty Search Position

`indexOf(String str, int fromIndex)` finds the first occurrence of `str` starting from index `fromIndex`. For `str = ""`, the result formula is very specific:

```text
indexOf("", fromIndex)
    = min(max(fromIndex, 0), text.length())
```

In other words, Java **clamps the index to the range from 0 to `length()`** when the search string is empty.

Example with `text = "Java"`, where `length() == 4`:

| `fromIndex` | `text.indexOf("", fromIndex)` | Explanation |
| ---: | ---: | --- |
| `-3` | `0` | Negative index is clamped to the start position. |
| `0` | `0` | Empty match right at the beginning of the string. |
| `2` | `2` | Empty match at the boundary before the third code unit. |
| `4` | `4` | Position right after the last character is allowed. |
| `9` | `4` | Exceeds length; result is clamped to `length()`. |

**Easy mistake:** if the search string is **non-empty**, passing a `fromIndex` greater than or equal to `length()` usually leaves no positions to match and returns `-1`. With an empty search string, even a very large `fromIndex` still returns `length()`:

```java
String text = "Java";
System.out.println(text.indexOf("a", 99)); // -1
System.out.println(text.indexOf("", 99));  // 4
```

Do not assume that "an out-of-bounds `fromIndex` makes every search return `-1`".

## 5. `lastIndexOf("", fromIndex)`: Searching Backward

`lastIndexOf(String str, int fromIndex)` finds the last occurrence whose starting position is **not greater than `fromIndex`**. For `str = ""`, the rule differs from `indexOf` on negative indices:

```text
If fromIndex < 0:
    lastIndexOf("", fromIndex) = -1
Otherwise:
    lastIndexOf("", fromIndex) = min(fromIndex, text.length())
```

Given `text = "Java"`:

| `fromIndex` | `text.lastIndexOf("", fromIndex)` | Explanation |
| ---: | ---: | --- |
| `-3` | `-1` | No valid starting position to the left of a negative index. |
| `0` | `0` | The first empty match is also the last allowed position. |
| `2` | `2` | Closest empty match from the left at position 2. |
| `4` | `4` | Empty match at the end of the string. |
| `9` | `4` | Index greater than length is clamped to the end of the string. |

Important contrast:

```java
String text = "Java";
System.out.println(text.indexOf("", -1));     // 0
System.out.println(text.lastIndexOf("", -1)); // -1
```

Both APIs interpret `fromIndex` according to their search direction. With a negative index, forward search still starts at the beginning of the string; backward search has no valid start point left and returns `-1`.

**Do not confuse `lastIndexOf("")` with `lastIndexOf("", 0)`**:

```java
"Java".lastIndexOf("")     // 4
"Java".lastIndexOf("", 0)  // 0
```

The overload without `fromIndex` considers the last empty match position across the entire string, whereas passing `0` only considers positions up to `0`.

## 6. Empty Prefix/Suffix and Index Checking with `startsWith("", offset)`

`startsWith(String prefix)` and `endsWith(String suffix)` return `true` when the argument is empty, even if the source string is also empty:

```java
"Java".startsWith("") // true
"Java".endsWith("")   // true
"".startsWith("")     // true
"".endsWith("")       // true
```

With the `offset` overload, the condition is stricter. `text.startsWith("", offset)` returns `true` **if and only if** `0 <= offset <= text.length()`:

| `text = "Java"`, `length() = 4` | Result |
| --- | --- |
| `text.startsWith("", -1)` | `false` |
| `text.startsWith("", 0)` | `true` |
| `text.startsWith("", 2)` | `true` |
| `text.startsWith("", 4)` | `true` |
| `text.startsWith("", 5)` | `false` |

Compare the two calls when `offset` exceeds the length:

```java
String text = "Java";
System.out.println(text.indexOf("", 5));     // 4
System.out.println(text.startsWith("", 5));   // false
```

`indexOf` normalizes the index for an empty search string; `startsWith` with an invalid `offset` returns `false`. Therefore, **do not extrapolate index rules from one API to another**.

## 7. Java 17+ Program: A Re-runnable Boundary Results Table

Create file `EmptySearchBoundaryDemo.java`:

```java
public class EmptySearchBoundaryDemo {
    public static void main(String[] args) {
        String text = "Java";
        int[] positions = {-3, 0, 2, 4, 9};

        System.out.println("length = " + text.length());
        System.out.println("indexOfEmpty = " + text.indexOf(""));
        System.out.println("lastIndexOfEmpty = " + text.lastIndexOf(""));
        System.out.println("containsEmpty = " + text.contains(""));
        System.out.println("startsWithEmpty = " + text.startsWith(""));
        System.out.println("endsWithEmpty = " + text.endsWith(""));

        for (int from : positions) {
            System.out.println(
                "from=" + from
                + " indexOf=" + text.indexOf("", from)
                + " lastIndexOf=" + text.lastIndexOf("", from)
                + " startsWith=" + text.startsWith("", from)
            );
        }

        String empty = "";
        System.out.println("empty.indexOfEmpty = " + empty.indexOf(""));
        System.out.println(
            "empty.lastIndexOfEmpty = " + empty.lastIndexOf(""));
        System.out.println("empty.containsEmpty = " + empty.contains(""));
        System.out.println("empty.indexOfA = " + empty.indexOf("a"));
    }
}
```

Compile and run:

```bash
javac EmptySearchBoundaryDemo.java
java EmptySearchBoundaryDemo
```

Output:

```text
length = 4
indexOfEmpty = 0
lastIndexOfEmpty = 4
containsEmpty = true
startsWithEmpty = true
endsWithEmpty = true
from=-3 indexOf=0 lastIndexOf=-1 startsWith=false
from=0 indexOf=0 lastIndexOf=0 startsWith=true
from=2 indexOf=2 lastIndexOf=2 startsWith=true
from=4 indexOf=4 lastIndexOf=4 startsWith=true
from=9 indexOf=4 lastIndexOf=4 startsWith=false
empty.indexOfEmpty = 0
empty.lastIndexOfEmpty = 0
empty.containsEmpty = true
empty.indexOfA = -1
```

Three differences you should be able to explain yourself:

1. `indexOf("", -3) == 0` yet `lastIndexOf("", -3) == -1`.
2. `indexOf("", 9) == 4` yet `startsWith("", 9) == false`.
3. Searching for `""` in source `""` still succeeds at `0`; searching for `"a"` in an empty source fails.

## 8. Boundary Indices When the Search String Is **Non-Empty**

Do not memorize only the empty-string case and misapply it to all search strings. With `text = "ababa"`, length `5`:

```java
String text = "ababa";

System.out.println(text.indexOf("aba"));       // 0
System.out.println(text.indexOf("aba", 1));    // 2
System.out.println(text.indexOf("aba", 3));    // -1

System.out.println(text.lastIndexOf("aba"));   // 2
System.out.println(text.lastIndexOf("aba", 1)); // 0

System.out.println(text.indexOf("ba", -10));    // 1
System.out.println(text.indexOf("ba", 5));      // -1
System.out.println(text.lastIndexOf("ba", 99)); // 3
System.out.println(text.lastIndexOf("ba", -1)); // -1
```

This is a Java fragment placed inside a method. These results show:

- `indexOf("aba", 1)` searches from index `1` to the end, so it skips the match at `0` and finds the match at `2`.
- `lastIndexOf("aba", 1)` accepts only starting points no greater than `1`, so it finds the occurrence at `0`.
- For a non-empty search string, `indexOf` from `length()` has no matching position left.
- For `lastIndexOf`, an index greater than the length can still find the string to the left, because it is a **backward** search.
- Two occurrences can **overlap**, like `"aba"` at indices `0` and `2`.

General model: `indexOf` finds the first occurrence starting **at `fromIndex` or later** (negative indices are treated as `0`); `lastIndexOf` finds the last occurrence starting **at most at `fromIndex`**. A result of `-1` means no occurrence satisfies the condition.

## 9. Watch Out for `null`: Not Equivalent to `""`

An empty search string is a **valid value**; `null` is **not a string**.

```java
String text = "Java";
String keyword = null;

// text.indexOf(keyword);  // Throws NullPointerException.
// text.contains(keyword); // Throws NullPointerException.
// text.startsWith(keyword); // Throws NullPointerException.
```

The three API call lines above are commented out so the example does not throw when compiled/run. Likewise, if the `text` variable itself is `null`, `text.indexOf(...)` also throws `NullPointerException` because there is no receiver object for the call.

If `keyword` comes from a UI, API, or configuration, **define the policy explicitly**. Depending on the feature, you might:

- Reject `null` and `""` as invalid keywords.
- Treat `""` as an unfiltered search condition (return all records), checking it explicitly rather than accidentally relying on `contains("")`.
- Allow `""` to model empty positions in a text-processing API.

These choices differ in business semantics; Java cannot guess which one the user wants.

## 10. Dangerous Bug: A Find-All Loop Getting Stuck on an Empty Keyword

When iterating over occurrences of a substring, developers commonly advance the next search position using `keyword.length()`:

```java
// Code illustrating the WRONG approach if keyword is "":
int from = 0;
int hit;
while ((hit = text.indexOf(keyword, from)) >= 0) {
    System.out.println(hit);
    from = hit + keyword.length();
}
```

If `keyword.equals("")`, then `keyword.length() == 0`. On the first iteration, `hit` can be `0`, and `from` stays `0`. The next iteration finds the exact same position: **the loop makes no progress**.

One way to prevent this is requiring `keyword` to be non-empty before searching. If a feature needs to list all **empty boundary points**, write a separate finite-step branch (from `0` to `text.length()`); do not reuse a loop written for non-empty substrings without fixing the index-increment rule.

### Java 17+ Example with Input Validation and Overlapping Match Support

Create file `SafeSubstringSearch.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class SafeSubstringSearch {
    static List<Integer> findAll(String text, String keyword) {
        Objects.requireNonNull(text, "text");
        Objects.requireNonNull(keyword, "keyword");

        if (keyword.isEmpty()) {
            throw new IllegalArgumentException("keyword must not be empty");
        }

        List<Integer> positions = new ArrayList<>();
        int from = 0;

        while (from < text.length()) {
            int found = text.indexOf(keyword, from);
            if (found == -1) {
                break;
            }
            positions.add(found);
            from = found + 1; // Allow the next match to overlap.
        }

        return positions;
    }

    public static void main(String[] args) {
        System.out.println(findAll("ababa", "aba"));
        System.out.println(findAll("aaaa", "aa"));
        System.out.println(findAll("", "a"));
        System.out.println(findAll("Java", "x"));

        try {
            findAll("Java", "");
        } catch (IllegalArgumentException ex) {
            System.out.println(ex.getMessage());
        }
    }
}
```

Run:

```bash
javac SafeSubstringSearch.java
java SafeSubstringSearch
```

Output:

```text
[0, 2]
[0, 1, 2]
[]
[]
keyword must not be empty
```

In `findAll()`:

- Check `null` before invoking methods on `text` or `keyword`.
- Reject `keyword.isEmpty()` so `indexOf("")` never keeps returning the same position.
- Advancing `from = found + 1` finds **overlapping occurrences as well**. If the problem only wants **non-overlapping** matches with a non-empty keyword, you can advance `from = found + keyword.length()`.
- The loop is finite because `from` increases and is bounded by the string length. When no results remain, `indexOf()` returns `-1` and the loop stops.

For a program that needs to expose empty match positions as a valid feature, describe it clearly: on a string with `n` UTF-16 code units there are **`n + 1` boundaries** (from `0` to `n`). This is a **UTF-16 index position** convention, not the number of grapheme boundaries perceived by a user.

## 11. Unicode: Search Positions Are Measured in UTF-16, Not Visible Emojis

`String`'s `indexOf()` and `lastIndexOf()` APIs return **UTF-16 code unit indices**. Example:

```java
String text = "A\uD83D\uDE00B"; // A😀B, the emoji is a surrogate pair.

System.out.println(text.length());        // 4
System.out.println(text.indexOf("B"));    // 3
System.out.println(text.indexOf(""));     // 0
System.out.println(text.lastIndexOf("")); // 4
System.out.println(text.indexOf("", 2));  // 2
```

In terms of visible character sequences, `A😀B` usually has three perceived characters. In UTF-16 indices, however, it has four code units: `A` at 0; the emoji's two code units at 1 and 2; `B` at 3.

Because an empty search string consumes zero code units, position `2` is still a **valid searchable UTF-16 boundary**, even though that boundary lies between the two halves of a surrogate pair. That is why you should not directly interpret a `""` match position as a "visible character position" in a UI.

If an application wants to step by Unicode code points, use APIs like `codePointAt()`, `codePointCount()`, and `offsetByCodePoints()` where appropriate. If it needs to operate on user-perceived characters (graphemes), proper grapheme segmentation rules are needed. **`String.length()` and `indexOf()` indices do not solve that automatically.**

String search comparisons via the APIs above are also **case-sensitive** and **do not normalize Unicode automatically**. For example, `"Java".indexOf("java") == -1`; and two visually identical Unicode representations can have different code unit sequences. If business rules require normalization, do so consistently before searching.

## 12. Additional Boundary Cases

| Case | Result / Note |
| --- | --- |
| `text.indexOf("")` | Always `0` for every non-`null` `String text`. |
| `text.lastIndexOf("")` | Always equals `text.length()`. |
| `text.contains("")` | Always `true` for any non-`null` `String`. |
| `text.indexOf("", Integer.MAX_VALUE)` | Equals `text.length()`. |
| `text.indexOf("", Integer.MIN_VALUE)` | Equals `0`. |
| `text.lastIndexOf("", Integer.MAX_VALUE)` | Equals `text.length()`. |
| `text.lastIndexOf("", Integer.MIN_VALUE)` | `-1`. |
| `text.startsWith("", text.length())` | `true`. |
| `text.startsWith("", text.length() + 1)` | `false`, assuming addition does not overflow (true for normal practical Java strings). |
| `text.indexOf("x")` when `x` is absent | `-1`. |
| `text.indexOf("") == -1` | Always `false` when `text` is non-`null`. |
| `text.contains(" ")` | Searches for a **literal space**, not synonymous with `contains("")`. |

Remember that `indexOf(int ch)` searches for a **character/code point** via an `int` parameter and does not take an empty search string; the `""` rules in this lesson apply to the overloads accepting **`String`** (or `CharSequence` for `contains()`).

## 13. Misconceptions That Easily Cause Bugs

1. **"With no characters, nothing can be found."** False: the empty string is a valid substring; `indexOf("")` returns `0`.
2. **"`lastIndexOf("")` always returns `0`."** False: on `"Java"`, it returns `4`.
3. **"`contains("")` means the source must have at least one character."** False: `"".contains("")` is still `true`.
4. **"An index greater than the length always makes `indexOf` return `-1`."** False when the search string is empty: `text.indexOf("", 999)` returns `text.length()`.
5. **"`indexOf` and `lastIndexOf` handle negative indices the same way."** False: `indexOf("", -1)` returns `0`; `lastIndexOf("", -1)` returns `-1`.
6. **"`startsWith("", offset)` is always true for every offset."** False: only true when `offset` is in `0..length()`.
7. **"An empty string is the same as `null`."** False: `""` is a valid object whereas `null` is not a `String` object.
8. **"A find-all loop can always increment by `keyword.length()` regardless of value."** False: when `keyword` is empty, an increment of `0` can cause an infinite loop.
9. **"Every search index is a visible character count."** False: `String` uses UTF-16 code-unit positions, even inside a surrogate pair.

## 14. Self-Check

**Question 1.** Given `String s = "abc";`, what are the following three results?

```java
System.out.println(s.indexOf(""));
System.out.println(s.lastIndexOf(""));
System.out.println(s.contains(""));
```

Answer:

```text
0
3
true
```

**Question 2.** Why do the following two calls produce different results?

```java
String s = "abc";
System.out.println(s.indexOf("", -5));
System.out.println(s.lastIndexOf("", -5));
```

The results are `0` and `-1`, respectively, because forward search clamps negative input to `0`, whereas backward search with `fromIndex < 0` has no valid starting point.

**Question 3.** If `String s = "";`, what are the results of `s.startsWith("")`, `s.endsWith("")`, and `s.indexOf("x")`?

Respectively: `true`, `true`, and `-1`. An empty source still has an empty prefix/suffix, yet does not contain `"x"`.

**Question 4.** A search box allows users to leave it blank, and the specification states "if nothing is entered, show all records." Should you just write `value.contains(keyword)`?

You should not rely solely on the implicit behavior of `contains("")`. Explicitly check `keyword == null`, `keyword.isEmpty()` (or `isBlank()` if business rules treat whitespace as blank), and then take the "no filter" branch. Doing so makes the data policy clear and prevents breakage if the code later changes APIs without preserving the same behavior.

**Question 5.** Why does a loop advancing `from = found + keyword.length()` get stuck when `keyword` is empty?

Because `keyword.length() == 0` and `indexOf("", from)` returns `from` right back if it is within range. Reject empty keywords or implement a separate boundary-iteration branch.

## Summary

- `""` is a valid search string: `indexOf("") == 0`, `lastIndexOf("") == length()`, `contains("") == true`, `startsWith("") == true`, and `endsWith("") == true`.
- `indexOf("", fromIndex)` clamps `fromIndex` to `0..length()`. `lastIndexOf("", fromIndex)` returns `-1` for negative indices, while non-negative indices are capped at `length()`.
- `startsWith("", offset)` returns `true` only when `offset` is within `0..length()`.
- For non-empty search strings, `-1` means no qualifying match; search results are measured in **UTF-16 code-unit indices**.
- Clearly distinguish `""`, whitespace, and `null`. When writing a loop to find multiple matches, **handle empty keywords explicitly** to avoid failing to advance.
- Edge cases are not exceptions to guess at: each method has its own contract; read and test the exact API you use.

## References

- [Java SE 21 API — `java.lang.String`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html): official contract for `indexOf(String)`, `indexOf(String, int)`, `lastIndexOf(String)`, `lastIndexOf(String, int)`, `contains(CharSequence)`, `startsWith(String, int)`, and `endsWith(String)`.
- [Java SE 21 API — `java.lang.Character`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Character.html): UTF-16, surrogate pairs, and Unicode code points.