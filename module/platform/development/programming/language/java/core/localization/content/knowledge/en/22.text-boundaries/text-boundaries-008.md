# StringCharacterIterator and Its Limits When Used for Program Source Code

`java.text.StringCharacterIterator` is a Java Core class implementing the `CharacterIterator` interface, allowing **forward, backward, and indexed positioning within a character string**. It is useful when a text API needs a cursor over a string region, yet the name "CharacterIterator" is very easy to misunderstand: this class iterates over **UTF-16 `char` units**, does not combine surrogate pairs into Unicode code points, is unaware of graphemes, does not find word boundaries, and **cannot parse Java source code syntax**.

This lesson belongs to the **Text Boundaries** module. Its goal is to understand the iterator contract, use `begin/end/index` properly, distinguish code units / code points / visible characters, and recognize when you need `BreakIterator` or a lexer/parser instead of continuing to write manual `char` loops. All standalone runnable source examples target Java 17+.

## 1. Concept and Scope of Responsibility

`CharacterIterator` is an interface in `java.text` describing a bidirectional, positioned traversal protocol over a text region. `StringCharacterIterator` implements that interface over a `String`, providing:

- a readable region with start index `getBeginIndex()` and end index `getEndIndex()`;
- a current cursor index `getIndex()`;
- operations `first()`, `last()`, `current()`, `next()`, `previous()`, and `setIndex(int)`;
- the special value `CharacterIterator.DONE` when no valid character remains;
- state cloning capability via `clone()`.

`String` in Java may be immutable, yet **the iterator has mutable position state**. Calling `first()` or `setIndex()` changes the cursor of that iterator itself, so do not share one instance across multiple algorithms or threads expecting each caller to keep its own position.

Minimal illustrative snippet:

~~~java
import java.text.CharacterIterator;
import java.text.StringCharacterIterator;

StringCharacterIterator it =
        new StringCharacterIterator("Java");

for (char c = it.first();
        c != CharacterIterator.DONE;
        c = it.next()) {
    System.out.print(c);
}
// Prints: Java
~~~

This is an **in-method illustrative snippet**. `first()` positions at the start and returns the first character; `next()` **advances by one position first and then returns the character**. Calling `next()` before processing the first character skips the first element. This loop also has an edge case with `U+FFFF`; see section 5.

### Not BreakIterator

`BreakIterator` finds visible character, word, line, or sentence boundaries according to text/locale rules; `StringCharacterIterator` only returns the `char` at a position. A word-finding algorithm can use the iterator as a **data source**, but the iterator does not itself know where spaces, punctuation, or word boundaries are.

## 2. Methods and Position Contract

Example string `"abXYZ"`:

~~~text
Text:           a  b  X  Y  Z
UTF-16 index:   0  1  2  3  4
endIndex:                      5
~~~

The `end` index is **exclusive**: if a region `[begin,end)` has `begin=1` and `end=4`, it covers indexes 1, 2, 3, namely `bXY`. However, `getIndex()` **is allowed to equal `end`** to represent the cursor positioned at the end.

| API | Effect | Notes |
| --- | --- | --- |
| `new StringCharacterIterator(text)` | Creates cursor over full string at 0 | Works for empty strings |
| `new StringCharacterIterator(text,pos)` | Sets initial position | `pos` must be valid |
| `new StringCharacterIterator(text,begin,end,pos)` | Reads only `[begin,end)` | Indexes still belong to original string |
| `first()` | Moves to `begin`, returns first char | Returns `DONE` if empty |
| `last()` | Moves to `end-1`, returns last char | Returns `DONE` if empty |
| `current()` | Returns `char` at current position | At `end`, returns `DONE` |
| `next()` | Advances one position, returns new char | If reaching `end`, returns `DONE` |
| `previous()` | Moves back one position, returns new char | Does not go before `begin` |
| `setIndex(p)` | Sets position to `p` | Valid when `begin <= p <= end` |
| `getIndex()` | Gets current index | May equal `end` |
| `getBeginIndex()`, `getEndIndex()` | Region bounds | `begin` inclusive; `end` exclusive |

A window:

~~~java
StringCharacterIterator it =
        new StringCharacterIterator("abXYZ", 1, 4, 2);

System.out.println(it.current());       // X
System.out.println(it.getBeginIndex()); // 1
System.out.println(it.getEndIndex());   // 4
~~~

This is an **illustrative snippet** requiring `import java.text.StringCharacterIterator`. Here `first()` returns `b`, `last()` returns `Y`; calling `next()` after `last()` moves the cursor to 4 and returns `DONE`. Calling `previous()` from position 4 returns to 3 and returns `Y`.

`setIndex(end)` is **valid** and returns `DONE`. Conversely, `setIndex(end+1)` or `setIndex(begin-1)` throws `IllegalArgumentException`. When handling regions supplied by APIs or users, verify:

~~~text
0 <= begin <= end <= text.length()
begin <= pos <= end
~~~

In particular, `begin/end` are **UTF-16 offsets** in `String`, not byte offsets in a UTF-8 file, code point counts, or reader-perceived "letters".

## 3. UTF-16 `char` Is Not Equivalent to a Unicode Code Point

Java `String` indexes by UTF-16 code units. A `char` value is a 16-bit unit. A Unicode code point outside the Basic Multilingual Plane (BMP) requires **two** units: a high surrogate and a low surrogate.

For `"A😀B"`:

~~~text
Reader:           A      😀       B          (3 perceived clusters in example)
Code points:     U+0041  U+1F600 U+0042      (3)
UTF-16 units:      A     high low   B         (4)
UTF-16 indexes:    0       1    2    3
~~~

`String.length()` returns `4`, `codePointCount(0,length)` returns `3`; a `char`-based iterator visits **4** elements. Calling `substring(0,2)` can split mid-surrogate pair; `setIndex(2)` points at the low surrogate rather than a whole emoji.

If an algorithm needs code points:

~~~java
String text = "A\uD83D\uDE00B";
int count = text.codePointCount(0, text.length()); // 3

for (int cp : text.codePoints().toArray()) {
    // cp is an int representing a Unicode code point
}
~~~

This is a Java 17 illustrative snippet. Beyond `String.codePoints()`, there are `codePointAt(index)` and `Character.charCount(cp)` for manual position control:

~~~java
int cp = text.codePointAt(index);
index += Character.charCount(cp);
~~~

Here `index` must be a valid position, and the application must have a policy for unpaired surrogates or malformed input. Using `charAt` or `StringCharacterIterator` without pairing surrogates produces wrong results when an algorithm genuinely needs code point processing.

### A Code Point Is Not a Grapheme Cluster Either

For `"e\u0301"` (`e` + combining acute accent):

~~~text
UTF-16 units: 2
Code points: 2
User typically sees: 1 accented letter
~~~

An emoji with a skin tone modifier or a ZWJ sequence can also form one grapheme cluster from multiple code points. `StringCharacterIterator` has no grapheme-boundary detection algorithm; `String.codePoints()` does not merge code points into graphemes either. When you need text selection, UI cursor movement, or visible character counts, use a tested Unicode segmentation solution such as `BreakIterator.getCharacterInstance(locale)` within its supported scope.

**Do not assume** grapheme/emoji data on every JDK 17 matches the latest Unicode/UAX #29; check the runtime version and your product's real strings.

## 4. Forward Traversal, Backward Traversal, and Cursor Management

Forward traversal:

~~~java
for (char c = it.first();
        c != CharacterIterator.DONE;
        c = it.next()) {
    // Process one UTF-16 char
}
~~~

Backward traversal:

~~~java
for (char c = it.last();
        c != CharacterIterator.DONE;
        c = it.previous()) {
    // Process one UTF-16 char
}
~~~

These are illustrative snippets assuming `it` has been created. The difference between `current` and `next` is worth noting: `current` **does not move**, whereas `next` changes the index; mixing them up can undercount or double-count a character.

When an algorithm must walk from a middle position in both directions, record `getIndex()` before moving the cursor. If you reuse one iterator for two scans and call `first` again, the previous scan's cursor is not preserved. Create another iterator or `clone` when two independent traversals are needed.

### A Window Is Not a String Copy

`new StringCharacterIterator(text,begin,end,pos)` only restricts the traversal range. It does not rebase `begin` to 0, alter byte layout, or allocate a new token. If you want an independent `String` for the window, call `text.substring(begin,end)` when appropriate; only do so if `begin/end` are exact UTF-16 offsets and do not split mid-surrogate pair accidentally.

Windows are very useful when **another parser has already determined the exact range** of a word/token and you want to use an iterator to re-scan it. The iterator does not find that range itself.

## 5. CharacterIterator.DONE and the U+FFFF Case

The constant `CharacterIterator.DONE` has the `char` value `'\uFFFF'`, a **Unicode noncharacter** chosen as the end-of-text sentinel. The interface was designed assuming this value does not appear as normal text content.

However, a Java `String` **can contain the code unit `0xFFFF`**. With uncontrolled input, a loop checking only `c != CharacterIterator.DONE` can stop **right at a data character U+FFFF**, even though the cursor has not reached `getEndIndex()`.

Instead of relying on the sentinel, when you must traverse **every UTF-16 unit of arbitrary input**, use an index-based loop:

~~~java
for (int i = it.getBeginIndex(); i < it.getEndIndex(); i++) {
    char c = it.setIndex(i);
    // c may equal DONE yet still be data inside the region
}
~~~

This is an illustrative snippet assuming an existing variable `it`. It processes every code unit in the region, including a value matching the sentinel. This does **not** turn it into a code-point iterator or lexical analyzer; it merely avoids mistaking a data value for the end marker.

In applications whose data is verified not to contain U+FFFF, the `c != DONE` loop is the pattern shown in the API docs. For untrusted data or parsing/security tools, understand this limitation and define an input validation policy.

## 6. Complete Java 17 Example

The following program demonstrates index windows, surrogate pairs, misunderstood comment markers, and the U+FFFF sentinel. Output uses ASCII letters/digits so it does not depend on whether the terminal renders emojis well.

Create **`StringCharacterIteratorDemo.java`**:

~~~java
import java.text.CharacterIterator;
import java.text.StringCharacterIterator;

public class StringCharacterIteratorDemo {
    public static void main(String[] args) {
        String ascii = "abXYZ";
        StringCharacterIterator window =
                new StringCharacterIterator(ascii, 1, 4, 2);

        System.out.println("Range: "
                + window.getBeginIndex()
                + ".." + window.getEndIndex());
        System.out.println("Current: " + window.current());
        System.out.println("First: " + window.first());
        System.out.println("Last: " + window.last());
        System.out.println("Next is DONE: "
                + (window.next() == CharacterIterator.DONE));
        System.out.println("Index after end: " + window.getIndex());
        System.out.println("Previous: " + window.previous());
        System.out.println("At end is DONE: "
                + (window.setIndex(4) == CharacterIterator.DONE));

        String emoji = "A\uD83D\uDE00B";
        int high = 0;
        int low = 0;
        StringCharacterIterator units =
                new StringCharacterIterator(emoji);

        for (char c = units.first();
                c != CharacterIterator.DONE;
                c = units.next()) {
            if (Character.isHighSurrogate(c)) high++;
            if (Character.isLowSurrogate(c)) low++;
        }

        System.out.println("UTF-16 units: " + emoji.length());
        System.out.println("Code points: "
                + emoji.codePointCount(0, emoji.length()));
        System.out.println("Surrogate halves: " + high + "/" + low);

        String code = "\"// inside string\"; // actual comment";
        int naiveMarkers = 0;
        for (int i = 0; i + 1 < code.length(); i++) {
            if (code.charAt(i) == '/'
                    && code.charAt(i + 1) == '/') {
                naiveMarkers++;
            }
        }
        System.out.println("Naive // markers: " + naiveMarkers);

        String containsDone = "A" + (char) 0xFFFF + "B";
        int seen = 0;
        StringCharacterIterator sentinel =
                new StringCharacterIterator(containsDone);
        for (char c = sentinel.first();
                c != CharacterIterator.DONE;
                c = sentinel.next()) {
            seen++;
        }
        System.out.println("DONE sentinel ambiguity: "
                + seen + "/" + containsDone.length());
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 -encoding UTF-8 StringCharacterIteratorDemo.java
java StringCharacterIteratorDemo
~~~

Stdout verified on the JDK:

~~~text
Range: 1..4
Current: X
First: b
Last: Y
Next is DONE: true
Index after end: 4
Previous: Y
At end is DONE: true
UTF-16 units: 4
Code points: 3
Surrogate halves: 1/1
Naive // markers: 2
DONE sentinel ambiguity: 1/3
~~~

**Explanation:**

1. The region `[1,4)` on `"abXYZ"` contains only `bXY`. `current` at position 2 is `X`; `last` returns `Y`; the following `next` moves to position `4` and returns `DONE`; `previous` from there returns to `Y`.
2. `A😀B` has four UTF-16 code units yet three code points. The iterator visits one high surrogate and one low surrogate rather than synthesizing an "emoji" object.
3. The simulated source string contains two `//` pairs, yet only the pair outside the string literal is a Java comment. The count 2 is **wrong if used as a comment count**.
4. The string `A + U+FFFF + B` has three code units, yet the loop stops upon encountering `U+FFFF` and counts only 1. This is an intentional example of `DONE` ambiguity.

## 7. Why Can't It Be Used Directly to Understand Program Code?

`StringCharacterIterator` has no concept of **token**, **keyword**, **string literal**, **comment**, **operator**, or **AST**. It only reports which `char` unit sits at which position. A **lexer** for Java must take source text and produce tokens according to the lexical specification. Only then does a **parser** analyze syntactic structure (declarations, expressions, statements...) based on those tokens.

Example:

~~~java
String source = "\"// inside string\"; // real comment";
~~~

This creates a runtime string simulating source text. There are two `//` pairs, yet one sits inside a string literal. A loop checking `source.charAt(i)=='/' && source.charAt(i+1)=='/'` finds both. Only a lexer tracking literal state can tell which pair is a comment.

A real Java lexer must handle:

- whitespace, line terminators, and line/column positions;
- Unicode escapes per Java input translation rules;
- line comments `//` and block comments `/* ... */`;
- string literals, character literals, escapes, and text blocks;
- integer/floating-point literals with decimal points, prefixes, suffixes, and digit separators;
- Unicode identifiers, keywords, and contextual keywords;
- multi-character operators/tokens such as `==`, `!=`, `->`, `::`, `&&`;
- syntactic cases and rules across Java versions;
- lexical errors, diagnostics, and error recovery.

A simplified state machine might have these states:

~~~text
DEFAULT
  "       → STRING
  //      → LINE_COMMENT
  /*      → BLOCK_COMMENT
STRING
  escape  → handle next character per grammar
  "       → DEFAULT
LINE_COMMENT
  newline → DEFAULT
BLOCK_COMMENT
  */      → DEFAULT
~~~

This is **only a conceptual diagram**, not a valid Java lexer: text blocks, Unicode escape preprocessing, and many other details remain. A lexer may use `StringCharacterIterator` as a **`char` source**, yet its correctness is determined by **the algorithm and JLS specification**.

### Unicode Escapes Differ from Runtime Strings

In Java source code, sequences of backslashes and `u` can be processed during translation steps **prior to tokenization**, under the validity rules for Unicode escapes in the JLS. That differs from already having a runtime `String` and passing it into an iterator.

Do not write a regex to replace every `\uXXXX`-like sequence and call it a lexer; valid backslash rules, Unicode escapes, and source-translation phases must conform to the Java specification. For linting, refactoring, compilation, or security scanning tools, prefer the compiler API or a specialized lexer/parser tested against the target Java version.

### Identifiers in Java Are Case-Sensitive

Java does not fold identifiers to lowercase by default: `name` and `Name` are two distinct names. `StringCharacterIterator` cannot validate a legal identifier merely by checking `Character.isLetter(c)`.

If you must traverse a Unicode identifier, consider the **code point** APIs:

~~~java
int cp = source.codePointAt(index);
boolean start = Character.isJavaIdentifierStart(cp);
boolean part = Character.isJavaIdentifierPart(cp);
index += Character.charCount(cp);
~~~

This is an illustrative snippet assuming valid `String source` and `int index`. Those checks on `int cp` only assist with code point classification; they do **not** replace checking keywords, Unicode escapes, lexical context, ignorable characters, or Java grammar.

## 8. Choosing the Right Tool for the Boundary Type

| Need | Tool/Strategy | Limitation |
| --- | --- | --- |
| Traverse a UTF-16 region in `String` | `StringCharacterIterator` | Returns only `char` and index; has sentinel |
| Get `char` at a specific position | `String.charAt(i)` | Does not combine code points |
| Traverse Unicode code points | `String.codePoints()`, `codePointAt` | Does not split graphemes |
| Segment words, sentences, lines, visible letters | `BreakIterator` / Unicode segmentation | Depends on rules/runtime; does not parse Java |
| Normalize Unicode representation | `java.text.Normalizer` | Unaware of words/tokens |
| Identify Java lexical tokens | JLS-compliant lexer | Needs states, escapes, versioning |
| Parse Java syntax, refactor | Parser/compiler API, AST | Needs structural semantics |
| Validate Unicode identifiers | Code-point APIs and grammar checks | Not `isJavaIdentifierStart` alone |
| Read source files | `Reader`/appropriate charset then lexer | UTF-8 bytes differ from UTF-16 offsets |

### How Do BreakIterator and CharacterIterator Work Together?

`BreakIterator` can receive text via `setText(String)` or `setText(CharacterIterator)`. That does **not** make `StringCharacterIterator` boundary-aware: it is a source/cursor; the break-finding algorithm belongs to `BreakIterator`.

~~~text
StringCharacterIterator:   UTF-16 character/unit at offset
BreakIterator:             rule-based text break positions
Java Lexer:                tokens per lexical grammar
Java Parser:               syntactic structure / AST
~~~

Using the right layer depends on whether you want to display/edit natural text, process code points, or genuinely understand source code.

## 9. Byte, UTF-16, Code Point, and Editor Offsets

Java source on disk is often stored as UTF-8. After decoding with a charset, a Java `String` uses UTF-16 indexes. Therefore:

~~~text
UTF-8 bytes → decode → Java String (UTF-16 indexed)
                           |
                           v
                       lexer/parser
                           |
                           v
                       token spans
~~~

A byte offset in a file does **not** automatically correspond to a `String` index. A code-point index also differs from a UTF-16 index whenever non-BMP code points exist.

Name position contracts explicitly:

~~~text
startByteOffset
startUtf16Offset
endUtf16Offset
startCodePointIndex
startLine
startColumn
~~~

Do not call `substring(startByteOffset,endByteOffset)` if those numbers are actually byte offsets. Do not compute source offsets by "adding 1 per visible character": Unicode combining marks, surrogate pairs, tabs, and CRLF can make the measurement units diverge.

When a parser returns a validated UTF-16 range, `StringCharacterIterator(text,begin,end,pos)` can be handy for re-reading that slice of source. However, **the iterator does not produce token ranges**, does not count lines/columns automatically, and does not guarantee ranges align with grapheme/code point boundaries.

## 10. Performance, State, and Alternatives

- `StringCharacterIterator` is stateful, risking conflicts if reused across multiple scans.
- In a linear scan, cost is mainly reading UTF-16 units sequentially; it does not pre-build a code point list or AST.
- If you only need one position, `charAt(i)` is usually simpler.
- When reading very large files or network data, a properly designed `Reader`/stream-based lexer with lookahead can avoid holding the entire source in one `String`; still, grammar correctness remains the primary requirement.
- Do not use `StringCharacterIterator` to decode files yourself; the charset is applied when reading bytes.
- Do not use it to perform Unicode normalization or locale-sensitive case conversion.
- If an algorithm needs to share source content across multiple cursors, create separate iterators or `clone` when appropriate instead of sharing one mutable cursor.
- For syntax highlighting, code navigation, or refactoring, a compiler/parser is far more reliable than simple regexes, especially when source contains varied literals and escapes.

## 11. Common Mistakes Table

| Mistake | Why It Is Wrong | How to Avoid |
| --- | --- | --- |
| Treating `char` as a Unicode code point | Emojis have surrogate pairs | Use code-point APIs |
| Treating a code point as a visible character | Combining marks / emoji sequences | Use Unicode segmentation |
| Using the iterator as a lexer | No lexical states | JLS-compliant lexer/parser |
| Counting every `//` as a comment | May lie inside a literal | Properly parse strings/comments |
| Using simplified regex for text blocks/escapes | Lacks Java grammar | Tested parser/lexer |
| Mistaking `end` for inclusive | `end` is one past the region | Always use `[begin,end)` |
| Thinking `setIndex(end)` throws an error | `end` is valid for the cursor | Handle `DONE` |
| Relying solely on `c != DONE` with U+FFFF input | Data value collides with sentinel | Validation or index loop |
| Using UTF-8 byte offsets as UTF-16 indexes | Lengths differ | Convert units properly |
| Sharing an iterator across threads | Position gets mutated | Separate instances |
| Thinking `BreakIterator` is a lexer | Natural-text word rules differ from Java tokens | Separate processing layers |
| Using `isJavaIdentifierStart(char)` for all Unicode | Supplementary code points exist | Use `int` overload and grammar |
| Lowercasing identifier names before parsing | Java is case-sensitive | Preserve source text |
| Using the iterator to count UI graphemes | No segmentation | Appropriate boundary tool |

## 12. Testing and Exercises

A test matrix should include:

- Region `new StringCharacterIterator("abXYZ",1,4,2)`: verify `current/first/last/next/previous` and `getIndex` at `end`.
- Empty region `[begin,begin)`: verify `DONE` and no out-of-bounds access.
- `setIndex(end)` succeeds; `setIndex(end+1)` throws `IllegalArgumentException`.
- `A😀B`: 4 UTF-16 units, 3 code points; iterator sees two surrogate halves.
- `e + combining acute`: may be one visible letter yet two code points.
- String containing `U+FFFF`: sentinel loop stops early; index loop still sees all units.
- `//` inside and outside a string literal: naive counter gets comment count wrong.
- Source with escapes, text blocks, Unicode identifiers: test with an appropriate lexer/parser.
- Verify offsets from a UTF-8 file and a UTF-16 `String` are not mixed.
- Two algorithms sharing one iterator: test moving the position to observe mutable state.

**Q1.** Does `StringCharacterIterator` return a `char` or a code point?

**Answer:** It returns a UTF-16 `char`. A non-BMP code point uses two `char`s.

**Q2.** For `StringCharacterIterator("abXYZ",1,4,2)`, why is `getEndIndex() == 4`?

**Answer:** The readable region covers indexes 1, 2, 3; 4 is the index **immediately after** the last character. `end` is exclusive yet still a valid cursor position.

**Q3.** Can `StringCharacterIterator` be used alone to recognize `//` as a Java comment?

**Answer:** Not with the iterator alone; you need lexical state and literal/comment handling according to Java grammar.

**Q4.** Why can the loop `c != CharacterIterator.DONE` stop before the end?

**Answer:** `DONE` equals `char` U+FFFF, a code unit that a Java `String` can contain.

**Q5.** Is iterating code points enough to identify a grapheme?

**Answer:** No. One grapheme can consist of multiple code points (combining marks or emoji sequences).

**Hands-on exercise:** Traverse `A😀B` using `StringCharacterIterator` and `String.codePoints()`, comparing element counts. Restrict the iterator to `bXY`, test `setIndex(end)` and out-of-range indexes. Then create a source string containing `//` inside a literal and a real comment; build the expected token table and explain why the iterator cannot produce that table without a lexer.

## 13. Official References

- [StringCharacterIterator — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/StringCharacterIterator.html): three constructors, bounds, and cursor methods.
- [CharacterIterator — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/CharacterIterator.html): `DONE` and `first/next/previous/setIndex` contract.
- [String — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): UTF-16 indexing, `length`, `codePointAt`, and `codePoints`.
- [Character — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html): surrogate pairs, code points, and identifier characters.
- [BreakIterator — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/BreakIterator.html): boundary segmentation.
- [Java Language Specification 17, Chapter 3](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html): Unicode escapes, lexical structure, comments, and tokens.
- [Compiler Tree API — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/tree/package-summary.html): syntax trees for source analysis tools.

**Conclusion:** `StringCharacterIterator` is a **UTF-16** cursor over a bounded string region, not a Unicode code-point iterator, grapheme boundary finder, lexer, or parser. Use it when you need the `CharacterIterator` interface; use code-point/segmentation APIs for Unicode and a **JLS**-compliant lexer/parser when the real requirement is understanding program code.
