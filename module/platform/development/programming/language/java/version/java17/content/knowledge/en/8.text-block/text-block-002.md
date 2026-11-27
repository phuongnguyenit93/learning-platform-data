# Opening Delimiter, Closing Delimiter, and First Newline of Text Blocks in Java 17

**Topic:** Java 17 → Text block  
**Goal:** Read `"""` syntax accurately; understand whether the mandatory newline after the opening delimiter is included in the string; recognize how closing delimiter placement alters the trailing newline of the string.

A text block is a **multiline string literal** form in Java. It uses three consecutive double quotes (`"""`) to open and close, allowing you to represent text such as HTML, JSON, SQL, or multiline messages without concatenating a long string from many literals. Text blocks became a **standard language feature in Java 15** (JEP 378), so Java 17 uses them normally, **without needing `--enable-preview`**.

A common point of confusion is that **the opening and closing delimiters are asymmetric in how they are placed on lines**:

- **The opening delimiter** must be followed by a **line terminator** (the text then begins on the next line).
- **The closing delimiter** can sit on its own line or on the same line as the last content character.
- **The mandatory newline immediately after the opening delimiter is not included in the string value**.
- **The newline immediately before the closing delimiter**, if it follows a content line, **is usually part of the string**. It determines whether the string ends with a `\n` character.

The examples in this document use standard syntax and APIs applicable in Java 17.

## 1. Minimal structure of a text block

Example:

~~~java
String greeting = """
    Hello,
    Java 17!
    """;
~~~

Reading each part:

| Part in source code | Role | Included in string value? |
| --- | --- | --- |
| First `"""` | **Opening delimiter**. | No. |
| Newline character after opening delimiter | Ends the opening delimiter declaration line; **required by syntax**. | **No**. |
| `Hello,` and `Java 17!` | Content lines. | Yes. |
| Newline after `Hello,` | Separates the two content lines. | Yes; represented as `\n` in the string. |
| Newline after `Java 17!` | Newline before the line containing the closing delimiter. | Yes; represented as `\n` in the string. |
| Final `"""` | **Closing delimiter**. | No. |
| `;` after closing delimiter | Ends the Java statement. | No. |

In the case above, after processing common indentation, the value is equivalent to a regular string literal:

~~~java
String greeting = "Hello,\nJava 17!\n";
~~~

This leads to two important rules:

1. A text block does not automatically add a `\n` character **at the beginning** just because the opening delimiter is on its own line.
2. A text block can have a `\n` **at the end** if the last content line ends with a line terminator before the closing delimiter.

> In the examples above, the leading spaces before the content and closing delimiter are **source code indentation**. Java 17 automatically handles incidental indentation in text blocks. Therefore, the described result does not contain four spaces at the beginning of each line.

## 2. Opening delimiter `"""`: a newline is mandatory

The valid form of the opening delimiter is **three consecutive double quotes**, optionally followed by whitespace and obligatorily followed by a **line terminator**. The text block content starts on the **next source line**.

**Correct:**

~~~java
String message = """
    Hello, Java 17!
    """;
~~~

**Incorrect:**

~~~java
// COMPILE ERROR: missing line terminator after opening delimiter.
// String message = """Hello, Java 17!""";
~~~

**Incorrect:**

~~~java
// COMPILE ERROR: text content appears immediately after opening delimiter.
// String message = """Hello,
//     Java 17!""";
~~~

In both incorrect examples, closing with three double quotes does not fix the error: **the opening delimiter was not completed with valid syntax**. A Java text block is not triple quotes used to wrap a single-line string.

### 2.1. Can there be whitespace after the opening delimiter?

Yes. According to Java syntax, after the opening `"""`, whitespace belonging to *text block white space* is allowed before the line terminator. Whitespace immediately following the opening delimiter **is not part of the text block content**.

The example below is valid; for readability, it is usually best to place the opening delimiter at the end of the line with no trailing whitespace:

~~~java
String text = """   
    Hello
    """;
~~~

On the `text` declaration line, there are three spaces after `"""` before the line break. The value is still `"Hello\n"`; those three spaces do not form a prefix of the string.

**Style recommendation:** Place the opening delimiter at the end of the line, break the line immediately, and then start the content. This helps readers clearly distinguish the **mandatory syntax line** from the **actual content lines**.

## 3. Does the first newline belong to the string?

**No.** The line terminator immediately after the opening delimiter is a mandatory part of the opening delimiter, so Java does not include it in the string value.

Consider:

~~~java
String first = """
    Alpha
    """;
~~~

After stripping common indentation, `first` has the value:

~~~text
Alpha\n
~~~

The first character is `A`, not `\n`. In other words:

~~~java
System.out.println(first.startsWith("A"));  // true
System.out.println(first.startsWith("\n")); // false
System.out.println(first.equals("Alpha\n")); // true
~~~

If represented as a source diagram:

~~~text
Source line 1: String first = """  +  [mandatory newline]
                                           |
                                           v
                                     NOT in string

Source line 2:     Alpha              +  [content newline]
                                           |
                                           v
                                       "Alpha\n"

Source line 3:     """                +  [closing delimiter]
~~~

**Note:** Ignoring the newline after the opening delimiter applies only to the **line terminator of the opening delimiter**. It does not mean Java removes all leading blank lines from the content.

## 4. How to make a string start with a newline character?

To have an actual `\n` at the beginning of the string, **leave a blank content line after the opening delimiter line**:

~~~java
String withLeadingNewline = """

    Alpha
    """;
~~~

Here:

1. The opening `"""` and its mandatory line terminator are on the first line.
2. The next line is **blank**, but has its own line terminator: this blank line contributes one `\n` to the string.
3. The `Alpha` line is the next content line.
4. The newline after `Alpha` also stays in the string because the closing delimiter is on the next line.

Thus:

~~~java
System.out.println(
    withLeadingNewline.equals("\nAlpha\n")
); // true
~~~

Direct comparison:

| Source code | String value |
| --- | --- |
| Opening delimiter, newline, `Alpha`, newline, closing delimiter | `"Alpha\n"` |
| Opening delimiter, newline, **one blank line**, `Alpha`, newline, closing delimiter | `"\nAlpha\n"` |

This rule is useful when writing content that needs an exact leading blank line, such as preformatted text. For ordinary application text, an accidental leading blank line easily causes comparison failures, so add it intentionally.

## 5. Closing delimiter `"""` determines the trailing newline

Unlike the opening delimiter, **the closing delimiter does not have to be on its own line**. In Java 17, the placement of the closing delimiter is a key factor in determining how the string ends.

### 5.1. Closing delimiter on its own line: usually ends with `\n`

~~~java
String withFinalNewline = """
    Hello
    """;
~~~

The value is:

~~~java
"Hello\n"
~~~

Here, the newline character **after `Hello`** belongs to the content. The closing delimiter is on the following line, so the content line ended with a line terminator.

### 5.2. Closing delimiter at the end of the content line: no `\n` added

~~~java
String withoutFinalNewline = """
    Hello""";
~~~

The value is:

~~~java
"Hello"
~~~

There is no line terminator between the final `o` and the closing delimiter. The closing delimiter itself does not add a newline character.

### 5.3. Side-by-side observation

~~~java
System.out.println(withFinalNewline.equals("Hello\n"));   // true
System.out.println(withoutFinalNewline.equals("Hello"));   // true
System.out.println(withFinalNewline.length());             // 6
System.out.println(withoutFinalNewline.length());          // 5
~~~

The difference is just **one trailing line feed `\n` character**, yet it can affect file output, exact string checks, digital signatures, and message formatting.

**Do not misunderstand:** Three double quotes do not "generate" `\n`. The newline is included in the value because **it appears between the content and the closing delimiter**. Moving the closing delimiter onto the same line as the content removes that newline.

## 6. Closing delimiter can end immediately in an empty text block

A text block does not have to contain any characters in its body:

~~~java
String empty = """
    """;
~~~

The value of `empty` is the **empty string `""`**:

~~~java
System.out.println(empty.isEmpty()); // true
System.out.println(empty.length());  // 0
~~~

The newline after the opening delimiter is discarded by syntax rules. The closing delimiter sits right on the first content line, so no content characters are collected.

If there is **one actual blank line between the opening and closing delimiters**:

~~~java
String oneNewline = """

    """;
~~~

then the value is **`"\n"`**:

~~~java
System.out.println(oneNewline.equals("\n")); // true
System.out.println(oneNewline.length());     // 1
~~~

This is the clearest example distinguishing the **mandatory newline of the opening delimiter** from a **blank line belonging to content**.

## 7. Closing delimiter on its own line and indentation handling

Besides determining the trailing newline, the indentation position of the **line containing the closing delimiter** also participates in Java 17's *incidental whitespace* processing rules.

Common example:

~~~java
String text = """
        A
        B
        """;
~~~

Value after Java strips common indentation:

~~~java
"A\nB\n"
~~~

If the closing delimiter is placed **with less indentation**, the remaining indentation on the content may be preserved:

~~~java
String indented = """
        A
        B
    """;
~~~

Equivalent value:

~~~java
"    A\n    B\n"
~~~

Here, the `A` and `B` lines are indented by eight spaces in source, while the closing delimiter is indented by four spaces. Java strips four spaces of common indentation; the remaining four spaces before `A` and `B` are **significant content**.

Therefore, when saying "closing delimiter on its own line means the string ends with `\n`", we must still distinguish **the trailing newline** from **indentation whitespace**:

- The newline between `B` and the closing delimiter is kept as `\n`.
- The number of leading spaces on each content line depends on the common indentation level and the closing delimiter's position.
- The closing delimiter is not included in the string, but its position can affect how indentation is stripped.

This detail is especially useful when you need to preserve leading spaces in sample source code or formats like YAML and ASCII art.

## 8. How to clearly observe newline characters at runtime

`System.out.println(text)` does not always make it obvious to learners what is a **trailing newline in the string** versus the **newline added by `println` itself**.

To observe this, we can replace each `\n` line feed character with two visible characters—a backslash and the letter `n`:

~~~java
static String visible(String text) {
    return text.replace("\n", "\\n");
}
~~~

For example, `visible("A\nB\n")` returns the visible string `A\nB\n` (containing literal `\` and `n` characters instead of line feeds). This does not modify the original text block; it only makes test output easier to read.

### Complete program for Java 17

Create file **`TextBlockDelimitersDemo.java`**:

~~~java
public class TextBlockDelimitersDemo {
    private static void show(String label, String value) {
        String visible = value.replace("\n", "\\n");
        System.out.println(
            label + " = [" + visible + "], length=" + value.length()
        );
    }

    public static void main(String[] args) {
        String withFinalNewline = """
            Hello
            """;

        String withoutFinalNewline = """
            Hello""";

        String withLeadingNewline = """

            Hello
            """;

        String empty = """
            """;

        String oneNewline = """

            """;

        show("withFinalNewline", withFinalNewline);
        show("withoutFinalNewline", withoutFinalNewline);
        show("withLeadingNewline", withLeadingNewline);
        show("empty", empty);
        show("oneNewline", oneNewline);
    }
}
~~~

Compile and run with JDK 17:

~~~shell
javac --release 17 TextBlockDelimitersDemo.java
java TextBlockDelimitersDemo
~~~

Displayed output:

~~~text
withFinalNewline = [Hello\n], length=6
withoutFinalNewline = [Hello], length=5
withLeadingNewline = [\nHello\n], length=7
empty = [], length=0
oneNewline = [\n], length=1
~~~

Explanation:

1. `withFinalNewline`: newline after opening delimiter is discarded; newline after `Hello` is kept.
2. `withoutFinalNewline`: closing delimiter sits directly after `Hello`, so there is no trailing `\n`.
3. `withLeadingNewline`: blank line **after the opening line** creates an actual leading `\n`.
4. `empty`: only the mandatory newline after the opening delimiter exists, so there are no content characters.
5. `oneNewline`: there is one real blank line before the closing delimiter, producing a single-character `\n` value.

The program uses only `String.replace`, `String.length`, and standard text block syntax. No preview APIs or third-party libraries are needed.

## 9. Text blocks in JSON, SQL, and HTML: mind the newline

Text blocks are helpful for multiline content, and closing delimiter placement directly affects the string value.

### 9.1. JSON with a trailing newline

~~~java
String json = """
    {
      "name": "Java 17",
      "active": true
    }
    """;
~~~

The value `json` ends with `}\n`. A trailing newline usually does not affect how a compliant JSON parser reads the data, but **exact byte/string comparison** distinguishes `"}"` from `"}\n"`.

### 9.2. JSON without a trailing newline

~~~java
String json = """
    {
      "name": "Java 17",
      "active": true
    }""";
~~~

The value ends with the `}` character because the closing delimiter is placed immediately after the curly brace. This is the clear choice if an interface or output format requires no trailing newline.

### 9.3. Multiline SQL

~~~java
String query = """
    SELECT id, title
    FROM lessons
    WHERE published = true
    """;
~~~

In this example, the SQL statement has a newline character after `true`. If you want to send the SQL statement without a trailing newline, you can place the closing delimiter immediately after `true`:

~~~java
String query = """
    SELECT id, title
    FROM lessons
    WHERE published = true""";
~~~

Many systems ignore a trailing newline in SQL statements, yet knowing how the literal is constructed remains important when testing or comparing output values.

### 9.4. HTML and text written to files

~~~java
String html = """
    <p>Hello</p>
    """;
~~~

The string `html` has value `"<p>Hello</p>\n"`. If written directly to a file with `Files.writeString(path, html)`, the trailing newline character **is also written**. A text block is not a tool that automatically strips all line terminators before saving.

## 10. Source line breaks: `LF`, `CRLF`, and the value Java receives

Java source files may use different line-ending characters depending on the operating system or editor configuration, commonly:

- `LF` (line feed, `\n`).
- `CRLF` (carriage return + line feed, `\r\n`).

**Java 17 normalizes line terminators in text block content to `LF`**, according to text block processing rules. Therefore:

~~~java
String lines = """
    One
    Two
    """;
~~~

has a value equivalent to:

~~~java
"One\nTwo\n"
~~~

even when the source file is saved with CRLF line endings. The mandatory newline immediately after the opening delimiter is still not included in the string.

**Do not equate the operating system line separator with text blocks.** `System.lineSeparator()` may return `"\r\n"` on Windows, but text blocks in Java 17 still use `\n` for normalized line terminators in the content. When you need to convert to a specific line-ending format, handle it intentionally where data is output.

Java 17's text block processing order includes normalizing line terminators, stripping incidental indentation, and then processing escape sequences. Therefore, escapes such as `\n`, `\s`, and `\` line continuation are a separate matter from **newlines appearing naturally in source code**.

## 11. What other way is there to avoid a trailing newline?

Besides placing the closing delimiter immediately after the last content line, Java 17 supports the **line continuation escape**: a backslash `\` at the end of a content line suppresses the line terminator that follows it.

Example:

~~~java
String joined = """
    Hello \
    Java 17
    """;
~~~

After indentation and escape processing, the value is equivalent to:

~~~java
"Hello Java 17\n"
~~~

The `\` after the space in the content tells Java not to keep the line terminator at that position; `Java 17` is joined directly. If you only want to remove the trailing newline, you can write:

~~~java
String withoutFinalNewline = """
    Hello\
    """;
~~~

The value is `"Hello"`. However, for a lesson focused on **closing delimiters**, the more readable form is usually:

~~~java
String withoutFinalNewline = """
    Hello""";
~~~

**Do not confuse line continuation with Java automatically dropping a newline**: a `\` at the end of a line is an intentional escape syntax; whereas the mandatory newline after the opening delimiter is discarded because it belongs to the opening delimiter.

## 12. Common mistakes when using opening and closing delimiters

| Mistake or assumption | What actually happens? | Proper way to write |
| --- | --- | --- |
| Writing `"""Hello"""` on one line. | Missing mandatory line terminator after opening delimiter; syntax error. | Start content on the line after `"""`. |
| Thinking a text block always starts with `\n`. | The newline right after the opening delimiter is discarded. | Add **a blank content line** if you truly want a leading newline. |
| Thinking the closing delimiter itself adds `\n`. | The closing delimiter creates no newline; `\n` comes from the preceding line terminator. | Place closing delimiter on the same line as the final content if no final newline is wanted. |
| Moving the closing delimiter to a new line just for neat code without checking the value. | May cause the string to end with `\n`. | Verify whether the output contract allows a trailing newline. |
| Comparing two text blocks with the same visible text and assuming they are equal. | They may differ in leading/trailing `\n` or indentation. | Compare with `equals`, inspect escape characters and `length`. |
| Looking at `println` output and thinking the text block has an extra blank line. | `println` adds its own line terminator after printing the value. | Use a `visible` helper or `System.out.print`. |
| Assuming all whitespace before the closing delimiter becomes content. | Incidental indentation rules may strip leading whitespace. | Fix indentation levels and inspect the actual string. |
| Assuming text blocks are raw strings that skip escape processing. | Java 17 still processes escape sequences after normalizing content. | Distinguish `\n` from source line terminators vs. explicit `\n` escapes in content. |

## 13. Practical scenario: exact value comparison

Suppose a method returns text used in automated testing:

~~~java
static String welcomeMessage() {
    return """
        Welcome
        """;
}
~~~

If the test writes:

~~~java
String expected = "Welcome";
String actual = welcomeMessage();

System.out.println(expected.equals(actual)); // false
~~~

the cause is not the word `Welcome`, but the trailing newline. The value of `actual` is `"Welcome\n"`.

There are at least two solutions depending on the contract:

**Option A — the value should keep the trailing newline:**

~~~java
String expected = "Welcome\n";
~~~

**Option B — the value should have no trailing newline:**

~~~java
static String welcomeMessage() {
    return """
        Welcome""";
}
~~~

Choose based on the required data format. Avoid unconditionally calling `strip()` or `trim()` just to make a comparison pass, as those operations can delete meaningful whitespace or newlines in other content.

## 14. Practice exercises

**Exercise 1.** Predict `length()`:

~~~java
String a = """
    A
    """;

String b = """
    A""";

String c = """

    A""";
~~~

**Answer:** `a.length() == 2` (`"A\n"`), `b.length() == 1` (`"A"`), `c.length() == 2` (`"\nA"`).

**Exercise 2.** Convert the regular string `"red\nblue"` to a text block **without** a trailing newline.

~~~java
String colors = """
    red
    blue""";
~~~

**Exercise 3.** Convert the regular string `"\nred\nblue\n"` to a text block.

~~~java
String colors = """

    red
    blue
    """;
~~~

**Exercise 4.** Identify the syntax error:

~~~java
// Incorrect:
// String invalid = """first line
//     second line""";
~~~

**Answer:** The opening delimiter line contains `first line` right after the three double quotes; Java requires a line terminator immediately after the opening delimiter (whitespace before the terminator is allowed). Fix by moving `first line` to the next line.

**Exercise 5.** If the source file uses CRLF, does the value Java gets from the following text block preserve CRLF?

~~~java
String sample = """
    A
    B
    """;
~~~

**Answer:** No. Line terminators in text block content are normalized by Java to `\n`; the string is equivalent to `"A\nB\n"`.

## 15. Rules to remember

1. **The opening delimiter of a text block must be followed immediately by a line terminator** (whitespace before the terminator is permitted). Do not write content on the same line as the opening `"""`.
2. **This first line terminator is not included in the string.** The first content line begins on the next source line.
3. To get a **leading newline**, add a blank content line after the opening line.
4. **The closing delimiter can be on its own line or on the last content line.** If the last content line has a line terminator before the closing delimiter, that `\n` is retained.
5. When the closing delimiter is on **its own line**, its indentation can also affect the leading whitespace preserved on content lines.
6. Java 17 text blocks use **`\n` for normalized line terminators**, even if the source file uses CRLF.
7. For strings requiring character-for-character matching, consider both **leading/trailing newlines** and **indentation**, not just the visible text.

### Official references

- [JEP 378 — Text Blocks](https://openjdk.org/jeps/378): text blocks standardized since JDK 15, including syntax and newline rules.
- [Java Language Specification, Java SE 17 — §3.10.6 Text Blocks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.10.6): opening/closing delimiters and content processing order.
- [Java Language Specification, Java SE 17 — §3.4 Line Terminators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.4): definition of line terminators in Java source code.
- [Java SE 17 Programmer’s Guide — Text Blocks](https://docs.oracle.com/en/java/javase/17/text-blocks/index.html): guide to using text blocks in Java 17.

**Conclusion:** The opening delimiter specifies **that a newline is required to start the content** without putting that newline into the string; the closing delimiter specifies **where the content ends** and thus directly affects the trailing newline. Understanding both positions helps you write readable Java 17 text blocks while controlling the exact `String` value.
