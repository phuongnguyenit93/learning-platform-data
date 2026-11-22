# Line Ending Normalization in Java Text Blocks

## 1. The problem: source code with CR, LF, or CRLF

A **text block** is Java's multiline string syntax (standard since Java 15), opened and closed with three double quotes `"""`. The contents of a `.java` file can use different line-ending styles:

| Name | Symbol | Unicode Code | Escape in Java Strings |
| --- | --- | --- | --- |
| Line Feed | LF | U+000A | `\n` |
| Carriage Return | CR | U+000D | `\r` |
| Carriage Return + Line Feed | CRLF | U+000D U+000A | `\r\n` |

Some editors save code with CRLF, while others save with LF. When using a text block, you usually want the same string value regardless of whether the source file was formatted on Windows or Linux.

**Core rule:** Java normalizes all **physical line terminators inside the source code content of a text block** to **LF (`\n`)** at compile time. Specifically:

- A CRLF in source is converted to **one** LF.
- A lone CR in source is converted to LF.
- An LF in source is kept as is.

Therefore, the same text block with only its physical line endings changed in source yields the exact same string value. This **does not mean every `String` in Java is automatically normalized**: strings read from files, sockets, or databases still keep their existing line endings unless the application processes them further.

## 2. In what order does Java process a text block?

According to the *Java Language Specification* (JLS §3.10.6), text block content is converted into a string in three stages, in this exact order:

1. **Normalize line terminators:** CRLF → LF, CR → LF; LF stays unchanged.
2. **Strip incidental whitespace:** remove incidental indentation and trailing whitespace per line according to rules equivalent to `String.stripIndent()`.
3. **Interpret escapes:** process `\n`, `\r`, `\t`, `\s`, `\\`, and line-continuation escapes with `\`, according to rules equivalent to `String.translateEscapes()`.

```text
Text block in source file
            |
            v
Normalize CRLF and CR to LF
            |
            v
Process incidental whitespace
            |
            v
Interpret escape sequences
            |
            v
String value at runtime
```

Why does this order matter? A CR that appears **literally in the source file** belongs to step 1 and is converted to LF. However, when you write the escape `\r` using two characters—backslash and the letter `r`—the CR character is only **produced in step 3**. By then normalization has already finished, so this CR remains in the `String` value.

Two concepts to distinguish clearly:

- **Physical line terminator:** the actual newline characters between lines of text in the source code file.
- **Escape sequence:** writing `\n` or `\r` in Java syntax; the compiler only interprets them into control characters during the escape-interpretation stage.

Do not treat `\r\n` written via escapes as a physical CRLF in the source file.

## 3. Text block values across three source line-ending styles

Java example:

```java
String colors = """
    red
    green
    blue
    """;
```

Whether the file containing this example is saved with LF, CRLF, or CR for the lines inside the text block, the final value is still equivalent to:

```java
String colors = "red\n" + "green\n" + "blue\n";
```

The `colors` string has **15 characters**, consisting of three LFs and zero CRs.

You can visualize the same source under the three representations below. The symbols `␍` denote CR and `␊` denote LF; these are illustrative notations, not characters to type into the program:

```text
Source saved with LF:
"""␊
    red␊
    blue␊
    """

Source saved with CRLF:
"""␍␊
    red␍␊
    blue␍␊
    """

Source mixing CR and LF:
"""␍
    red␍
    blue␊
    """
```

All three variants represent `"red\nblue\n"` after normalization and indentation processing. CRLF does not create two LF characters because the pair is treated as a single line terminator.

### Leading and trailing newlines

Text block opening syntax requires a line terminator immediately after `"""`. The mandatory newline after the opening delimiter **is not the first character of the string**. However, the newline before the closing delimiter is kept if the closing delimiter is placed on its own line:

```java
String hasFinal = """
    red
    green
    """;

String noFinal = """
    red
    green""";

// hasFinal.equals("red\ngreen\n") == true
// noFinal.equals("red\ngreen") == true
```

If you need a string that does not end with LF, placing the closing delimiter as in `noFinal` is a clear choice. Do not confuse this change with changing the CRLF/LF style of the source file.

## 4. Escapes produce CR or CRLF after the normalization step

Text blocks still support Java string escapes. Because they are interpreted in the final stage, you can explicitly produce CR or CRLF:

```java
String withCr = """
    A\rB
    """;

String withCrLf = """
    A\r\nB
    """;

String withLf = """
    A\nB
    """;
```

With the closing delimiter on its own line, the corresponding values are:

| Variable | Runtime value, written as a Java literal | Explanation |
| --- | --- | --- |
| `withCr` | `"A\rB\n"` | `\r` produces CR; the trailing LF comes from the physical line |
| `withCrLf` | `"A\r\nB\n"` | Two escapes produce one CR and one LF; plus trailing LF |
| `withLf` | `"A\nB\n"` | `\n` produces LF; plus trailing LF |

Here, `withCrLf` contains a real CRLF even though the source code may be saved with LF. Physical line-ending normalization **does not remove a CR created by an escape**.

Another syntax easily confused here is `\` at the end of a physical line, commonly called a *line continuation escape*:

```java
String joined = """
    hello\
    world
    """;

// joined.equals("helloworld\n") == true
```

A `\` immediately before a physical newline causes that newline **not to appear** in the `String` value. By contrast, `\n` written on the same line is an escape that **creates** an LF. Text block whitespace rules can still affect spaces placed next to a line continuation.

## 5. Self-contained, verifiable Java 17+ program

Save the following snippet in **`TextBlockLineEndingsDemo.java`**:

```java
public class TextBlockLineEndingsDemo {

    private static String visible(String value) {
        return value.replace("\\", "\\\\")
                    .replace("\r", "\\r")
                    .replace("\n", "\\n");
    }

    private static void show(String name, String value) {
        System.out.println(name + " = " + visible(value));
    }

    public static void main(String[] args) {
        String basic = """
            alpha
            beta
            """;

        String noFinal = """
            alpha
            beta""";

        String escapedCr = """
            A\rB
            """;

        String escapedCrLf = """
            A\r\nB
            """;

        String joined = """
            alpha\
            beta
            """;

        show("basic", basic);
        show("noFinal", noFinal);
        show("escapedCr", escapedCr);
        show("escapedCrLf", escapedCrLf);
        show("joined", joined);

        System.out.println("basic has CR = " + (basic.indexOf('\r') >= 0));
        System.out.println("basic equals literal = "
                + basic.equals("alpha\nbeta\n"));
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 TextBlockLineEndingsDemo.java
java TextBlockLineEndingsDemo
```

Exact output:

```text
basic = alpha\nbeta\n
noFinal = alpha\nbeta
escapedCr = A\rB\n
escapedCrLf = A\r\nB\n
joined = alphabeta\n
basic has CR = false
basic equals literal = true
```

In the output above, `\r` and `\n` are **visible characters** substituted by `visible`; they let you observe differences that are otherwise hard to see in a terminal. The `visible` method does not mutate the original string value.

To test cross-platform stability, run the program, then use an editor to switch the source file's line endings from LF to CRLF (or vice versa), recompile, and run it again. If only the file's physical line endings change, the output will not change.

### Why not use only println to inspect?

If you print `basic` or `escapedCrLf` directly, terminals often display LF and CRLF almost identically. When you need to verify the **actual characters**, use one of the following approaches:

- `equals("alpha\nbeta\n")` for an exact comparison.
- `indexOf('\r')` or `indexOf('\n')` to search for characters.
- `length()`, `charAt()`, or iterating over code points when inspecting structure.
- Converting control characters into visible markers like the `visible` method above.

## 6. When should you explicitly convert LF to CRLF?

Text blocks produce consistent LFs. Software may need to convert them to another form **for output requirements**, such as a protocol or file format specifying CRLF. That is a separate runtime operation:

```java
String content = """
    first
    second
    """;

String crlf = content.replace("\n", "\r\n");
System.out.println(crlf.equals("first\r\nsecond\r\n")); // true
```

The snippet above works when **the input contains only LF**. If the original string already has CRLF from escapes or concatenation with other data, replacing every LF like that turns `\r\n` into `\r\r\n`. Do not apply this conversion blindly to strings of unknown state.

If the destination requires line endings matching the **current operating system** rather than a fixed form:

```java
String nativeText = content.replace("\n", System.lineSeparator());
```

`System.lineSeparator()` on Windows is typically CRLF; on many Unix systems it is LF. This is a runtime choice and does not alter text block normalization rules. If a protocol specification mandates CRLF regardless of the host machine, `"\r\n"` is clearer than `System.lineSeparator()`.

When writing files, `Files.writeString(path, content, StandardCharsets.UTF_8)` writes out the exact line terminators **already present in `content`**. The file-writing API does not automatically convert LFs produced by a text block into OS-specific CRLFs.

## 7. Compile-time normalization vs. runtime normalization

`String` objects can come from many sources. Only text block literals in Java source code are processed by the compiler according to the three steps above.

| Source / mechanism | Timing | Rule for CR/LF |
| --- | --- | --- |
| Text block literal `"""..."""` | Compile time | Normalizes **physical** line terminators to LF |
| Regular string literal `"a\r\nb"` | Compile time | Escapes produce CR and LF; does not go through text block content normalization |
| `String.stripIndent()` | Runtime | Strips incidental indentation; not a command that automatically converts all CRLFs to LF in arbitrary input |
| `String.translateEscapes()` | Runtime | Interprets escapes; can produce CR and LF |
| `String.lines()` | Runtime | Splits lines on CR, LF, CRLF; the resulting stream does not retain line terminators |
| `System.lineSeparator()` | Runtime | Provides the platform's line separator, does not modify text blocks |
| `String.replace(...)` | Runtime | Replaces characters/substrings according to programmed rules |

For example, external data can contain CRLF/CR even if your text blocks contain only LF:

```java
String received = "a\r\nb\rc\n";
String lfOnly = received.replace("\r\n", "\n").replace("\r", "\n");

System.out.println(lfOnly.equals("a\nb\nc\n")); // true
```

Here the application performs **runtime normalization**, independent of the text block mechanism. Replacing `"\r\n"` first and then `"\r"` handles both CRLF and lone CR.

## 8. Common mistakes

1. **Assuming a Java file saved with CRLF creates a text block containing CRLF.** In reality, physical CRLFs are converted to LF in the first step.
2. **Assuming a text block cannot contain CR.** The `\r` escape can produce CR after the normalization step.
3. **Confusing the mandatory newline after the opening delimiter with a trailing newline.** The newline after the opening `"""` is syntax; the trailing newline depends on whether the closing delimiter is on the same line as the last content or on its own line.
4. **Confusing `\n` with the line-continuation `\` escape.** `\n` adds an LF; `\` immediately before a physical newline removes that newline.
5. **Forgetting incidental indentation.** After normalizing line terminators, Java also strips leading and trailing whitespace according to text block rules; the result does not depend solely on newlines.
6. **Using `println` to prove newline values.** The console can make CRLF and LF look identical; verify using `equals` or by encoding characters into readable symbols.
7. **Converting LF to CRLF when the string already contains CRLF.** Unchecked replacement can produce `\r\r\n`.
8. **Depending on the OS without a clear requirement.** Text block LFs are designed to be consistent across platforms; only convert when the output format specifically requires it.

## 9. Self-check

**Question 1:** A Java file has the following text block and is saved with CRLF. What is the value of `s`?

```java
String s = """
    A
    B
    """;
```

**Answer:** `"A\nB\n"`; physical CRLF line terminators are normalized to LF. The value contains no CR.

**Question 2:** How many CRs and LFs does the following text block contain?

```java
String s = """
    A\r\nB
    """;
```

**Answer:** **One CR and two LFs**. The `\r\n` escape pair creates CRLF, and the physical newline at the end of the text block creates an additional LF. `s.equals("A\r\nB\n")` is `true`.

**Question 3:** Why should you not unconditionally use `System.lineSeparator()` when writing a protocol that requires CRLF?

**Answer:** Because the value returned by `System.lineSeparator()` depends on the runtime environment. A protocol requiring fixed CRLF must explicitly generate `"\r\n"` regardless of the operating system.

**Question 4:** Why does changing source code from CRLF to LF not change a text block `String`, whereas changing `"\r\n"` to `"\n"` in an escape can change it?

**Answer:** The first case changes **physical** line endings that are normalized at compile time. The second case changes an **escape sequence** interpreted in the final stage, which alters the actual characters in the string.

## References

- [Java Language Specification, Java SE 21 — §3.10.6 Text Blocks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-3.html#jls-3.10.6): order of line terminator normalization, incidental whitespace processing, and escape translation.
- [Oracle Programmer's Guide to Text Blocks, Java SE 21](https://docs.oracle.com/en/java/javase/21/text-blocks/index.html): practical guide, CR/LF/CRLF examples, trailing newlines, and platform-dependent line-ending conversion.

The examples apply to Java 17 and later; text blocks became a standard language feature in Java 15.