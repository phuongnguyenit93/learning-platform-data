# regionMatches() for Comparing a String Region in Java

## 1. Objectives and Use Cases

When comparing two strings, sometimes you **do not need to compare their entire contents**. For example: checking whether four characters in the middle of two identifiers match; comparing a segment starting at a specific position in text; or checking a region **case-insensitively**.

`String.regionMatches()` does exactly this: it compares **two contiguous regions of the same length** specified by offsets and a character-unit count. The method returns a `boolean`, **does not modify the source strings**, and does not allocate a new substring.

After this lesson, you will be able to:

1. Correctly use both **overloads** of `regionMatches()`.
2. Determine `toffset`, `ooffset`, and `len` accurately; distinguish **start position**, **length**, and **end index**.
3. Predict `true`/`false` when regions match, differ in characters, go out of bounds, or have length `0`.
4. Understand `ignoreCase`, Unicode/locale limitations, and UTF-16 index units.
5. Compare it against `equals()`, `equalsIgnoreCase()`, `startsWith()`, `substring()`, and `matches()`.
6. Write a wrapper helper to guard against `null`, negative parameters, and bounds before using it in business logic.

Prerequisites: `String`, 0-based indexing, `length()`, `charAt()`, `boolean`, and method calls. Standalone examples use **Java 17+**.

## 2. Two Overloads and Parameter Meanings

Java provides two forms:

~~~java
public boolean regionMatches(int toffset,
                             String other,
                             int ooffset,
                             int len);

public boolean regionMatches(boolean ignoreCase,
                             int toffset,
                             String other,
                             int ooffset,
                             int len);
~~~

General syntax:

~~~java
left.regionMatches(leftOffset, right, rightOffset, length);
left.regionMatches(ignoreCase, leftOffset, right, rightOffset, length);
~~~

Where:

| Parameter | Type | Role |
| --- | --- | --- |
| `left` (receiving object) | `String` | First string (`this`) |
| `toffset` / `leftOffset` | `int` | Starting index of the region in `left` |
| `other` / `right` | `String` | Second string |
| `ooffset` / `rightOffset` | `int` | Starting index of the region in `right` |
| `len` / `length` | `int` | **Number of UTF-16 units** to compare in each region, not the end index |
| `ignoreCase` | `boolean` | `true`: ignore case differences per `Character` rules; `false`: exact comparison |

The four-parameter form performs an exact (case-sensitive) comparison. The five-parameter form lets you choose case behavior via `ignoreCase`.

**Key point:** `len` is a single length applied to both regions; the method does not allow one side to be longer than the other and trim to fit.

## 3. Visualizing Offsets

Consider two strings:

~~~text
left  = "prefix-Java-END"
         012345678901234
                ^^^^
                positions 7..10 = Java

right = "Start-Java-OK"
         0123456789012
               ^^^^
               positions 6..9 = Java
~~~

We compare **four UTF-16 units** starting at index `7` of `left` and index `6` of `right`:

~~~java
String left = "prefix-Java-END";
String right = "Start-Java-OK";

boolean same = left.regionMatches(7, right, 6, 4);
System.out.println(same); // true
~~~

Both regions are `"Java"`, so the result is `true`, even though the two strings **are not equal overall**.

If we increase `len` to `6`, the compared regions become `"Java-E"` and `"Java-O"`, yielding `false`:

~~~java
System.out.println(left.regionMatches(7, right, 6, 6)); // false
~~~

**Do not confuse with `substring(begin, end)`:** `substring(7, 11)` takes an **exclusive end index** as its second argument, whereas `regionMatches(7, right, 6, 4)` takes a **length of 4** as its last argument. Mixing up those two conventions is a very common bug.

## 4. Exact Matching: Four Parameters

Syntax:

~~~java
boolean result = first.regionMatches(
        firstOffset, second, secondOffset, count);
~~~

Positions are compared from left to right. With the four-parameter form, both regions must have the exact same sequence of **UTF-16 code units**.

~~~java
String a = "--JAVA--";
String b = "xxJAVAyy";
String c = "xxJavaYY";

System.out.println(a.regionMatches(2, b, 2, 4)); // true
System.out.println(a.regionMatches(2, c, 2, 4)); // false
~~~

Uppercase `"JAVA"` and `"Java"` differ at corresponding characters, so they do not match in exact mode.

If you only want to know whether the entire strings have the same content, use `equals()`:

~~~java
boolean allEqual = a.equals(b);              // false
boolean areaEqual = a.regionMatches(2, b, 2, 4); // true
~~~

Do not use `regionMatches()` in place of `equals()` when the requirement is comparing the **entire** content. A region check can return `true` while the prefix, suffix, or total length differs.

## 5. Ignoring Case: Five Parameters

The five-parameter version adds an `ignoreCase` flag at the start:

~~~java
String left = "prefix-Java-END";
String right = "Start-jAvA-OK";

System.out.println(left.regionMatches(7, right, 6, 4));
// false

System.out.println(left.regionMatches(false, 7, right, 6, 4));
// false

System.out.println(left.regionMatches(true, 7, right, 6, 4));
// true
~~~

Meaning:

- `ignoreCase = false`: checks that the regions match **exactly**.
- `ignoreCase = true`: checks equivalence **case-insensitively** using `Character`'s mechanism; `'J'` and `'j'` can be treated as equivalent.

There is no need to allocate two lowercased strings via `toLowerCase()` beforehand when you only need to compare a region using `regionMatches(true, ...)` rules.

### Not Equivalent to Natural-Language Text Comparison

`regionMatches(true, ...)` **does not use `Locale`** and does not replace *collation* algorithms across languages. According to the Java 17 Javadoc, this form compares **Unicode code point** sequences in the regions; when ignoring case, the mechanism converts case via `Character.toUpperCase(int)` followed by `Character.toLowerCase(int)`.

Consequently, `ignoreCase`:

- Is not a language-specific search and comparison algorithm.
- Does not strip Vietnamese tone marks or auto-normalize Unicode.
- Does not guarantee handling all *full case folding* rules that can expand one letter into multiple code points.
- Does not allow two regions of different UTF-16 lengths to match.

If business logic requires locale-specific ordering or equivalence, consider `java.text.Collator` or an appropriate text-processing library; security/identifier requirements may need **exact comparison** rather than ignoring case.

## 6. Boundary Conditions: Offsets, Length, and Empty Regions

For `len >= 0`, the safest mental model is that both half-open index intervals must be valid:

~~~text
Left region:  [toffset, toffset + len)
Right region: [ooffset, ooffset + len)
~~~

The interval `[a, b)` includes index `a` but **excludes** index `b`.

Validity conditions when checking proactively:

~~~text
toffset >= 0
ooffset >= 0
len >= 0
toffset <= left.length()
ooffset <= right.length()
len <= left.length() - toffset
len <= right.length() - ooffset
~~~

When an offset is negative or a region extends past the string's length, the method returns `false` (assuming `other` is valid)—unlike `substring()`, which typically throws an exception on invalid indices.

Examples:

~~~java
String a = "Java";
String b = "JAVA";

System.out.println(a.regionMatches(0, b, 0, 1));  // true
System.out.println(a.regionMatches(1, b, 1, 3));  // false
System.out.println(a.regionMatches(-1, b, 0, 2)); // false
System.out.println(a.regionMatches(0, b, 0, 5));  // false
System.out.println(a.regionMatches(4, b, 4, 0));  // true
~~~

The last line compares two **empty regions** at the end of both strings; with two valid offsets and `len = 0`, there are no characters to differ, so it returns `true`.

**Important:** enforce `len >= 0` as a precondition in your program. Do not rely on negative-length behavior, as it is not a meaningful region-comparison request and results can be surprising. When receiving offsets from users or untrusted data, validate arguments before calling.

### Why Check Bounds with Subtraction?

In a custom helper, the condition:

~~~java
len <= text.length() - offset
~~~

is generally safer than `offset + len <= text.length()` when offset/len come from arbitrary integers, because integer addition can **overflow**. Before subtracting, ensure `offset` lies within `[0, text.length()]`.

### null Is Not Treated as a Normal false

~~~java
String source = "Java";
String other = null;

// source.regionMatches(0, other, 0, 2); // NullPointerException
~~~

An `other == null` argument throws `NullPointerException`; a `source == null` receiver also cannot invoke the method. Decide your `null` contract: reject with an explicit exception, or return `false` through a custom wrapper helper.

## 7. Unicode: Offset/Len Count UTF-16, Not Perceived Characters

`toffset`, `ooffset`, and `len` are all measured in **UTF-16 code units** (16-bit `char` units). A Unicode code point outside the BMP, such as the emoji `😀`, is represented by a **surrogate pair** of two UTF-16 units.

~~~java
String text = "A😀Z";

System.out.println(text.length()); // 4
System.out.println(text.codePointCount(0, text.length())); // 3
~~~

Diagram:

~~~text
Displayed:         A      😀       Z
UTF-16:           [A] [high][low] [Z]
Index:             0    1    2    3
UTF-16 length:                   4
Code points:                     3
~~~

To compare the **entire emoji**, `len` is `2`, not `1`:

~~~java
String a = "A😀Z";
String b = "X😀Y";
System.out.println(a.regionMatches(1, b, 1, 2)); // true
~~~

If `len = 1`, only half of the surrogate pair enters the comparison region. That can produce a result that looks right yet **does not reflect comparing a full emoji**:

~~~java
String a = "A😀Z";
String b = "X😁Y";

// Two different emojis with the same high surrogate.
System.out.println(a.regionMatches(1, b, 1, 1)); // true
System.out.println(a.regionMatches(1, b, 1, 2)); // false
~~~

**Lesson:** align region boundaries at the **start/end of a code point**, avoiding splitting inside a surrogate pair. When computing indices in code points, use `offsetByCodePoints()` to convert to appropriate UTF-16 offsets before calling:

~~~java
String text = "A😀Z";
int start = text.offsetByCodePoints(0, 1); // 1
int end = text.offsetByCodePoints(start, 1); // 3
int len = end - start; // 2 UTF-16 code units

System.out.println(text.regionMatches(start, "😀", 0, len)); // true
~~~

**Another note:** a code point is still not necessarily a *grapheme cluster* (user-perceived character). For example, `"é"` can be encoded as a single code point or as `"e\u0301"` (e + combining acute accent). Those two strings do not share the same UTF-16 code-unit sequence; `regionMatches()` does not auto-normalize them. If business logic needs canonical equivalence, look at `java.text.Normalizer` and agreed comparison rules.

## 8. When to Use regionMatches Instead of Other APIs?

| Purpose | Suitable API | Reason |
| --- | --- | --- |
| Compare **two full strings** exactly | `a.equals(b)` | Clear intent, no offset math needed |
| Compare two full strings case-insensitively | `a.equalsIgnoreCase(b)` | Directly expresses intent |
| Compare **two arbitrary regions** in two strings | `a.regionMatches(offsetA, b, offsetB, len)` | Supports offsets on both sides |
| Compare two regions ignoring case | `a.regionMatches(true, offsetA, b, offsetB, len)` | Includes `ignoreCase` flag |
| Check a prefix at a position in one string | `a.startsWith(prefix, offset)` | Clearer when the compared region in the pattern always starts at 0 |
| Check a suffix | `a.endsWith(suffix)` | No need to compute the start offset manually |
| Extract a region to use as a `String` value | `a.substring(begin, end)` | Returns a substring rather than a boolean |
| Find the location of a fragment at an unknown offset | `a.indexOf(fragment)` | Returns the index or `-1` |
| Match a regular expression | `Pattern`/`Matcher` or `matches()` | Use when the pattern is a regex, not two regions at known offsets |

Example checking a prefix starting at the third position:

~~~java
String log = "--ERROR: disk full";
String prefix = "ERROR";

System.out.println(log.regionMatches(2, prefix, 0, prefix.length())); // true
System.out.println(log.startsWith(prefix, 2)); // true
~~~

Both work well; when simply testing a `prefix`, `startsWith(prefix, 2)` is usually easier to read.

Compare with:

~~~java
String a = "prefix-Java-END";
String b = "Start-Java-OK";

boolean same = a.substring(7, 11).equals(b.substring(6, 10));
~~~

The result is also `true` if the indices are valid. However, this creates **substring values** just to compare; `regionMatches()` directly expresses region comparison without requiring the caller to allocate substrings. Do not assume it is always faster in every environment; measure in practice if the code is a bottleneck.

## 9. Standalone Java 17+ Example

Create file **`RegionMatchesDemo.java`**:

~~~java
public class RegionMatchesDemo {
    public static void main(String[] args) {
        String left = "prefix-Java-END";
        String right = "Start-Java-OK";
        String mixed = "Start-jAvA-OK";

        System.out.println(left.regionMatches(7, right, 6, 4));
        System.out.println(left.regionMatches(7, right, 6, 6));
        System.out.println(left.regionMatches(7, mixed, 6, 4));
        System.out.println(left.regionMatches(true, 7, mixed, 6, 4));
        System.out.println(left.regionMatches(false, 7, mixed, 6, 4));

        System.out.println(left.regionMatches(-1, right, 6, 4));
        System.out.println(left.regionMatches(7, right, 6, 99));
        System.out.println(left.regionMatches(
                left.length(), right, right.length(), 0));

        String smile = "A😀Z";
        String grin = "X😁Y";
        System.out.println(smile.regionMatches(1, grin, 1, 1));
        System.out.println(smile.regionMatches(1, grin, 1, 2));

        System.out.println(left.startsWith("Java", 7));
        System.out.println(left.equals(right));
    }
}
~~~

Compile and run:

~~~bash
javac RegionMatchesDemo.java
java RegionMatchesDemo
~~~

**Exact** stdout:

~~~text
true
false
false
true
false
false
false
true
true
false
true
false
~~~

Group-by-group explanation:

1. `"Java"` at offset `7` of `left` matches `"Java"` at offset `6` of `right`: `true`.
2. Comparing six units gives `"Java-E"` and `"Java-O"`, which differ: `false`.
3. `mixed` contains `"jAvA"`, so case-sensitive mode yields `false`; `ignoreCase = true` yields `true`; `false` yields `false`.
4. Negative offset or overly large `len`: `false`; empty regions at the end of both strings: `true`.
5. Emojis `😀` and `😁` share the **same high surrogate**, so comparing `len = 1` (only the high surrogate) outputs `true`; comparing full `len = 2` outputs `false`.
6. `startsWith("Java", 7)` returns `true`, while `equals(right)` returns `false` because the full strings differ.

The program is a single standalone file with matching class and file names and requires no external libraries beyond the JDK.

## 10. Writing a Region-Comparison Helper with Input Validation

In an API receiving offsets/lengths from outside, you can publish a clear contract: **return `false` if either string is `null`, if `len` is negative, or if a region goes out of bounds**.

~~~java
public final class RegionUtils {
    private RegionUtils() {}

    public static boolean sameRegion(
            String left, int leftOffset,
            String right, int rightOffset,
            int len, boolean ignoreCase) {

        if (left == null || right == null || len < 0
                || leftOffset < 0 || rightOffset < 0) {
            return false;
        }
        if (leftOffset > left.length()
                || rightOffset > right.length()) {
            return false;
        }
        if (len > left.length() - leftOffset
                || len > right.length() - rightOffset) {
            return false;
        }
        return left.regionMatches(
                ignoreCase, leftOffset, right, rightOffset, len);
    }
}
~~~

This is a standalone **utility class snippet** in Java source form; if you want to save it separately, create `RegionUtils.java`. Every condition has a purpose:

- Check `null` so it does not throw an unintended `NullPointerException`.
- Require `len >= 0` because a negative length is meaningless under the chosen contract.
- Validate offsets against each string's length.
- Compare against `length() - offset` to avoid addition that could overflow `int`.
- Finally delegate to `regionMatches()`.

Testing the helper:

~~~java
System.out.println(RegionUtils.sameRegion(
        "prefix-Java", 7, "JAVA", 0, 4, true)); // true
System.out.println(RegionUtils.sameRegion(
        null, 0, "JAVA", 0, 4, true));          // false
System.out.println(RegionUtils.sameRegion(
        "Java", 0, "Java", 0, -1, false));      // false
~~~

**There is no single null policy right for every program.** Another API might choose to throw `IllegalArgumentException` or `NullPointerException` to signal caller errors. What matters is a clear contract and consistent testing.

## 11. Complexity and Effective Usage

Algorithmically, comparing two regions of `len` UTF-16 units takes at most work proportional to the region length, typically described as **O(len)**; if an early mismatch occurs, comparison can stop early. Extra memory in normal usage is **O(1)** because no two separate substrings are allocated.

However, do not infer that every JDK version shares the exact same micro-optimizations or runtime for a specific case; Unicode case folding carries its own processing cost.

Effective practices:

- Use `regionMatches()` when **start positions are already known** in both strings.
- If you must locate an unknown position first, use `indexOf()` or a suitable search algorithm.
- If **full-string comparison** is needed, `equals()`/`equalsIgnoreCase()` communicates intent more clearly.
- If locale-aware text comparison or normalized Unicode equivalence is needed, define business requirements before choosing the API.
- When comparing secret data requiring timing-attack resistance, do not assume `regionMatches()` is constant-time; it is not designed to guarantee that property.

## 12. Tiered Exercises

### Exercise 1 — Reading Positions

Given `left = "abc-JAVA-xyz"` and `right = "12-JAVA-45"`, compute the offsets for the two `"JAVA"` regions and use `regionMatches()` to compare exact four units. Predict the result before running.

### Exercise 2 — Case Sensitivity

Compare `"Java"` with `"jAvA"` using the four-parameter and five-parameter overloads respectively. Explain why `ignoreCase = true` changes the result.

### Exercise 3 — Valid Arguments

With `"abc"` and `"ABC"`, test `toffset = -1`, `ooffset = -1`, `len = 4`, then `toffset = 3`/`ooffset = 3`/`len = 0`. Note why each returns `false` or `true`; do not confuse empty regions with out-of-bounds regions.

### Exercise 4 — Comparing via substring vs. regionMatches

Write both ways to compare the corresponding regions in `"prefix-Java-END"` and `"Start-Java-OK"`. Choose clear variable names so readers do not confuse `len` with `substring()`'s end index. Point out why `regionMatches()` needs no substring allocation at the call site.

### Exercise 5 — Different Emoji Characters

Given `"A😀B"` and `"X😁Y"`, try `len = 1` and `len = 2` at offset `1`. Explain via UTF-16 surrogate pairs. Recompute the indices when prepending another emoji to the start of the string.

### Exercise 6 — Creating a Safe Helper

Implement `sameRegion(...)` accepting nullable inputs. Write at least six test cases: matching regions, differing regions, ignoreCase, null, negative offset, out-of-bounds, and empty region. Explain why checking `len > length - offset` is safer than addition-based checks in code receiving external integers.

### Exercise 7 — Choosing the Right API

For three requirements—"two full names are equal", "string starts with `ERROR` at index `3`", and "the middle region of two paths matches"—choose `equals()`, `startsWith(prefix, offset)`, or `regionMatches()` respectively and explain the differences.

### Exercise 8 — Unicode Normalization

Compare `"é"` with `"e\u0301"` using `regionMatches()`. Then apply `java.text.Normalizer.normalize(..., Normalizer.Form.NFC)` to both and compare again. Explain why similar visual appearance does not imply identical UTF-16 code-unit sequences.

## 13. Common Mistakes and Checklist

| Mistake | Consequence | How to Avoid |
| --- | --- | --- |
| Confusing `len` with end index | Wrong region compared or out of bounds | Remember regions are `[offset, offset + len)` |
| Using 1-based offsets like ordinal numbers | Off-by-one character shift | Java indices start at `0` |
| Expecting `regionMatches()` to compare full strings | May return `true` when differences lie outside the region | Use `equals()` for full comparison |
| Using four-parameter form expecting case-insensitivity | `"Java"` differs from `"java"` | Use five-parameter form with `ignoreCase = true` |
| Assuming `ignoreCase` is locale-aware comparison | Wrong for certain languages and business rules | Identify locale, use collation APIs when appropriate |
| Assuming `len = 1` covers one emoji | Surrogate pair may need two `char`s | Align bounds to UTF-16 boundaries of code points |
| Passing `other = null` | May throw NPE | Check null beforehand per contract |
| Passing `len < 0` expecting a meaningful result | Invalid region-comparison request | Reject negative lengths in helpers |
| Using `substring()` with bad bounds just to compare | Can throw exceptions or create intermediate values | Use `regionMatches()` when offsets are known |
| Believing the method normalizes Unicode | Two encodings of the same form can differ | Normalize beforehand if business logic requires it |
| Using it as a constant-time secret comparison | No constant-time guarantee | Use APIs suited for security tasks |

**Pre-call checklist:**

1. Are there exactly **two strings** and **two known offsets**?
2. Is `len` the count of **UTF-16 code units**, not the end index?
3. Are both segments long enough? Are `null` and negative arguments handled?
4. Do you need to ignore case? If yes, do the locale-independent rules of `regionMatches(true, ...)` satisfy your business rules?
5. If emojis or combining characters exist, do the region boundaries fall on proper Unicode units?
6. Is the `boolean` return value actually checked/used?

**Rule to remember:** `regionMatches()` compares **a region in the current string** against **a same-length region in another string**, returning `true/false` without mutating data. Indices and lengths are measured in **UTF-16**; the `ignoreCase` flag controls case matching, **not natural-language comparison**.

## 14. Standard Reference Documentation

- [Java SE 17 — String.regionMatches(int, String, int, int)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#regionMatches(int,java.lang.String,int,int)): exact-match overload and offset/len semantics.
- [Java SE 17 — String.regionMatches(boolean, int, String, int, int)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#regionMatches(boolean,int,java.lang.String,int,int)): ignoreCase overload and Unicode/locale rules.
- [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): `length()`, `offsetByCodePoints()`, `equals()`, `startsWith()`, and `substring()`.
- [Java SE 17 — Character](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html): Unicode code points, surrogate pairs, and case mapping.
- [Java SE 17 — Collator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Collator.html), [Normalizer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html): locale-dependent comparison and normalization when business rules require them.
