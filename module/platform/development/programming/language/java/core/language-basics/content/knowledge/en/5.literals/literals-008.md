# Text Blocks: Opening, Closing Syntax, and Indentation Handling in Java

> **Java core — language-basics / Literal**  
> **Requirements:** JDK 17+; text blocks are a standard feature since Java 15, requiring no preview flags.  
> **Objective:** Write the opening/closing `"""` delimiters correctly; determine when a string contains a trailing newline; explain *incidental indentation* handling; know how to use the `\s` escape and line continuation; compile and inspect string values yourself.

## 1. A text block is still a `String`

A **text block** is a multi-line literal syntax, well suited for JSON, HTML, or long queries. It produces an ordinary `String`, not a separate data type.

~~~java
String ordinary = "Hello\nJava\n";
String block = """
        Hello
        Java
        """;
System.out.println(ordinary.equals(block)); // true
~~~

Text blocks usually make code easier to read than concatenating multiple strings with `+ "\n"`, yet **they do not guarantee preserving every space verbatim from source code**. Java applies rules to normalize line terminators and strip incidental indentation.

## 2. Syntax of the opening and closing delimiters

Typical structure:

~~~java
String message = """
        Dong thu nhat
        Dong thu hai
        """;
~~~

- **The opening delimiter** consists of three double quotes `"""`, optionally followed by whitespace, and **must be followed by a line terminator**. Content starts on the **next** line; the mandatory line break right after the opening delimiter does not become the first character of the value.
- **The closing delimiter** also consists of `"""`, and can sit on its **own line** or on the **same line as the final content**.
- The `;` terminates the variable declaration statement; it is not part of the String value.
- You do not need to escape isolated double quotes `"` inside a text block as in ordinary strings, as long as they do not accidentally form a closing delimiter.

**Intentionally invalid syntax** (kept in a comment, not runnable):

~~~java
// String bad = """Hello""";  // Missing line terminator after opening delimiter.
~~~

A text block is not a string template: variable names placed inside the content are not automatically replaced with variable values. If you want to insert dynamic data, use concatenation, `String.format`, or another appropriate API.

## 3. The closing delimiter decides whether there is a trailing newline

Compare:

~~~java
String withNewline = """
        A
        B
        """;

String noNewline = """
        A
        B""";
~~~

| Closing delimiter placement | Equivalent Java value | Key point to remember |
| --- | --- | --- |
| Own line after B | `"A\nB\n"` | The newline after B **belongs to the string** |
| Right against B on the same line | `"A\nB"` | No trailing newline |

This is a **real data** difference, not merely a source formatting difference. If software outputs JSON or generates test text that must not have a trailing newline, deliberately choose the closing delimiter position or reformat the string to match the exact requirement.

**Do not use `strip()` indiscriminately** to "fix" an unwanted newline because that method also removes leading/trailing whitespace that may be meaningful.

## 4. Incidental indentation handling rules

When code is placed inside a method or class, text block lines usually must be indented to match Java formatting. Java **removes common indentation used purely for code layout**, while deeper indentation is preserved.

~~~java
String list = """
        root
          child
        """;
~~~

The string `list` has the equivalent value:

~~~text
root
  child
~~~

In addition, it has a **trailing newline** because the closing delimiter sits on its own line.

Practical rules:

1. Align the closing delimiter with the content line that has the base indentation level if you want to strip code-layout indentation.
2. Any line indented deeper than the common level keeps **the extra difference**. In the example, `child` keeps two spaces.
3. **Shifting the closing delimiter to the left** can cause Java to strip less indentation and keep extra leading spaces on all lines.
4. Use spaces consistently rather than mixing tabs and spaces, because looking identical in an editor does not mean the actual indentation characters are equal.
5. Blank lines and trailing spaces on lines are also governed by specific rules; do not assume every whitespace character typed in source code is preserved.

More precisely, Java uses non-blank lines and the position of the closing delimiter to determine the level of *incidental indentation*. This is not an arbitrary "strip all leading whitespace" operation.

## 5. Order of newline and escape processing

Java normalizes line terminators inside text block content to **LF** (`\n`), even if the source file is saved with CRLF. Next, it strips incidental indentation and trailing whitespace on lines as specified; **lastly**, it interprets escapes.

| Content syntax | Meaning |
| --- | --- |
| `\n` | Escaped newline character |
| `\t` | Escaped tab character |
| `\s` | A single space; especially useful for **preserving trailing spaces on a line** |
| `\` right before a line terminator | **Line continuation**: drops that line terminator, joining two parts of content |

Example:

~~~java
String spaces = """
        end\s\s
        """;

String joined = """
        pre\
        fix
        """;
~~~

The value of `spaces` is `"end  \n"` (two spaces before the newline). The value of `joined` is `"prefix\n"`: the `\` joins `pre` and `fix`, while the newline after `fix` remains.

**Difference:** `\n` in source code produces one LF character in the value; whereas to print the two characters backslash and letter `n` themselves, you must escape accordingly, such as the ordinary string `"\\n"`.

## 6. A Java 17+ program for exact verification

Create the file **TextBlockDemo.java**:

~~~java
public class TextBlockDemo {
    private static String visible(String value) {
        return value.replace(" ", "_").replace("\n", "|");
    }

    public static void main(String[] args) {
        String indented = """
                first
                  second
                """;

        String noFinalNewline = """
                one
                two""";

        String keptSpaces = """
                end\s\s
                """;

        String joined = """
                pre\
                fix
                """;

        System.out.println("indented=" + visible(indented));
        System.out.println("noFinalNewline=" + visible(noFinalNewline));
        System.out.println("keptSpaces=" + visible(keptSpaces));
        System.out.println("joined=" + visible(joined));
        System.out.println("sameType=" + indented.getClass().getSimpleName());
    }
}
~~~

Run from the directory containing the file in Bash, PowerShell, or Command Prompt:

~~~bash
javac -encoding UTF-8 TextBlockDemo.java
java TextBlockDemo
~~~

**Expected output:**

~~~text
indented=first|__second|
noFinalNewline=one|two
keptSpaces=end__|
joined=prefix|
sameType=String
~~~

The `visible` method simply turns spaces into `_` and newlines into `|` so they can be seen clearly on the console; it **does not modify the original string**.

Line-by-line explanation:

- `indented` keeps the two spaces before `second` and a trailing newline.
- `noFinalNewline` has no newline after `two` because the closing delimiter sits right against the final content.
- `keptSpaces` has two real spaces thanks to the two `\s` escapes, right before the trailing newline.
- `joined` joins `pre` with `fix`, with no newline in between; the trailing newline remains.
- `sameType` confirms that the created object is a `String`.

## 7. Common mistakes

| Symptom | Cause | How to handle |
| --- | --- | --- |
| Compiler reports invalid opening delimiter | Writing content immediately after opening `"""` | Put a line terminator after the opening delimiter |
| Data has an unintended trailing `\n` | Closing delimiter is on its own line | Place the closing delimiter right after the final content if you want to omit that newline |
| Trailing spaces on a line disappear | Trailing whitespace is stripped during text block normalization | Use `\s` to preserve intentional spaces |
| Data keeps excessive leading whitespace | Shifting the closing delimiter left reduces the incidental indentation stripped | Realign lines and the closing delimiter |
| String on Windows differs from source file's newlines | Java normalizes CRLF to LF inside text blocks | Inspect the output data rather than relying on source file line endings |
| Text block does not interpolate variables automatically | A text block is a String literal, not a template | Use intentional formatting/string concatenation |
| Three consecutive double quotes appear inside content | May prematurely terminate the text block | Escape or restructure the quoted section |

If **byte-for-byte** preservation of an external document is required, a text block is not the default choice: consider reading a resource/file and controlling encoding and line endings explicitly.

## 8. Short exercises

**Exercise 1 — Trailing newline:** Write two text blocks containing `Hello`: one closed on its own line, one closed right against `Hello`. Compare `length()` and output via `visible`.

**Exercise 2 — Indentation:** Write two lines `root` and `  child`, shift the closing delimiter position to the left, and observe how many spaces remain using `visible`.

**Exercise 3 — Trailing spaces:** Compare two literal spaces at the end of a source line with two `\s\s` escapes. Are they preserved the same way?

**Exercise 4 — Line continuation:** Change `pre` and `fix` to `foo` and `bar`, and test with/without `\` before the line terminator. Predict which newlines the value contains.

**Exercise 5 — JSON:** Write multi-line JSON in a text block and print it out. Check content indentation, double quotes, and the trailing newline before using it as real data.

### Key takeaway

**A text block is a `String`**, using triple double quotes; the opening delimiter must be followed by a newline. **The position of the closing delimiter determines the trailing newline.** Java normalizes newlines, strips incidental indentation, and only then interprets escapes such as `\s` and `\` line continuation. When exact spaces or newlines matter, visualize them with a helper like `visible`.
