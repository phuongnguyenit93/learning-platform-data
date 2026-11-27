# Removing Incidental Indentation and Closing Delimiter Placement in Java 17 Text Blocks

> **Topic:** Java 17  
> **Chapter:** Text block  
> **Focus:** How the compiler strips incidental indentation (*incidental indentation*), how the closing `"""` determines common indentation and the trailing newline, along with techniques for preserving intentional whitespace.

## 1. Why does Java need to strip text block indentation automatically?

Before **text blocks**, a multiline HTML string usually had to be concatenated from literals with `\n` and `+`:

```java
String html = "<main>\n" +
              "    <h1>Java 17</h1>\n" +
              "    <p>Hello!</p>\n" +
              "</main>\n";
```

With text blocks, available as a standard feature since Java 15, we can write text close to the content being represented:

```java
String html = """
        <main>
            <h1>Java 17</h1>
            <p>Hello!</p>
        </main>
        """;
```

In a Java file, content lines are pushed to the right to align with the source code's indentation level. Yet normally we **do not want** eight leading spaces on every line to appear in the actual string. Java automatically strips whitespace considered *incidental*: whitespace that only serves source code formatting.

In the example above, `html` is equivalent to:

```java
"<main>\n" +
"    <h1>Java 17</h1>\n" +
"    <p>Hello!</p>\n" +
"</main>\n"
```

The spaces before `<h1>` and `<p>` are preserved because they represent the **relative structure** of the HTML. The common source-code margin is removed.

**Key takeaway:** Do not guess a text block's value solely from the opening `"""` position. **The closing `"""`, the indentation of content lines, and whether the last line breaks** all affect the result.

## 2. Text block syntax and two places for the closing delimiter

A text block has type `String`, starts with three double quotes `"""`, followed by optional whitespace and then **a mandatory newline** before the content.

### 2.1. Closing delimiter on its own line

```java
String message = """
        Hello
        Java 17
        """;
```

This is the common layout. The value is equivalent to:

```java
String message = "Hello\nJava 17\n";
```

The newline **before the closing delimiter** is part of the content, so the string ends with `\n`.

### 2.2. Closing delimiter immediately after the last character

```java
String message = """
        Hello
        Java 17""";
```

The value is equivalent to:

```java
String message = "Hello\nJava 17";
```

Here there is **no trailing `\n`**, because the closing delimiter appears right after `17`. Placing the closing delimiter on the last content line also affects how the compiler determines what indentation to strip, explained in section 5.

### 2.3. Invalid forms

```java
// Invalid: missing newline after opening delimiter.
// String s = """One line""";

// Invalid: content appears directly on the opening delimiter line.
// String s = """first line
//             next line
//             """;
```

If you only need a short single-line string, use a regular string literal:

```java
String name = "Java 17";
```

A text block is not a different data type from `String`. It is simply a convenient syntax for multiline strings with dedicated whitespace-processing rules.

## 3. Distinguishing incidental indentation from essential indentation

**Incidental indentation** is the leading whitespace on lines that the compiler considers alignment caused by source code position, so it strips it automatically.

**Essential indentation** is the remaining indentation after subtracting the common margin; it represents data structure such as HTML, JSON, SQL, or indented paragraphs.

Example:

```java
String html = """
        <section>
            <h2>Title</h2>
            <p>Content</p>
        </section>
        """;
```

Suppose the leading spaces on the content lines are **8, 12, 12, 8** spaces respectively, and the line with the closing `"""` also has **8** spaces. Then the common indentation stripped is **8**:

| Line | Leading spaces in source | Stripped | Remaining in string |
|---|---:|---:|---:|
| `<section>` | 8 | 8 | 0 |
| `<h2>...` | 12 | 8 | 4 |
| `<p>...` | 12 | 8 | 4 |
| `</section>` | 8 | 8 | 0 |
| Closing `"""` line | 8 | Participates in determining margin | Does not become visible content |

The result looks like:

```html
<section>
    <h2>Title</h2>
    <p>Content</p>
</section>
```

This result still **ends with `\n`** because the closing delimiter sits on its own line.

### Observing indentation with visible markers

When visualizing otherwise invisible spaces, we use the symbol **`·` = one space** in the illustration below. This is an explanatory symbol, **not content to copy into Java**.

```text
In source code:
········<section>
············<h2>Title</h2>
········</section>
········"""              ← closing delimiter indent = 8

After removing 8 common whitespace characters:
<section>
····<h2>Title</h2>
</section>
```

The relative four-space indent of `<h2>` is intentional, so it is kept.

## 4. How does Java 17 compute incidental indentation?

The compiler processes text block content essentially in three phases, in order:

1. **Normalize line terminators:** CR (`\r`), LF (`\n`), and CRLF (`\r\n`) in the *source content* are normalized to LF (`\n`).
2. **Remove incidental whitespace:** Compute the common indentation from the determining lines, strip the common indentation, and strip trailing whitespace on each line.
3. **Interpret escape sequences:** For instance, `\s` becomes a space, and `\` immediately before a line terminator joins two lines.

This order is crucial: a `\s` escape used to preserve a trailing space only becomes a space **after** the incidental whitespace removal step.

### 4.1. Steps to determine common indentation

The *incidental indentation* rule can be understood as follows:

1. Split the content into lines by LF.
2. Take **non-blank lines** as the set of determining lines. Lines containing only ordinary whitespace do not determine indentation.
3. If the **last line** (the line before the closing delimiter, when the closing delimiter is on its own line) is blank, **still include this last line in the determining set**. This allows the closing delimiter's indentation to affect the common margin.
4. Count consecutive leading whitespace characters on each determining line and pick the **minimum**.
5. Strip that common count of whitespace characters from the start of non-blank lines; replace blank lines with empty lines, and strip trailing whitespace from every line.

**Note on the closing delimiter:** The closing `"""` does not itself become three characters in the `String`. When placed on its own line, **the spaces preceding it** form the content of that final line, and this line participates in determining the margin. When the closing delimiter sits immediately after content, there is no whitespace-only last line before the closing delimiter to constrain indentation that way.

### 4.2. Example: the least-indented line decides the result

```java
String value = """
        alpha
          beta
            gamma
        """;
```

Leading space counts of the three lines are `8, 10, 12`, and the closing delimiter indent is `8`. The strip amount is `min(8, 10, 12, 8) = 8`.

The exact value of `value` is:

```java
"alpha\n  beta\n    gamma\n"
```

Visible output:

```text
alpha
  beta
    gamma
```

### 4.3. Ordinary blank lines do not reset common indentation to 0

```java
String note = """
        First line

          Next line
        """;
```

An empty line between two text lines **does not** force the compiler to keep zero indentation. In this case, the result is equivalent to:

```java
"First line\n\n  Next line\n"
```

The special case is **the final line immediately before the closing delimiter**: even if it contains only whitespace, it is counted so the programmer can control how much indentation to preserve.

### 4.4. An unindented line makes the common strip amount 0

```java
String value = """
        indented
not indented
        """;
```

Because the second line starts at column 0, the minimum leading whitespace count is **0**. Java cannot strip eight spaces from the first line while preserving the described relative indentation. The result retains eight spaces before the "indented" line.

This situation often happens when a line inside a JSON or SQL block is accidentally pushed flush against the left margin.

## 5. Closing delimiter `"""` position determines preserved indentation

This is the most important aspect when aligning text blocks in Java 17. Compare **the same two content lines** with the closing delimiter placed at different positions.

### 5.1. Closing delimiter aligned with outermost content: strips all common margin

```java
String a = """
        first
          second
        """;
```

Indent levels: `first = 8`, `second = 10`, closing delimiter `= 8`. Java strips 8 leading whitespace characters.

Value:

```java
"first\n  second\n"
```

This is the recommended alignment for most text blocks because it is predictable and keeps content sitting naturally inside source code.

### 5.2. Closing delimiter shifted left: preserves partial indentation

```java
String b = """
        first
          second
    """;
```

Here the closing delimiter sits after **4** spaces, less than the **8**-space indent of `first`. The compiler chooses a strip amount of **4**.

Value:

```java
"    first\n      second\n"
```

Thus, merely moving the closing delimiter to the left keeps **4 extra spaces at the start of each content line**. This is useful if you genuinely want the resulting lines to have a fixed margin.

### 5.3. Closing delimiter at column 0: preserves all source indentation

```java
String c = """
        first
          second
""";
```

The closing delimiter at the start of the line has indentation **0**, making the common margin **0**.

Value:

```java
"        first\n          second\n"
```

This is a way to **strip no leading indentation** when the text block ends its last line with LF. Use it intentionally, because a closing delimiter misaligned from the Java code body can make source harder to read.

### 5.4. Closing delimiter indented deeper than content adds no spaces

```java
String d = """
        first
          second
            """;
```

Counts: `first = 8`, `second = 10`, closing delimiter `= 12`. The minimum **is still 8**, so the result matches `a`:

```java
"first\n  second\n"
```

Moving the closing delimiter **to the right** does not automatically add indentation to the content. The strip amount cannot exceed the indentation of the least-indented content line.

### 5.5. Summary table of the four closing delimiter positions

| Closing delimiter position on its own line | `first` line indent | Closing delimiter indent | Indentation stripped | Remaining indent before `first` |
|---|---:|---:|---:|---:|
| Aligned with `first` | 8 | 8 | 8 | 0 |
| Shifted left by four spaces | 8 | 4 | 4 | 4 |
| At start of line | 8 | 0 | 0 | 8 |
| Shifted right by four spaces | 8 | 12 | 8 | 0 |

**Mental formula:** When the closing delimiter sits on its own line, take the minimum leading whitespace count across all non-blank lines **and the closing delimiter line**, then strip that amount. Avoid looking only at the opening delimiter's column.

## 6. Closing delimiter right after the last line: changes both `\n` and stripping

Placing `"""` on the same line as content is a special case worth noting.

### 6.1. No trailing newline

```java
String text = """
        one
          two""";
```

Value:

```java
"one\n  two"
```

There is no `\n` after `two`. At the same time, the line ending with `two"""` **does not create a blank final line holding closing delimiter indentation**.

Therefore, the strip amount is determined solely by the content lines (8 whitespace characters in the example), not by the column of a standalone closing delimiter.

### 6.2. Cannot use a "left-shifted closing delimiter" to preserve indent if placed right after text

Compare:

```java
String a = """
        red
        blue""";

String b = """
        red
        blue
    """;
```

Values:

```java
// a: "red\nblue"
// b: "    red\n    blue\n"
```

`a` has no blank final line to define an indent of 4; `b` has a closing delimiter line indented by 4 spaces, so it preserves 4 spaces before the content.

**Common pitfall:** These two text blocks differ in **both leading indentation and trailing newline**. Do not move the closing delimiter solely to "tidy up" code if the string is used for exact comparisons, snapshot assertions, or byte-exact protocol messages.

### 6.3. How to both preserve desired indentation and omit the trailing newline

Java 17 supports the **backslash immediately before a line terminator** escape for line continuation:

```java
String text = """
            red
            blue\
        """;
```

Explanation:

- Both content lines have **12** leading spaces.
- The closing delimiter has **8** leading spaces.
- The compiler strips **8** common spaces, leaving **4** spaces on each content line.
- The `\` right before the newline after `blue` removes that newline from the result.

Value:

```java
"    red\n    blue"
```

This keeps the closing delimiter on its own line, expresses intentional indentation, and avoids a trailing `\n`. Use it when those exact details matter for your data.

**Do not confuse:** `\` before a newline is a **line continuation** escape. `\n` is two source characters interpreted as an LF character; they are different constructs.

### 6.4. Using `String.indent` to add indentation after creating the string

```java
String content = """
        red
        green
        """;

String indented = content.indent(4);
```

`String.indent(4)` adds four spaces to the **beginning of each line**. It fits when the desired indent level comes from program logic rather than Java source alignment.

**Note:** `String.indent(int)` normalizes newlines and ensures an LF at the end of the resulting string's lines, even if the input had no trailing LF; do not use it as a substitute for closing delimiter placement if you strictly need no trailing newline.

## 7. Complete Java 17 example: inspecting exact results of multiple closing delimiter positions

To see the actual whitespace, do not just call `System.out.println(text)` and eyeball it. The following example replaces spaces with `·`, tabs with `⇥`, and LF with `⏎` before displaying.

Create file `TextBlockIndentDemo.java`:

```java
public class TextBlockIndentDemo {

    private static String visible(String text) {
        return text.replace(" ", "·")
                   .replace("\t", "⇥")
                   .replace("\n", "⏎\n");
    }

    private static void show(String label, String text) {
        System.out.println(label + " = [" + visible(text) + "]");
        System.out.println("  length = " + text.length()
                + ", endsWithLF = " + text.endsWith("\n"));
    }

    public static void main(String[] args) {
        String aligned = """
                first
                  second
                """;

        String movedLeft = """
                first
                  second
            """;

        String inlineClosing = """
                first
                  second""";

        String preservedNoFinalLF = """
                    first
                      second\
                """;

        show("aligned", aligned);
        show("movedLeft", movedLeft);
        show("inlineClosing", inlineClosing);
        show("preservedNoFinalLF", preservedNoFinalLF);
    }
}
```

Compile and run with JDK 17:

```bash
javac --release 17 TextBlockIndentDemo.java
java TextBlockIndentDemo
```

For readability, expected results are shown as literal values:

| Variable | Exact string value | Ends with `\n`? |
|---|---|---|
| `aligned` | `"first\n  second\n"` | Yes |
| `movedLeft` | `"    first\n      second\n"` | Yes |
| `inlineClosing` | `"first\n  second"` | No |
| `preservedNoFinalLF` | `"    first\n      second"` | No |

Notice that `aligned` and `movedLeft` differ only in **closing delimiter position**; meanwhile `inlineClosing` and `preservedNoFinalLF` both lack a trailing LF yet have **different preserved indentation**.

The program intentionally uses larger indentation counts inside the `main` body, yet the results still follow the same relative margin calculation as the shorter examples above.

## 8. Trailing whitespace on lines is also stripped

In addition to leading indentation, Java 17 removes **trailing whitespace on every line** in text block content. This keeps Java files from depending on whether an editor automatically trims trailing spaces.

The following example is for illustration only; `·` represents spaces **after text**:

```text
In source code:
········alpha···
········beta·
········"""

Processed value:
alpha\nbeta\n
```

If an application needs to preserve trailing spaces (for example fixed-width data or protocol-specific messages), they must be expressed **intentionally**.

### 8.1. Using the `\s` escape to keep one space

```java
String padded = """
        red  \s
        blue\s
        """;
```

Because escapes are interpreted **after** trailing whitespace removal:

- The line `red  \s` keeps **three** spaces after `red` (two spaces in source, plus one from `\s`).
- The line `blue\s` keeps **one** space after `blue`.

Value:

```java
"red   \nblue \n"
```

This shows how `\s` acts as a **fence** protecting the spaces before it at the end of a line.

### 8.2. Using the octal escape `\040`

```java
String padded = """
        red\040\040
        blue\040
        """;
```

The `\040` escape corresponds to a space; the resulting content is:

```java
"red  \nblue \n"
```

In modern Java code, `\s` is usually easier to read when the intent is simply to preserve spaces. Both are supported in Java 17.

### 8.3. Do not replace `\s` with `\u0020`

`\u0020` is a **Unicode escape**; Java processes Unicode escapes very early when reading source code, before parsing text blocks and stripping whitespace. Therefore, it can become an actual space in source and get removed as trailing whitespace.

To keep whitespace across text block processing, use `\s` or `\040` instead of relying on `\u0020`.

### 8.4. A whitespace-only line becomes an empty line

```java
String text = """
        first

        second
        """;
```

Equivalent value:

```java
"first\n\nsecond\n"
```

If the middle line has several invisible spaces and no other characters, it is still treated as a blank line and that whitespace is stripped. Do not put spaces on a blank line expecting a "padded" line in the resulting string.

## 9. Tabs, spaces, and lint warnings for misindentation

For computing indentation, Java counts **whitespace characters**, without assuming one tab equals four or eight visual spaces.

For example, if one line has four leading tabs and another has eight leading spaces, Java does not treat those two margins as equal based on editor display width. One tab counts as **one character** when applying the indentation-stripping rule.

That is why you should **consistently use either spaces or tabs** for all indentation in a text block. Mixing the two can produce skewed output that is hard to spot visually.

Java 17 provides a warning flag for text blocks:

```bash
javac --release 17 -Xlint:text-blocks TextBlockIndentDemo.java
```

Depending on the source content, the checker can emit warnings such as:

- `inconsistent white space indentation` — mixed indentation makes the result hard to predict.
- `trailing white space will be removed` — trailing spaces at the end of a line are about to be stripped.

The command above is useful for **detecting whitespace issues during development**; it does not change the string value rules Java 17 uses. Warnings will not appear if the code is already consistently aligned.

## 10. Distinguishing three concerns: indentation, trailing newline, and internal newlines

When working with text blocks, three separate goals require individual decisions.

| Goal | How to control | Example |
|---|---|---|
| Strip source-formatting indentation | Align closing delimiter with outermost content | `<xml>` at same indent as `"""` |
| Keep extra leading indent per line | Shift closing delimiter left relative to content lines | Content 12 spaces, closing delimiter 8 spaces → keeps 4 |
| Omit trailing `\n` | Place closing delimiter right after last character, or use `\` before final newline | `text"""` or `text\` then closing delimiter on next line |
| Keep trailing spaces on a line | Use `\s`/`\040` inside text block | `value\s` |
| Omit newline between two source lines | Use `\` right before line terminator on line to join | `Hello \` then `world` |
| Add or remove indentation via runtime transform | Use `String.indent(int)` while mindful of trailing LF | `text.indent(4)` |

### 10.1. Using line continuation when source needs a line break but the string does not

```java
String longLine = """
        This is a long sentence that needs to be split\
         across two lines in source\
         but at runtime is only a single line.
        """;
```

The resulting value has no LF at the two positions using `\` line continuation. However, **actual spacing** also depends on what precedes and follows the join. If you want exactly one space between two words, place the space where it is preserved with `\s`, or write the content so the intent is clear.

A cleaner example:

```java
String sentence = """
        Hello\s\
        world\
        """;
```

Value:

```java
"Hello world"
```

`\s` inserts a space before `world`, while the line continuations remove the LFs immediately after them. Use this syntax only where a long string genuinely needs to span multiple source lines.

### 10.2. The opening delimiter does not create a leading blank line

```java
String value = """
        one
        two
        """;
```

Although in Java source the opening `"""` must be followed by a line break, **the mandatory newline after the opening delimiter does not become a leading `\n` in the string**. The value starts directly with the letter `o` of `one`.

To make the string start with a blank line, you must explicitly leave an extra blank line after the opening delimiter:

```java
String value = """

        one
        """;
```

Equivalent value:

```java
"\none\n"
```

## 11. Practical examples: HTML, SQL, and JSON

Text blocks are especially useful for structures that need to preserve **relative indentation**.

### 11.1. HTML — preserving tag structure

```java
String html = """
        <article>
            <h1>Notification</h1>
            <p>Sent successfully.</p>
        </article>
        """;
```

The output preserves four spaces before `<h1>` and `<p>`, without preserving the Java code's outer indentation. If the content is sent over a protocol or snapshot test that must match byte-for-byte, decide explicitly whether a trailing `\n` is needed.

### 11.2. SQL — avoiding incidental whitespace in queries

```java
String sql = """
        SELECT id, name
        FROM customers
        WHERE active = ?
        ORDER BY name
        """;
```

Here, common indentation is stripped and each line starts in the right place. Text blocks make queries readable, yet **do not replace parameterized queries**: user data must still be passed via `PreparedStatement` or library parameters, never concatenated directly into the SQL string.

### 11.3. JSON — preserving structure independent of source margin

```java
String json = """
        {
            "success": true,
            "data": {
                "id": 42
            }
        }
        """;
```

Single double quotes in JSON do not need escaping. The outer margin disappears while inner object indentation is kept. If storing snapshots or comparing exact strings, the closing delimiter position still matters due to trailing newlines or preserved indentation.

### 11.4. Data where indentation has semantic meaning

Not every format ignores whitespace. For example, fixed-width data, code samples, or Markdown content with indentation-sensitive code blocks:

```java
String markdown = """
            - Main item
                - Sub item
        """;
```

The closing delimiter sits after eight spaces while the first content line has twelve spaces, so the value preserves **four spaces** before `- Main item` and **eight spaces** before `- Sub item`. That is an intentional choice; aligning the closing delimiter with the content would change the preserved indentation.

## 12. How does `String.stripIndent()` relate?

Java 17 provides the method:

```java
String stripIndent()
```

on `String`. It removes incidental indentation in an **already existing string at runtime**, based on lines and leading/trailing whitespace. Its processing is very close to the compiler's logic when reading a text block.

Example independent of text blocks:

```java
String raw = "    alpha\n      beta";
String normalized = raw.stripIndent();

System.out.println(normalized.equals("alpha\n  beta")); // true
```

However, distinguish between:

- **Text blocks:** The compiler strips indentation **when constructing the literal**, while the closing delimiter line position still applies. The resulting `String` already holds the processed value.
- **`stripIndent()`:** Processes a runtime `String`; it cannot see where `"""` was in Java source once that information is gone.

**Do not automatically call `.stripIndent()` on every text block.** A text block has already had its indentation stripped at compile time; calling it again can strip intentional indentation.

For instance:

```java
String indented = """
            first
              second
        """;

// The value of indented has 4 spaces before "first".
// Calling stripIndent() again on a String ending with LF
// requires checking the method's last-line rule, rather than
// assuming it acts like shifting the closing delimiter in source.
```

When extra runtime formatting is needed, choose the right operation: `stripIndent()` to normalize indentation in a multiline string; `indent(n)` to change indentation intentionally; or line-by-line processing if exact line endings and whitespace must be preserved.

## 13. Common mistakes and fixes

| Symptom | Cause | Fix |
|---|---|---|
| String loses intended indentation | Closing delimiter is aligned with content lines, so common indent is stripped | Shift closing delimiter left or design explicit indent in content |
| String gets extra spaces before every line | Closing delimiter is shifted left relative to content, so Java strips fewer spaces | Move closing delimiter to the desired margin |
| String has an unexpected trailing `\n` | Closing delimiter sits on its own line after content | Place closing delimiter right after last character or use line continuation |
| String is missing a trailing `\n` | Closing delimiter is placed flush against the last content line | Move closing delimiter onto its own line if LF is needed |
| One line throws off indentation for all others | One line is less indented than the rest and dictates the strip amount | Check indentation of all content lines |
| Trailing spaces on a line disappear | Java strips trailing whitespace automatically | Use `\s` or `\040` escape intentionally |
| Tabs and spaces produce weird alignment | Java counts whitespace characters, not visual display width | Standardize indentation and enable `-Xlint:text-blocks` |
| A blank line with many spaces becomes empty | Blank lines do not retain standalone whitespace content | Do not use bare spaces for padding; express intent explicitly |
| Using `\u0020` still loses the space | Unicode escapes are processed early, becoming whitespace before stripping | Use `\s`/`\040` |
| String breaks when reformatting code in an IDE | Reindent changes only the closing delimiter or only some lines | Realign both content and closing delimiter; verify actual string value |
| SQL/JSON looks nice, but string comparison fails | Trailing newline or preserved indent differs | Compare normalized values or adjust closing delimiter as required |
| Calling `stripIndent()` to "fix" everything | Text block already stripped indentation; runtime stripping has its own semantics | Call only intentionally while knowing the input string's state |

## 14. Practice exercises

### Exercise 1 — Predict stripped indentation

Given code:

```java
String s = """
        A
            B
        C
    """;
```

How many spaces precede `A`, `B`, and `C` in `s`? Is there a trailing LF?

**Answer:** The closing delimiter is at 4 spaces, while the three lines have 8, 12, and 8 respectively; Java strips 4. Thus `A` keeps 4 spaces, `B` keeps 8, `C` keeps 4, and there is a trailing LF:

```java
"    A\n        B\n    C\n"
```

### Exercise 2 — Moving the closing delimiter without changing text characters

Predict the output:

```java
String a = """
        x
        y
        """;

String b = """
        x
        y
""";
```

**Answer:**

```java
// a = "x\ny\n"
// b = "        x\n        y\n"
```

Only the position of `"""` on its own line changed, yet the indentation in `String` changed.

### Exercise 3 — Omit trailing newline while keeping four-space indent

Write a text block with the exact value:

```java
"    first\n    second"
```

Do not use `+` literal concatenation, and do not call `trim()`/`strip()` afterwards.

**Suggested answer:**

```java
String s = """
            first
            second\
        """;
```

Content has 12 spaces and the closing delimiter has 8 spaces, keeping 4; the `\` before LF on the `second` line prevents a trailing newline.

### Exercise 4 — Preserving two trailing spaces

Given `"A  \nB\n"`, represent it with a text block without relying on invisible trailing spaces in your editor.

**Hint:**

```java
String s = """
        A \s
        B
        """;
```

Before `\s` there is one visible space in code, and the escape contributes one more space, so the result has exactly two spaces after `A`.

### Exercise 5 — Spotting mixed tab and space indentation errors

If one line is indented with four tabs and another with eight spaces, does Java automatically treat them as having the same indentation because the editor displays both margins aligned?

**Answer:** No. One tab is one whitespace character, not always equal to four or eight spaces. Standardize indentation across text block lines and use `javac -Xlint:text-blocks` when you need to catch inconsistent alignment.

### Exercise 6 — Leading LF or not?

Given:

```java
String first = """
        Hello
        """;

String second = """

        Hello
        """;
```

**Answer:** `first` equals `"Hello\n"`. `second` equals `"\nHello\n"`. The mandatory newline right after the opening delimiter does not create a leading LF; an **additional** blank line placed after the opening delimiter creates the leading LF.

## 15. Practical guidelines to apply in Java 17

1. **By default, place the closing `"""` on its own line at the same indentation as the outermost content lines** to remove incidental indentation while preserving relative structure.
2. If a string needs intentional left padding, **indent the content deeper than the closing delimiter** by the number of spaces you want to keep; avoid casually shifting margins once strings are used in snapshots or protocols.
3. Decide explicitly **whether a trailing `\n` character is needed**. When you want to keep the closing delimiter on its own line without a trailing LF, use the `\` escape at the end of the last content line.
4. Do not rely on invisible trailing spaces; use `\s` or another escape when that whitespace is an actual part of the data.
5. Avoid mixing tabs and spaces within the same text block. You can enable `-Xlint:text-blocks` to receive whitespace warnings.
6. When exact string values matter, specify and test against the **exact `String` value** including spaces and LFs, rather than merely inspecting terminal output.
7. Text blocks have been standard since **Java 15** and are stable in **Java 17**; these examples require no preview flags or newer Java syntax.

## 16. Official references

- [Oracle — Programmer's Guide to Text Blocks (Java 17)](https://docs.oracle.com/en/java/javase/17/text-blocks/index.html): syntax, incidental white space, closing delimiter placement, trailing newlines, `\s` escape, and `-Xlint:text-blocks`.
- [JEP 378 — Text Blocks](https://openjdk.org/jeps/378): design and processing algorithm finalized in Java 15 and applicable to Java 17.
- [Java Language Specification 17 — §3.10.6 Text Blocks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.10.6): syntax specification and text block content processing.
- [Java Language Specification 17 — §3.10.7 Escape Sequences](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.10.7): escape interpretation order and special sequences.
- [Java SE 17 API — String.stripIndent() and String.indent()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): runtime string indentation methods.

**Remember:** In Java 17, leading indentation is stripped according to the **minimum indent of the determining lines**, which includes the closing `"""` line if it stands on its own. Shifting the closing delimiter can alter how many leading spaces are preserved; placing the closing delimiter right after the last character omits the trailing LF. Understanding these three points makes text blocks both readable in Java source and exact in the strings they produce.
