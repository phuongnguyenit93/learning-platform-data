# Resulting Strings After Processing and Inspecting Characters in Text Blocks — Java 17

## 1. What object does a text block produce?

In Java 17, a **text block** is a syntax for writing multiline strings using `"""` delimiters. After the compiler processes the content inside, the result is still an ordinary **`String`**. The program has no separate data type called `TextBlock`, and the string object does not remember whether it was written with a text block or regular double quotes.

```java
String normal = "Hello\nJava\n";

String multiline = """
        Hello
        Java
        """;

System.out.println(normal.equals(multiline)); // true
```

Both expressions produce the **exact same character content**:

```text
Hello⏎
Java⏎
```

In this display, `⏎` only illustrates the `\\n` (LF) newline character, not an actual character added to the String.

What you need to learn is **the string value after processing**, rather than guessing the result from text positioning in an editor. What looks visible in a Java file does not always match the runtime `String` character-for-character, because Java processes line breaks, indentation whitespace, and escape sequences.

Text blocks have been a stable feature since Java 15 (JEP 378) and are available in Java 17 **without enabling preview**. The rules in this lesson remain useful in modern Java.

## 2. Basic syntax and the opening newline

A text block opens with three double quotes, followed by permitted whitespace and **one mandatory line terminator**. Content starts on the next line:

```java
String greeting = """
        Hello
        Java 17
        """;
```

The example above creates a string with two lines of content. The first character of the string is `'H'`, **not** the newline after the opening `"""`. The newline immediately after the opening delimiter is part of the opening syntax; it is not automatically inserted at the start of the string.

You cannot write a text block on a single line like this:

```java
// Invalid: line terminator required immediately after opening delimiter.
// String invalid = """Hello""";
```

Just like a string literal, a text block can be assigned to a variable, returned from a method, passed to APIs, and used with `equals`, `length`, `substring`, `replace`, `lines`, `codePoints`, and so on.

### Where the closing delimiter sits decides the ending character

The following two snippets differ in **the position of the closing `"""`**:

```java
String withFinalNewline = """
        Alpha
        Beta
        """;

String withoutFinalNewline = """
        Alpha
        Beta""";
```

After processing:

```java
withFinalNewline.equals("Alpha\nBeta\n");    // true
withoutFinalNewline.equals("Alpha\nBeta");   // true
```

In the first example, there is an LF after `Beta` because the `Beta` content line terminates before reaching the line containing the closing delimiter. In the second example, the closing delimiter stands directly after `Beta`, so there is no trailing LF.

**Practical rule:** When string content must be exact down to the last character (payloads, messages, statements, snapshot tests), decide explicitly whether a trailing `\\n` is needed.

## 3. Three main steps that produce the string value

To understand a text block accurately in Java 17, follow the three steps Java uses to interpret its content:

1. **Normalize line terminators** inside text block content: `CR` (U+000D) and `CRLF` are normalized to `LF` (U+000A).
2. **Strip incidental indentation** (*incidental indentation*) and trailing whitespace on lines according to text block rules. Meaningful relative indentation may still remain.
3. **Interpret escape sequences**: such as `\\n`, `\\t`, `\\s`, and a trailing backslash for line continuation.

This order is crucial: Java strips source whitespace according to text block rules **before** interpreting escapes. Therefore `\\s` can intentionally produce a trailing space that ordinary whitespace stripping does not remove.

| Step | Source data | What may differ in the String |
|---|---|---|
| Normalize newlines | File uses CRLF or CR | Newlines in the text block string are LF `\\n` |
| Strip indentation | Code is indented inside a class/method | Common indentation is removed |
| Handle trailing whitespace | Spaces/tabs exist at end of source line | Ordinary trailing whitespace is not kept |
| Interpret escapes | Source contains `\\s`, `\\t`, `\\n`, trailing `\\` | String receives space, tab, newline, or joined lines accordingly |

Note that Java also translates Unicode escapes in source code before tokenization. For text block exercises, express desired characters with appropriate escapes and inspect the final string directly rather than trying to trace every compiler pass.

## 4. Line terminator normalization: CR, LF, CRLF

A text block can be written in a source file using different line-ending conventions depending on OS or Git settings:

| Symbol | Code point | Description |
|---|---|---|
| LF | U+000A | Line feed, written in Java as `'\\n'` |
| CR | U+000D | Carriage return, written in Java as `'\\r'` |
| CRLF | U+000D then U+000A | Pair of characters commonly used for line breaks in Windows source files |

For **line terminators belonging to text block content**, Java normalizes CR and CRLF to LF. Therefore the same text block usually produces the exact same string value whether the source file uses CRLF or LF.

```java
String text = """
        first
        second
        """;

System.out.println(text.equals("first\nsecond\n")); // true
System.out.println(text.indexOf('\r'));              // -1
```

This example illustrates newlines produced by **source content lines**. If you explicitly write the `\\r` escape inside a text block, the escape step at the end can still produce CR in the resulting string:

```java
String explicitCr = """
        A\rB""";

System.out.println(explicitCr.indexOf('\r')); // 1
```

Thus, **normalizing source lines does not mean a String created from a text block can never contain CR**. Distinguish line terminators present in source text from characters produced by escapes.

When an application communicates with a system requiring `CRLF`, construct the output in that format intentionally and test it; do not assume text blocks follow the operating system's line separator.

## 5. Stripping incidental indentation

Text blocks often sit deeply nested inside classes or methods, so source code is indented for readability. Java does not put all of that indentation whitespace into the string.

```java
String note = """
        first
        second
        """;

System.out.println(note.equals("first\nsecond\n")); // true
```

In the example, the common whitespace before `first`, `second`, and the closing delimiter is treated as **incidental indentation**. After processing, the string starts right at `f`.

### 5.1. Relative indentation is still preserved

```java
String tree = """
        root
          child
            leaf
        """;
```

The result is:

```text
root
  child
    leaf
```

Equivalent to:

```java
"root\n  child\n    leaf\n"
```

Common indentation has been stripped; **two spaces before `child` and four spaces before `leaf`** remain to show relative structure.

### 5.2. Closing delimiter position also participates in indentation rules

A closing delimiter at a different indentation level can cause more leading whitespace to be retained:

```java
String indented = """
        one
          two
      """;
```

In the example above, incidental indentation is determined by the minimum relevant indent, including the closing delimiter's position when it sits on its own line. Because the closing delimiter is shifted left relative to `one`, the result retains some leading whitespace:

```java
indented.equals("  one\n    two\n"); // true
```

This technique can be used when you genuinely need leading spaces on every line, though it is sensitive to someone re-indenting the closing delimiter. For whitespace-sensitive data, state expectations with tests rather than relying solely on editor alignment.

### 5.3. Source trailing whitespace is usually removed

Suppose a line appears to have spaces after `A`:

```java
String noTrailingSpaces = """
        A
        B
        """;
```

Java strips trailing whitespace from source lines per text block rules. If you want to **intentionally keep a trailing space**, write the `\\s` escape explicitly:

```java
String keepOneSpace = """
        A\s
        B
        """;

System.out.println(keepOneSpace.equals("A \nB\n")); // true
```

One meaningful space has been added after `A`. Readers can tell this is an intentionally preserved space rather than an editor formatting artifact.

### 5.4. Tabs and spaces are not equivalent

In a String, tab `\\t` is **one character U+0009**, whereas space `' '` is **U+0020**. Two strings may look nearly identical in a terminal yet be completely different:

```java
String tabbed = "A\tB";
String spaced = "A B";

System.out.println(tabbed.equals(spaced)); // false
```

For exact control, avoid mixing tabs and spaces at the start of source lines, prefer `\\t` when you truly want a tab in the resulting string, and inspect character values after compilation.

## 6. Escape sequences in text blocks

Text blocks support Java string escapes, along with escapes handy for multiline text.

| Escape in Java source | Resulting character or effect | When needed |
|---|---|---|
| `\\n` | LF, U+000A | Explicitly insert a newline at a position |
| `\\r` | CR, U+000D | Protocol requiring carriage return |
| `\\t` | Tab, U+0009 | Tab-separated data |
| `\\s` | Space, U+0020 | Preserve an exact space, especially at line end |
| `\\\\` | One backslash character | Text literally needs `\\` |
| `\\"` | Double quote `"` | When escaping quotes or avoiding closing the block |
| `\\` immediately before line terminator | **Line continuation**: omits that line terminator | Spread source across lines while joining output into one line |

Inside text blocks, most single double quotes do not need escaping:

```java
String json = """
        {
          "name": "Java",
          "version": 17
        }
        """;
```

The `"` characters in `"name"` and `"Java"` are normal characters inside the text block. If three consecutive double quotes are needed in the content, prevent them from being recognized as the closing delimiter, for instance by escaping appropriately.

### 6.1. Line continuation: trailing backslash on a line

Suppose you want a **continuous** String while wrapping Java source across multiple lines:

```java
String combined = """
        Java\
        Seventeen\
        Rocks
        """;
```

After processing:

```java
combined.equals("JavaSeventeenRocks\n"); // true
```

The trailing backslash is not kept in the string; it only signals **source line continuation**. Therefore there is no LF between `Java` and `Seventeen`, nor between `Seventeen` and `Rocks`.

If you want a space at the join point, specify it explicitly:

```java
String words = """
        Java\s\
        Seventeen
        """;

System.out.println(words.equals("Java Seventeen\n")); // true
```

On the first line, `\\s` produces one space and the line-continuation escape removes the LF. After processing, the two words are joined on one line with **one** space between them.

Do not confuse using `\\n` in source with having a newline in the text block:

- Writing `\\n` asks for an LF at the escape's position.
- Placing an actual newline in text block content normally also creates an LF.
- Writing `\\` at the end of a line suppresses the LF at that join point.

## 7. Observing results: don't rely solely on `println`

When printed to the console, some characters are **hard to distinguish visually**:

- Trailing spaces on a line are usually invisible.
- Tabs are expanded by the terminal to varying display columns.
- `\\r` can return the cursor to the start of the line when rendered by a terminal.
- An LF at the end of the String plus an LF added by `println` can distort the perceived number of lines.

Therefore, when you need to know the **exact post-processed** string, check using `equals`, `length`, character indexing, and code point representation.

### 7.1. `print` and `println` produce different display output

```java
String text = """
        Hello
        """;

System.out.print(text);   // Prints exact String content.
System.out.println(text); // Prints String then appends println's line separator.
```

In both cases, `text` itself **does not change**. Yet `println` appends a newline from the print API, so you should not treat the total number of lines seen on screen as sole proof of String content.

### 7.2. Visualizing whitespace with custom symbols

Create an **inspection-only** view where space is shown as `·`, tab as `⇥`, and LF as `↵`:

```java
static String visible(String text) {
    return text
            .replace(" ", "·")
            .replace("\t", "⇥")
            .replace("\r", "␍")
            .replace("\n", "↵\n");
}
```

Example:

```java
String sample = """
        name:\sJava
        end\s
        """;

System.out.print(visible(sample));
```

When displayed, the end of the second line will show `·` right before `↵`. This is a **presentation helper for inspection**; `sample` itself still contains real spaces and LF characters, not `·` or `↵`.

### 7.3. Comparing against an expected string

A clear way to prove the result:

```java
String actual = """
        header
          item
        """;

String expected = "header\n  item\n";

if (!expected.equals(actual)) {
    throw new AssertionError("Text content differs");
}
```

This checks **every character** exactly, including indentation whitespace and the trailing LF.

When a project uses JUnit, you can replace this with `assertEquals(expected, actual)`; JUnit is an external testing library, **not built into JDK 17**.

### 7.4. Checking indices and UTF-16 code units

`String.length()` counts **UTF-16 code units**, not necessarily the characters a reader perceives. For ASCII and common characters in the BMP, each character is one UTF-16 code unit.

```java
String value = """
        A\s
        """;

System.out.println(value.length());     // 3: 'A', ' ', '\n'
System.out.println(value.charAt(0));   // A
System.out.println((int) value.charAt(1)); // 32: U+0020
System.out.println((int) value.charAt(2)); // 10: U+000A
```

This confirms there are no unexpected leading spaces and that the intentionally preserved trailing space appears right before the newline.

## 8. Code points, Unicode characters, and what users see

A string can contain characters outside the Basic Multilingual Plane (BMP), such as many emojis. These characters use **two UTF-16 code units** (a surrogate pair). Hence `length()` and `charAt()` do not always correspond one-to-one with Unicode code points.

```java
String emoji = """
        😀""";

System.out.println(emoji.length());                         // 2
System.out.println(emoji.codePointCount(0, emoji.length())); // 1
System.out.printf("U+%X%n", emoji.codePointAt(0));           // U+1F600
```

To iterate over **Unicode code points**:

```java
String text = """
        A😀
        """;

text.codePoints().forEach(cp ->
        System.out.printf("U+%04X%n", cp));
```

Output:

```text
U+0041
U+1F600
U+000A
```

In Java 17:

- `chars()` emits the code of each UTF-16 code unit.
- `codePoints()` emits the Unicode code points.
- `charAt(i)` accesses one UTF-16 code unit at index `i`.
- `codePointCount(0, s.length())` counts code points across the entire String.

A **user-perceived character** (*grapheme cluster*) can even consist of multiple code points, such as letters with combining diacritics or emoji sequences. So even the code point count does not necessarily equal the visible character count.

The direct takeaway for text blocks: **text blocks only change how strings are written in source code**. Once the `String` is produced, all of Java's Unicode rules and string-processing APIs apply identically to regular string literals.

## 9. Complete program running on Java 17

The `Main.java` file below demonstrates:

1. The difference between having a trailing LF and having no trailing LF.
2. Preserved relative indentation.
3. A space produced with `\\s`.
4. How to inspect **every code point** of a String.

```java
public class Main {
    static String visible(String text) {
        return text
                .replace(" ", "·")
                .replace("\t", "⇥")
                .replace("\r", "␍")
                .replace("\n", "↵\n");
    }

    static void inspect(String name, String text) {
        System.out.println("[" + name + "]");
        System.out.println("UTF-16 units: " + text.length());
        System.out.println("Content: " + visible(text));
        System.out.print("Code points:");
        text.codePoints().forEach(cp ->
                System.out.printf(" U+%04X", cp));
        System.out.println();
    }

    public static void main(String[] args) {
        String withLf = """
                Hi
                """;

        String noLf = """
                Hi""";

        String nested = """
                root
                  child
                """;

        String keptSpace = """
                A\s
                """;

        inspect("withLf", withLf);
        inspect("noLf", noLf);
        inspect("nested", nested);
        inspect("keptSpace", keptSpace);

        System.out.println(withLf.equals("Hi\n"));            // true
        System.out.println(noLf.equals("Hi"));                 // true
        System.out.println(nested.equals("root\n  child\n")); // true
        System.out.println(keptSpace.equals("A \n"));          // true
    }
}
```

Compile and run with JDK 17:

```bash
javac --release 17 -encoding UTF-8 Main.java
java Main
```

What to observe in the results:

| Variable | Exact String value | `length()` |
|---|---|---:|
| `withLf` | `"Hi\\n"` | 3 |
| `noLf` | `"Hi"` | 2 |
| `nested` | `"root\\n  child\\n"` | 13 |
| `keptSpace` | `"A \\n"` | 3 |

For `keptSpace`, the code point sequence is `U+0041 U+0020 U+000A`. The `U+0020` space was intentionally created right before the newline.

For `nested`, the two spaces before `child` reside inside the resulting String; they are not mere Java source formatting whitespace.

## 10. Using String APIs for further inspection

### 10.1. `String.lines()` and its limitation when checking trailing newlines

`lines()` is useful for processing content line by line:

```java
String text = """
        red
        blue
        """;

text.lines().forEach(System.out::println);
```

However, `lines()` **does not retain line-ending characters in each element**. Hence scanning `lines()` alone is insufficient to verify whether there is a trailing LF.

```java
String a = "red\nblue\n";
String b = "red\nblue";

System.out.println(a.lines().count()); // 2
System.out.println(b.lines().count()); // 2
System.out.println(a.equals(b));       // false
```

When you need to check for a trailing newline, use `endsWith("\\n")`, `equals`, or inspect character codes rather than relying on line count.

### 10.2. `strip`, `stripTrailing`, and `trim`

**Runtime** whitespace-stripping methods are distinct from **compile-time text block processing rules**.

```java
String text = """
        Hello
        """;

System.out.println(text.equals("Hello\n"));  // true
System.out.println(text.strip().equals("Hello")); // true
```

`strip()` does not mutate the original String; it returns a new String with leading and trailing whitespace removed per the method's rules. Do not casually call `strip()` on data that needs its trailing newline or meaningful indentation preserved.

`stripIndent()` and `translateEscapes()` are useful String APIs when processing text at runtime, yet they **are not proof** that a String came from a text block: at compile time, a text block's result has already gone through the required processing steps. Calling them again can further alter existing data.

### 10.3. Comparing strings rather than references

```java
String first = """
        one
        two
        """;

String second = "one\ntwo\n";

System.out.println(first.equals(second)); // true
```

Do not use `==` to verify string content. The `==` operator compares object references; even though Java interns literals and some constant expressions, reference equality is not the content-verification contract needed here.

## 11. Common mistakes when inspecting text blocks

### 11.1. Confusing a standalone closing delimiter with an inline closing delimiter

```java
String a = """
        done
        """;
String b = """
        done""";
```

`a` equals `"done\\n"`; `b` equals `"done"`. When passing text to snapshot tests or content-hash comparisons, one extra or missing LF changes the outcome.

### 11.2. Trying to keep spaces by typing spaces at line end

Editors or formatters can strip trailing spaces. More importantly, text blocks themselves have a rule removing trailing whitespace. Use `\\s` to make preserved spaces explicit.

### 11.3. Confusing source file indentation with resulting indentation

Java removes incidental indentation; do not guess how many spaces are in the String by counting columns from the left edge of the editor. Both the closing delimiter and relatively indented lines affect the result. Use `visible` and `equals` to check.

### 11.4. Drawing conclusions from `println` output

`println` appends a line separator when printing. Trailing spaces on lines are usually invisible. To verify accurately, check `length()`, `charAt`, `codePoints()`, or compare against an expected literal.

### 11.5. Assuming text blocks parse data formats

```java
String json = """
        {"name":"Java","major":17}
        """;
```

`json` is still just a **String**. Text blocks do not validate JSON, automatically deserialize JSON into objects, escape dynamic data, or protect against SQL injection or formatting bugs during string concatenation. If you need real JSON manipulation, use a proper parser; for dynamic SQL, use prepared statements and parameterization.

### 11.6. Using text blocks to change file-writing encoding

String values in the JVM are represented in Java's UTF-16 model. When writing to a file or sending over a network, you must still choose an appropriate encoding (typically UTF-8). Text blocks **do not specify output file encoding**:

```java
java.nio.file.Files.writeString(
        java.nio.file.Path.of("message.txt"),
        """
        Hello Java 17
        """,
        java.nio.charset.StandardCharsets.UTF_8);
```

Here `Files.writeString` takes the constructed String and encodes it as UTF-8 bytes when writing the file.

## 12. Exercises for reading exact resulting strings

### Exercise 1: Identify trailing LF

```java
String a = """
        A
        B
        """;

String b = """
        A
        B""";
```

Write two ordinary string literals whose contents equal `a` and `b`.

**Answer:** `a.equals("A\\nB\\n")` and `b.equals("A\\nB")` are both `true`. The difference is the final LF character.

### Exercise 2: Distinguish relative indentation

```java
String layout = """
        parent
            child
        """;
```

State how many spaces precede `child` after processing and write a verification expression.

**Answer:** four spaces. Verify with:

```java
System.out.println(layout.equals("parent\n    child\n")); // true
```

### Exercise 3: Preserve a trailing space

```java
String line = """
        END\s
        """;
```

Write the last three code points in order and predict `line.length()`.

**Answer:** the last three code points are `U+0044` (D), `U+0020` (space), and `U+000A` (LF). The full string is `"END \\n"` and `length() == 5`.

### Exercise 4: Joining lines with an escape

```java
String text = """
        first\
        second
        """;
```

State whether the string contains one or two lines, and whether there is a space between the two words.

**Answer:** `text.equals("firstsecond\\n")` is `true`. There is no space between the two words; there is only a trailing LF because the `second` line ends before the closing delimiter.

### Exercise 5: Counting `length` and code points

```java
String value = """
        😀""";
```

Predict `value.length()` and `value.codePointCount(0, value.length())`.

**Answer:** `2` and `1` respectively, because an emoji outside the BMP takes one code point but two UTF-16 code units.

### Exercise 6: Write a verification function

Write a method taking `String actual` that checks whether it equals the two lines `key=value` and `done`, with exactly one LF after each line. The method returns `boolean`.

```java
static boolean hasExpectedContent(String actual) {
    return "key=value\ndone\n".equals(actual);
}
```

Then create one text block that satisfies the condition and another text block that differs only in the **trailing LF** to see how `equals` distinguishes data that the console cannot clearly show.

## 13. Completion criteria

Learners have mastered this lesson when they can:

1. Explain that text blocks in Java 17 produce **`String`**, not a new data type.
2. State the three processing steps: normalize newlines, strip incidental whitespace, interpret escapes.
3. Distinguish a closing delimiter on its own line from a closing delimiter immediately after the last character; accurately predict presence or absence of a trailing LF.
4. Explain how common indentation is removed while relative indentation remains.
5. Use `\\s` to preserve trailing spaces and trailing `\\` to join content; distinguish them from `\\n` and `\\t`.
6. Verify Strings via `equals`, `length`, `charAt`, and `codePoints`, avoiding conclusions drawn solely from `println`.
7. Distinguish UTF-16 code units, Unicode code points, and visible characters when strings contain emojis or multi-code-point characters.
8. Compile examples with JDK 17 using `javac --release 17`, without preview syntax.

## 14. Official references

- [OpenJDK JEP 378 — Text Blocks](https://openjdk.org/jeps/378): description of text block processing rules, incidental whitespace, and escape sequences.
- [Java Language Specification SE 17 — Text Blocks (§3.10.6)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.10.6): grammar and specification of text block character values.
- [Java SE 17 API — `String`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): `length`, `charAt`, `codePoints`, `lines`, `stripIndent`, `translateEscapes`, and string manipulation methods.
- [Java SE 17 API — `Character`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html): Java's code point and UTF-16 model.

**Core takeaway:** the multiline appearance of text block source code is only part of the story. What matters is **the character sequence after the three processing steps**. To verify data accurately down to every space, tab, and newline, inspect the `String` itself with equality checks and character APIs rather than trusting source appearance or screen output.
