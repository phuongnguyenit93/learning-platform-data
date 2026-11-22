# String.indent(int): Adjusting Indentation and Normalizing Line Endings in Java

## 1. Lesson Objectives

When assembling multi-line text for log output, content generation, or data presentation, we often want to increase or decrease the number of whitespace characters at the **beginning of each line**. Java provides **String.indent(int n)** (since **Java 12**) to perform this operation while also **normalizing line terminators to LF**.

After this lesson, you will be able to:

- Explain the effects of **n > 0**, **n < 0**, and **n = 0**.
- Accurately predict results with spaces, tabs, blank lines, CR, LF, CRLF, and strings without a newline.
- Distinguish **indent()** from **lines()**, **stripLeading()**, **stripIndent()**, and manual concatenation.
- Avoid common mistakes when processing text from Windows, Unix, text blocks, and fixed-format data.

Key point: **indent() does not merely change leading whitespace**. Calling **indent(0)** can still modify a string because line terminators are normalized and an LF may be appended to the final line.

## 2. Method Signature and General Mechanism

~~~java
public String indent(int n)
~~~

This is a method of **java.lang.String**. Strings are immutable: the method returns a resulting String without modifying the source object.

Conceptually, Java performs the following steps:

1. Splits the input string into lines according to rules similar to **String.lines()**.
2. Adjusts the whitespace characters **at the start of each line** according to the parameter **n**.
3. Joins the adjusted lines, **each followed by LF** (the **\n** character, U+000A).

Rules by parameter:

| Value of n | Effect on each line | Notes |
| --- | --- | --- |
| **n > 0** | Adds exactly **n ASCII spaces U+0020** at the start of the line | Does not add n tabs; applies to blank lines too |
| **n = 0** | Does not change the content of each line | Still normalizes line endings and may add a trailing LF |
| **n < 0** | Removes up to **\|n\| whitespace characters** from the start of each line | If there are fewer than \|n\| whitespace characters, removes all of them; remaining content is kept |
| **Empty string** | Returns an empty string | Does not create a line or newline on its own |

The method processes **each line independently**. It does not find a “common indentation” and remove only the minimum indentation of the whole block. That is an important difference from **stripIndent()**.

## 3. What Counts as a Line and a Line Terminator?

**String.lines()** recognizes the following three types of line terminators:

| Character | Symbol | Common Context |
| --- | --- | --- |
| Line Feed | **\n** (LF, U+000A) | Linux/Unix and many APIs |
| Carriage Return | **\r** (CR, U+000D) | Legacy data or certain sources |
| CR then LF | **\r\n** (CRLF) | Windows text |

**indent()** normalizes all of those line terminators to **\n**.

A line is the sequence of characters **excluding its line terminator**. If the string already ends with a line terminator, **lines() does not create an extra phantom empty line after the final terminator**.

Example:

~~~text
Conceptual input: A\r\nB\rC\n
Lines:            "A", "B", "C"
After indent(0):  A\nB\nC\n
~~~

Two potentially surprising consequences:

- For input **"A"** (no newline character), **"A".indent(0)** returns **"A\n"**.
- For input **"A\n"**, **"A\n".indent(0)** remains **"A\n"**, not turning into **"A\n\n"**.

The string **""** has no lines, so both **"".indent(0)** and **"".indent(2)** return **""**.

**The normalization scope of indent() is limited to the three line terminators above.** Do not assume it recognizes and converts every Unicode character that looks like a line break, such as Unicode line separator U+2028. Do not confuse it with the broader rules of regex **\R**.

## 4. Standalone Java 17+ Example Showing Whitespace Clearly

When using **System.out.println()**, leading whitespace is hard to see and **println()** adds its own newline. The following example converts spaces to **_**, tabs to **<TAB>**, LF to the literal text **\n**, and CR to the literal text **\r** before printing. The underscore is only a **display symbol**, not a character inserted by **indent()** into the real string.

Create the file **IndentDemo.java**:

~~~java
public class IndentDemo {
    private static String visible(String text) {
        return text.replace(" ", "_")
                .replace("\t", "<TAB>")
                .replace("\r", "\\r")
                .replace("\n", "\\n");
    }

    private static void show(String label, String text) {
        System.out.println(label + ": [" + visible(text) + "]");
    }

    public static void main(String[] args) {
        String mixed = "A\r\n  B\rC\n";

        show("origin", mixed);
        show("indent(+2)", mixed.indent(2));
        show("indent(-2)", mixed.indent(-2));
        show("indent(0)", mixed.indent(0));

        show("blank line", "X\n\nY".indent(2));
        show("tab", "  X\n\tY\nZ".indent(-1));
        show("empty", "".indent(2));
        show("one line", "X".indent(0));
    }
}
~~~

Compile and run:

~~~bash
javac IndentDemo.java
java IndentDemo
~~~

Output:

~~~text
origin: [A\r\n__B\rC\n]
indent(+2): [__A\n____B\n__C\n]
indent(-2): [A\nB\nC\n]
indent(0): [A\n__B\nC\n]
blank line: [__X\n__\n__Y\n]
tab: [_X\nY\nZ\n]
empty: []
one line: [X\n]
~~~

Detailed explanation:

1. Input **mixed** consists of three lines. Line **B** already has two leading spaces.
2. **indent(2)** adds two spaces to **every line**, so B ends up with four spaces total. At the same time, both CRLF and CR become LF.
3. **indent(-2)** removes B's two spaces, while A and C have no leading spaces so their text stays unchanged.
4. **indent(0)** keeps the exact two spaces before B while still converting all three line-ending types to LF.
5. For the blank line between X and Y, **indent(2)** still adds two spaces to the blank line, so that line is no longer a length-0 string in terms of character content.
6. **indent(-1)** removes one leading whitespace character: X goes from two spaces down to one, while the tab leading Y is removed completely.
7. An empty string remains empty; the string **"X"** has one line, so an LF is appended at the end after **indent(0)**.

## 5. Positive n: Adding Spaces to the Start of Each Line

When **n > 0**, Java creates exactly **n space characters U+0020** and places them at the start of each line.

~~~java
String data = "first\nsecond";
String result = data.indent(4);

System.out.println(result.equals("    first\n    second\n")); // true
~~~

It does not matter whether a line already has indentation; **indent(4)** does not align lines to an absolute column, but rather **adds 4 more spaces to each line**.

For the string:

~~~text
first
  second
~~~

after **indent(2)**, the relative indentation difference remains two spaces:

~~~text
  first
    second
~~~

Distinguish clearly:

- **indent(2)** increases the indentation of **each line** by two spaces.
- **String.repeat(2)** repeats the **entire string** twice; unrelated to indentation rules.
- Calling **indent(2)** twice typically adds a total of four spaces to every line (for non-empty inputs); the method does not track whether text was “previously indented”.

**Blank lines:** if the input contains a real blank line between two terminators, **indent(n > 0)** also inserts spaces into that blank line:

~~~java
String input = "A\n\nB";
String result = input.indent(2);
System.out.println(result.equals("  A\n  \n  B\n")); // true
~~~

If a system requires blank lines to have exact length 0 or forbids trailing whitespace, consider a different processing step. **indent() does not automatically strip whitespace from blank lines**.

## 6. Negative n: Removing Up to |n| Leading Whitespace Characters Per Line

When **n < 0**, Java removes between 0 and **|n|** whitespace characters from the **beginning of each line**, depending on how many are actually present.

~~~java
String text = "    A\n B\nC";
String result = text.indent(-3);

System.out.println(result.equals(" A\nB\nC\n")); // true
~~~

- Line A has four spaces: three removed, one remains.
- Line B has one space: one removed, none remain.
- Line C has no spaces: nothing removed.

If a line starts with fewer than **|n|** whitespace characters, the method **does not delete into non-whitespace characters**. For example, **" A".indent(-5)** still keeps the letter **A**, followed by LF.

### 6.1. A Tab Counts as One Character, Not a Visual Width

Java uses the **Character.isWhitespace** definition of whitespace when removing negative indentation. The tab character **\t** counts as **one whitespace character**, without expanding to 4 or 8 columns:

~~~java
String source = "\t  A";
System.out.println(source.indent(-1).equals("  A\n")); // true
System.out.println(source.indent(-2).equals(" A\n"));  // true
~~~

The actual visual width of a tab depends on tab stops in the terminal or editor. Therefore, **indent(-2)** means removing at most **two whitespace characters**, not guaranteeing a shift left by two **visual columns**.

Java does not treat only ASCII space as whitespace. Yet not **every Unicode character that looks like a space** satisfies **Character.isWhitespace**. If inputs contain special Unicode characters, verify the character category and desired rules.

### 6.2. indent(-n) Differs from Removing a Common Indentation

Consider three lines:

~~~text
    A
  B
      C
~~~

Using **indent(-2)** removes two whitespace characters from the start of each line, giving:

~~~text
  A
B
    C
~~~

There is no step that analyzes the entire block to infer a “baseline indentation”. If you need to remove **common/incidental indentation**, look at **stripIndent()** instead of assuming **indent(-n)** behaves like it.

## 7. n Equals 0: Why Does the Result Still Change?

**indent(0)** does not alter the characters of each split line, yet **it still rebuilds the string with LF terminating every line**.

~~~java
String input = "red\r\ngreen\rblue";
String output = input.indent(0);

System.out.println(output.equals("red\ngreen\nblue\n")); // true
System.out.println(input.equals(output));               // false
~~~

The input has CRLF, CR, and no final terminator. The output consists of three lines, all ending with LF.

This is useful when you want to convert multi-line text from different platforms into a **uniform LF form** while keeping the leading characters of each line intact.

However, there are two caveats to remember:

- **Adds a trailing LF:** if the input is non-empty and the last line has no terminator, **indent(0)** appends LF. Thus it is not a normalizer that merely replaces CRLF/CR with LF while preserving the exact presence or absence of a trailing newline.
- **Pre-existing blank lines:** real blank lines are still preserved according to **lines()** rules, with LF output terminators. No new phantom blank line is generated *after* the input's final terminator.

Examples of terminator differences:

| Input as Java String literal | Result after **indent(0)** |
| --- | --- |
| **""** | **""** |
| **"A"** | **"A\n"** |
| **"A\n"** | **"A\n"** |
| **"A\r"** | **"A\n"** |
| **"A\r\n"** | **"A\n"** |
| **"A\n\n"** | **"A\n\n"** |
| **"\n"** | **"\n"** |

The table uses **Java String literal notation**: for example, **"A\n"** contains one character A and one LF character, not the two characters backslash and n.

## 8. Blank Lines, Trailing Whitespace, and Edge Cases

### 8.1. indent() Only Modifies the Start of Each Line

**indent() does not trim whitespace at the end of a line's content**:

~~~java
String input = "A  \n B  ";
String out = input.indent(-1);

System.out.println(out.equals("A  \nB  \n")); // true
~~~

The two spaces after A and two spaces after B still remain. If you want to trim trailing whitespace on lines, handle that separately according to business requirements.

### 8.2. Strings with Consecutive Terminators

~~~java
String input = "A\r\n\r\nB";
System.out.println(input.indent(0).equals("A\n\nB\n")); // true
~~~

The first CRLF is one terminator; the next CRLF represents a **real blank line** between A and B. After normalization, one blank line remains in the middle.

### 8.3. Strings Containing Only Spaces

~~~java
String spaces = "   ";
System.out.println(spaces.indent(-2).equals(" \n"));  // true
System.out.println(spaces.indent(-5).equals("\n"));   // true
System.out.println(spaces.indent(2).equals("     \n")); // true
~~~

This is **one line whose content consists solely of whitespace**, not an empty string. The result still has a trailing LF. If your application wants to remove all blank lines, define an explicit rule; **indent() does not filter lines by default**.

### 8.4. Very Large Values of n

Avoid calling **indent(n)** with huge positive values taken directly from user input: character insertion happens **per line**, which can cause memory usage to grow sharply or exceed String/heap limits. The number of added characters is approximately **n × number of lines**.

For **negative n**, the behavior is to remove at most the existing whitespace characters, and it can never delete content characters. Java even handles **Integer.MIN_VALUE** without requiring you to compute **Math.abs(n)** yourself; computing **Math.abs(Integer.MIN_VALUE)** in helper code can cause integer overflow and should be avoided.

## 9. Comparison with Related String Methods

| API | Purpose | Difference Compared to **indent(int)** |
| --- | --- | --- |
| **lines()** (Java 11+) | Returns a Stream of lines, stripping terminators | Does not add/remove indentation or return a joined String |
| **stripLeading()** (Java 11+) | Removes whitespace at the **start of the entire String** | Does not iterate over every line |
| **stripTrailing()** (Java 11+) | Removes whitespace at the **end of the entire String** | Can affect a trailing newline; does not adjust per-line indentation |
| **strip()** (Java 11+) | Removes whitespace at both ends of the entire String | Does not preserve multi-line structure in the same way |
| **stripIndent()** (Java 15+) | Removes common/incidental indentation, handles blank lines and trailing whitespace | Computes minimum indentation across eligible lines; not simply removing n characters per line |
| **repeat(int)** (Java 11+) | Repeats the entire String n times | Does not indent by line |
| **indent(int)** (Java 12+) | Adds or removes up to a specified number of leading whitespace chars on **each line**, normalizes to LF | Takes a count parameter and always reconstructs terminators as LF |

### 9.1. indent(-2) Differs from stripLeading()

~~~java
String input = "  A\n  B";

System.out.println(input.indent(-2).equals("A\nB\n"));   // true
System.out.println(input.stripLeading().equals("A\n  B")); // true
~~~

**stripLeading()** only removes the spaces before A because it operates on the beginning of the **entire string**; the spaces before B follow a newline and remain intact.

### 9.2. indent(-n) Differs from stripIndent()

**stripIndent()** (Java 15+) is designed to handle common/incidental indentation, making it especially suitable for text blocks. It determines the minimum indentation according to its own rules, removes that indentation from eligible lines, and removes trailing whitespace per the method's specification.

Example:

~~~java
String input = "    A\n  B\n      C";
String fixed = input.indent(-2);

System.out.println(fixed.equals("  A\nB\n    C\n")); // true
~~~

In this example, if the goal is to shift the entire block so the least-indented line touches the left margin, **stripIndent()** expresses that goal more naturally. Do not swap the two methods in code without checking blank lines, the last line, trailing whitespace, and line-terminator changes, because their rules differ.

### 9.3. Text Blocks and indent()

Text blocks (Java 15+) strip incidental indentation according to their own compile-time rules when constructing the String value. Afterward, you can still call **indent()** on that value:

~~~java
String message = """
        hello
        world
        """;

System.out.println(message.indent(2).equals("  hello\n  world\n")); // true
~~~

In this example, the original text block already had its common indentation stripped, and then **indent(2)** adds exactly two spaces to each line.

Do not count indentation solely by looking at the text block delimiters in source code: the actual String value after Java applies text-block processing is the input to **indent()**.

## 10. Practical Applications

### 10.1. Indenting Multi-Line Text in Reports

~~~java
String detail = "name: Alice\nrole: developer";
String report = "User:\n" + detail.indent(2);

System.out.print(report);
~~~

Output:

~~~text
User:
  name: Alice
  role: developer
~~~

**print()** is chosen so as not to add an unintended extra newline: **indent(2)** already placed an LF at the end of every line in **detail**.

### 10.2. Normalizing Line Endings from Different Sources

~~~java
String imported = "first\r\nsecond\rthird";
String normalized = imported.indent(0);

System.out.println(normalized.equals("first\nsecond\nthird\n")); // true
~~~

A uniform LF representation is useful when comparing text content line by line or feeding a pipeline that only accepts LF. However, if checksums or file formats require exact byte preservation or distinguishing presence/absence of a trailing LF, **indent(0)** is a meaningful transformation that must be chosen deliberately.

### 10.3. Reducing Indentation in Fixed-Indent Snippets

~~~java
String source = "    GET /users\n    Accept: application/json";
String compact = source.indent(-4);

System.out.println(
        compact.equals("GET /users\nAccept: application/json\n")); // true
~~~

If each line has at least four leading whitespace characters, **indent(-4)** removes up to four characters. If any line has less indentation, it simply removes what is available without throwing an error for missing whitespace.

## 11. Common Mistakes and How to Check

1. **Thinking indent(0) leaves the String unchanged.** It normalizes CR/CRLF to LF and adds a trailing LF for non-empty strings lacking a terminator. Verify with **equals()**, **length()**, or escaped representation.
2. **Assuming negative n removes n visual columns.** A tab counts as one whitespace character, not expanded to tab stops; visual width may differ.
3. **Assuming indent(-n) computes common indentation for the whole block.** It removes at most |n| characters per line independently. When removing incidental indentation, consider **stripIndent()**.
4. **Overlooking blank lines when n is positive.** Blank lines also receive n spaces and may become whitespace-only lines.
5. **Using println() and thinking indent() generated two newlines.** Because the resulting String already ends with LF, **println()** adds another terminator; use **print()** or control newlines when concatenating.
6. **Thinking indent() strips trailing spaces on lines.** It only adjusts the start of lines; whitespace at the end of text remains.
7. **Assuming indent() handles all Unicode line separators.** **String.lines()** line-splitting rules focus on CR, LF, and CRLF. For other data formats, use an appropriate parsing strategy.
8. **Putting indent(0) into a byte-sensitive pipeline without thought.** Converting CRLF to LF and adding a trailing LF alters content; this can change checksums or byte-level comparisons.
9. **Reading a text block as having the exact number of spaces shown in source.** Text blocks already undergo incidental indentation removal; verify the actual String value.
10. **Using unbounded positive n with long inputs.** Risks huge data expansion and high memory cost; constrain input length and parameters according to your problem.

## 12. Quick Self-Check

Predict the outputs, then run the following statements in Java 17+:

~~~java
System.out.println("A".indent(0).equals("A\n"));
System.out.println("A\r\nB".indent(0).equals("A\nB\n"));
System.out.println("  A\n B".indent(-2).equals("A\nB\n"));
System.out.println("A\n\nB".indent(1).equals(" A\n \n B\n"));
System.out.println("\tX".indent(-1).equals("X\n"));
System.out.println("".indent(3).equals(""));
~~~

**All six lines print true.** If any result surprises you, trace:

- How many lines does the string have according to **lines()**?
- How many leading whitespace characters does each line have?
- Does that prefix get **n spaces added** or **up to |n| whitespace characters removed**?
- Finally, is every line terminated with LF?

## 13. Key Takeaways

**String.indent(int n)** is a **line-by-line** operation:

- **Positive n:** adds n spaces at the start of **every line**, including blank lines.
- **Negative n:** removes up to |n| leading whitespace characters per line; a tab counts as one character.
- **n equals 0:** keeps line content unchanged, but still normalizes **CR/CRLF/LF → LF**.
- **Empty input:** empty output; **non-empty input:** result ends with LF after the final line.
- **Trailing whitespace on lines:** is not removed by **indent()**.

When choosing an API, clearly distinguish three needs: **changing indentation by a fixed amount** (**indent**), **removing common block indentation** (**stripIndent**), and **trimming only the start/end of the entire String** (**stripLeading/stripTrailing/strip**).

### Official References

- Java SE 17, **String.indent(int)**, **String.lines()**, and **String.stripIndent()**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html
- Java SE 17, **Character.isWhitespace(int)**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html
