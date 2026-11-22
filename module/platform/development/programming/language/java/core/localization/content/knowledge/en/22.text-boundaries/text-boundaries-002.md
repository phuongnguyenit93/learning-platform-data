# first, next, previous, and BreakIterator.DONE in Java

## 1. Why Must We Traverse Text Boundaries?

In multilingual applications, you cannot always split text by whitespace or iterate `char` by `char` to find words, sentences, line-wrap points, or user-perceived characters. Some languages do not place spaces between words; there are punctuation marks, ligatures/combining letters, multi-code-point emojis, and segmentation conventions that vary by locale.

Java provides `java.text.BreakIterator` to **traverse text boundaries**. This object acts like a **stateful cursor** moving across valid positions for a given segmentation type. The most important methods in this lesson:

- `first()`: positions the cursor at the first boundary.
- `next()`: moves to the boundary after the current position.
- `previous()`: moves to the boundary before the current position.
- `BreakIterator.DONE`: sentinel value indicating **there are no more boundaries in the current traversal direction**.

A common misconception: `next()` **does not return a word**, `previous()` **does not return a character**, and `DONE` **is not a string slicing index**. These methods return **integer offsets**; you must use a pair of consecutive boundaries to extract a text segment.

For example, for `"One two!"` with `BreakIterator.getWordInstance(Locale.US)`, the boundaries in verified Java data are:

```text
Text:    O n e   t w o !
Offset:  0 1 2 3 4 5 6 7 8

Word boundaries: 0 → 3 → 4 → 7 → 8 → DONE(-1)

Segments: [0,3) "One"
          [3,4) " "
          [4,7) "two"
          [7,8) "!"
```

Both the space and the exclamation mark form **their own segments** in the word iterator. Thus, the name `getWordInstance` does not mean `next()` returns only words containing letters.

### Learning Objectives

After this lesson you will be able to:

1. Explain the exact meaning of `first()`, `next()`, `previous()`, `last()`, `current()`, and `DONE`.
2. Write safe forward and backward traversal loops without dropping or duplicating segments.
3. Distinguish between a **boundary** and the **segment between two boundaries**.
4. Use the results to call `substring` properly and know they are **UTF-16 offsets**, not code point ordinal indexes.
5. Understand the differences among `getCharacterInstance`, `getWordInstance`, `getSentenceInstance`, and `getLineInstance`.
6. Handle empty strings, exhausted iterators, spaces/punctuation, locales, and mutable state.
7. Know when to check Unicode graphemes, tokenization, or use a deeper linguistic analysis library separately.

## 2. Creating a `BreakIterator` with the Right Type and Locale

`BreakIterator` is an abstract class; applications normally obtain an instance through its factories:

| Factory | What boundaries does it serve? | Must not be equated with |
| --- | --- | --- |
| `BreakIterator.getCharacterInstance(locale)` | Character boundaries at the text segmentation level | Every Java `char` or necessarily every glyph |
| `BreakIterator.getWordInstance(locale)` | Word segmentation boundaries and intervening segments | A tokenizer that outputs only meaningful words |
| `BreakIterator.getSentenceInstance(locale)` | Sentence boundaries according to segmentation rules | Perfect grammatical sentence parsing |
| `BreakIterator.getLineInstance(locale)` | Rule-compliant line break opportunities | Displayed lines after layout or only newline characters |

Overloads that do not accept a `Locale` use the JVM's default locale related to text formatting. For multi-user applications, pass the locale explicitly:

```java
Locale locale = Locale.forLanguageTag("vi-VN");
BreakIterator words = BreakIterator.getWordInstance(locale);
words.setText("Chào bạn!");
```

This is a **code snippet inside a method**, requiring `import java.text.BreakIterator;` and `import java.util.Locale;`.

The actual concrete subclass chosen by the JDK/provider may differ. Do not cast to a specific implementation class when code only needs the `BreakIterator` contract. Segmentation data may also change across JDK, Unicode, and locale provider versions; if your product relies on specific segmentation, test on the target runtime.

### Mandatory Step: `setText`

Before traversing a specific string, call `setText(String)` to set its content:

```java
BreakIterator iterator = BreakIterator.getWordInstance(Locale.US);
iterator.setText("One two!");
```

`setText` sets the content and places the iterator state at the starting position. Still, call `first()` explicitly at the beginning of your algorithm because it makes the loop's initialization condition clear and independent of any cursor left over from prior operations.

With the `setText(CharacterIterator)` overload, the index range can be bounded by the underlying iterator's `getBeginIndex()` / `getEndIndex()`, so do not generalize that **every** `first()` returns 0. With `setText(String)`, the first boundary is normally index 0 and the last boundary is `text.length()`.

## 3. State Model: The Cursor Sits on *Boundaries*, Not on Characters

Simple model:

```text
Boundaries:      b0         b1    b2        b3   b4
                  |          |     |         |    |
Text:            "O n e"    " "   "t w o"    "!"
Index:            0          3     4         7    8

first()  → b0
next()   → b1 → b2 → b3 → b4 → DONE
previous() ← boundary before current()
last()   → b4
```

In `"One two!"`, `b0=0`, `b1=3`, `b2=4`, `b3=7`, `b4=8`.

To extract a segment, you must have **two offsets**:

```java
int start = iterator.first();
int end = iterator.next();

if (end != BreakIterator.DONE) {
    String segment = text.substring(start, end);
}
```

This is an illustrative snippet assuming `iterator` has been given text and `text` is declared. `substring(start,end)` takes the half-open interval **[start, end)** — inclusive of `start` and exclusive of `end`. Do not call `substring(0, next())` on every iteration, as that extracts growing prefixes rather than individual segments.

### `first()`

- Moves the cursor to the first boundary.
- Returns the first boundary position.
- When using `setText(String)`, this is 0.
- Calling `first()` again **resets** traversal progress; you cannot resume from the previous position.

### `next()`

- Finds the boundary immediately **after** the current position, moves the cursor there, and returns the offset.
- If already at the last boundary, returns `BreakIterator.DONE`.
- Returning `DONE` **does not mean `current()` turns into `-1`**. In the JDK, the cursor remains at the last boundary when `next()` cannot advance further.

### `previous()`

- Finds the boundary immediately **before** the current position.
- If already at the first boundary, returns `BreakIterator.DONE`.
- Use `last()` followed by `previous()` for natural backward iteration.
- Calling `previous()` after `next()` has iterated to `DONE` can move back to the second-to-last boundary (because `current` is still at the end).

### `BreakIterator.DONE`

`DONE` is an integer sentinel with value **`-1`** in Java SE. It indicates **there is no next or previous boundary**, rather than being a real boundary.

```java
if (end == BreakIterator.DONE) {
    // Reached the end of segments in the traversal direction.
}
```

Never pass `-1` to `String.substring(...)` or use it as an array index: it will throw `StringIndexOutOfBoundsException` or an equivalent bounds error. Compare against the constant `BreakIterator.DONE` instead of scattering literal `-1` values so the intent stays clear.

## 4. Standard Loop with `first` and `next`

Safe and common pattern:

```java
for (int start = iterator.first(), end = iterator.next();
     end != BreakIterator.DONE;
     start = end, end = iterator.next()) {

    String segment = text.substring(start, end);
    // Process segment [start,end)
}
```

Step-by-step explanation:

1. `start = first()` sets the initial offset.
2. `end = next()` sets the ending offset of the first segment.
3. The condition `end != DONE` confirms the slicing offset is valid.
4. Process `text.substring(start,end)`.
5. `start = end` makes the previous end boundary the start of the next segment; `end = next()` advances one boundary.
6. When `next()` returns `DONE`, stop **without calling `substring(start, -1)`**.

### Standalone Java 17+ Example: Iterating Word Segments

Create `ForwardBreakIteratorDemo.java`:

```java
import java.text.BreakIterator;
import java.util.Locale;

public class ForwardBreakIteratorDemo {
    public static void main(String[] args) {
        String text = "One two!";
        BreakIterator iterator =
                BreakIterator.getWordInstance(Locale.US);
        iterator.setText(text);

        int start = iterator.first();
        int end;

        while ((end = iterator.next()) != BreakIterator.DONE) {
            System.out.println("[" + start + "," + end + ") = "
                    + "'" + text.substring(start, end) + "'");
            start = end;
        }

        System.out.println("DONE=" + BreakIterator.DONE);
        System.out.println("current=" + iterator.current());
    }
}
```

Run with JDK 17+:

```bash
javac ForwardBreakIteratorDemo.java
java ForwardBreakIteratorDemo
```

Verified stdout with `Locale.US` segmentation data:

```text
[0,3) = 'One'
[3,4) = ' '
[4,7) = 'two'
[7,8) = '!'
DONE=-1
current=8
```

The segments `" "` and `"!"` are still returned because the iterator determines **boundaries**, not filtered non-word segments. If the goal is word counting, add a policy to filter segments containing word characters (or use a language-appropriate tokenization library). Counting `next()` calls is **not** equivalent to counting words.

## 5. Standard Loop with `last` and `previous`

If you want to iterate **segments in reverse order**, do not take `first()` and then call `previous()`: at the beginning there is no preceding boundary, so the first call returns `DONE`.

Start at the **last boundary**:

```java
int end = iterator.last();
int start;

while ((start = iterator.previous()) != BreakIterator.DONE) {
    String segment = text.substring(start, end);
    // Process current segment from right to left
    end = start;
}
```

The two offsets still obey `start < end` in the source string, even though the **segment traversal order** is from end to start. Do not swap arguments in `substring(start,end)` to `substring(end,start)`.

### Java 17+ Example: Backward Traversal

File `BackwardBreakIteratorDemo.java`:

```java
import java.text.BreakIterator;
import java.util.Locale;

public class BackwardBreakIteratorDemo {
    public static void main(String[] args) {
        String text = "One two!";
        BreakIterator iterator =
                BreakIterator.getWordInstance(Locale.US);
        iterator.setText(text);

        int end = iterator.last();
        int start;

        while ((start = iterator.previous()) != BreakIterator.DONE) {
            System.out.println("[" + start + "," + end + ") = "
                    + "'" + text.substring(start, end) + "'");
            end = start;
        }

        System.out.println("DONE=" + BreakIterator.DONE);
        System.out.println("current=" + iterator.current());
    }
}
```

```bash
javac BackwardBreakIteratorDemo.java
java BackwardBreakIteratorDemo
```

```text
[7,8) = '!'
[4,7) = 'two'
[3,4) = ' '
[0,3) = 'One'
DONE=-1
current=0
```

**Iterating segments backward** is different from **reversing every character inside each segment**. This example prints the segment `"two"` intact, not `"owt"`. If your goal is reversing a Unicode string by grapheme, you also need to handle code points/emojis; `BreakIterator` helps locate boundaries, not perform the reverse itself.

## 6. `current()` and What Happens at `DONE`?

`current()` returns the **current** boundary position held by the iterator, unlike `DONE`, which signals the end of a move.

Example on `"One two!"`:

| Operation | Return Value | `current()` After Operation |
| --- | ---: | ---: |
| `first()` | 0 | 0 |
| `next()` | 3 | 3 |
| `next()` | 4 | 4 |
| `next()` | 7 | 7 |
| `next()` | 8 | 8 |
| `next()` | `DONE=-1` | 8 |
| `previous()` (after `DONE`) | 7 | 7 |
| `last()` | 8 | 8 |
| `next()` (at end) | `DONE=-1` | 8 |
| `first()` | 0 | 0 |
| `previous()` (at start) | `DONE=-1` | 0 |

A common mistake is treating `DONE` as a position the cursor actually moved to. **Do not store `int index = next()` and assume `current() == index` in all cases**, because when `next()` returns `DONE`, `current()` stays at the last boundary.

Similarly, a loop can call `next()` multiple times after `DONE` and keep getting `DONE`. This is not a reason to increment a counter or advance by characters; stop the loop as soon as you see the sentinel.

### Concrete State Example

Create `BreakIteratorStateDemo.java`:

```java
import java.text.BreakIterator;
import java.util.Locale;

public class BreakIteratorStateDemo {
    public static void main(String[] args) {
        BreakIterator iterator =
                BreakIterator.getWordInstance(Locale.US);
        iterator.setText("One two!");

        System.out.println("first=" + iterator.first());
        System.out.println("next1=" + iterator.next());
        System.out.println("next2=" + iterator.next());
        System.out.println("next3=" + iterator.next());
        System.out.println("next4=" + iterator.next());
        System.out.println("next5=" + iterator.next());
        System.out.println("current=" + iterator.current());
        System.out.println("previous=" + iterator.previous());
        System.out.println("current=" + iterator.current());

        System.out.println("first again=" + iterator.first());
        System.out.println("previous at first=" + iterator.previous());
        System.out.println("current=" + iterator.current());
    }
}
```

```bash
javac BreakIteratorStateDemo.java
java BreakIteratorStateDemo
```

```text
first=0
next1=3
next2=4
next3=7
next4=8
next5=-1
current=8
previous=7
current=7
first again=0
previous at first=-1
current=0
```

## 7. Empty String: Only One Boundary Position

With `String text = ""`:

- `first()` is 0.
- `last()` is also 0.
- `next()` right after `first()` returns `DONE`.
- `previous()` at the start position also returns `DONE`.
- There are no **positive-length segments** to add to a list.

Therefore, the standard loop `while ((end = next()) != DONE)` naturally executes 0 times; do not synthesize a fake empty string as the "first word".

Java 17+ example:

```java
import java.text.BreakIterator;
import java.util.Locale;

public class EmptyTextDemo {
    public static void main(String[] args) {
        BreakIterator iterator =
                BreakIterator.getWordInstance(Locale.US);
        iterator.setText("");

        System.out.println("first=" + iterator.first());
        System.out.println("next=" + iterator.next());
        System.out.println("previous=" + iterator.previous());
        System.out.println("last=" + iterator.last());
    }
}
```

```bash
javac EmptyTextDemo.java
java EmptyTextDemo
```

```text
first=0
next=-1
previous=-1
last=0
```

This output helps distinguish an **empty string** from **no iterator**. `DONE` does not signal a read error; it is the normal end-of-traversal result.

## 8. Helper Methods for Moving the Cursor

In addition to the three main methods, there are:

| Method | Meaning |
| --- | --- |
| `last()` | Moves cursor to the final boundary of the text |
| `current()` | Reads current offset without moving |
| `next(int n)` | Moves `n` boundaries: positive moves forward, negative moves backward, 0 stays put |
| `following(int offset)` | Finds the **first** boundary **after** the given offset |
| `preceding(int offset)` | Finds the **last** boundary **before** the offset |
| `isBoundary(int offset)` | Checks whether `offset` lies on a boundary; **may modify `current`** |
| `getText()` | Returns a `CharacterIterator` reflecting the set content |

`following(offset)` differs from `next()`: `following` jumps from the **specified** offset rather than simply relying on the `current` boundary. `preceding(offset)` works analogously to find the boundary before `offset`.

The offsets accepted and returned by these APIs are **UTF-16 indexes of the text** (for `String`). If an offset lands inside a surrogate pair, boundary selection depends on the segmentation algorithm and that offset must not be assumed to correspond to a complete code point.

### Java 17+ Example: `next(int)`, `following`, `preceding`, and `isBoundary`

File `BreakIteratorNavigationDemo.java`:

```java
import java.text.BreakIterator;
import java.util.Locale;

public class BreakIteratorNavigationDemo {
    public static void main(String[] args) {
        BreakIterator it = BreakIterator.getWordInstance(Locale.US);
        it.setText("One two!");

        System.out.println("first=" + it.first());
        System.out.println("next(2)=" + it.next(2));
        System.out.println("next(-1)=" + it.next(-1));
        System.out.println("following(3)=" + it.following(3));
        System.out.println("preceding(4)=" + it.preceding(4));
        System.out.println("isBoundary5=" + it.isBoundary(5));
        System.out.println("current=" + it.current());
        System.out.println("isBoundary(7)=" + it.isBoundary(7));
    }
}
```

```bash
javac BreakIteratorNavigationDemo.java
java BreakIteratorNavigationDemo
```

```text
first=0
next(2)=4
next(-1)=3
following(3)=4
preceding(4)=3
isBoundary5=false
current=7
isBoundary(7)=true
```

Because `5` is inside the word `two`, `isBoundary(5)` returns `false` while moving the cursor to the boundary **after** it, at `7`. If you subsequently call `next()` without accounting for this side effect, you may **skip a segment**. Do not treat `isBoundary` as a pure query that never mutates iterator state.

**Note:** if you pass an offset outside the valid range of the `CharacterIterator`, these methods can throw `IllegalArgumentException`. `DONE` only means "no boundary found" under search conditions, not a substitute for validating input offsets and state.

## 9. Character, Word, Sentence, Line: Same API, Different Boundaries

When switching factories, the behavior of `first`/`next`/`previous`/`DONE` **does not change in principle**, but **which offsets count as boundaries** changes.

For `"One two!"`, according to verified Java US segmentation data:

| Iterator | Illustrative Segments |
| --- | --- |
| `getCharacterInstance` | `"O"`, `"n"`, `"e"`, `" "`, `"t"`, `"w"`, `"o"`, `"!"` |
| `getWordInstance` | `"One"`, `" "`, `"two"`, `"!"` |
| `getSentenceInstance` | `"One two!"` |
| `getLineInstance` | `"One "`, `"two!"` |

The difference with `getLineInstance` is easy to misunderstand: it describes **positions where line breaks are allowed**, rather than requiring the text to contain `\n` or guaranteeing exactly two rendered lines. A layout engine still needs width, font, and line-breaking policy information.

### Java 17+ Example: Comparing All Four Types

Create `BreakTypesDemo.java`:

```java
import java.text.BreakIterator;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public class BreakTypesDemo {
    static List<String> segments(String s, BreakIterator it) {
        it.setText(s);
        List<String> list = new ArrayList<>();
        int start = it.first();
        for (int end = it.next(); end != BreakIterator.DONE;
                start = end, end = it.next()) {
            list.add(s.substring(start, end));
        }
        return list;
    }

    public static void main(String[] args) {
        String text = "One two!";
        System.out.println("character="
                + segments(text,
                    BreakIterator.getCharacterInstance(Locale.US)));
        System.out.println("word="
                + segments(text,
                    BreakIterator.getWordInstance(Locale.US)));
        System.out.println("sentence="
                + segments(text,
                    BreakIterator.getSentenceInstance(Locale.US)));
        System.out.println("line="
                + segments(text,
                    BreakIterator.getLineInstance(Locale.US)));
    }
}
```

```bash
javac BreakTypesDemo.java
java BreakTypesDemo
```

```text
character=[O, n, e,  , t, w, o, !]
word=[One,  , two, !]
sentence=[One two!]
line=[One , two!]
```

The `character`/`word` lines are printed by `List.toString()`, so an element containing a single space appears as **two consecutive spaces between commas**; that is the list formatting and **no element is missing**. For automated comparisons, printing `start`/`end` as in `ForwardBreakIteratorDemo` is clearer and less dependent on whitespace display.

Some languages segment words differently from English; do not treat US output on ASCII as a universal rule.

## 10. Returned Offsets Are Still UTF-16 Indexes

This is especially important in localization. Java `String.length()` returns the count of **UTF-16 code units**, not Unicode code points or grapheme clusters.

Example:

```text
A🌍B
```

There are three Unicode code points, yet `String.length() == 4` because `🌍` U+1F30D consists of two UTF-16 code units. With `BreakIterator.getCharacterInstance(Locale.US)` on a JDK that segments a valid surrogate pair as one character, the boundaries in the example are:

```text
0 → 1 → 3 → 4
```

Not `0 → 1 → 2 → 3`. If `next()` returns offset `3`, it points to the position after the entire emoji, corresponding to `substring(1,3)`.

### Java 17+ Example Independent of Console Emoji Fonts

File `BreakIteratorUtf16Demo.java`:

```java
import java.text.BreakIterator;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public class BreakIteratorUtf16Demo {
    public static void main(String[] args) {
        String globe = new String(Character.toChars(0x1F30D));
        String text = "A" + globe + "B";

        BreakIterator it =
                BreakIterator.getCharacterInstance(Locale.US);
        it.setText(text);

        List<Integer> offsets = new ArrayList<>();
        for (int at = it.first(); at != BreakIterator.DONE;
                at = it.next()) {
            offsets.add(at);
        }

        System.out.println("utf16 length=" + text.length());
        System.out.println("codePoints="
                + text.codePointCount(0, text.length()));
        System.out.println("boundaries=" + offsets);
    }
}
```

```bash
javac BreakIteratorUtf16Demo.java
java BreakIteratorUtf16Demo
```

```text
utf16 length=4
codePoints=3
boundaries=[0, 1, 3, 4]
```

Because `String` indexes in UTF-16, `BreakIterator` results are used directly with `substring(start,end)`. Do not mistakenly convert this offset to a "code point ordinal" and pass it into `substring` again.

### Warning on Complex Emojis and JDK 17

Not every *grapheme cluster* has only one code point. For example, ZWJ-joined emojis, skin-tone modifiers, or regional indicator pairs can contain multiple code points. **JDK 17 `BreakIterator.getCharacterInstance` is not guaranteed to handle every modern extended grapheme cluster completely**; the default implementation was upgraded per UAX #29 starting in JDK 20 (JDK-8291660). When you need accurate visible character boundaries on Java 17, you can use the regex `Pattern.compile("\\X")` (which supports extended grapheme clusters) or an appropriate Unicode library, and always test against your product's Unicode version.

**Do not use `BreakIterator.getCharacterInstance` as proof that each segment is a fixed-width glyph**. Grapheme boundaries and font/pixel layout are different problems.

## 11. Word Boundaries Do Not Mean Only Words

The `"One two!"` example for the word iterator produces all of:

```text
"One"    — letters
" "      — whitespace
"two"    — letters
"!"      — punctuation
```

If you only want to count words, one approach is to **filter segments** using a business rule:

```java
static boolean hasLetterOrDigit(String segment) {
    return segment.codePoints()
            .anyMatch(Character::isLetterOrDigit);
}
```

This is an **illustrative method**, not a universal definition of a word across all languages. Linguistic and product words can include hyphens, numbers, hashtags, apostrophes, complex scripts, emojis, or lack spaces. For Chinese, Japanese, Thai, or other scripts, segmentation may depend on locale data and dictionaries; word counting algorithms for analytics/search typically need a specialized tokenizer.

Several use cases to distinguish:

- **Segmenting to select a word with a cursor:** a word boundary engine is appropriate.
- **Tokenizing for search indexing:** an analyzer/tokenizer with normalization/casefolding and domain rules.
- **Editorial word counting:** requires defining what counts as "one word".
- **Splitting sentences:** use the sentence iterator, do not count periods.

Do not assign the wrong responsibility to `BreakIterator` simply because it has a `getWordInstance` method.

## 12. Backward Iteration and Mutable State Issues

`BreakIterator` is a **stateful iterator**. `first()`, `last()`, `next()`, `previous()`, and even some boundary-checking methods can change `current()`. Consequences:

- Do not use the same instance to **concurrently** iterate forward and backward if the operations interleave without management.
- Do not share one mutable iterator across requests/threads without isolating state.
- Do not call `setText(...)` in the middle of a loop while still using `start/end` from the old text.
- If you need to iterate again from the start, call `first()` and recompute.
- If you need to inspect an arbitrary position using `following/preceding` during iteration, consider creating another iterator or saving the offset and restoring state properly.
- `BreakIterator` supports `clone()`; however, cloning must also be used on controlled text/state and not abused as a way to maintain a shared mutable iterator across threads.

### Don't Forget to Preserve the Text Behind the Boundaries

Segments obtained from `text.substring(start,end)` are only valid if `start/end` were generated from **the exact text being segmented by the iterator**. If a normalization, case-conversion, diacritic-stripping, or encoding step changes the length, offsets from the transformed text **do not necessarily** work on the raw text.

For example, `"e\u0301"` is two code units, whereas the NFC form `"\u00E9"` is only one. If you segment normalized text and use those offsets to slice/highlight raw text, positions can be wrong. This is a common issue when highlighting search results. Keep an offset mapping or segment and operate on the same representation.

## 13. Common Mistakes

| Mistake | Consequence | Correct Approach |
| --- | --- | --- |
| Thinking `next()` returns a word | It returns a **boundary index** | Use `substring(start,end)` |
| Using `substring(0, end)` on every turn | Extracts growing prefixes, not segments | Update `start=end` |
| Passing `DONE=-1` to `substring` | Negative index error | Check `end != DONE` before slicing |
| Iterating backward from `first()` | `previous()` immediately returns `DONE` | Start from `last()` |
| Swapping arguments `substring(end,start)` when iterating backward | `beginIndex > endIndex` | Always use `substring(start,end)` with `start` less than `end` |
| Thinking `current() == DONE` after `next() == DONE` | `current` remains at the last boundary | Check the return value of `next` |
| Thinking the word iterator skips spaces and punctuation | It also returns boundaries for these segments | Filter by token policy |
| Calling `isBoundary(offset)` as a purely read-only query | Can change `current` position | Be careful before calling `next/previous` |
| Using `String.length()` as visible character count | UTF-16 code units differ from graphemes | Choose the right unit |
| Using boundaries from a normalized string to slice a raw string | Offsets may shift | Use matching strings/mapping |
| Assuming the line iterator returns lines created by `\n` | It represents line-break opportunities | Distinguish line layout from newline characters |
| Counting `next()` calls to count words | Does not distinguish punctuation/whitespace | Use dedicated tokenization |
| Sharing one iterator across multiple threads | Mutable state can get corrupted | Use per-operation instances |
| Assuming every JDK/provider segments ZWJ emojis identically | Unicode implementations evolve | Test JDK 17/20+ and check policy |
| Using `Locale.getDefault()` for all users | Does not reflect user locale | Pass locale explicitly |

## 14. Boundary Algorithm Design Checklist

Before implementing, answer:

1. **What boundaries are you finding?** Character, word, sentence, or line?
2. **What is the source locale?** Display language may differ from the JVM default.
3. **Is the text raw or normalized?** Which version do the returned offsets belong to?
4. **What is the index unit?** `BreakIterator` uses UTF-16 offsets for `String`.
5. **Are `first()`/`last()` used in the right direction?** Do not call `previous()` at the start or `next()` at the end and treat `DONE` as an offset.
6. **Does every loop check `DONE` before slicing?**
7. **Are segments filtered by business rules?** Spaces/punctuation do not disappear automatically.
8. **What about empty text and whitespace-only text?** Must not produce fake words.
9. **Are there combining marks, surrogates, ZWJ, or emojis?** Segmentation and glyph width are different.
10. **Is a mutable iterator shared across threads?** Create per-use instances or separate ownership.
11. **Are Unicode and multiple locales tested across JDK versions?** Do not test only ASCII.
12. **Do offsets need to be preserved for UI highlighting?** Must remain compatible with raw text/rendered text.
13. **Is line breaking being confused with tokenization or sentence segmentation?**
14. **Must boundaries be recomputed after text changes?** Yes, because old offsets can become invalid.

## 15. Self-Check Questions

1. **What does `first()` return?** The first boundary and moves `current` there.
2. **Does `next()` return a word string or a position?** It returns a **UTF-16 boundary offset**, not a string.
3. **What is the value of `BreakIterator.DONE`?** `-1` in Java SE, a sentinel rather than an offset.
4. **For `"One two!"` with a word iterator, what sequence of boundaries is returned?** `0,3,4,7,8` then `DONE`.
5. **Why are there `" "` and `"!"` segments?** Because word segmentation includes whitespace/punctuation; it does not filter words automatically.
6. **How do you write the forward loop termination condition?** `while ((end = iterator.next()) != BreakIterator.DONE)`.
7. **To iterate segments backward, how do you initialize?** `end = iterator.last()`, then call `previous()` to get `start`.
8. **Why does `previous()` right after `first()` return `DONE`?** There is no boundary before the start of the text.
9. **What will `current()` be after `next()` at the end returns `DONE`?** It remains at the last boundary, not `-1`.
10. **What does `last()` return on an empty text?** `0` if the text was set via `setText("")`.
11. **Does `following(3)` choose offset 3 if 3 is a boundary?** No; it finds the boundary *after* 3.
12. **Can `isBoundary(5)` affect the subsequent `next()` call?** Yes, because it can position `current` at the boundary after the offset.
13. **Does `BreakIterator` use code point offsets or UTF-16?** UTF-16 offsets for `String`.
14. **In `"A🌍B"`, what offsets do character boundaries pass through?** `0,1,3,4` on verified JDKs.
15. **Can you rely on `getWordInstance` for 100% accurate Vietnamese/Thai/Chinese word counting?** No; you must define what a word is and test segmentation per language.
16. **What does `getLineInstance` analyze?** Line-break opportunities, not UI line counts or only newline markers.
17. **Why shouldn't offsets from normalized text be used to slice the original text?** Because normalization can change length, invalidating the offset correspondence.
18. **In a multi-user server, how should iterators be managed?** Dedicated instance per operation/request or clear ownership; avoid sharing mutable state.

## References

- [Java SE 17 — BreakIterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/BreakIterator.html): `first`, `last`, `next`, `previous`, `current`, `DONE`, and segmentation factories.
- [Java SE 17 — CharacterIterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/CharacterIterator.html): `beginIndex/endIndex` ranges and text indexes.
- [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): `substring` and UTF-16 indexes.
- [Unicode Standard Annex #29 — Text Segmentation](https://www.unicode.org/reports/tr29/): definitions of grapheme, word, and sentence boundaries.
- [Unicode Standard Annex #14 — Line Breaking](https://www.unicode.org/reports/tr14/): line break opportunity rules.
- [OpenJDK JDK-8291660 — Support grapheme clusters in BreakIterator](https://bugs.openjdk.org/browse/JDK-8291660): JDK 20 implementation change for extended grapheme clusters.
