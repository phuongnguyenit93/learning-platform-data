# `String.indexOf(String)` and `indexOf(String, fromIndex)` — Searching Substrings from a Specified Position

## 1. Goals and Use Cases

`String.indexOf` finds the position where a **literal substring** appears within a `String`. In particular, the overload taking `fromIndex` lets you choose **where to start searching**. You can use it to locate delimiters, extract a data field, find the next occurrence, and list every match, including **overlapping** matches.

After this lesson, you should understand:

- How `indexOf(String str)` and `indexOf(String str, int fromIndex)` differ.
- `fromIndex` is the **inclusive index where searching starts**; it is not the number of characters to skip or an index into the substring `str`.
- The result is the starting index of the first match, measured in **UTF-16 code units**; if not found, `-1` is returned.
- How negative `fromIndex`, `fromIndex` equal to or greater than `length()`, empty substrings, empty target strings, and `null` are handled.
- How to use `indexOf` in an advancing loop, handle overlapping cases, and combine it safely with `substring`.
- The limitations of literal search when content involves case differences, Unicode, or word-based matching requirements.

## 2. Two Commonly Used Overloads

In `java.lang.String`, Java provides:

~~~java
int indexOf(String str)
int indexOf(String str, int fromIndex)
~~~

How to read them:

~~~java
String text = "Java JavaScript Java";

int first = text.indexOf("Java");     // 0
int second = text.indexOf("Java", 1); // 5
int third = text.indexOf("Java", 6);  // 16
~~~

`indexOf("Java")` searches from the start of the string; it can be thought of as `indexOf("Java", 0)` in terms of **result**. `indexOf("Java", 1)` excludes starting position `0` from the candidates, so it gets position `5`. `indexOf("Java", 6)` also skips the match starting at `5`, so it gets position `16`. The match at index `5` may extend past position `6`; the condition is still that the **match's starting point** must be greater than or equal to `fromIndex`.

Visualizing positions:

~~~text
Text:     J a v a   J a v a S c r i p t   J a v a
Index:    0 1 2 3 4 5 6 7 8 9 ...      15 16 17 18 19

"Java" starts at: 0, 5, 16
fromIndex = 0  -> returns 0
fromIndex = 1  -> returns 5
fromIndex = 5  -> returns 5 (inclusive)
fromIndex = 6  -> returns 16
~~~

In both overloads, the return value is an `int`:

- If found: `0 <= result < text.length()` for a **non-empty** substring.
- If not found: `result == -1`.
- For an **empty substring**, the result can also equal `text.length()`, because an empty string matches at the trailing boundary. This is an important exception to the inequality for non-empty results.

## 3. Exact Rules for `fromIndex`

Suppose `text` has length `n` in UTF-16 code units, and `needle` is the substring to find.

For a **non-empty** `needle`, `indexOf(needle, fromIndex)` finds the earliest occurrence whose **starting position is greater than or equal to `max(fromIndex, 0)`**. If none exists, it returns `-1`.

| Scenario | Example | Result |
| --- | --- | --- |
| Find first occurrence | `"banana".indexOf("ana")` | `1` |
| Start right at a match position | `"banana".indexOf("ana", 1)` | `1` |
| Skip an earlier match position | `"banana".indexOf("ana", 2)` | `3` |
| Negative `fromIndex` | `"banana".indexOf("ana", -100)` | `1`, equivalent to searching from `0` |
| `fromIndex` equals `length()`, non-empty needle | `"banana".indexOf("ana", 6)` | `-1` |
| `fromIndex` greater than `length()`, non-empty needle | `"banana".indexOf("ana", 999)` | `-1` |
| Substring longer than remaining text | `"banana".indexOf("ana", 4)` | `-1` |
| Target substring absent | `"banana".indexOf("xyz", 0)` | `-1` |

Note that `fromIndex` is **not an upper bound on the search**. The method can still match characters after `fromIndex`; it only restricts the candidate's **starting** position. For example, `"banana".indexOf("ana", 2)` returns `3` because `"ana"` starts at `3`.

### Empty Substring: A Separate Rule

When `needle.equals("")`, the result is:

~~~text
indexOf("", fromIndex) = min(max(fromIndex, 0), text.length())
~~~

Applying this to `"Java"` (`length() == 4`):

| Call | Result |
| --- | ---: |
| `"Java".indexOf("")` | `0` |
| `"Java".indexOf("", -10)` | `0` |
| `"Java".indexOf("", 2)` | `2` |
| `"Java".indexOf("", 4)` | `4` |
| `"Java".indexOf("", 100)` | `4` |

**Why isn't it `-1` when `fromIndex` is too large?** An empty substring matches at every valid boundary, including the end of the string, and Java clamps the result to `[0, length()]`. This rule is especially important in loops finding multiple occurrences.

### Empty Source String

~~~java
String empty = "";

System.out.println(empty.indexOf("x"));    // -1
System.out.println(empty.indexOf(""));     // 0
System.out.println(empty.indexOf("", 50)); // 0
~~~

An empty string contains no **non-empty** substrings, yet the empty string itself matches at the single boundary `0`.

## 4. What `indexOf` Does, and What It Does Not Do

`indexOf(String)` searches for an **exact contiguous sequence of characters**, not a regular expression (regex); it has no built-in notion of "whole words", does not automatically normalize Unicode, and does not ignore case differences.

Example:

~~~java
String text = "Java JavaScript";
System.out.println(text.indexOf("Java"));   // 0
System.out.println(text.indexOf("Java", 1)); // 5
System.out.println(text.indexOf("java"));   // -1
~~~

The match at `5` is **inside `JavaScript`**. If the goal is to find the standalone word `Java`, you must check word boundaries or use a parser with explicit rules. If the goal is to match a regex like `Ja.a`, use `Pattern`/`Matcher`; `indexOf("Ja.a")` only looks for a literal dot `.` in the text.

**Distinguishing overloads:** `text.indexOf('a', fromIndex)` uses the `char/int` overload; `text.indexOf("a", fromIndex)` uses the **`String`** overload. Simple cases may yield the same position, but the `int ch` overload also has rules for supplementary Unicode code points. This lesson focuses on searching for a **`String` substring**.

## 5. Complete Java 17+ Example, Verified by Compiling and Running

Create the file **`IndexOfSubstringDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class IndexOfSubstringDemo {
    public static void main(String[] args) {
        String text = "Java JavaScript Java";
        System.out.println("length=" + text.length());
        System.out.println("first=" + text.indexOf("Java"));
        System.out.println("from1=" + text.indexOf("Java", 1));
        System.out.println("from6=" + text.indexOf("Java", 6));
        System.out.println("missing=" + text.indexOf("Python", 0));
        System.out.println("negativeFrom=" + text.indexOf("Java", -100));
        System.out.println("tooLargeFrom=" + text.indexOf("Java", 999));
        System.out.println("emptyNegative=" + text.indexOf("", -3));
        System.out.println("emptyAt3=" + text.indexOf("", 3));
        System.out.println("emptyTooLarge=" + text.indexOf("", 999));
        System.out.println("nonemptyAtEnd=" + text.indexOf("Java", text.length()));
        System.out.println("emptyAtEnd=" + text.indexOf("", text.length()));

        String overlap = "bananana";
        String term = "ana";
        List<Integer> positions = new ArrayList<>();
        for (int from = 0, found;
             (found = overlap.indexOf(term, from)) != -1;
             from = found + 1) {
            positions.add(found);
        }
        System.out.println("overlapping=" + positions);

        positions.clear();
        for (int from = 0, found;
             (found = overlap.indexOf(term, from)) != -1;
             from = found + term.length()) {
            positions.add(found);
        }
        System.out.println("nonOverlapping=" + positions);

        String email = "user@example.com";
        int separator = email.indexOf("@");
        String domain = separator >= 0 ? email.substring(separator + 1) : "";
        System.out.println("domain=" + domain);

        String emoji = Character.toString(0x1F600);
        String mixed = "A" + emoji + "B" + emoji;
        System.out.println("mixedLength=" + mixed.length());
        System.out.println("emojiFirst=" + mixed.indexOf(emoji));
        System.out.println("emojiNext=" + mixed.indexOf(emoji, 2));
        System.out.println("lowSurrogate=" + mixed.indexOf(String.valueOf(mixed.charAt(2))));
        System.out.println("caseSensitive=" + "Java".indexOf("java"));
    }
}
~~~

Compile/run (verified in Java 17 compatibility mode):

~~~bash
javac --release 17 -encoding UTF-8 IndexOfSubstringDemo.java
java IndexOfSubstringDemo
~~~

Exact `stdout`:

~~~text
length=20
first=0
from1=5
from6=16
missing=-1
negativeFrom=0
tooLargeFrom=-1
emptyNegative=0
emptyAt3=3
emptyTooLarge=20
nonemptyAtEnd=-1
emptyAtEnd=20
overlapping=[1, 3, 5]
nonOverlapping=[1, 5]
domain=example.com
mixedLength=6
emojiFirst=1
emojiNext=4
lowSurrogate=2
caseSensitive=-1
~~~

**Output explanation:**

1. `"Java JavaScript Java"` has `length() == 20`. `"Java"` appears at UTF-16 indices `0`, `5`, `16`; the `fromIndex` values select the corresponding positions.
2. With `fromIndex = -100`, it searches as if from `0`. With `999`, `"Java"` cannot have a valid starting position, so `-1` is returned.
3. An empty substring matches at boundaries `0`, `3`, or `20` after clamping `fromIndex` to `length()`; a non-empty needle at `fromIndex = 20` returns `-1`.
4. In `"bananana"`, `"ana"` starts at `1`, `3`, `5`. Advancing `from = found + 1` allows overlapping matches; advancing `found + term.length()` skips matched characters.
5. The position of `'@'` in the email is checked before calling `substring(separator + 1)`, avoiding treating `-1` as if it were a found position.
6. `mixed` has six UTF-16 code units because each emoji `U+1F600` uses two code units. The two emojis start at indices `1` and `4`; a lone low surrogate at index `2` can still be found if you deliberately construct a substring containing just that code unit.
7. `"Java".indexOf("java")` returns `-1`: this search is case-sensitive.

## 6. Finding the Next Occurrence Using `fromIndex`

Common question: "I found one result; how do I continue?"

For a **non-empty** substring `needle`, we choose:

- **Allow overlapping:** `nextFrom = found + 1` (advance by one **UTF-16 code unit**).
- **Disallow overlapping:** `nextFrom = found + needle.length()` (skip the entire matched sequence).

Example `"bananana"` and `"ana"`:

~~~text
String:  b a n a n a n a
Index:   0 1 2 3 4 5 6 7
"ana":     1..3
"ana":         3..5
"ana":             5..7
Overlapping:          [1, 3, 5]
Non-overlapping:      [1, 5]
~~~

General pattern when you want **all starting positions, including overlapping ones**:

~~~java
static List<Integer> allPositions(String text, String needle) {
    if (needle.isEmpty()) {
        throw new IllegalArgumentException("needle must be non-empty");
    }

    List<Integer> positions = new ArrayList<>();
    for (int from = 0, found;
         (found = text.indexOf(needle, from)) != -1;
         from = found + 1) {
        positions.add(found);
    }
    return positions;
}
~~~

The snippet above is an **illustrative method**; you must import `java.util.List` and `java.util.ArrayList` when placing it inside a complete Java class (as in `IndexOfSubstringDemo`).

The `needle.isEmpty()` check cannot be omitted casually. Searching for `""` in a loop that only terminates on `-1` risks an **infinite loop**: once `from` exceeds `length()`, `indexOf("", from)` still returns `length()`, never becoming `-1`. If business logic needs the positions of all empty spans, explicitly define `0, 1, ..., text.length()`—that is, `length() + 1` UTF-16 boundaries—instead of using a non-empty needle search pattern.

For non-overlapping matches, replace just the single line `from = found + 1` with `from = found + needle.length()`; keep the non-empty needle guard.

### Be Careful with `-1`

Never treat `-1` as a valid position for `substring` or `charAt`:

~~~java
String record = "name=value";
int equalsAt = record.indexOf("=");

if (equalsAt >= 0) {
    String name = record.substring(0, equalsAt);
    String value = record.substring(equalsAt + 1);
    System.out.println(name + " => " + value);
}
~~~

If the separator is missing and you still execute `substring(0, equalsAt)`, you pass `-1` as an index and get an out-of-bounds error. In some cases like `substring(indexOf("@") + 1)`, the result `-1 + 1 == 0` **throws no error** yet silently returns the entire string; that is also a logic bug to avoid.

## 7. Meaning of Index Results When Unicode Is Present

Java `String` uses UTF-16. `length()`, `substring(...)`, and `indexOf(String, fromIndex)` operate in **UTF-16 code unit indices**.

Example:

~~~text
Displayed value:      A       😀       B       😀
Code point:         U+0041  U+1F600  U+0042  U+1F600

UTF-16 index:          0    1    2      3    4    5
Code unit:            0041 D83D DE00   0042 D83D DE00
                             \__/                \__/
                            one CP              one CP
String.length() == 6
~~~

Therefore:

~~~java
String emoji = Character.toString(0x1F600);
String s = "A" + emoji + "B" + emoji;

System.out.println(s.indexOf(emoji));     // 1
System.out.println(s.indexOf(emoji, 2));  // 4
~~~

The results `1` and `4` are **UTF-16 positions**, not code point ordinals. `fromIndex = 2` falls inside the first surrogate pair, so it does not match the emoji starting at `1` again; the next emoji starts at `4`.

More importantly, `indexOf(String)` matches **contiguous UTF-16 units**, so a needle intentionally containing **a lone surrogate code unit** can still be found inside a surrogate pair:

~~~java
String lowHalf = String.valueOf(s.charAt(2));
System.out.println(s.indexOf(lowHalf)); // 2
~~~

If you want to operate on complete Unicode code points, ensure your needle/boundaries do not split a surrogate pair. If you need the **position counted in code points**, convert the UTF-16 index `matchIndex` to the number of code points before the match position:

~~~java
int matchIndex = s.indexOf(emoji);
if (matchIndex >= 0) {
    int codePointsBefore = s.codePointCount(0, matchIndex);
    System.out.println(codePointsBefore); // 1
}
~~~

This assumes `matchIndex` is a valid code point boundary. For an unpaired surrogate match, the result cannot be treated as a complete Unicode character boundary.

Additionally, Unicode strings can have multiple encodings that look identical (such as precomposed `é` vs. `e` plus a combining accent). `indexOf` **does not normalize NFC/NFD** before searching. If business logic requires canonically equivalent matching, you can use `java.text.Normalizer` to normalize both data **and needle** under a consistent policy before comparing; when working with the normalized string, remember that returned indices belong to the **normalized string** and may not map directly back to the original string.

## 8. Distinguishing from `contains`, `startsWith`, and `lastIndexOf`

| Goal | Appropriate API | Result |
| --- | --- | --- |
| Only need to know whether a substring is present | `text.contains(needle)` | `boolean` |
| Need the position of the first occurrence | `text.indexOf(needle)` | `int`, or `-1` |
| Need the first occurrence from a position | `text.indexOf(needle, fromIndex)` | `int`, or `-1` |
| Need to check a prefix at a specific position | `text.startsWith(prefix, offset)` | `boolean` |
| Need to search from right to left | `text.lastIndexOf(needle)` or `lastIndexOf(needle, fromIndex)` | `int`, or `-1` |
| Need regular expressions or capture groups | `java.util.regex.Pattern` and `Matcher` | Regex-based match |

`contains` is convenient when the index is unused, though it does not return a position. `startsWith(prefix, offset)` checks **strictly at `offset`**, whereas `indexOf(prefix, offset)` can find a match at **any position from `offset` onward**. `lastIndexOf` has its own search direction and `fromIndex` rules; you cannot take `indexOf` examples as-is to infer all of its behavior.

## 9. Case-Sensitive and "Whole Word" Search

`indexOf` is case-sensitive:

~~~java
String headline = "Java Core";
System.out.println(headline.indexOf("java")); // -1
~~~

If business logic needs case-insensitive search, do not assume calling `toLowerCase()` is the right solution for every language and scenario. Case conversion can depend on locale, alter UTF-16 length, and shift index meanings; Unicode case folding and grapheme matching follow their own rules.

For text restricted to ASCII where the goal is merely checking containment, you can normalize inputs under a fixed policy (such as `Locale.ROOT`). If you need **indices in the original string**, verify how indices map after transformation; do not assume indices of a lowercased string match positions in the original string one-for-one. For natural-language searching, consider `Collator` or a suitable search engine.

`indexOf("Java")` can also find `"Java"` inside `"JavaScript"`. If "whole word" matching is required, you need boundary rules (whitespace, punctuation, Unicode letters, etc.) or a specific regex, not just a single `indexOf` call.

## 10. Performance and Proper Usage

- `indexOf` is well suited for **literal substring search**, especially when inputs and search rules are simple.
- Results are measured as **UTF-16 offsets**. When passing them to `substring`, you can use the index directly once boundaries are valid and `-1` has been checked.
- A **fixed runtime complexity** cannot be inferred from the API signature alone; JDK search implementations and optimizations can vary. For very large strings or many complex patterns, measure on real data.
- When scanning the same content repeatedly, avoid accidentally creating many large string copies and consider data structures/algorithms suited to the problem.
- `fromIndex` does not mutate the string. `String` is immutable; each call simply returns the matched position within the existing string.
- Do not assume the result is a visible-character (grapheme cluster) index. To slice by code point or grapheme, perform the appropriate boundary conversion.

## 11. Common Mistakes

1. **Confusing `fromIndex` with a starting offset in `needle`.** In reality, it is the search starting position in the **source string**.
2. **Overlooking the inclusivity of `fromIndex`.** `indexOf("ana", 1)` on `"banana"` immediately returns `1`; to find the next occurrence, use `found + 1` or `found + needle.length()` depending on the overlap policy.
3. **Failing to handle `-1`.** Can cause an exception in `substring` or a silent bug if `1` is added to `-1`.
4. **Using a loop that allows an empty needle.** Since `indexOf("", hugeIndex) == length()`, a loop waiting for `-1` may never terminate.
5. **Assuming an oversized `fromIndex` always returns `-1`.** The exception is searching for an **empty substring**: it returns `length()`.
6. **Advancing `fromIndex` by `needle.length()` when overlapping results are needed.** This misses `3` in the `"bananana"` example.
7. **Assuming `indexOf` supports regex or is case-insensitive.** The method searches **literally, case-sensitively**, and ignores word boundaries.
8. **Forgetting that the result is a UTF-16 index.** Can split a surrogate pair in half if indices are applied carelessly to Unicode text.
9. **Confusing `null` with `""`.** `text.indexOf((String) null)` throws `NullPointerException`; `text.indexOf("")` is valid and returns `0`.
10. **Applying indices obtained after Unicode/case normalization directly to the original string without checking.** Transformations can alter the code unit count; indices belong to the exact string that was searched.

## 12. Self-Check Exercises

**Question 1.** What does `"ababab".indexOf("ab", 2)` return?

**Answer:** `2`, because `fromIndex` includes position `2`.

**Question 2.** What does `"banana".indexOf("ana", 2)` return? Why?

**Answer:** `3`. The match at `1` starts before `fromIndex`, while the match at `3` is allowed.

**Question 3.** How do `"Java".indexOf("", 999)` and `"Java".indexOf("a", 999)` differ?

**Answer:** They return `4` and `-1`, respectively; an empty needle is clamped to the trailing boundary of the string.

**Question 4.** Given `"bananana"` and needle `"ana"`, what advancement from a match `found` captures all of `[1, 3, 5]`?

**Answer:** `from = found + 1`. Advancing by `found + needle.length()` yields `[1, 5]`.

**Question 5.** If `indexOf("@")` returns `-1`, should you immediately call `substring(index + 1)`?

**Answer:** No. `-1 + 1` becomes `0` and can return the entire string as an unintended business result. Check `index >= 0` first.

**Question 6.** Why is the second emoji in `"A😀B😀"` at UTF-16 index `4`?

**Answer:** The letter `A` uses one code unit; the first emoji uses two code units at indices `1` and `2`; the letter `B` is at index `3`, so the second emoji starts at index `4`.

**Question 7.** Can `text.indexOf(needle, fromIndex)` return an index **less than** `fromIndex` when `fromIndex` is non-negative?

**Answer:** No for a non-empty needle; it only accepts matches whose starting position is `>= fromIndex`. For an empty needle with `fromIndex > length()`, the result is clamped to `length()`, which is smaller than `fromIndex`.

## 13. References

- [Oracle Java SE 17 — `String.indexOf(String)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#indexOf(java.lang.String)): finding the first occurrence of a literal substring.
- [Oracle Java SE 17 — `String.indexOf(String, int)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#indexOf(java.lang.String,int)): `fromIndex` semantics, `-1` result, and empty needles.
- [Oracle Java SE 17 — `String.substring`, `codePointCount`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): APIs using/converting UTF-16 indices.
- [Oracle Java SE 17 — `Character`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html): code points, surrogate pairs, UTF-16.

**Takeaway:** `indexOf(needle, fromIndex)` returns the **starting UTF-16 index** of the first occurrence at position `>= fromIndex`, or `-1`. A negative `fromIndex` is treated as starting at `0`; an empty substring has its own `length()` clamping rule. When searching repeatedly, advance the starting point according to your **overlapping/non-overlapping** policy, and always check for `-1` before using an index for extraction.