# BreakIterator for Character, Word, Sentence, and Line Break Positions in Java

## 1. Why Can't Multilingual Text Be Split Using Only Indexes or Spaces?

In Java, `String` stores text as **UTF-16 code units**. A word or a character that the user perceives on the screen does not necessarily occupy exactly one UTF-16 element:

- An accented letter can be represented by a precomposed code point or multiple combining code points.
- Non-BMP emojis typically occupy two UTF-16 code units; composite emojis can contain multiple code points and joiner characters.
- Not every language puts spaces between words.
- Sentence boundaries differ from period boundaries: periods can also appear in abbreviations or numbers.
- Breaking lines in the right place is not just about finding `\n` characters; layout needs to know **where line breaks are allowed**.

Therefore, code like:

```java
String first = text.substring(0, 1);
String[] words = text.split(" ");
String[] sentences = text.split("\\.");
```

can be semantically wrong or split in the middle of Unicode components. This is an **illustrative code snippet**, not a recommended practice. `substring(0,1)` only takes one code unit, `split(" ")` only understands ASCII spaces, and `split("\\.")` assumes a period always ends a sentence.

Java provides `java.text.BreakIterator` to find **text boundaries by type and by `Locale`**. The main types are:

1. `getCharacterInstance(locale)` — boundaries of character clusters treated as characters in a segmentation model.
2. `getWordInstance(locale)` — word boundaries and other segments.
3. `getSentenceInstance(locale)` — sentence boundaries.
4. `getLineInstance(locale)` — **line break opportunities**.

`BreakIterator` does not perform the full job of a linguistic tokenizer, a modern emoji detector, a rendering engine, or a layout engine. It provides **boundary positions** that a program can iterate over and use as needed.

## 2. Creating a BreakIterator by Type and Locale

`BreakIterator` is an abstract class; typically you obtain an instance from a factory:

```java
import java.text.BreakIterator;
import java.util.Locale;

BreakIterator characters =
        BreakIterator.getCharacterInstance(Locale.US);
BreakIterator words =
        BreakIterator.getWordInstance(Locale.US);
BreakIterator sentences =
        BreakIterator.getSentenceInstance(Locale.US);
BreakIterator lines =
        BreakIterator.getLineInstance(Locale.US);
```

Zero-argument factory methods such as `getWordInstance()` use the **JVM default locale**. In an application serving users from multiple regions, you should not let the server's default locale silently dictate segmentation for every user.

After creating an instance, **you must pass the text**:

```java
words.setText("Hello, world!");
```

`BreakIterator` holds the text state and iteration position. When switching to another string, call `setText(...)` again. You can reuse one iterator for different strings sequentially, but you must not use the same mutable instance concurrently across multiple threads.

Each factory returns an iterator with a **different segmentation strategy**, not merely four names for the same algorithm. Exact results may vary by `Locale`, JDK, locale data provider, and Unicode data version.

## 3. Boundary Model: Start and End Indexes

When iterating over a string, `BreakIterator` returns **boundary indexes**, not a `String` directly for each word or sentence.

Suppose we have the string:

```text
Hello, world!
```

Boundaries are positions **between** characters, including the start position 0 and the end position equal to `text.length()`. A text segment is represented by the interval:

```text
[start, end)
```

- `start` **includes** the character at that position.
- `end` **excludes** the character at that position.
- Extract the segment with `text.substring(start, end)`.
- The UTF-16 length of the segment is `end - start`.

For example, `"Hello"` is `[0,5)`; the comma is at `[5,6)` and a space after it is at `[6,7)`.

Key APIs related to traversal:

| Method | Meaning |
|---|---|
| `first()` | Sets and returns the first boundary index |
| `last()` | Sets and returns the last boundary index |
| `next()` | Moves to the next boundary; returns `BreakIterator.DONE` at the end |
| `previous()` | Moves to the previous boundary; returns `DONE` at the start |
| `current()` | Returns the current boundary without moving |
| `following(offset)` | Boundary **after** the given index |
| `preceding(offset)` | Boundary **before** the given index |
| `isBoundary(offset)` | Checks whether a position is a boundary |
| `setText(String)` | Replaces the entire input text |

`BreakIterator.DONE` is a sentinel value, not a valid offset to pass to `substring`. You must check for it before slicing the string.

The indexes used in the examples have the same unit as `String.length()` and `substring(...)`: **UTF-16 code units**, not UTF-8 bytes, code point counts, or visible grapheme counts.

## 4. Standard Left-to-Right Iteration Pattern

Common structure:

```java
iterator.setText(text);
int start = iterator.first();

for (int end = iterator.next();
     end != BreakIterator.DONE;
     start = end, end = iterator.next()) {

    String segment = text.substring(start, end);
    // Process segment according to the iterator type.
}
```

This is an **illustrative code snippet**, assuming `iterator` and `text` have already been created in the method.

Workflow:

1. `first()` gets the first boundary.
2. `next()` gets the next boundary.
3. The pair `start, end` defines a segment `[start,end)`.
4. After processing, `start` becomes the previous `end`.
5. Loop until `DONE`.

The reason to use `end = iterator.next()` instead of `start + 1` is that a segment can contain multiple code units; boundaries must come from **segmentation rules**, not arbitrary index addition.

You can iterate backward:

```java
for (int end = iterator.last(), start = iterator.previous();
     start != BreakIterator.DONE;
     end = start, start = iterator.previous()) {

    String segment = text.substring(start, end);
}
```

The backward pattern is suitable when you need to find the word/sentence end near the cursor, though you still must handle `DONE` and not mix up the `start/end` order.

## 5. Character BreakIterator: Perceived Characters and Unicode

### Code Unit, Code Point, and Grapheme Cluster Differ

In Java, at least three concepts must be distinguished:

- **UTF-16 code unit:** 16-bit unit; `String.length()` counts these units.
- **Unicode code point:** a Unicode scalar/code value, which may occupy one or two UTF-16 code units.
- **Grapheme cluster:** the unit a user typically perceives as a single character, which may consist of multiple code points.

For example:

```java
String s = "a\u0301b";
System.out.println(s.length()); // 3
```

In this string, `a` + the combining acute accent can form one displayed cluster; the letter `b` is the next cluster. If you split by each code unit, you would separate the accent from the base letter.

`BreakIterator.getCharacterInstance(locale)` provides **character** boundaries to support segmentation closer to the text units users perceive, rather than always stepping one code unit at a time.

### Standalone Java 17+ Example: Letter with Combining Mark

Save `CharacterBreakDemo.java`:

```java
import java.text.BreakIterator;
import java.util.Locale;

public class CharacterBreakDemo {
    public static void main(String[] args) {
        String text = "a\u0301b";
        BreakIterator iterator =
                BreakIterator.getCharacterInstance(Locale.US);
        iterator.setText(text);

        System.out.println("length=" + text.length());

        for (int start = iterator.first(),
                 end = iterator.next();
             end != BreakIterator.DONE;
             start = end, end = iterator.next()) {

            System.out.printf(
                    "[%d,%d)=%s%n",
                    start, end, text.substring(start, end));
        }
    }
}
```

Compile/run:

```bash
javac CharacterBreakDemo.java
java CharacterBreakDemo
```

Verified output:

```text
length=3
[0,2)=á
[2,3)=b
```

The first segment consists of two code units (`a` and the combining mark), yet can be displayed as a single accented character. Using character boundaries is more appropriate than `substring(0,1)` when you need to move a cursor or slice displayed text.

### Emojis and Segmentation Limits in the JDK

For a simple emoji outside the BMP, `String.length()` can be 2 while `codePointCount(...)` is 1. Java example with a surrogate pair written using escapes:

```java
String emoji = "\uD83D\uDE42"; // U+1F642
System.out.println(emoji.length()); // 2
System.out.println(
        emoji.codePointCount(0, emoji.length())); // 1
```

Many `BreakIterator` implementations recognize ordinary surrogate pairs and do not split between the two code units. However, **do not claim this API is perfect for every modern emoji sequence**. Emojis can contain skin-tone modifiers, zero-width joiners, regional indicators, and complex sequences; support depends on the runtime's segmentation data/version.

If a professional editor, UI handling complex emojis, or grapheme counter needs to conform to up-to-date Unicode standards, test with real data and consider a dedicated segmentation library such as ICU4J. Do not use `codePointCount()` as an equivalent to grapheme segmentation: **a code point is not a grapheme cluster**.

## 6. Word BreakIterator: Words and Non-Word Segments

`getWordInstance(locale)` produces **word**-level boundaries. It does not return only a list of meaningful words; segments consisting of punctuation, whitespace, or numbers can also appear.

With:

```text
Hello, world! 42.
```

Segments observed in the JDK environment used for this article:

| Range `[start,end)` | Segment |
|---|---|
| `[0,5)` | `Hello` |
| `[5,6)` | `,` |
| `[6,7)` | Whitespace |
| `[7,12)` | `world` |
| `[12,13)` | `!` |
| `[13,14)` | Whitespace |
| `[14,16)` | `42` |
| `[16,17)` | `.` |

**Do not** call every `substring(start,end)` segment from the word iterator a "word" in a tokenizer. If an application wants to filter only segments containing letters or digits, an extra checking step is required.

For example:

```java
boolean containsLetterOrDigit =
        segment.codePoints().anyMatch(
                Character::isLetterOrDigit);
```

This is only a coarse filter, suitable for demos. A production **tokenizer** may need to keep apostrophes, hyphens, decimal numbers, emojis, hashtags, proper names, or units according to its own grammar.

### Standalone Java 17+ Example of Word Segmentation

Save `WordBreakDemo.java`:

```java
import java.text.BreakIterator;
import java.util.Locale;

public class WordBreakDemo {
    public static void main(String[] args) {
        String text = "Hello, world! 42.";
        BreakIterator words =
                BreakIterator.getWordInstance(Locale.US);
        words.setText(text);

        for (int start = words.first(), end = words.next();
             end != BreakIterator.DONE;
             start = end, end = words.next()) {

            String segment = text.substring(start, end);
            String printable = segment.replace(" ", "_");

            System.out.printf(
                    "[%d,%d)=%s%n", start, end, printable);
        }
    }
}
```

Run:

```bash
javac WordBreakDemo.java
java WordBreakDemo
```

Output:

```text
[0,5)=Hello
[5,6)=,
[6,7)=_
[7,12)=world
[12,13)=!
[13,14)=_
[14,16)=42
[16,17)=.
```

In the output, `_` is merely a **placeholder symbol for visibility** representing an ASCII space; the original text was not modified.

### Languages Without Spaces Between Words

For Thai, Chinese, Japanese, or other scripts, the notion of a "word" boundary may require dictionaries, segmentation models, or special rules. A locale-based `BreakIterator` is a starting point, not a guarantee of the accuracy of a dedicated linguistic tokenizer or search engine results. Even different JDKs or locale providers can produce different boundaries.

For Vietnamese, spaces usually separate **syllables** rather than always separating **compound words**. For example, `"học sinh"` has a space between two syllables yet may be treated as a single lexical unit depending on the task. If you need search, NLP word segmentation, or indexing, you must choose an appropriate tokenizer instead of assuming the word `BreakIterator` understands all Vietnamese compound words.

## 7. Sentence BreakIterator: Sentence Endings

`BreakIterator.getSentenceInstance(locale)` recognizes sentence boundaries based on sentence segmentation rules. It does not merely run `text.split("\\.")`.

Example:

```text
Hello world! How are you? Fine.
```

With `Locale.US`, the observed segments are:

```text
[0,13)=Hello world!_
[13,26)=How are you?_
[26,31)=Fine.
```

The `_` here represents the **trailing space at the end of each sentence**. This is very important: the intervals returned by the sentence iterator may **include trailing whitespace after punctuation**, because boundaries are defined across the text, not according to a requirement to trim every sentence.

### Complete Java 17+ Example

Save `SentenceBreakDemo.java`:

```java
import java.text.BreakIterator;
import java.util.Locale;

public class SentenceBreakDemo {
    public static void main(String[] args) {
        String text = "Hello world! How are you? Fine.";
        BreakIterator sentences =
                BreakIterator.getSentenceInstance(Locale.US);
        sentences.setText(text);

        for (int begin = sentences.first(),
                 end = sentences.next();
             end != BreakIterator.DONE;
             begin = end, end = sentences.next()) {

            String segment =
                    text.substring(begin, end).replace(" ", "_");
            System.out.printf(
                    "[%d,%d)=%s%n", begin, end, segment);
        }
    }
}
```

Run:

```bash
javac SentenceBreakDemo.java
java SentenceBreakDemo
```

Output:

```text
[0,13)=Hello_world!_
[13,26)=How_are_you?_
[26,31)=Fine.
```

The program does not drop any character from the original string: concatenating the segments sequentially in order reconstructs the exact original text, because the iterator only provides **break points**.

### The Abbreviation Period Trap

Strings like `"Dr. Smith arrived."` or `"Version 1.2 is ready."` contain periods, but not every period ends a sentence. Sentence `BreakIterator` is designed better than blindly splitting on periods, yet recognition of abbreviations, proper names, and context may still be imperfect.

If an application needs sentence segmentation for NLP or legal/medical text extraction, add domain-specific tests and consider a specialized engine rather than assuming `BreakIterator` boundaries are always semantically accurate.

## 8. Line BreakIterator: Possible Line-Break Positions, Not Pre-Laid Lines

`BreakIterator.getLineInstance(locale)` returns **potential line break opportunities** according to language rules and text segmentation conventions. It does **not** calculate font width, container size, or pixel counts.

Example:

```text
Hello world again.
```

With `Locale.US`, the observed segments are:

```text
[0,6)=Hello_
[6,12)=world_
[12,18)=again.
```

Valid break positions are reported as 6, 12, and 18 according to the segmentation in the example; `_` represents a space. If an application has a very wide drawing area, it may not wrap at 6 or 12. If the area is narrow, the layout engine must choose an appropriate break opportunity based on glyph metrics and layout policy.

### Standalone Java 17+ Example

Save `LineBreakDemo.java`:

```java
import java.text.BreakIterator;
import java.util.Locale;

public class LineBreakDemo {
    public static void main(String[] args) {
        String text = "Hello world again.";
        BreakIterator lines =
                BreakIterator.getLineInstance(Locale.US);
        lines.setText(text);

        for (int start = lines.first(), end = lines.next();
             end != BreakIterator.DONE;
             start = end, end = lines.next()) {

            System.out.printf(
                    "[%d,%d)=%s%n",
                    start,
                    end,
                    text.substring(start, end).replace(" ", "_"));
        }
    }
}
```

Compile/run:

```bash
javac LineBreakDemo.java
java LineBreakDemo
```

Output:

```text
[0,6)=Hello_
[6,12)=world_
[12,18)=again.
```

**Do not treat the line iterator's segments as rendered page layout results**. Line wrapping must also be combined with:

- Actual display width and font.
- Glyph width, shaping, ligatures, and writing direction.
- Mandatory line breaks caused by `\n`, `\r\n`, or line-break control characters.
- Rules forbidding breaks before/after certain punctuation marks.
- Policy for handling long words with no suitable break position.
- Hyphenation rules if supported by the system.

With Swing/JavaFX or layout toolkits, prefer the UI library's layout mechanism. `BreakIterator` helps **find break candidates**, not replace a rendering engine.

## 9. A Java 17+ Example Sharing a Boundary Traversal Helper

You can avoid code duplication in an application by writing a method that accepts an already-created `BreakIterator`:

```java
import java.text.BreakIterator;
import java.util.ArrayList;
import java.util.List;

public class BoundarySegments {
    public static List<String> segments(
            String text, BreakIterator iterator) {

        iterator.setText(text);
        List<String> result = new ArrayList<>();

        for (int begin = iterator.first(), end = iterator.next();
             end != BreakIterator.DONE;
             begin = end, end = iterator.next()) {

            result.add(text.substring(begin, end));
        }

        return result;
    }
}
```

This is a valid compilable Java class containing a utility method, but it **has no `main`** and cannot be executed directly with `java BoundarySegments`. It is called from another class or a unit test:

```java
List<String> parts = BoundarySegments.segments(
        "Hello world!",
        BreakIterator.getWordInstance(Locale.US));
```

If you want the call snippet above to run in a separate class, you need to import `List`, `Locale`, and `BreakIterator`.

With this method, **returned segments can be punctuation or whitespace**. Do not name the result `wordsOnly` when using a word iterator. If you need offset information for highlighting or cursor placement, return a `Segment(start,end,text)` data type instead of returning only strings.

### Designing a Clear Segment Type

In Java 17 you can declare a record:

```java
record Segment(int start, int end, String text) {}
```

When building the list, add `new Segment(begin, end, text.substring(begin,end))`. A record lets external code access positions via `start()`, `end()`, and `text()` without manually summing segment lengths.

If the data is Unicode-normalized or has spaces replaced before segmentation, the offsets are valid only for **the specific string passed into the iterator**, and do not automatically match the original raw input.

## 10. Finding Boundaries Near the Cursor: following, preceding, isBoundary

Besides full traversal, an editor or input form often needs to:

- Find the end of the word after the cursor position.
- Jump back to the start of the word before the cursor position.
- Check whether the cursor position lies exactly on a segmentation boundary.

The methods:

```java
int after = iterator.following(offset);
int before = iterator.preceding(offset);
boolean boundary = iterator.isBoundary(offset);
```

Semantics to remember:

- `following(offset)` returns the boundary **strictly greater than** `offset`, not greater than or equal to.
- `preceding(offset)` returns the boundary **strictly less than** `offset`.
- `isBoundary(offset)` indicates whether `offset` is a boundary; note that this method can mutate the iterator's internal position per its API contract.
- When no boundary remains in the requested direction, `BreakIterator.DONE` is returned; do not pass this sentinel to `substring`.

### Standalone Java 17+ Example

Save `BoundaryNavigationDemo.java`:

```java
import java.text.BreakIterator;
import java.util.Locale;

public class BoundaryNavigationDemo {
    public static void main(String[] args) {
        BreakIterator it =
                BreakIterator.getWordInstance(Locale.US);
        it.setText("Hello, world! 42.");

        System.out.println("following0=" + it.following(0));
        System.out.println("preceding8=" + it.preceding(8));
        System.out.println("isBoundary5=" + it.isBoundary(5));
        System.out.println("isBoundary6=" + it.isBoundary(6));
    }
}
```

Run:

```bash
javac BoundaryNavigationDemo.java
java BoundaryNavigationDemo
```

Verified output:

```text
following0=5
preceding8=7
isBoundary5=true
isBoundary6=true
```

In the example string, position 7 starts the word `world`. `preceding(8)` returns `7`, the boundary immediately before offset 8. `following(0)` returns `5`, right after `Hello`.

**Be careful with state:** after calling `following`, `preceding`, or `isBoundary`, the iterator's current position may change. If you later want to iterate from the start, call `first()`; if from the end, call `last()`. Do not continue relying on the old `current()` without checking.

## 11. Do Not Confuse Boundaries with Semantic Analysis

The four iterator types solve different levels of problems:

| Goal | Suitable Iterator | Not Solved Automatically |
|---|---|---|
| Move across character clusters | Character | All modern emoji grapheme sequences, shaping/rendering |
| Split text into word/punctuation segments | Word | Full tokenizer, compound words/grammar |
| Find sentence break points | Sentence | Semantic understanding and all abbreviations |
| Find line-wrap opportunities | Line | Width measurement and actual layout |

For example, an editor application might use:

- Character boundaries for cursor movement/selection.
- Word boundaries for selecting a word on double-click.
- Sentence boundaries for selecting or processing a sentence.
- Line boundaries to help layout find break points.

However, **the same offset** can be a boundary in one mode and not in another. Do not use word boundaries as a proxy for characters, or line boundaries to measure word length.

## 12. Unicode Normalization and Offsets

Unicode normalization can change string length. For example:

```java
String raw = "a\u0301";
String nfc = java.text.Normalizer.normalize(
        raw, java.text.Normalizer.Form.NFC);

System.out.println(raw.length()); // 2
System.out.println(nfc.length()); // 1
```

This is an illustrative snippet. If you run `BreakIterator` on `nfc`, the boundaries correspond only to **the `nfc` string**. You must not use them directly to slice `raw` if length or Unicode code order changed.

A text-processing pipeline needs to decide:

1. Whether to keep raw text or use normalized text for rendering.
2. Which version `BreakIterator` runs on.
3. Whether search indexing and highlighting use the same version or maintain an offset mapping table.
4. Which index system selection and cursor positions are stored in.

Some UI bugs appear only with Vietnamese accents in combining form, so you should test both precomposed and decomposed forms.

## 13. Segmentation Boundaries Depend on Locale and Runtime

`BreakIterator` provides overloads accepting `Locale`:

```java
Locale vietnamese = Locale.forLanguageTag("vi-VN");
BreakIterator wordIterator =
        BreakIterator.getWordInstance(vietnamese);
```

However, two things must be separated:

**First:** passing a locale lets the implementation select the corresponding segmentation rules when supported.

**Second:** segmentation results are **not guaranteed to be identical across all JDKs/providers**, nor does it automatically become a semantically accurate word segmenter for every language.

Long-lived text-processing data and programs should:

- Explicitly record the chosen locale.
- Test with real words/sentences in the target language.
- Re-check when upgrading JDKs or changing locale providers.
- For Vietnamese NLP tasks, consider a dedicated Vietnamese analyzer instead of treating spaces between syllables as always being word boundaries.
- For emojis and complex graphemes, verify the Unicode version supported by the runtime.

Do not hardcode demo offsets like `[0,5)` as general rules. They are only specific results for a specific string.

## 14. Performance and State Limitations

`BreakIterator` is a **stateful iterator**. Each `setText` attaches new text; `next()` and `previous()` mutate the position. Therefore:

- Do not share a single instance whose `setText` is being changed across multiple threads without synchronization.
- For each short task, create an instance by type and locale or manage dedicated copies.
- If you need to run across multiple strings in one thread, you can reuse the instance and call `setText` again, but do not assume `current()` remains valid for the old string.
- Avoid calling `setText` in the middle of an iteration loop.
- When filtering words, always check `end != DONE` before slicing the string.

For very long texts, storing a list of all segments in memory may be unnecessary; you can stream each `[start,end)`. However, if the UI frequently jumps backward/forward and needs offsets of many segments, caching can improve performance in some designs.

Do not assume segmentation results from the current runtime version are stable data for permanent storage. If you persist offsets long-term while text can be edited or normalized, you must have a mechanism to update the offsets.

## 15. Common Pitfalls

**1. Thinking `BreakIterator.getCharacterInstance` always steps by exactly one `char`.** Clusters with combining marks can contain multiple code units.

**2. Thinking one code point always equals one grapheme cluster.** Complex emojis or combining marks can consist of multiple code points.

**3. Thinking the word iterator only returns alphabetic words.** It also returns punctuation, whitespace, numbers, and other segments.

**4. Splitting Vietnamese words by spaces and treating each part as a lexical word.** Spaces can separate the syllables of a compound word.

**5. Splitting sentences with `split("\\.")`.** Fails to properly handle abbreviation periods, sentences with `?`/`!`, and locale rules.

**6. Treating line `BreakIterator` as a pixel-based line-wrapping engine.** It only returns break opportunities, not font/container measurements.

**7. Forgetting `setText` before iterating.** The iterator does not automatically know the application's current text.

**8. Not handling `DONE`.** The sentinel cannot be used as `endIndex` in `substring`.

**9. Mistaking `[start,end)` for an interval inclusive of `end`.** `String.substring(start,end)` is end-exclusive.

**10. Using boundaries from normalized text to slice raw text.** Offsets may no longer correspond.

**11. Using an uncontrolled default locale.** Behavior can differ across servers or users.

**12. Assuming `BreakIterator` always identifies every emoji and specialized text accurately.** Unicode segmentation and locale data still have implementation limits.

**13. Continuing to use an old `current()` after `following`/`preceding`/`isBoundary`.** The iterator has mutable state that changes.

**14. Using UTF-16 offsets as UTF-8 byte offsets or grapheme indexes.** Indexes must be converted according to the target API.

**15. Reusing a single mutable instance across concurrent requests.** Text data and boundaries risk getting mixed up.

## 16. Testing Checklist

| Scenario | What to Verify |
|---|---|
| Simple ASCII string | Concatenating all segments must reconstruct the exact string |
| Letter with combining mark, e.g. `a\u0301` | Character iterator can keep the mark cluster together with the letter |
| Single non-BMP emoji code point | Must not arbitrarily split inside a surrogate pair; verify on runtime |
| Multi-code-point / ZWJ emoji | Needs thorough testing; may require ICU4J |
| Punctuation and whitespace | Word iterator still returns non-word segments |
| Sentences joined by `!`, `?`, `.` | Sentence boundaries and trailing space after sentences |
| Abbreviations | Must not split mechanically on periods |
| Text containing `\n` or `\r\n` | Distinguish forced line breaks from break opportunities |
| Languages without spaces between words | Check quality per locale |
| NFC-normalized text vs. raw NFD | Offsets may differ |
| Indexes near start/end of text | `following/preceding` return `DONE` appropriately |
| Empty string | Produces no segments and never calls `substring` with `DONE` |
| Segmentation across multiple threads | Mutable iterator is not improperly shared |

A useful invariant in unit tests: if you iterate sequentially from `first()` to `DONE`, the `[start,end)` intervals must be contiguous in order and concatenate to exactly the input text, provided the API is applied to the entire original string. This test helps catch dropped spaces or punctuation caused by your own application logic.

## 17. Self-Check Q&A

**Q1.** What are the four main factory methods of `BreakIterator`?

**Answer:** `getCharacterInstance`, `getWordInstance`, `getSentenceInstance`, and `getLineInstance`, with overloads accepting `Locale`.

**Q2.** Does the word `BreakIterator` return only alphabetic words?

**Answer:** No. It can also return whitespace, punctuation, and numeric segments; you must filter according to application requirements.

**Q3.** In `"Hello, world! 42."`, what interval does `Hello` occupy?

**Answer:** `[0,5)`. End index 5 is not included in the segment.

**Q4.** How is `BreakIterator.DONE` used?

**Answer:** As a sentinel value indicating no more boundaries when calling `next()` or `previous()`, which must be checked before slicing the string.

**Q5.** Does the line iterator automatically wrap lines when the viewport is only 80 pixels wide?

**Answer:** No. It reports potential break positions; choosing among them depends on font, width, and the layout engine.

**Q6.** Why shouldn't `"a\u0301b"` always be sliced with `substring(0,1)` to get the first character?

**Answer:** Because the first displayed character can consist of `a` and a combining acute accent, occupying two code units.

**Q7.** Can offsets from `BreakIterator` after NFC be used to slice raw NFD text?

**Answer:** Not reliably. Normalization can change lengths/offsets; use the same string or maintain a mapping.

**Q8.** When should you consider ICU4J or a dedicated tokenizer?

**Answer:** When the application requires modern emoji/grapheme segmentation, complex language word segmentation, or high-accuracy NLP beyond the limits of the default `BreakIterator`.

## 18. Key Takeaways

`BreakIterator` provides **locale-sensitive text boundaries** at four levels: character, word, sentence, and line-break opportunities. The standard traversal loop uses `first()`, `next()`, and `BreakIterator.DONE`, then extracts each segment via `substring(start,end)` using UTF-16 indexes.

The core takeaway is that **a boundary does not equal semantics**: "word" does not contain only words, "sentence" does not necessarily strip whitespace, "line" is not visual layout, and "character" needs verification with complex Unicode graphemes. To build correct multilingual Java applications, choose the iterator type and locale based on the task and test with real user text.

**Official references:** [Java SE 17 — BreakIterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/BreakIterator.html) · [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html) · [Java SE 17 — Character](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html) · [Unicode Standard Annex #29 — Text Segmentation](https://www.unicode.org/reports/tr29/) · [Unicode Standard Annex #14 — Line Breaking](https://www.unicode.org/reports/tr14/).
