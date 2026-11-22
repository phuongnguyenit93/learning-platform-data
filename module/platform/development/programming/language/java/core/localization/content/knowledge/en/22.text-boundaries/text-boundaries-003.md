# BreakIterator: following, preceding, isBoundary, and UTF-16 Indexes in Java

When a user places the cursor in the middle of a string, wants to select the nearest word, move by one "visible character", or slice a text segment, **the index of a Java `String` is not necessarily the boundary the user expects**. Java provides `java.text.BreakIterator` to find text boundaries according to rules suited to each type: character, word, line, and sentence. Three methods that are very easy to confuse are **`following(int)`**, **`preceding(int)`**, and **`isBoundary(int)`**.

This lesson explains in detail:

- A boundary is actually a **position between UTF-16 code units**, not a word ordinal number.
- `following(offset)` finds the boundary **strictly greater than** `offset`; `preceding(offset)` finds the boundary **strictly less than** `offset`; `isBoundary(offset)` checks **`offset` itself**.
- `BreakIterator.DONE`, start/end-of-string cases, invalid offsets, and the iterator's current state.
- Why emojis, non-BMP characters, and combining marks make `String.length()`, `codePointCount`, and "user-visible characters" differ.
- How to use boundary results with `substring` and handle selection/cursor movement.
- Why you cannot take code point indexes, UTF-8 byte offsets, or word counts and pass them directly to `following`.

The examples target **Java 17+**, using `Locale.ROOT` or an explicit locale and deterministic output snippets; for word/sentence segmentation rules that depend on JDK locale data, the lesson focuses on **API invariants** rather than asserting that every JDK version splits words identically.

## 1. What Is BreakIterator?

`BreakIterator` is an abstract class in the `java.text` package. You obtain an implementation from a factory:

| Factory | Purpose |
| --- | --- |
| `BreakIterator.getCharacterInstance(locale)` | Text-unit boundaries used for character navigation; not simply a single UTF-16 `char` |
| `BreakIterator.getWordInstance(locale)` | Boundaries of segments that may include words, whitespace, and punctuation |
| `BreakIterator.getLineInstance(locale)` | Positions where lines may break according to language rules |
| `BreakIterator.getSentenceInstance(locale)` | Sentence boundaries |

An instance works only on **the assigned text**:

```java
import java.text.BreakIterator;
import java.util.Locale;

BreakIterator boundaries =
        BreakIterator.getWordInstance(Locale.ROOT);
boundaries.setText("Hello, Việt Nam!");
```

This is a **fragment** and must be placed inside a Java method. After `setText`, the iterator knows which string to scan. Calls to `first()`, `last()`, `next()`, `previous()`, `following(...)`, and `preceding(...)` can update the **current position**.

`BreakIterator` does not slice or delete strings itself; it returns **offsets**. Extracting the corresponding content typically uses `String.substring(start, end)` with two validated indexes.

### A Boundary Is a Position, Not a Character

The string `"cat"` has three UTF-16 code units, yet has **four possible boundary positions**:

```text
String:            c   a   t
UTF-16 index:      0   1   2
Boundary slots:   0 | 1 | 2 | 3
                 ^   ^   ^   ^
```

With `getCharacterInstance`, a simple ASCII string like `"cat"` has boundaries `0, 1, 2, 3`. Boundary `3` is the **end of the string** (`String.length()`), not the index of a character existing at position 3.

Word or sentence boundaries are usually **sparser** than character boundaries: the interval from `start` to `end` can contain many UTF-16 code units. The exact meaning of "boundary" depends on the chosen iterator type.

## 2. Why Are Offsets UTF-16, Not Code Points?

Java `String` stores strings as **UTF-16 code units**. A Unicode character in the BMP typically occupies one `char` code unit; many non-BMP code points require **two** `char` values forming a surrogate pair.

Example `"A😀B"`:

```text
Visible content:         A       😀       B
Code point:             U+0041  U+1F600   U+0042
Code point count:          1       1        1
UTF-16 code units:         1       2        1
UTF-16 offsets:         0   1   2   3   4
                        | A | hi  lo | B |
Character boundaries:   0   1       3   4
                                ^^^^^
                          two code units for 😀
```

The string's `String.length()` is **4**, while `codePointCount(0, length())` is **3**. UTF-16 index `2` lies **between the high surrogate and low surrogate**: it is not a valid position to split the emoji in half as a complete character.

The following APIs return or accept **UTF-16 indexes**:

- `String.length()`, `String.charAt(index)`, `String.substring(begin, end)`.
- `String.offsetByCodePoints(index, count)`: **returns** a UTF-16 index after advancing by code points.
- `BreakIterator.first()/next()/following()/preceding()/current()`, when text is provided via `setText(String)`.
- `StringCharacterIterator` with an appropriate range, though it may have a **non-zero `beginIndex`**, which must be accounted for when converting offsets.

**Do not pass a code point ordinal as a UTF-16 offset.** To convert the position "after 2 code points from the start" into a UTF-16 offset, use `text.offsetByCodePoints(0, 2)`. Even so, **a code point boundary is still not guaranteed to be a visible character boundary**, because a grapheme can contain multiple code points such as a letter with combining marks.

## 3. following(offset): The First Boundary *After* an Offset

`following(int offset)` returns **the first boundary at a position strictly greater than `offset`**:

```text
following(offset) = min { b ∈ B | b > offset }
```

Here `B` is the iterator's set of boundaries for the given text. If no boundary exists after `offset`, the method returns `BreakIterator.DONE`.

**Properties to remember:**

- If `offset` **is already a boundary**, `following(offset)` does **not** return `offset` itself: it finds the next boundary.
- If `offset` **lies between two boundaries**, the result is the boundary after it.
- If `offset == lastBoundary`, the result is `DONE`.
- An `offset` outside the allowed text range causes `following` to throw `IllegalArgumentException`.
- On success, the iterator moves its current position to the returned boundary; when `offset` is already at the last boundary and the result is `DONE`, the current state is not moved past the end per the API contract.

Example with boundaries `0, 2, 5`:

| Call | Result | Why |
| --- | --- | --- |
| `following(0)` | `2` | First boundary greater than 0 |
| `following(1)` | `2` | 1 lies between 0 and 2 |
| `following(2)` | `5` | Does not return 2 itself |
| `following(4)` | `5` | 4 lies inside segment 2–5 |
| `following(5)` | `DONE` | Already at the last boundary |

This table is an **illustration based on a hypothetical boundary set**; it is not an assertion that any given Vietnamese sentence must have boundaries `0, 2, 5` on every JDK.

## 4. preceding(offset): The Last Boundary *Before* an Offset

`preceding(int offset)` returns **the last boundary strictly less than `offset`**:

```text
preceding(offset) = max { b ∈ B | b < offset }
```

This is semantically symmetric to `following`:

- If `offset` is itself a boundary, `preceding(offset)` still steps **backward to the prior boundary**, not returning `offset` itself.
- If `offset` is inside a segment, it returns the left-hand boundary.
- If `offset == firstBoundary`, it returns `DONE`.
- Out of text range, it throws `IllegalArgumentException`.
- On success, the current position moves to the returned boundary; at the first boundary, returning `DONE` does not move `current` out of range.

With the same boundary set `0, 2, 5`:

| Call | Result |
| --- | --- |
| `preceding(0)` | `DONE` |
| `preceding(1)` | `0` |
| `preceding(2)` | `0` |
| `preceding(4)` | `2` |
| `preceding(5)` | `2` |

**Off-by-one trap:** the user clicks right on the boundary between two words. If you want "the word containing this position", you must define a policy choosing **the left segment or the right segment**, rather than simply calling both `following(offset)` and `preceding(offset)` and assuming they bracket a single word.

## 5. isBoundary(offset): Checking *That Exact Position*

`isBoundary(int offset)` returns `true` when **`offset` itself** belongs to the iterator's boundary set, and `false` otherwise. It does not ask "is `offset` inside a word".

Example with `B = {0, 2, 5}`:

```text
isBoundary(0) = true
isBoundary(1) = false
isBoundary(2) = true
isBoundary(3) = false
isBoundary(5) = true
```

Points to note:

1. **The start and end of the text** are normally valid boundaries; for `setText(String)`, the offset range is `0..text.length()` (inclusive).
2. `isBoundary(-1)` or `isBoundary(text.length()+1)` throws `IllegalArgumentException`, rather than merely returning `false`.
3. Do not use `isBoundary` to check whether a UTF-16 `char` is an independent Unicode character. It checks **a boundary of the `BreakIterator` type in use** (character/word/line/sentence).
4. If you need to preserve iterator state, do not assume every boundary-query method is an operation **with no effect on the cursor**. You can call `first()` or reposition with `following/preceding` before running a subsequent loop. The API documentation specifies distinct `current` position behaviors for positioning operations.

### Comparing the Three Methods at a Boundary

With `B = {0, 2, 5}`, when `offset` is `2`:

```text
isBoundary(2) == true
preceding(2) == 0
following(2) == 5
```

Point `2` belongs to the boundary set, yet both `following` and `preceding` **skip over it** due to the strict greater-than / less-than relation. This is the most important distinction in this topic.

## 6. Standalone Java 17+ Example: Deterministic ASCII Boundaries

Create **`BoundaryMethodsDemo.java`**:

```java
import java.text.BreakIterator;
import java.util.Locale;

public class BoundaryMethodsDemo {
    private static String label(int pos) {
        return pos == BreakIterator.DONE
                ? "DONE" : Integer.toString(pos);
    }

    public static void main(String[] args) {
        BreakIterator it =
                BreakIterator.getCharacterInstance(Locale.ROOT);
        it.setText("cat");

        System.out.println("Length: 3");
        System.out.println("following(1): " + label(it.following(1)));
        System.out.println("preceding(2): " + label(it.preceding(2)));
        System.out.println("isBoundary(2): " + it.isBoundary(2));
        System.out.println("following(3): " + label(it.following(3)));
        System.out.println("preceding(0): " + label(it.preceding(0)));

        System.out.print("All boundaries:");
        for (int p = it.first(); p != BreakIterator.DONE;
                p = it.next()) {
            System.out.print(" " + p);
        }
        System.out.println();
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 BoundaryMethodsDemo.java
java BoundaryMethodsDemo
```

Stdout:

```text
Length: 3
following(1): 2
preceding(2): 1
isBoundary(2): true
following(3): DONE
preceding(0): DONE
All boundaries: 0 1 2 3
```

The example uses a simple ASCII string and `getCharacterInstance` to avoid differences in word splitting on complex contextual text. The `first()/next()` loop lists **both the start and end boundaries**, rather than counting characters directly by counting output lines.

**Note:** The loop starts with `first()`, not relying on whatever `current` position remained after the earlier `following/preceding/isBoundary` calls.

## 7. An Emoji Is Two UTF-16 Code Units Yet One Code Point

Create **`SurrogateBoundaryDemo.java`**:

```java
import java.text.BreakIterator;
import java.util.Locale;

public class SurrogateBoundaryDemo {
    public static void main(String[] args) {
        String text = "A\uD83D\uDE00B"; // A😀B

        BreakIterator it =
                BreakIterator.getCharacterInstance(Locale.ROOT);
        it.setText(text);

        System.out.println("UTF-16 length: " + text.length());
        System.out.println("Code points: "
                + text.codePointCount(0, text.length()));
        System.out.println("Boundary at 2: "
                + it.isBoundary(2));
        System.out.println("Boundary at 3: "
                + it.isBoundary(3));
        System.out.println("following(1): " + it.following(1));
        System.out.println("preceding(3): " + it.preceding(3));
        System.out.println("Emoji length: "
                + text.substring(1, 3).length());

        System.out.print("Breaks:");
        for (int p = it.first(); p != BreakIterator.DONE;
                p = it.next()) {
            System.out.print(" " + p);
        }
        System.out.println();
    }
}
```

```bash
javac -encoding UTF-8 SurrogateBoundaryDemo.java
java SurrogateBoundaryDemo
```

Stdout in JDK 17:

```text
UTF-16 length: 4
Code points: 3
Boundary at 2: false
Boundary at 3: true
following(1): 3
preceding(3): 1
Emoji length: 2
Breaks: 0 1 3 4
```

**Explanation:** `\uD83D\uDE00` is a surrogate pair in the Java string and together encodes the code point `U+1F600`. Offset `1` is before the emoji, offset `3` is after it; `2` lies **between** the two code units, so it is not treated as a character boundary here.

If code accidentally calls `text.substring(1, 2)`, the result contains only a **high surrogate**; it is not a complete Unicode scalar value and may render as a replacement character when encoded to UTF-8. Do not use `substring(index, index+1)` for arbitrary user-entered characters.

**Specifically:** a *grapheme cluster* can contain multiple code points, such as `a` plus an acute accent or an emoji sequence with ZWJ joiners. You cannot infer that `BreakIterator.getCharacterInstance` on every JDK/version/provider will handle every modern emoji sequence by the exact same segmentation rules. To guarantee UX for newer graphemes, check the target Unicode data and JDK version, or use a library supporting the segmentation standard appropriate for your application.

## 8. Code Point Boundaries Differ from Grapheme Boundaries

Consider the letter `"e\u0301"` consisting of `e` and a **combining acute accent**:

```text
UTF-16 index:       0   1   2
Text units:          e  ◌́
Code points:         U+0065 U+0301
One visible letter:  é  (typically)
```

`text.offsetByCodePoints(0, 1)` returns `1` because it advances across **one code point**. However, that lies between the base letter and the combining mark, not a good boundary for moving a caret as a single character. `BreakIterator.getCharacterInstance` following character-break rules can place boundaries outside this cluster at `0` and `2` (in the simple example above), helping text selection avoid separating the accent from the letter.

### Java 17 Demo — `CombiningMarkBoundaryDemo.java`

```java
import java.text.BreakIterator;
import java.util.Locale;

public class CombiningMarkBoundaryDemo {
    public static void main(String[] args) {
        String text = "e\u0301";
        BreakIterator it =
                BreakIterator.getCharacterInstance(Locale.ROOT);
        it.setText(text);

        int afterOneCodePoint = text.offsetByCodePoints(0, 1);
        System.out.println("Length: " + text.length());
        System.out.println("Code point count: "
                + text.codePointCount(0, text.length()));
        System.out.println("After 1 code point: "
                + afterOneCodePoint);
        System.out.println("Break at code point index: "
                + it.isBoundary(afterOneCodePoint));

        System.out.print("Breaks:");
        for (int p = it.first(); p != BreakIterator.DONE;
                p = it.next()) {
            System.out.print(" " + p);
        }
        System.out.println();
    }
}
```

```bash
javac -encoding UTF-8 CombiningMarkBoundaryDemo.java
java CombiningMarkBoundaryDemo
```

Stdout for a basic letter+accent cluster on JDK 17:

```text
Length: 2
Code point count: 2
After 1 code point: 1
Break at code point index: false
Breaks: 0 2
```

**Lesson:** "moving by one Unicode code point" and "moving by one user-visible character" can be two different operations. `offsetByCodePoints` only prevents splitting surrogate pairs; it does not apply grapheme rules. `BreakIterator` helps identify boundaries according to the desired semantic type.

## 9. Start/End, DONE, and Out-of-Range Offsets

For text set via `setText(String)` of length `n` UTF-16 code units, only offsets in **`0..n`** (inclusive) are within the allowed range.

| Case | Result/Behavior |
| --- | --- |
| `first()` | First boundary, normally `0` |
| `last()` | Last boundary, normally `n` |
| `following(n)` | `BreakIterator.DONE` |
| `preceding(0)` | `BreakIterator.DONE` |
| `isBoundary(0)` | `true` |
| `isBoundary(n)` | `true` |
| `following(-1)` | `IllegalArgumentException` |
| `preceding(n + 1)` | `IllegalArgumentException` |
| `isBoundary(-1)` | `IllegalArgumentException` |

`BreakIterator.DONE` is an integer sentinel equal to **`-1`**, not a valid position inside a string. Do not pass `DONE` to `substring` or `charAt`; check it first.

**File `BoundaryEdgesDemo.java`:**

```java
import java.text.BreakIterator;
import java.util.Locale;

public class BoundaryEdgesDemo {
    public static void main(String[] args) {
        BreakIterator it =
                BreakIterator.getCharacterInstance(Locale.ROOT);
        it.setText("ab");

        System.out.println("First: " + it.first());
        System.out.println("Last: " + it.last());
        System.out.println("After last: "
                + (it.following(2) == BreakIterator.DONE));
        System.out.println("Before first: "
                + (it.preceding(0) == BreakIterator.DONE));
        System.out.println("End boundary: " + it.isBoundary(2));

        try {
            it.following(-1);
            System.out.println("Unexpected success");
        } catch (IllegalArgumentException ex) {
            System.out.println("Out-of-range rejected");
        }
    }
}
```

```bash
javac -encoding UTF-8 BoundaryEdgesDemo.java
java BoundaryEdgesDemo
```

Stdout:

```text
First: 0
Last: 2
After last: true
Before first: true
End boundary: true
Out-of-range rejected
```

**Empty text:** `setText("")` can have a single boundary at `0`; both `first()` and `last()` equal `0`, and `following(0)`/`preceding(0)` return `DONE`. When designing slicing logic, handle the absence of content segments rather than assuming at least one segment always exists.

## 10. current, next, previous: Don't Lose Your Traversal Position

`BreakIterator` is a **stateful** iterator. The `current()` method reports the current boundary position; `next()` moves to the next boundary, and `previous()` moves to the prior boundary. When `following(offset)` or `preceding(offset)` succeeds, `current` is set to the returned boundary.

Example with `"cat"`, moving left to right:

```text
first() -> 0; current() -> 0
next()  -> 1; current() -> 1
next()  -> 2; current() -> 2
next()  -> 3; current() -> 3
next()  -> DONE; current() remains at the last boundary
```

Distinguish `following(offset)` from `next()`:

- `following(offset)` positions **relative to the passed `offset`**, regardless of what `current` was before.
- `next()` positions **relative to the existing `current` position**.
- `preceding(offset)` positions **relative to `offset`**, whereas `previous()` steps back from `current`.
- `isBoundary(offset)` is a boundary check; code should not rely on `current` before/after the check if it wants to avoid depending on iterator/provider details.

Therefore, if you just called `following(1)` and then call `next()`, `next()` advances from **the boundary `following` found**, rather than returning to the start of the string. To iterate everything from the beginning again, use `first()`.

### State Demo — `IteratorStateDemo.java`

```java
import java.text.BreakIterator;
import java.util.Locale;

public class IteratorStateDemo {
    public static void main(String[] args) {
        BreakIterator it =
                BreakIterator.getCharacterInstance(Locale.ROOT);
        it.setText("abc");

        System.out.println("After first: " + it.first());
        System.out.println("After following(0): "
                + it.following(0));
        System.out.println("Current: " + it.current());
        System.out.println("Next: " + it.next());
        System.out.println("Previous: " + it.previous());
        System.out.println("Current again: " + it.current());
    }
}
```

```bash
javac -encoding UTF-8 IteratorStateDemo.java
java IteratorStateDemo
```

Stdout:

```text
After first: 0
After following(0): 1
Current: 1
Next: 2
Previous: 1
Current again: 1
```

These positioning methods **have side effects** on the iterator; avoid sharing a single actively iterating instance across threads or unrelated UI operations. `BreakIterator` is mutable; create an instance per task or manage reuse/synchronization intentionally.

## 11. Slicing Content with Proper Boundaries

A safe way to iterate segment by segment is `start = first()`, then `end = next()`. Yield `substring(start, end)`, then set `start = end`.

**File `SafeSegmentsDemo.java`:**

```java
import java.text.BreakIterator;
import java.util.Locale;

public class SafeSegmentsDemo {
    public static void main(String[] args) {
        String text = "A\uD83D\uDE00B";
        BreakIterator it =
                BreakIterator.getCharacterInstance(Locale.ROOT);
        it.setText(text);

        int start = it.first();
        for (int end = it.next();
                end != BreakIterator.DONE;
                start = end, end = it.next()) {
            System.out.println("[" + start + "," + end + "): "
                    + text.substring(start, end));
        }
    }
}
```

```bash
javac -encoding UTF-8 SafeSegmentsDemo.java
java SafeSegmentsDemo
```

Stdout with a UTF-8 console:

```text
[0,1): A
[1,3): 😀
[3,4): B
```

**Important:** `substring(begin, end)` uses a **half-open** interval `[begin,end)`, matching the exact way two boundaries represent a segment. `end` is not the index of the last character, but the position **immediately after** the segment. Do not add 1 out of an "end-inclusive" habit.

With `getWordInstance`, the loop returns **segments between boundaries** rather than guaranteeing only alphabetic words: there may be whitespace, punctuation, numbers, or segments your product does not want to count as a "word". If counting words, classify segments according to policy (for example checking whether a code point is a letter/digit). Do not equate segment count with semantic word count.

## 12. Using following and preceding to Select the Segment Containing the Caret

Suppose the caret is at an arbitrary offset. We can find the boundaries to the left and right, while carefully handling **the exact case where the caret lands on a boundary**.

**Algorithm to select the segment to the right of the caret** (if the caret is on a boundary, pick the right-hand segment; if the caret is in the middle of a segment, pick the segment containing the caret):

```text
Input: String text, BreakIterator it, int caret
1. Validate 0 <= caret <= text.length()
2. if caret == text.length(): no segment to the right
3. right = it.following(caret)
4. if it.isBoundary(caret): left = caret
   else: left = it.preceding(caret)
5. If left / right are valid: substring(left, right)
```

The above is **pseudocode**; checking `isBoundary` may position `current` depending on the implementation, so every positioning step uses an **explicit offset**, not `next()` on implicit state.

If you want **the left-hand segment** when the caret sits right on a boundary, the formula differs:

```text
If caret > 0 and isBoundary(caret):
  left = preceding(caret)
  right = caret
If caret is between two boundaries:
  left = preceding(caret)
  right = following(caret)
```

The left/right selection policy must be designed from UI requirements, not decided automatically by `BreakIterator`. On the boundary between two words, **a caret is not inside a single unique word** unless you specify which side takes precedence.

### Example: Selecting the Grapheme to the Right of the Caret

Save **`SelectAtCaretDemo.java`**:

```java
import java.text.BreakIterator;
import java.util.Locale;

public class SelectAtCaretDemo {
    private static String selectRight(String text, int caret) {
        if (caret < 0 || caret > text.length()) {
            throw new IndexOutOfBoundsException();
        }
        if (caret == text.length()) {
            return "";
        }

        BreakIterator it =
                BreakIterator.getCharacterInstance(Locale.ROOT);
        it.setText(text);

        boolean atBoundary = it.isBoundary(caret);
        int left = atBoundary ? caret : it.preceding(caret);
        int right = it.following(caret);

        if (left == BreakIterator.DONE
                || right == BreakIterator.DONE) {
            return "";
        }
        return text.substring(left, right);
    }

    public static void main(String[] args) {
        String text = "A\uD83D\uDE00B";

        System.out.println("At 1: "
                + selectRight(text, 1).length());
        System.out.println("At 2: "
                + selectRight(text, 2).length());
        System.out.println("At 3: "
                + selectRight(text, 3));
        System.out.println("At 4 is empty: "
                + selectRight(text, 4).isEmpty());
    }
}
```

```bash
javac -encoding UTF-8 SelectAtCaretDemo.java
java SelectAtCaretDemo
```

Stdout:

```text
At 1: 2
At 2: 2
At 3: B
At 4 is empty: true
```

Caret `1` is right before the emoji; `2` lies inside the surrogate pair (a UTF-16 offset that can appear in data or API calls even though UIs normally avoid placing a caret there). Under the policy "take the segment containing the offset, preferring the right-hand segment if directly on a boundary", both `1` and `2` yield the 2-code-unit emoji segment. Position `4` is the end of the string, so there is no segment to the right.

**In a real UI**, the caret may also be a position in the framework's own model rather than implicitly a UTF-16 index of a Java `String`. Identify the coordinate system and convert properly before calling `BreakIterator`.

## 13. getWordInstance, getLineInstance, getSentenceInstance: Different Semantics

An offset like `5` can be:

- A **character** boundary (between two characters).
- Not a **word** boundary if it is in the middle of a word.
- Not a **line** break point if breaking there is invalid.
- Not a **sentence** boundary if it is in the middle of a sentence.

There is no single boundary set shared across all modes. For instance, calling `getWordInstance(Locale.forLanguageTag("vi-VN"))` and then `isBoundary(offset)` checks a **word boundary according to the runtime's ruleset**, not "a valid position to split a surrogate pair". Conversely, `getCharacterInstance` aims to split appropriate character units, yet does not act as a Vietnamese word/semantic segmenter.

### Counting Text Segments Does Not Equal Counting Linguistic "Words"

For example, the text `"Hello, world!"` has a comma, a space, and an exclamation mark. The word break iterator provides split positions between text regions, including non-word regions. Therefore, the loop:

```java
for (int b = it.first(); b != BreakIterator.DONE; b = it.next()) {
    // b is a boundary position; not yet a "word" token.
}
```

is an illustrative **fragment**, not a standalone program. To determine actual tokens, extract `text.substring(prev, next)` and classify them. Rules for spaceless scripts (some East Asian languages) and punctuation handling depend on the provider, Unicode/CLDR data, or JDK algorithm, so do not hardcode a list of "all word offsets" across different runtimes.

### When to Choose Which Type?

| Need | Iterator | Note |
| --- | --- | --- |
| Select a character/letter cluster | `getCharacterInstance` | Does not split surrogate pairs/combining sequences in supported cases |
| Move across word regions | `getWordInstance` | Includes punctuation/whitespace boundaries |
| Wrap lines for text layout | `getLineInstance` | Reports only break opportunities; does not measure pixel width |
| Split sentences by general rules | `getSentenceInstance` | Does not fully understand semantics, abbreviations, or specialized domains |

`BreakIterator` supports text boundaries; it **does not replace** a linguistic parser, lexical model, rich-text layout system, or business data validation rules.

## 14. StringCharacterIterator and Offset Ranges Not Starting at 0

`BreakIterator.setText(String)` is a convenience case: begin = `0`, end = `text.length()`. However, the `setText(CharacterIterator)` overload can accept a `StringCharacterIterator` representing a **slice of a string** with its own `beginIndex` and `endIndex`.

```java
String source = "abcdef";
StringCharacterIterator part =
        new StringCharacterIterator(source, 2, 5, 2);

BreakIterator it =
        BreakIterator.getCharacterInstance(Locale.ROOT);
it.setText(part);
```

This is a **fragment** requiring `import java.text.BreakIterator;`, `import java.text.StringCharacterIterator;`, and `import java.util.Locale;`. With this `StringCharacterIterator`, the designated region has **beginIndex = 2** and **endIndex = 5** (the slice `"cde"`). In this situation:

- `it.first()` corresponds to the first boundary of **the region**, not necessarily 0.
- `it.last()` corresponds to the last boundary of **the region**, not necessarily `source.length()`.
- Valid offsets for `following/preceding/isBoundary` must belong to **the `CharacterIterator` index range**, rather than implicitly using `0..partLength`.

Do not take region offset `2` and treat it as relative index `0` in `source.substring(...)`. If API code returns offsets in the `CharacterIterator`'s coordinate system, determine whether they refer to the original string or which subrange before slicing.

### Difference Between "Current Text Offset" and "Whole File Offset"

In a text editor application, the buffer might pass only the paragraph or cell being edited to `BreakIterator`. A boundary offset returned then is **not implicitly a whole-document coordinate**. If you slice `whole.substring(start,end)` and call `setText` on the new string, offsets start from 0 again; to map back to the document, add `start`. Conversely, when using a `CharacterIterator` with a non-zero `startIndex`, offsets may already carry the original coordinates. **Do not add the offset twice**.

## 15. Boundary Indexes Are Not UTF-8 Byte Offsets

A Unicode string may be stored in a file as UTF-8. Yet `BreakIterator` operates on **Java text character positions**, not bytes in a file. For `"A😀B"`:

```text
Java UTF-16:
  A    = 1 code unit
  😀   = 2 code units
  B    = 1 code unit
  length = 4

UTF-8 bytes:
  A    = 1 byte
  😀   = 4 bytes
  B    = 1 byte
  total = 6 bytes
```

The UTF-16 boundary at position `3` after the emoji does **not** correspond to byte offset 3 in UTF-8: the byte position after the emoji is `5`. Do not index `fileBytes[boundary]` or slice a byte array at `boundary` when the offset came from `BreakIterator`.

If you need byte positions for a protocol or file, convert explicitly—for example by encoding the prefix `text.substring(0, boundary)` in `StandardCharsets.UTF_8` and taking the byte length (only when necessary and with cost controlled). For many positions, build a byte↔UTF-16 mapping table with an appropriate decoder/encoder rather than repeatedly encoding prefixes.

**UTF-16 offsets differ from code point counts and grapheme indexes** — not only from byte offsets. When integrating Java with JavaScript, Python, databases, and UIs, explicitly document each API's index system.

## 16. Common Programming Pitfalls

| Mistake | Problem | Fix |
| --- | --- | --- |
| Thinking `following(x)` can return `x` | The method uses **>**, not **>=** | To check if `x` is a boundary, use `isBoundary(x)` |
| Thinking `preceding(x)` can return `x` | The method uses **<** | Choose a left/right segment policy at boundaries |
| Checking `following(last) == last` | The result must be `DONE` | Check the sentinel |
| Calling `substring(DONE, end)` | `DONE = -1`, not a valid index | Branch on `DONE` |
| Calling `isBoundary(-1)` to ask "is it invalid?" | Throws an exception | Validate the offset range first |
| Using code point count as a UTF-16 offset | Wrong after non-BMP characters | Use `offsetByCodePoints` when needed |
| Slicing `substring(i, i + 1)` for every glyph | Can split surrogate pairs/combining marks | Use character `BreakIterator` boundaries |
| Assuming `String.length()` is visible character count | It is UTF-16 code units | Distinguish code points/graphemes |
| Calling `next()` after `following` expecting to start at 0 | The iterator has repositioned | Call `first()` to iterate from the start |
| Treating `isBoundary` as a side-effect-free check | Can affect the position used by subsequent traversal | Reset `current` as needed |
| Taking word segments and counting all as words | Includes punctuation and whitespace | Classify segments |
| Hardcoding word boundaries for all locales | Algorithms/data differ | Test on target locale/JDK |
| Passing offsets from `CharacterIterator` without knowing `beginIndex` | Region can shift | Check begin/end and mapping |
| Using UTF-16 offsets as UTF-8 byte offsets | Wrong position in files/APIs | Convert coordinate systems |
| Reusing a mutable `BreakIterator` instance across requests | State leaks, race risk | Create separate instances/clones with an appropriate strategy |
| Trusting character `BreakIterator` to understand every latest ZWJ emoji | Unicode segmentation depends on version | Test/use an appropriate library |
| Comparing Vietnamese strings by bytes to conclude same/different glyphs | Unicode has precomposed/decomposed forms | Normalize per policy when needed |

## 17. Testing Behavior at Boundaries

A test suite should include both **exact-boundary** and **mid-segment** cases:

1. **ASCII:** `"cat"`, boundaries `0,1,2,3`; `following(1)=2`, `preceding(2)=1`, `isBoundary(2)=true`.
2. **Start/end:** `following(length)=DONE`, `preceding(0)=DONE`, `isBoundary(0/length)=true`.
3. **Out of range:** `-1` and `length+1` throw `IllegalArgumentException`.
4. **Surrogate pair:** `"A😀B"`, `length=4`, `codePointCount=3`, `isBoundary(2)=false`, `following(1)=3`.
5. **Combining mark:** `"e\u0301"` has two code points yet is one basic letter cluster; character boundaries avoid splitting the accent.
6. **Caret on boundary:** left vs. right segment selection has an explicit policy, especially at `0` and `length`.
7. **Caret mid-segment:** `preceding`/`following` return the surrounding boundaries without splitting the segment.
8. **State:** verify `current()` after `following/preceding`; new iteration starts from `first()`.
9. **Subregion:** `CharacterIterator` with non-zero `beginIndex` and accurate mapping to the original string.
10. **Locale:** `getWordInstance(Locale)` and `getSentenceInstance(Locale)` on paragraphs in different languages; snapshot exact outputs only when runtime/provider are pinned.
11. **Empty text:** no segments; never call `substring` with `DONE`.
12. **Data changes:** if text changes, call `setText` on the appropriate instance; do not reuse old boundaries as indexes into the edited string.

### Exercise A — Predict the Three Methods

Given a hypothetical boundary set `B = {0, 3, 7, 10}`, compute `following(3)`, `preceding(3)`, `isBoundary(3)`, `following(10)`, `preceding(0)`, and `isBoundary(6)`. Explain why "currently on a boundary" does not mean `following`/`preceding` stay at that position.

### Exercise B — UTF-16 with Emoji

Take `"X😀Y"`. Use `String.length`, `codePointCount`, and `offsetByCodePoints` to build an index table. Use `BreakIterator.getCharacterInstance` to print the boundaries, then slice the exact emoji with `substring`. Try slicing `substring(1, 2)` and describe why producing an unpaired surrogate is invalid.

### Exercise C — Accented Letters

Take `"e\u0301"` and `"\u00E9"`. Compare their code point counts and UTF-16 unit counts. Find character boundaries; if the product needs to compare content, apply `Normalizer.Form.NFC` separately from segmentation. Why do normalization and `BreakIterator` serve two different purposes?

### Exercise D — Selecting a Word by Caret

With `"Hello world!"` and `BreakIterator.getWordInstance(Locale.US)`, write a function returning the segment containing the caret, with a clear policy when the caret is on a boundary. Do not automatically treat whitespace/punctuation as words; accept only segments containing letters. Test offset `0`, inside `Hello`, after the space, and `length`.

### Exercise E — Partitioned Text

Use `StringCharacterIterator(source, begin, end, begin)` for a string with a prefix and suffix. Call `first/last`, try `following(begin)` and `preceding(end)`, and map the results back to the original string. Compare with calling `setText(source.substring(begin, end))` to receive 0-based offsets.

## 18. Official References

- [Java SE 21 — BreakIterator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/BreakIterator.html): `following`, `preceding`, `isBoundary`, `DONE`, `first`/`last`, `next`/`previous`.
- [Java SE 21 — String](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html): `length`, `substring`, `codePointCount`, `offsetByCodePoints`, and UTF-16 indexing.
- [Java SE 21 — CharacterIterator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/CharacterIterator.html): begin/end/current indexes of text to traverse.
- [Java SE 21 — StringCharacterIterator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/StringCharacterIterator.html): handling a range with `beginIndex`/`endIndex`.
- [Unicode Standard Annex #29](https://www.unicode.org/reports/tr29/): Unicode text segmentation, grapheme/word/sentence boundaries.
- [Unicode FAQ — UTF & BOM](https://www.unicode.org/faq/utf_bom.html): distinguishing UTF-16 code units, code points, and encodings.

## 19. Key Takeaways

**`following(offset)` finds the next boundary whose index is **greater than** `offset`; `preceding(offset)` finds the prior boundary whose index is **less than** `offset`; `isBoundary(offset)` checks **`offset` itself**.** Standing directly on a boundary does not make `following/preceding` return that boundary. At the start/end of the range, searches outside the bounds return `BreakIterator.DONE`, while invalid offsets throw `IllegalArgumentException`.

With `setText(String)`, `BreakIterator` indexes are **UTF-16 code-unit offsets** compatible with `substring`: a non-BMP emoji can take two code units and an accented letter can consist of multiple code points. Use the right `BreakIterator` type, handle `DONE`, start/end boundaries, `current` state, and locale rules; **do not confuse UTF-16 offsets with UTF-8 bytes, code point indexes, or "visible character counts"**.
