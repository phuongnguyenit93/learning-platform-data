# Incidental Indentation Whitespace and Closing Delimiter Position in Java Text Blocks

## 1. Why can the same text block produce different strings?

A **text block** is Java's multiline string syntax (standardized in Java 15). It starts with three double quotes `"""`, necessarily followed by a line terminator, and ends with three double quotes `"""`. The goal is to make embedding multiline text (SQL, JSON, HTML, messages, etc.) easy to read without concatenating multiple string literals.

However, there are two kinds of whitespace that are very easy to confuse:

- **Incidental indentation whitespace** (*incidental whitespace*): indentation meant only to make Java source code look neat, which is normally stripped automatically from the `String` value.
- **Content-meaningful whitespace** (*essential whitespace*): indentation that must be kept because it belongs to the text itself, such as two spaces before a YAML line or four spaces before a code block.

The position of the **closing delimiter `"""`** directly participates in how Java determines how much whitespace to strip from the beginning of each line. Changing the position of the closing delimiter, even without editing any text characters, can **change the runtime string value**. This is part of Java's semantics, not merely an editor formatting detail.

## 2. Syntax and the first-line rule

```java
String message = """
        Hello,
        This is a Java text block.
        """;
```

This is an illustrative snippet inside a method or initializer. After the opening `"""`, Java requires a line terminator: you cannot put content directly on the same line as the opening delimiter. The newline **immediately after the opening delimiter** is a syntactic element, not an automatic blank line at the start of the value.

With the layout above, the runtime content is equivalent to:

```text
Hello,\n
This is a Java text block.\n
```

In this `text` block, the `\n` notation represents a single LF character at the end of each line; it does not mean the two literal characters `\` and `n`. A typical text block **has a trailing newline** when the closing delimiter is on its own line after the final content line.

Writing the following is invalid because a line terminator is missing after the opening delimiter:

```java
// Invalid: content appears immediately after the opening delimiter.
// String bad = """hello""";
```

Even though triple quotes are used, the result is still a normal `String` object: you can call `length()`, `equals()`, `lines()`, `formatted()`, and so on. Text blocks do not automatically add indentation for display purposes; they produce the exact characters specified by Java's rules.

## 3. How does Java determine and remove incidental indentation?

Before processing escape sequences, Java normalizes the text block's line terminators to LF, and then removes incidental indentation. You can picture the core algorithm as follows:

1. Examine the leading whitespace of **every non-blank content line**.
2. If the closing `"""` sits on **its own line**, the whitespace before the closing delimiter is also a reference line for determining indentation.
3. Take the **minimum** indentation among the lines considered above; strip up to that common amount of whitespace from the start of each line.
4. Meaningless trailing whitespace on each line is removed during indentation processing; escape sequence processing happens afterward.

Blank lines should not be used as references for measuring leading indentation; the meaning of blank lines and trailing whitespace must be considered separately. When tabs are used, each whitespace character counts toward string content; do not rely on your IDE's visual tab width to predict the exact number of characters stripped.

**Important note:** Java does not "delete all leading spaces on every line." It removes **the smallest common indentation**, so relative indentation differences between lines are preserved.

Example:

```java
String block = """
        first
          second
        third
        """;
```

The `first` and `third` lines both have eight spaces in the source code, while `second` has two more. The closing delimiter is also indented by eight spaces. After stripping the common indentation, the equivalent value is:

```text
first\n
··second\n
third\n
```

In this output illustration, `·` is used to **make a single space visible**: `second` still keeps its two meaningful spaces relative to the remaining lines.

## 4. Closing delimiter position changes actual indentation

Compare three text blocks containing the exact same two content lines `red` and `blue`.

### Case A: Closing delimiter aligned with content

```java
String aligned = """
        red
        blue
        """;
```

Both the content lines and the closing delimiter line have eight leading spaces in the source code. The common indentation is eight; all eight are removed:

```text
red\n
blue\n
```

### Case B: Closing delimiter shifted to the left

```java
String closingLeft = """
        red
        blue
    """;
```

The closing delimiter has only four leading spaces. The minimum common indentation is now **four**. Consequently, each content line retains **four leading spaces**:

```text
····red\n
····blue\n
```

This is a common source of unintended indentation when someone moves the closing delimiter to the left to "make it look nicer." The text characters are identical, yet the resulting string gains extra spaces at the start of every line.

### Case C: Closing delimiter shifted to the right

```java
String closingRight = """
        red
        blue
            """;
```

The closing delimiter has twelve leading spaces, whereas the two content lines have only eight. The minimum remains **eight**, so the result matches Case A:

```text
red\n
blue\n
```

Shifting the closing delimiter to the right **cannot automatically strip more than the common indentation of the content lines**. The counts above are based on the exact number of spaces shown in the examples, not tab widths or IDE formatting settings.

## 5. Closing delimiter on the same line as the last content: trailing newline

These two ways of placing the closing delimiter differ:

```java
String withFinalLF = """
        red
        blue
        """;

String withoutFinalLF = """
        red
        blue""";
```

- `withFinalLF` has a value equivalent to `"red\nblue\n"`: there is an LF after `blue`.
- `withoutFinalLF` has a value equivalent to `"red\nblue"`: there is no trailing LF because the closing delimiter stands **immediately after the word `blue`** on the same line.

Placing the closing delimiter on the same line as the final content is a valid way to intentionally omit the trailing LF. Do not confuse this with omitting the line terminator after the **opening** delimiter: the opening delimiter must always be followed by a line terminator in text block syntax.

If you insert spaces before a same-line closing delimiter, those spaces can affect the content; to preserve or omit spaces intentionally, verify the actual value using comparison or a visible-character helper instead of relying on your eyes.

## 6. Java 17+ program to verify each case

Create `TextBlockIndentDemo.java` with the following content. This is a standalone program that can be compiled and run:

```java
public class TextBlockIndentDemo {
    static void show(String name, String value) {
        String visible = value.replace(" ", "·")
                .replace("\n", "\\n")
                .replace("\t", "\\t");
        System.out.println(name + ": [" + visible + "] len=" + value.length());
    }

    public static void main(String[] args) {
        String aligned = """
                red
                blue
                """;

        String closingLeft = """
                red
                blue
            """;

        String closingRight = """
                red
                blue
                    """;

        String noFinalNewline = """
                red
                blue""";

        String uneven = """
                red
                  blue
                """;

        String preservedSpace = """
                hi\s\s
                """;

        show("aligned", aligned);
        show("closingLeft", closingLeft);
        show("closingRight", closingRight);
        show("noFinalNewline", noFinalNewline);
        show("uneven", uneven);
        show("preservedSpace", preservedSpace);
    }
}
```

Commands to run:

```bash
javac --release 17 -encoding UTF-8 TextBlockIndentDemo.java
java TextBlockIndentDemo
```

Verified output using JDK in `--release 17` mode:

```text
aligned: [red\nblue\n] len=9
closingLeft: [····red\n····blue\n] len=17
closingRight: [red\nblue\n] len=9
noFinalNewline: [red\nblue] len=8
uneven: [red\n··blue\n] len=11
preservedSpace: [hi··\n] len=5
```

Convention for reading the output: each `·` character is **one space U+0020**; `\n` in the output is two visible characters representing **one actual LF** in the string. `len` is the `String` length measured in UTF-16 code units; in these examples using only ASCII letters, spaces, and LF, each character corresponds to one length unit.

Observations:

- `aligned` and `closingRight` both yield `red\nblue\n`, length 9.
- `closingLeft` keeps four spaces before **each** content line; length increases from 9 to 17.
- `noFinalNewline` is shorter than `aligned` by exactly one LF character.
- `uneven` preserves two spaces before `blue` because that is the relative indentation difference.
- `preservedSpace` keeps **two spaces at the end of `hi`** thanks to `\s\s`; this behavior is explained in the next section.

Use `String.equals` when you want to verify actual content. For example, `aligned.equals("red\nblue\n")` is `true`, whereas `aligned.equals("red\nblue")` is `false` because the trailing LF differs.

## 7. Trailing whitespace, blank lines, and the `\s` escape

Text blocks automatically strip extra whitespace **at the end of a line** during indentation processing. If you intentionally type a few spaces after the last word on a line in source code, those spaces can be stripped and are very hard to spot in a code review.

In a Java text block, write the `\s` escape to preserve **a single regular space** at a desired position, especially at the end of a line:

```java
String preserved = """
        hi\s\s
        """;
```

After processing, `preserved` is equivalent to `"hi  \n"`, containing two spaces after `hi` followed by LF. This works because Java processes escape sequences **after removing incidental indentation and trailing whitespace on lines**.

Actual blank lines are also part of the content:

```java
String paragraph = """
        Paragraph one.

        Paragraph two.
        """;
```

The result has **one blank line** between the two paragraphs: after `Paragraph one.` there are two consecutive LFs (one ending the line and one representing the blank line). Blank lines contain no text for predicting common indentation; when data requires keeping spaces on a blank line, use explicit escapes rather than invisible whitespace.

Another special escape in text blocks is the backslash `\` immediately before a line terminator: it can **join two lines without introducing an LF into the string**. Example:

```java
String joined = """
        micro\
        service
        """;
```

The content is equivalent to `"microservice\n"`. This is intentional behavior, **different** from placing the closing delimiter on the last line solely to omit the trailing LF of the entire string.

## 8. Relationship to `stripIndent()` and `indent()`

Java also provides indentation manipulation methods on `String`:

- `stripIndent()` strips common indentation and trailing line whitespace according to the API rules. Text blocks use this idea to normalize indentation; however, when writing a text block, **the position of the closing delimiter line** also helps determine the source content's indentation level. Therefore, do not assume calling `stripIndent()` on a `String` always matches what the compiler did on a text block.
- `indent(int n)` adjusts the indentation of lines in an existing string; when `n > 0`, it adds spaces to the start of each line, and when `n < 0`, it removes up to that amount of removable leading indentation. This method also normalizes line terminators and ensures the result follows the API's line-ending convention, so test carefully if preserving the exact trailing newline is required.

Never assume you can move the closing delimiter and "compensate" with a formatting call while keeping the string identical. If a string holds whitespace-sensitive content (YAML, Python, Markdown, signatures/hashes, templates, or snapshot output), every space and newline can affect the result.

## 9. Common mistakes when formatting text blocks

1. **Moving the closing delimiter too far left:** lowers the minimum indentation and accidentally keeps extra spaces on every content line.
2. **Thinking moving the closing delimiter further right strips more indentation:** in reality, common indentation is also bounded by the least-indented content lines.
3. **Forgetting the trailing LF:** a closing delimiter on its own line normally produces a trailing LF; place the closing delimiter right after the last content character to omit it intentionally.
4. **Assuming indentation on all lines is completely stripped:** Java only removes the common indentation. More deeply indented lines retain the difference.
5. **Trying to preserve trailing spaces by typing raw spaces:** trailing whitespace on lines is normally stripped; use `\s` when you genuinely need to keep it.
6. **Mixing tabs and spaces:** visual tab width in an editor is not a reliable measure of characters in a `String`. Choose a consistent indentation convention and verify the result if data is sensitive.
7. **Confusing display markers with runtime characters:** a displayed `\n` string in a debug tool may represent a single LF; distinguish printed escape text from an actual newline.
8. **Reading code without checking values:** write `equals` tests or print length alongside whitespace markers for templates where whitespace determines meaning.

### Checklist before editing or reviewing

- Identify whether the **closing `"""`** sits on its own line or on the last content line.
- Count the indentation of **non-blank** lines and of the closing delimiter line (if on its own line).
- Determine the common indentation that will be removed and the relative difference that will be kept.
- Check whether there is a trailing LF, blank lines, and trailing whitespace on lines.
- For whitespace-significant content, check `length()`, `equals()`, or a program printing spaces as markers instead of relying only on the IDE view.

**Remember:** text blocks make source code cleaner, yet they still must produce the exact `String`. When the closing delimiter is on its own line, **its indentation can determine how much whitespace is stripped**; when the closing delimiter sits flush against the final text, **the trailing LF can disappear**. Java strips only the common indentation, so relative indentation and intentional escapes still affect the content.
