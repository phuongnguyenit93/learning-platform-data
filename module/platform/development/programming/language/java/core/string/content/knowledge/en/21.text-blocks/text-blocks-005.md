# Escaping Spaces with `\s` and Line Continuation with Backslash in Java Text Blocks

## 1. The problem

A `Text block` is Java's multiline string syntax, delimited by `"""`. It has been an official feature since **Java 15**, so Java 17 and later can use it directly without enabling preview features. The resulting value is still a `String` object. Example:

~~~java
String s = """
    red
    blue
    """;
System.out.println(s.equals("red\nblue\n")); // true
~~~

Here, physical newlines inside the text block become LF (`\n`) in the string value. Because the closing `"""` sits on its own line, the LF after `blue` remains part of the result.

Two requirements come up frequently when authoring multiline text:

1. **Preserving trailing spaces on a line**: one or more spaces after the last character on a line can be significant data (for instance, Markdown formatting).
2. **Wrapping source code across multiple lines while producing a single-line result**: a long sentence or part of an SQL statement should not contain an LF where the source code wraps.

Java solves these with two escapes: **`\s` produces a space (`U+0020`)** and **`\` right at the end of a physical line removes that newline** (line continuation).

## 2. Why do these escapes work?

Java processes text block content in this order:

1. End the opening `"""` with a mandatory line terminator; content begins on the following line. Normalize source line terminators to LF.
2. Strip incidental indentation (`incidental indentation`) to allow clean alignment in the Java file. Unprotected spaces at the end of source lines are also removed (`trailing incidental whitespace`).
3. **Only at the end** interpret escape sequences such as `\s`, `\n`, `\t`, and the line-continuation `\`.

Step 2 occurring before step 3 is the key: in source code, `\s` is a notation consisting of a backslash and the letter `s`, not an actual space for the trailing-whitespace removal step to strip. Afterward, it becomes a space.

### Closing delimiter position determines the trailing LF

~~~java
String withFinalLf = """
    done
    """;
// Equals "done\n"

String withoutFinalLf = """
    done""";
// Equals "done"
~~~

Closing on the same line as the last content does not automatically produce an LF. This decision is independent of using `\s` or the line-continuation `\`.

## 3. `\s`: preserving trailing spaces on a line

### A single space, not all whitespace

In a Java string literal, `\s` produces **exactly one ASCII space U+0020**, not a tab, LF, or the entire Unicode whitespace class:

~~~java
String a = "Hello\sWorld";
String b = "Hello World";
System.out.println(a.equals(b)); // true
~~~

This escape works in both single-line string literals and text blocks. With text blocks, it is especially useful for specifying trailing spaces explicitly:

~~~java
String text = """
    A\s
    B\s\s
    """;
~~~

The exact value of `text` is `"A \nB  \n"`: after `A` there is one space before LF; after `B` there are two spaces before LF. The total length is **7** UTF-16 units: A + space + LF + B + space + space + LF.

~~~java
System.out.println(text.equals("A \nB  \n")); // true
System.out.println(text.length());             // 7
System.out.println(text.replace(" ", "<SP>").replace("\n", "\\n"));
// A<SP>\nB<SP><SP>\n
~~~

In the final illustrative line, `<SP>` is a marker to make actual spaces **visible**; `\n` is printed as the two observable characters `\` and `n`. This approach is much more reliable than glancing at `println` output, which does not clearly display trailing spaces.

### Why not type literal spaces at the end of the line?

~~~java
String invisibleSpaces = """
    A   
    """;

String explicitSpaces = """
    A\s\s\s
    """;
~~~

The three literal spaces after `A` in `invisibleSpaces` are stripped by the trailing incidental whitespace step. In `explicitSpaces`, the three `\s` escapes produce three spaces after that step has already run. Furthermore, editors configured to trim trailing whitespace on save will not break the intent of `explicitSpaces`.

Do not use `\s` for every ordinary space between words. Use it where you want to emphasize that **a space is an intentional part of the data**, especially at the end of a line or right before a line continuation.

### Do not confuse with `\s` in regex

Two notations share the same spelling but are handled by **two different parsers**:

| Written in Java code | Actual string passed to the regex engine | Meaning |
| --- | --- | --- |
| `Pattern.compile("\s+")` | ` +` | One or more **ASCII spaces**; Java already converted `\s` into a space. |
| `Pattern.compile("\\s+")` | `\s+` | One or more characters in the **regex whitespace class**. |

In the second example, `\\` in Java source produces an actual `\` so that `Pattern` can then interpret `\s`. When building a regex inside a text block, you must distinguish those two escape layers in the same way.

## 4. `\` at the end of a line: joining two lines without an LF between them

### Omitting the line terminator

A `\` placed **immediately before a source line's terminator** instructs the compiler to omit that line terminator from the `String` value:

~~~java
String normal = """
    red
    blue
    """;
// Equals "red\nblue\n"

String joined = """
    red\
    blue
    """;
// Equals "redblue\n"
~~~

In `joined`, the backslash at the end of the `red` line does not appear in the result either. The second line `blue` is joined directly onto `red`. The LF after `blue` remains because the second line has no continuation backslash.

A string split across three lines can be continued multiple times:

~~~java
String word = """
    con\
    tin\
    ued""";
// Equals "continued"
~~~

Use this technique when you want line breaks in **source code** for readability without introducing corresponding LFs into **the data**.

### Line continuation does not automatically insert a space

~~~java
String sentence = """
    Hello\
    World
    """;
// Equals "HelloWorld\n"
~~~

Many people assume Java automatically inserts a space between `Hello` and `World`, yet the result is a single joined word. If you need exactly one space, combine `\s` and `\`:

~~~java
String sentence = """
    Hello\s\
    World
    """;
// Equals "Hello World\n"
~~~

The `\s\` sequence at the end of the line performs two distinct actions: `\s` produces a space; `\` removes the LF. Place the closing `"""` on the same line as `World` if you do not want a trailing LF:

~~~java
String sentence = """
    Hello\s\
    World""";
// Equals "Hello World"
~~~

### `\` must stand immediately before the line terminator

Do not leave spaces or tabs **after** a backslash used for line continuation. If characters appear between `\` and the line terminator, it is no longer a valid line-continuation escape and can cause a compile error. This is also why you should avoid editors automatically appending trailing whitespace to lines ending with `\`.

`\\` has a **different** meaning: it produces a literal backslash **in the result**.

~~~java
String path = """
    C:\\temp\\
    next
    """;
// Value: "C:\\temp\\\nnext\n"
// The first line ends with an actual \ character, followed by LF.
~~~

To actually join lines, use a single `\` at the end of the line, not `\\`.

## 5. Effect of indentation when continuing lines

`\` removes the newline character, yet **does not automatically strip all spaces** at the start of the next line. Java removes only common incidental indentation:

~~~java
String a = """
    head\
      next
    """;
// Equals "head  next\n": two spaces remain between head and next.

String b = """
    head\
    next
    """;
// Equals "headnext\n".
~~~

Example `a` has two extra spaces before `next` relative to the common indentation level. They are preserved and, after removing the LF with `\`, become two spaces in the middle. For predictable results, **align the continued line with the common indentation** if you do not want extra spaces, or use `\s\` when you want exact control over a single space.

Also distinguish `\n` in source (an escape that **explicitly adds** an LF) from `\` at the end of a line (an escape that **explicitly removes** an LF). They are opposite operations, even though both deal with newlines.

## 6. Standalone Java 17+ program

Save the following source code as **`TextBlockWhitespaceDemo.java`**:

~~~java
public class TextBlockWhitespaceDemo {
    public static void main(String[] args) {
        String normal = """
            red
            blue
            """;

        String preserved = """
            A\s
            B\s\s
            """;

        String joined = """
            red\
            blue
            """;

        String withSpace = """
            Hi\s\
            there
            """;

        String noFinalNewline = """
            done""";

        String relativeIndent = """
            head\
              next
            """;

        System.out.println("normal=" + visible(normal));
        System.out.println("preserved=" + visible(preserved));
        System.out.println("joined=" + visible(joined));
        System.out.println("withSpace=" + visible(withSpace));
        System.out.println("noFinalNewline=" + visible(noFinalNewline));
        System.out.println("relativeIndent=" + visible(relativeIndent));
        System.out.println("preserved.length=" + preserved.length());
        System.out.println("preserved.equals="
                + preserved.equals("A \nB  \n"));
    }

    private static String visible(String s) {
        return s.replace(" ", "<SP>").replace("\n", "\\n");
    }
}
~~~

Compile and run in the folder containing the file using JDK 17+:

~~~bash
javac --release 17 TextBlockWhitespaceDemo.java
java TextBlockWhitespaceDemo
~~~

**Exact stdout output:**

~~~text
normal=red\nblue\n
preserved=A<SP>\nB<SP><SP>\n
joined=redblue\n
withSpace=Hi<SP>there\n
noFinalNewline=done
relativeIndent=head<SP><SP>next\n
preserved.length=7
preserved.equals=true
~~~

These lines use the `visible` method to turn LF into the text `\n` and spaces into `<SP>`. That allows verifying **embedded LFs**, **trailing LFs**, **space counts**, and **spaces from intentional indentation**. The `preserved.equals=true` check verifies the content directly rather than relying on terminal rendering.

## 7. Comparison and choosing the right form

| Goal | Source syntax | String value |
| --- | --- | --- |
| Keep LF between two lines | `red` then newline `blue` in text block | `red\nblue` |
| Omit LF between two lines | `red\` then newline `blue` | `redblue` |
| Omit LF while adding one space | `red\s\` then newline `blue` | `red blue` |
| Keep one space at end of line | `red\s` then newline | `red \n` |
| Keep two spaces at end of line | `red\s\s` then newline | `red  \n` |
| No trailing LF in string | Place closing `"""` directly after last content | No trailing `\n` |
| Store a literal backslash character | Use `\\` in source | One actual `\` |

**Practical scenarios:**

- With **Markdown**, two spaces at the end of a line can signify a *hard line break*. `\s\s` makes it clear that those two spaces are intentionally placed before the LF.
- With **SQL or long prose**, line continuation improves code readability but can merge tokens; for example, `SELECT\s\` followed by `FROM` yields `SELECT FROM`, whereas `SELECT\` alone yields `SELECTFROM`.
- With **protocols or byte-exact data**, remember a text block's LF is `\n`. If a standard requires CRLF, produce `\r\n` explicitly where needed and verify the encoded bytes rather than assuming OS source line endings control the output.

## 8. Common mistakes

1. **Counting whitespace by eye:** terminals poorly display trailing spaces. Use `equals(...)`, `length()`, or a `visible` helper.
2. **Typing literal trailing spaces instead of `\s`:** text block processing can strip them. Use `\s` to express intent clearly.
3. **Leaving a space after the line-continuation `\`:** the backslash is no longer adjacent to the line terminator, which easily causes a compile error.
4. **Forgetting a space when continuing a line:** `\` only removes the LF; it does not add a space. Use `\s\` when needed.
5. **Confusing regex `\s` with Java `\s`:** if you want a regex whitespace pattern, escape it as `"\\s"` in Java source.
6. **Confusing `\\` with line continuation:** `\\` creates a literal backslash and does not remove the following LF.
7. **Ignoring remaining indentation after continuation:** indentation beyond the common level is kept and can show up in the middle of the joined sentence.
8. **Forgetting the trailing LF when the closing delimiter is on its own line:** use `equals(...)` to confirm the target string.
9. **Adding `strip()` or `trim()` as a quick fix:** those methods can delete whitespace that was intentional data; specifying the exact content in source is much clearer.

## 9. Self-check exercises

Predict the output before running:

~~~java
String a = """
    AB\
    CD
    """;
// a.equals("ABCD\n") == true

String b = """
    AB\s\
    CD""";
// b.equals("AB CD") == true

String c = """
    AB\s\s
    CD
    """;
// c.equals("AB  \nCD\n") == true
~~~

Modify the second example yourself to produce `"AB  CD"` (two spaces and no trailing LF). The answer is to use `AB\s\s\` on the first line and place the closing `"""` on the same line as `CD`.

**Remember:** `\s` produces **exactly one space U+0020**; `\` at the end of a line **removes the exact line terminator after it**. Spaces from relative indentation and the text block's trailing LF must still be considered separately.

## References

- [Java Language Specification 17 — §3.10.6 Text Blocks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.10.6): syntax and processing order.
- [Java Language Specification 17 — §3.10.7 Escape Sequences](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.10.7): the `\s` escape and line continuation.
- [OpenJDK JEP 378 — Text Blocks](https://openjdk.org/jeps/378): examples of trailing spaces, line terminators, and design goals.