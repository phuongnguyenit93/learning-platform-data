# Text Blocks in Java: Final Line With or Without a Newline Character

When using a **text block** in Java, the final newline character may or may not be part of the String value. This single-character difference affects string comparison, file output, payload generation, and testing. This lesson focuses on how to decide whether **the final line has or does not have a newline character** using the closing delimiter position and text block escapes in Java 17+.

## 1. Syntax and the meaning of newlines

A text block starts with three consecutive double quotes (**"""**) followed by a mandatory line terminator, contains multiline content, and ends with **"""**:

~~~java
String text = """
        first
        second
        """;
~~~

In this example, the String has content equivalent to:

~~~java
String text = "first\nsecond\n";
~~~

The newline right after the **opening delimiter** of the text block serves to start the content and **does not appear** at the start of the String value. Conversely, the newline after the last content line may be kept depending on where the closing delimiter is placed.

Key rules:

- If **the closing delimiter is on its own line below the last line**, the newline character between the final content and the closing delimiter belongs to the String.
- If **the closing delimiter is immediately after the last character of the content** on the same line, no trailing newline is created by the closing delimiter.
- Newlines between two content lines are preserved.
- Inside text blocks, Java normalizes source line terminators to LF (**\n**, U+000A), even when the source file is saved with CRLF.
- Text blocks still go through incidental indentation stripping; keep alignment consistent when comparing two variants.

Text blocks have been officially supported since Java 15, so Java 17 and later can compile the following examples without enabling preview features.

## 2. Placing the closing delimiter on its own line: with trailing LF

~~~java
String withFinalLf = """
        first
        second
        """;
~~~

There are **two LF characters**: one between **first** and **second**, and one after **second**. The exact value is:

~~~text
first\nsecond\n
~~~

This illustrative line uses two visible characters **\** and **n** to represent **each LF**; in the actual String, each LF is only **one** character.

~~~java
withFinalLf.equals("first\nsecond\n"); // true
withFinalLf.endsWith("\n");             // true
withFinalLf.length();                   // 13
~~~

Since **first** has 5 characters, **second** has 6 characters, and there are two LFs, the total length is 13.

## 3. Placing the closing delimiter directly after the final content: without trailing LF

~~~java
String withoutFinalLf = """
        first
        second""";
~~~

Here the closing delimiter sits immediately after **second**, so the value is:

~~~text
first\nsecond
~~~

Verification:

~~~java
withoutFinalLf.equals("first\nsecond"); // true
withoutFinalLf.endsWith("\n");           // false
withoutFinalLf.length();                 // 12
~~~

The two Strings above share the same words and the same LF **between** the two lines, yet they are not equal because the first variable has an extra LF after the second line.

| Syntax | Equivalent String | Trailing LF? |
| --- | --- | --- |
| Closing delimiter on its own line after the final line | **"first\nsecond\n"** | Yes |
| Closing delimiter flush against the last content character | **"first\nsecond"** | No |

**Note:** Moving the closing delimiter to a different line can also affect indentation-stripping rules if lines are not aligned consistently. The examples in this lesson use identical content indentation so that the only difference is a single trailing LF.

## 4. Complete Java 17+ example

Save as **TextBlockFinalNewlineDemo.java**:

~~~java
public class TextBlockFinalNewlineDemo {
    public static void main(String[] args) {
        String withLF = """
                first
                second
                """;

        String withoutLF = """
                first
                second""";

        // The '\' line continuation removes the LF at the end of the second line.
        String continued = """
                first
                second\
                """;

        // The '\n' escape explicitly adds an LF after second.
        String explicitLF = """
                first
                second\n""";

        show("withLF", withLF);
        show("withoutLF", withoutLF);
        show("continued", continued);
        show("explicitLF", explicitLF);

        System.out.println("withLF equals explicitLF: "
                + withLF.equals(explicitLF));
        System.out.println("withoutLF equals continued: "
                + withoutLF.equals(continued));
    }

    private static void show(String label, String value) {
        String visible = value.replace("\n", "\\n");
        System.out.printf("%s: [%s], length=%d, endsWithLF=%b%n",
                label, visible, value.length(), value.endsWith("\n"));
    }
}
~~~

Compile and run:

~~~bash
javac TextBlockFinalNewlineDemo.java
java TextBlockFinalNewlineDemo
~~~

Stdout:

~~~text
withLF: [first\nsecond\n], length=13, endsWithLF=true
withoutLF: [first\nsecond], length=12, endsWithLF=false
continued: [first\nsecond], length=12, endsWithLF=false
explicitLF: [first\nsecond\n], length=13, endsWithLF=true
withLF equals explicitLF: true
withoutLF equals continued: true
~~~

The **show** method converts LF in the value to the two visible characters **\n** for easier inspection and prints both **length** and **endsWith**. The **%n** in **printf** is the console output newline for printing, **not** a newline inside the String being inspected.

## 5. Three ways to explicitly control the trailing newline

### 5.1. Changing the closing delimiter position

With trailing LF:

~~~java
String sql = """
        SELECT id
        FROM users
        """;
~~~

Without trailing LF:

~~~java
String sql = """
        SELECT id
        FROM users""";
~~~

This is the most direct way for a reader to recognize your intent. In cases where placing the closing delimiter right after the final line hurts readability, you can use a line-continuation escape.

### 5.2. Line continuation escape: backslash at the end of a line

Inside a text block, a **\** placed **at the very end of a line** removes the newline character of that line:

~~~java
String text = """
        alpha
        omega\
        """;

// Equals "alpha\nomega" — no trailing LF.
~~~

This lets you keep the closing delimiter on its own line while still omitting the trailing LF. **Do not insert spaces after the \** because line continuation requires the backslash to sit right against the actual newline character. Editors that automatically append trailing spaces can alter the intended behavior.

Line continuation can also be used between content lines to join them without generating an LF at the join point; in that case, remember to account for indentation and spaces.

### 5.3. Explicit LF escape

If you want the closing delimiter right against the content while still having a trailing LF, add the **\n** escape:

~~~java
String text = """
        alpha
        omega\n""";

// Equals "alpha\nomega\n" — has trailing LF.
~~~

Java's **\n** escape represents exactly one LF character. It is not the literal pair of characters backslash and letter n.

You can choose based on the codebase's style conventions. The essential point is that the intended outcome is clear and verified by tests when exact character matching is required.

## 6. Trailing LF, trailing blank line, and trailing spaces are different

Consider three strings:

~~~java
String a = "alpha";
String b = "alpha\n";
String c = "alpha\n\n";
~~~

- **a** has no LF.
- **b** has one LF right after **alpha**.
- **c** has two consecutive LFs after **alpha**, meaning there is an extra blank line after the content line.

Representing b and c with text blocks:

~~~java
String b = """
        alpha
        """;

String c = """
        alpha

        """;
~~~

The completely blank line before the closing delimiter in example c gives the value an extra LF. When data must match exactly, do not arbitrarily delete a trailing blank line just because it contains no text.

**Spaces before an LF** are also different data from **an LF** alone. Java processes indentation and trailing whitespace on lines while creating a text block. If you want to explicitly preserve a space before an LF, you can use the **\s** (space) escape in the text block:

~~~java
String text = """
        alpha\s
        beta
        """;

// Result equivalent to "alpha \nbeta\n".
~~~

Here **\s** is a **Java escape** that produces a space; do not confuse it with the regex pattern **\\s** inside a Java String.

## 7. Why can `println` be misleading?

Calling **System.out.print(text)** prints the exact data as is; **System.out.println(text)** also appends a line terminator for the print call itself, depending on the platform. If `text` already ends with an LF, using `println` sends two consecutive line breaks to the console:

~~~java
String text = """
        hello
        """;

System.out.print(text);    // Prints "hello" and the LF already inside text.
System.out.println(text); // Prints text and then appends println's newline.
~~~

Therefore, merely looking at the console screen is not enough to conclude whether a string ends with an LF. Print **length()**, **endsWith("\n")**, or replace LF characters with two visible characters via **replace("\n", "\\n")**.

When writing text files, sending request bodies, computing checksums, verifying digital signatures, or comparing snapshots, a single trailing LF changes the payload at the byte level. For formats with strict requirements, choose and consistently maintain a newline convention.

## 8. Tests and line-processing APIs can easily hide a trailing LF

Two strings share the same content lines yet differ in their trailing newline:

~~~java
String expected = "one\ntwo";
String actual = """
        one
        two
        """;

System.out.println(expected.equals(actual)); // false
System.out.println(actual.endsWith("\n"));     // true
System.out.println(actual.length());          // 8
~~~

When you need to detect the difference, do not rely solely on line counts:

~~~java
String withLF = "one\ntwo\n";
String withoutLF = "one\ntwo";

System.out.println(withLF.lines().count());        // 2
System.out.println(withoutLF.lines().count());     // 2
System.out.println(withLF.split("\n").length);     // 2
System.out.println(withLF.split("\n", -1).length); // 3
~~~

**String.lines()** does not emit a trailing empty line merely because the String ends with a newline; **split** also discards trailing empty elements by default. Pass **-1** to `split` to retain the trailing empty string. To check directly for a trailing LF, the simplest approach remains **endsWith("\n")**.

Example testing exact expected content:

~~~java
String expected = "line 1\nline 2\n";
String actual = """
        line 1
        line 2
        """;

if (!expected.equals(actual)) {
    throw new AssertionError("Text block does not match exactly");
}
~~~

The snippet above illustrates an assertion condition that can be placed inside a Java method; only the program in section 4 is a standalone complete class example.

## 9. Removing exactly one trailing LF after creating a String

When you need to remove **only a single trailing LF**, you can use the String API without affecting other trailing characters:

~~~java
String raw = """
        first
        second
        """;

String withoutOneFinalLF = raw.endsWith("\n")
        ? raw.substring(0, raw.length() - 1)
        : raw;

// withoutOneFinalLF equals "first\nsecond".
~~~

Do not use **stripTrailing()** or **strip()** for this requirement when other whitespace must be preserved, because those methods remove **multiple whitespace characters**:

~~~java
String raw = "alpha  \n";

String onlyLfRemoved = raw.substring(0, raw.length() - 1);
// "alpha  " — the two trailing spaces are kept.

String stripped = raw.stripTrailing();
// "alpha" — removes both the two spaces and the LF.
~~~

If the data comes from outside a text block and contains CRLF, determine the newline convention before stripping; the example above is written for LF-normalized text block data.

## 10. Common mistakes and how to handle them

| Symptom | Cause | Solution |
| --- | --- | --- |
| Strings compare unequal even though console looks identical | One has a trailing LF and the other does not | Compare **length**, **endsWith**, and escaped contents |
| Extra blank line appears when printing | Using **println** with a String that already has a trailing LF | Use **print** if you need to print exact content |
| Text block lacks a trailing LF | Closing delimiter is placed flush against the last content character | Move the closing delimiter to its own line or add **\n** |
| Text block has an unexpected trailing LF | Closing delimiter sits on its own line below | Place the closing delimiter against the content or use line continuation **\** |
| Line counts still look identical | **lines()** and default **split** do not preserve trailing LF markers | Check **endsWith("\n")** |
| Leading spaces added or removed across lines | Moving the closing delimiter changes incidental indentation | Align consistently and inspect the actual String |
| More whitespace removed than expected | Using **stripTrailing()** to remove one LF | Remove a single character after checking **endsWith** |

## 11. Self-check

Predict the length and trailing character of the two strings:

~~~java
String x = """
        A
        B
        """;

String y = """
        A
        B""";
~~~

Answers:

- **x** equals **"A\nB\n"**, length **4**, **endsWith("\n")** is **true**.
- **y** equals **"A\nB"**, length **3**, **endsWith("\n")** is **false**.
- **x.equals(y)** is **false** because only `x` has a trailing LF.

When designing a text block, decide first **whether the data must end with an LF or not**, then place the closing **"""** or use escapes accordingly. The trailing LF is part of the String data, not just Java code layout.
