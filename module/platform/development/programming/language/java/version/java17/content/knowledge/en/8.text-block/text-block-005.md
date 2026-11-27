# The `\s` Escape and Backslash Line Continuation in Java 17 Text Blocks

**Topic:** Java 17  
**Chapter:** Text block  
**Lesson:** The `\s` escape and backslash line continuation

Text blocks allow you to declare multiline strings in Java using `"""` delimiters, which is very useful when storing JSON, SQL, HTML, multiline messages, or sample data. In addition to automatically stripping incidental indentation, text blocks support two special escapes to **precisely control whitespace and newline characters**:

- **`\s`:** Inserts **one regular space** (Unicode U+0020) into the resulting string. Especially useful when you need to preserve spaces at the **end of a line**, where directly typed spaces are stripped during text block processing.
- **`\` immediately before a source line terminator:** Acts as *line continuation* — **omits that newline from the resulting string**, so the content of the next source line joins directly onto the previous line.

Both escapes have been part of the standardized text block feature since **Java 15** (JEP 378), so on **Java 17** they are stable syntax without needing `--enable-preview`.

> **Remember:** `\s` creates **a space**, whereas `\` at the end of a line **removes one line break**. The backslash here is the `\` character (backslash), not the forward slash `/`.

## 1. Reviewing text block structure

A text block opens with three double quotes, followed by **a mandatory line terminator**; the content starts on the next line:

```java
String message = """
        Hello,
        This is Java 17.
        """;
```

The actual string value is equivalent to:

```java
String message = "Hello,\nThis is Java 17.\n";
```

Three notable points:

1. Leading spaces in the example are indentation for source code formatting. Common indentation does not become string content.
2. Line breaks inside a text block are normalized to **LF (`\n`)** when processing source content, regardless of the Java file's physical line-ending style.
3. Because the closing `"""` is on its own line, there is a `\n` character after `This is Java 17.` in the resulting string.

A text block still has type **`java.lang.String`**. It does not create a special data type, nor does it automatically interpolate data like a template string.

### 1.1. Why are these two escapes needed?

Imagine needing to produce the result:

```text
A··
B
```

In this illustration, each `·` represents **one real space**. That means after `A` there are two spaces before the newline character. If you write two literal spaces at the end of the text block line, they can be stripped when Java processes trailing whitespace.

Similarly, if you write:

```java
String text = """
        Java
        17
        """;
```

the result contains `Java\n17\n`. Yet sometimes we want **source code to span two lines** for readability while the string value must be `Java17\n` or `Java 17\n`. Line-continuation escapes give you that control.

## 2. Processing order of text block content

To understand `\s` and line continuation, you need to know that Java does not take every character between `"""` verbatim.

For text block content, the compiler conceptually processes it in three main steps:

1. **Normalize line terminators:** Source line-ending forms, such as CR and CRLF, are normalized to LF.
2. **Strip incidental white space (*incidental white space*):** Remove unnecessary common leading indentation and trailing whitespace on lines.
3. **Interpret escape sequences:** Only at this stage is `\s` turned into a space, `\n` turned into a newline character, and `\` + line terminator processed to suppress that newline.

Diagram:

```text
Content between """ ... """
          |
          v
Normalize line terminators to LF
          |
          v
Strip incidental indentation and trailing whitespace
          |
          v
Interpret escape sequences:
  \s        --> U+0020 space
  \ + LF    --> no newline added
          |
          v
Final String value
```

**Important consequence:** `\s` is interpreted **after** trailing whitespace removal. When the compiler checks for trailing whitespace, the source characters are still the escape sequence `\s` (`\` and `s`), so the space produced afterward is **preserved**.

Likewise, `\` used for line continuation is interpreted after Java determines and strips common indentation. As a result, two source lines can share the same indentation without that indentation sneaking into the middle of the joined string.

## 3. The `\s` escape: one exact space

In Java 17:

```java
String oneSpace = "\s";
System.out.println(oneSpace.length());     // 1
System.out.println(oneSpace.equals(" ")); // true
```

`\s` represents **one U+0020 space character**. It is not a tab, not a newline character, and not shorthand for "any whitespace".

You can repeat the escape multiple times:

```java
String twoSpaces = "\s\s";
String threeSpaces = "\s\s\s";

System.out.println(twoSpaces.length());   // 2
System.out.println(threeSpaces.length()); // 3
```

### 3.1. Preserving spaces at the end of a text block line

```java
String value = """
        A\s\s
        B
        """;
```

Exact equivalent value:

```java
String value = "A  \nB\n";
```

The two `\s` escapes after `A` produce **two trailing spaces** in the output. They are not removed by the text block's trailing-whitespace stripping rule.

Illustration table (`·` is used only for visibility):

| Source line in text block | Line in resulting string |
|---|---|
| `A\s\s` then newline | `A··` then newline |
| `B` then newline | `B` then newline |

If replaced with **two directly typed spaces** after `A` in source code, they would be treated as trailing whitespace during text block processing. Using `\s` states clearly: "these are intentional spaces that must exist in the final value."

### 3.2. Keeping a separating space in content

```java
String address = """
        House number:\s42
        Street: Hoa Mai
        """;
```

`\s` between `:` and `42` produces a space identical to an ordinary ` ` character:

```text
House number: 42
Street: Hoa Mai
```

When a space sits **between** words on the same line, you can still type a regular space directly. `\s` shows its clearest value when spaces appear at the **end of a line** or when you want to make an exact number of spaces explicit and intentional.

### 3.3. `\s` does not represent regex whitespace

This is a common point of confusion in Java 17:

```java
String javaSpace = "\s";  // One U+0020 space
String regexText = "\\s"; // Two characters: backslash and letter s
```

In **regex**, `\s` typically represents the whitespace character class according to regular expression rules. However, if you write the Java literal `"\s"`, Java **interprets the escape first**, so the regex engine receives only a single space.

To pass the regex `\s+` to Java `Pattern` to match one or more whitespace characters:

```java
String normalized = "A\tB\nC".replaceAll("\\s+", " ");
System.out.println(normalized); // A B C
```

If you write `replaceAll("\s+", " ")`, the regex argument becomes `" +"` — one or more **literal spaces**, which will not match tabs and newlines the way regex `\s+` does.

**Distinguishing the uses:**

| Java code | Actual string produced | When to use |
|---|---|---|
| `"\s"` | One space | Need to insert a U+0020 space |
| `"\\s"` | Backslash + `s` | Need to pass `\s` syntax to regex or text data |
| `"\t"` | One tab character | Need to insert a tab |
| `"\n"` | One LF character | Need to insert a newline |

These rules apply to `String` in general, not only text blocks.

## 4. Joining lines with `\` at the end of a source line

A backslash immediately before a source line terminator creates **line continuation**: Java omits that line terminator from the final string.

Example:

```java
String joined = """
        Java\
        17
        """;
```

Actual value:

```java
String joined = "Java17\n";
```

Even though `Java` and `17` sit on **two lines in source code**, they become **one content line** in the resulting string. Because the closing `"""` is on the next line, the string still ends with `\n` after `17`.

Diagram:

```text
SOURCE LINE                 STRING VALUE

Java\                       Java17\n
17
"""
```

There is no `\` character in the result: the backslash is a control marker for line continuation, not a character to print.

### 4.1. Joining two lines without a space

```java
String code = """
        ABC\
        DEF
        """;

System.out.println(code.equals("ABCDEF\n")); // true
```

Because no space was placed between the two parts, the result is `ABCDEF`.

### 4.2. Joining two lines while keeping one space

Line continuation **does not automatically insert a space**. If you want a separating space, write it explicitly:

```java
String sentence = """
        Java\s\
        17
        """;

System.out.println(sentence.equals("Java 17\n")); // true
```

Reading `Java\s\` at the end of the line:

1. `Java` — four letter characters.
2. `\s` — inserts **one space**.
3. `\` immediately before newline — omits the newline.
4. Next line has `17` — appended right after the space.

Thus the result is `Java 17\n`.

This combination of both escapes is very handy: **`\s` determines how many spaces remain; `\` determines where not to break the line.**

### 4.3. Joining multiple source lines into a single string line

```java
String query = """
        SELECT id, name\s\
        FROM users\s\
        WHERE active = true
        """;
```

Equivalent value:

```java
String query =
        "SELECT id, name FROM users WHERE active = true\n";
```

Source code readers still see three clear clauses of the SQL query, while the resulting string has only **one SQL line** (with one trailing newline from the closing delimiter's placement). Having a trailing newline usually does not affect SQL queries, though check specifically when passing strings to external systems.

### 4.4. `\` must sit right against the line terminator

Line continuation happens when the escape takes the form **backslash immediately followed by a line terminator**. Therefore:

```java
String joined = """
        Hello\
        World
        """;
```

is the valid form. If spaces are inserted **after** `\` and **before** the line break, you no longer have the `\` + line terminator escape. The code may become invalid or behave unexpectedly; avoid reformatting that area in a way that adds whitespace after the backslash.

**Practice:** When joining lines, make `\` the very last character on the source line, flush against the newline.

## 5. Line continuation does not remove all newlines

A `\` at the end of a line removes only the **line terminator immediately following it**.

```java
String text = """
        First\
        Second
        Third
        """;
```

Value:

```java
String text = "FirstSecond\nThird\n";
```

- The newline between `First` and `Second` is removed by `\`.
- The newline after `Second` remains.
- The newline after `Third` remains because the closing delimiter is on a new line.

If you need to join all three parts:

```java
String text = """
        First\
        Second\
        Third
        """;

System.out.println(text.equals("FirstSecondThird\n")); // true
```

Do not confuse line continuation with a command to "delete every newline inside the text block".

### 5.1. Removing the final newline with `\`

By default, placing the closing delimiter on its own line leaves a `\n` after the last content line. If you do not want a trailing newline:

```java
String noFinalNewline = """
        Done\
        """;

System.out.println(noFinalNewline.equals("Done")); // true
```

The `\` right after `Done` suppresses the newline leading to the closing delimiter line, so the result is just `Done`.

Another option is placing the closing delimiter immediately after the final content:

```java
String alsoNoFinalNewline = """
        Done""";

System.out.println(alsoNoFinalNewline.equals("Done")); // true
```

Both are valid. Use the first form when you want to **keep the closing delimiter on its own line** without adding a newline to the value.

## 6. Comparing `\s`, `\n`, and line continuation

These three escapes address three distinct needs:

| Syntax in Java source | Effect on resulting string | Purpose |
|---|---|---|
| `\s` | Adds one `U+0020` space | Preserve/insert a space |
| `\n` | Adds one `LF` newline | Explicitly insert a line break |
| `\` + physical source newline | **Does not add** that newline | Join two source lines into one output line |
| `\\` | Adds one literal backslash character | Include a literal `\` in the string |
| Physical line break in text block without `\` | Adds a newline (LF) | Keep multiline structure |

Example demonstrating the differences:

```java
String withSpace = """
        A\sB
        """;

String withNewline = """
        A\nB
        """;

String continued = """
        A\
        B
        """;

System.out.println(withSpace.equals("A B\n"));     // true
System.out.println(withNewline.equals("A\nB\n"));  // true
System.out.println(continued.equals("AB\n"));      // true
```

**Common point of confusion:** In `withNewline`, `\n` is written inside a single line of the text block; in addition to the newline created by the escape, the source line containing `B` also ends with a physical newline. Thus the result has a newline after `B`.

## 7. Relationship with incidental indentation handling

Text blocks are designed so source code can be indented along with Java structure without giving the String unwanted indentation.

```java
String html = """
        <section>
            <h1>Title</h1>
        </section>
        """;
```

Common whitespace before `<section>`, `<h1>`, and `</section>` is removed. However, the **intentional** indentation of `<h1>` relative to `<section>` is preserved.

With line continuation:

```java
String joined = """
        Alpha\
        Beta
        """;
```

After Java strips common indentation, the actual content lines are `Alpha\` and `Beta`. The escape interpretation phase drops the newline between them, yielding `AlphaBeta\n`.

### 7.1. Do not rely on manually typed trailing spaces

An editor may automatically strip trailing whitespace on save. Java also has a rule stripping trailing whitespace in text blocks. Therefore, if a string value must have a **specific number of trailing spaces**, write `\s` explicitly:

```java
String table = """
        Item:\s\s
        Price:
        """;
```

This helps both code readers and formatters recognize significant spaces.

### 7.2. When intentional leading spaces are needed

`\s` can also be used to insert spaces at the start of a line:

```java
String indented = """
        \s\sChild
        Parent
        """;

System.out.println(indented.equals("  Child\nParent\n")); // true
```

In this case, the two `\s` escapes are **content** to keep; they are not treated as common source-code indentation in the earlier step before escape processing.

However, if the goal is representing normal structural indentation, you can use the text block's own relative indentation for better readability. `\s` fits when you want to make a fixed number of spaces explicit.

## 8. Complete example inspecting actual characters in Java 17

When outputs contain trailing spaces or multiple newlines, `System.out.println` can make exact inspection hard. We can display characters with readable markers:

- `·` represents **one space**.
- `↵` represents **one newline**.

Save the program as **`TextBlockEscapeDemo.java`**:

```java
public class TextBlockEscapeDemo {

    static String visible(String text) {
        return text
                .replace(" ", "·")
                .replace("\n", "↵\n");
    }

    public static void main(String[] args) {
        String trailingSpaces = """
                A\s\s
                B
                """;

        String joinedWithoutSpace = """
                Java\
                17
                """;

        String joinedWithSpace = """
                Java\s\
                17
                """;

        String joinedSql = """
                SELECT id, name\s\
                FROM users\s\
                WHERE active = true
                """;

        String noFinalNewline = """
                Done\
                """;

        System.out.println("1. " + visible(trailingSpaces));
        System.out.println("2. " + visible(joinedWithoutSpace));
        System.out.println("3. " + visible(joinedWithSpace));
        System.out.println("4. " + visible(joinedSql));
        System.out.println("5. " + visible(noFinalNewline));

        System.out.println(trailingSpaces.equals("A  \nB\n"));
        System.out.println(joinedWithoutSpace.equals("Java17\n"));
        System.out.println(joinedWithSpace.equals("Java 17\n"));
        System.out.println(noFinalNewline.equals("Done"));
    }
}
```

Compile and run with JDK 17:

```bash
javac --release 17 TextBlockEscapeDemo.java
java TextBlockEscapeDemo
```

Expected output:

```text
1. A··↵
B↵

2. Java17↵

3. Java·17↵

4. SELECT·id,·name·FROM·users·WHERE·active·=·true↵

5. Done
true
true
true
true
```

The blank lines after results 1 through 4 appear because `visible` keeps `\n` and `println` adds a newline after printing. That is purely **output presentation**, not the text block adding two newlines.

### 8.1. Verifying with `String.equals`

Instead of relying on terminal whitespace rendering, the `equals` checks verify the **actual strings**:

- `"A  \nB\n"` has two spaces before the newline.
- `"Java17\n"` has no space between the two parts.
- `"Java 17\n"` has one space between the two parts.
- `"Done"` has no trailing newline.

This is how to assert expectations when writing tests for text block code. In this lesson, showing outputs serves purely to explain Java 17 language behavior.

## 9. Practical applications

### 9.1. Formatting text lines that require trailing spaces

Some text protocols or Markdown formats treat trailing spaces as meaningful. For example, in a string used to generate a Markdown document, **two trailing spaces** are interpreted by some renderers as a soft/forced line break according to Markdown syntax:

```java
String markdown = """
        Name: Minh\s\s
        Role: Developer
        """;
```

In the output:

```text
Name: Minh··↵
Role: Developer↵
```

Note that Markdown renderers may handle breaks in their own way; the purpose of the example is showing Java **preserved the exact two spaces**.

### 9.2. Writing readable SQL in source, one line in result

```java
String sql = """
        SELECT id, username\s\
        FROM accounts\s\
        WHERE enabled = true\s\
        ORDER BY id
        """;
```

Resulting string:

```text
SELECT id, username FROM accounts WHERE enabled = true ORDER BY id↵
```

If the SQL statement works fine containing newlines, you can keep the source lines **without** line continuation. Use `\` when the receiving system expects one line or when consistent single-line formatting is an actual requirement.

**SQL safety:** Text blocks only represent strings. Values coming from users must still be passed via parameterization mechanisms like `PreparedStatement`; line continuation does not make SQL data safer.

### 9.3. Joining a long notice with no newline between parts

```java
String notice = """
        The system will undergo maintenance this weekend.\s\
        Please complete your work before the announced time.
        """;
```

The value is nearly an ordinary single line:

```text
The system will undergo maintenance this weekend. Please complete your work before the announced time.
```

The actual string still has a trailing newline because the closing delimiter is on the next line. If an API call requires **strictly one line with no trailing newline**, add `\` on the last content line or intentionally choose how to omit the trailing newline.

### 9.4. Distinguishing source layout from data layout

Sometimes, source lines and data lines **should match**:

```java
String json = """
        {
          "id": 17,
          "status": "ok"
        }
        """;
```

Keeping newlines here makes the JSON easier to read; line continuation is unnecessary. Escapes are a tool for **precise control when needed**, not a rule to apply to every text block.

## 10. Common mistakes and misconceptions

### Mistake 1. Assuming `\s` means "any whitespace"

`\s` in Java string literals and text blocks is **one U+0020 space**. It is not regex `\s` once Java has interpreted string escapes. For regex, write `"\\s"` or `"\\s+"` if a quantifier is needed.

### Mistake 2. Thinking trailing `\` automatically inserts a space

```java
String result = """
        Hello\
        World
        """;
```

The result is `HelloWorld\n`, **not** `Hello World\n`. If spacing is needed, use `Hello\s\` or place a space explicitly in an appropriate position.

### Mistake 3. Confusing trailing `\` with `\n`

- `\n` **creates** a newline.
- `\` right before a source newline **removes** that newline.

The two escapes have opposite effects on line breaks at their respective positions.

### Mistake 4. Using literal spaces at the end of a line when exact values matter

```java
// Goal: two spaces after A, before the newline.
String correct = """
        A\s\s
        B
        """;
```

Typing literal spaces after `A` is hard to spot and gets stripped by trailing-whitespace processing. `\s` is clearer and more reliable for this purpose.

### Mistake 5. Putting other characters after the backslash before the newline

Line continuation requires **`\` immediately followed by a line terminator**. If you type a space after `\`, the line-continuation escape is no longer valid. Keep `\` as the last character of the source line.

### Mistake 6. Thinking line continuation removes the string's trailing newline

```java
String text = """
        A\
        B
        """;
```

The result is still `AB\n`, because the newline **after `B`** has no line-continuation escape. To remove the trailing newline, apply it on the **last line** or change the closing delimiter placement.

### Mistake 7. Thinking text blocks automatically add spaces between parts

Text blocks only apply newline, indentation, and escape rules. Joining `foo\` and `bar` yields `foobar`. Java does not guess word boundaries or insert spaces based on natural language semantics.

### Mistake 8. Calling `trim()` or `strip()` afterwards and unexpectedly losing spaces

```java
String text = """
        A\s\s
        """;

String stripped = text.stripTrailing();
```

`text` keeps two trailing spaces on the line and a trailing newline; yet `stripTrailing()` **explicitly strips trailing whitespace from the entire string**. If those characters must be kept, do not call whitespace-stripping methods on the result in ways that contradict your requirements.

Note that `stripTrailing()` strips whitespace at the **end of the string**, not automatically at the end of **every middle line** inside the string. Distinguish compiler-time text block processing from runtime `String` operations called later.

### Mistake 9. Using `\s` to represent a tab or newline

- Use `\t` if you need a tab.
- Use `\n` if you need an LF.
- Use `\s` if you need a regular space.

### Mistake 10. Thinking text blocks only work on Java 17

Text blocks have been stable since Java 15. Java 17 **inherits** the feature; do not describe it as syntax introduced for the first time in Java 17. Check your project's `--release` configuration if using a newer JDK while targeting an older Java version.

## 11. Quick selection guide by desired output

Suppose source code is laid out across multiple lines; pick the syntax according to the desired output string:

| Desired string | How to write at end of source line | Reason |
|---|---|---|
| `"A\nB\n"` | `A` then normal line break | Keeps newline |
| `"AB\n"` | `A\` then `B` on next line | Removes newline between A and B |
| `"A B\n"` | `A\s\` then `B` on next line | Inserts one space, removes newline |
| `"A  \nB\n"` | `A\s\s` then `B` on next line | Keeps two spaces before newline |
| `"A"` | `A\` then line with closing `"""` | Removes trailing newline |
| `"A\n"` | `A` then line with closing `"""` | Keeps trailing newline |

### Two questions to ask yourself

**1. Do I need whitespace or a newline?**  
If you need a **U+0020 space**, use `\s`. If you need to keep a newline, break the source line normally or use `\n`. If you need **no newline at a source boundary**, use `\` at the end of the line.

**2. Is formatting only for code readability or meaningful to the data?**  
If newlines or spaces matter to a protocol, template, test, or output format, express them with explicit escapes and use `String.equals` to verify the expected value.

## 12. Practice exercises with solutions

### Exercise 1. Predict the exact value

```java
String text = """
        X\s\s
        Y
        """;
```

**Question:** How many spaces follow `X`? Is there a newline after `Y`?

**Answer:** There are **two spaces** after `X` before the newline; there is **one newline** after `Y`. The value is equivalent to `"X  \nY\n"`.

### Exercise 2. Joining words without a space

```java
String text = """
        micro\
        service
        """;
```

**Question:** What does `text.equals("microservice\n")` return?

**Answer:** `true`, because the trailing backslash removes the newline between `micro` and `service`. The trailing newline after `service` remains.

### Exercise 3. Joining words with one space

**Task:** Complete the text block so its value equals `"Hello World\n"`, while `Hello` and `World` sit on two different source lines.

**One solution:**

```java
String text = """
        Hello\s\
        World
        """;
```

`\s` creates the space; `\` removes the newline.

### Exercise 4. No trailing newline

**Task:** Source code keeps the closing `"""` on its own line, yet the resulting string must equal `"READY"` exactly.

**Answer:**

```java
String text = """
        READY\
        """;
```

The final line uses line continuation to omit the newline right before the closing delimiter.

### Exercise 5. Spot the regex bug

```java
String text = "A\tB C";
String result = text.replaceAll("\s+", "_");
```

**Question:** Why does this code fail to replace the tab as expected?

**Answer:** Java interprets `"\s+"` as regex `" +"`, which only matches regular spaces. To pass regex `\s+` to match whitespace, use `"\\s+"`:

```java
String result = text.replaceAll("\\s+", "_");
```

### Exercise 6. Distinguishing a literal backslash from line continuation

**Task:** A text block contains two lines: the first line is `C:\temp` (with one literal `\`), the second line is `Done`; keep the newline between the two lines.

**One solution:**

```java
String pathInfo = """
        C:\\temp
        Done
        """;
```

`\\` is the escape for **one literal backslash** in the string, unlike a trailing `\` used for line continuation.

### Exercise 7. Analyze three newlines

```java
String text = """
        A\
        B
        C\
        D
        """;
```

**Question:** Which single-line string literal in Java source is this equivalent to?

**Answer:**

```java
String expected = "AB\nCD\n";
```

Two newlines are removed: between A–B and between C–D. The newline between B–C and the newline after D remain.

## 13. Official references

- [Oracle Java 17 — Text Blocks](https://docs.oracle.com/en/java/javase/17/language/text-blocks.html): text block structure, whitespace handling, `\s` escape, and line continuation.
- [OpenJDK JEP 378 — Text Blocks](https://openjdk.org/jeps/378): design description, processing order, and two new escapes standardized in Java 15.
- [Java Language Specification 17 — `3.10.6 Text Blocks`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.10.6): syntax and how text block values are determined.
- [Java Language Specification 17 — `3.10.7 Escape Sequences`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.10.7): supported escapes, including `\s` and `\` + line terminator.
- [JDK 17 API — `String`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): string methods related to whitespace handling such as `stripIndent()` and `translateEscapes()`.

**Core takeaway:** `\s` in Java 17 inserts **one U+0020 space**, especially useful for preserving spaces at the end of a text block line. `\` placed right before a source newline **joins two content lines** without inserting a newline. Combine `\s\` when joining lines while keeping exactly one space at the boundary.
