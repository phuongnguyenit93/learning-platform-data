# Opening and Closing Triple-Quote Delimiter Rules in Java Text Blocks

A **text block** is a way to declare a multiline `String` value in Java using a pair of **triple double-quote** delimiters `"""`. This syntax lets you place HTML, JSON, SQL, or long paragraphs directly into source code without concatenating multiple strings and repeatedly writing `\n`. Text blocks have been an official feature since **Java 15**; the runnable programs below use Java 17 or later.

A key point to remember from the start: the **opening** delimiter has a mandatory newline rule; the **closing** delimiter is more flexible. The position of the closing delimiter affects both the **trailing newline** and how Java **strips excess leading indentation**. We need to distinguish characters written in *source code* from the actual `String` value produced.

## 1. Structure of a text block

A text block has the form:

~~~java
String message = """
    First line
    Second line
    """;
~~~

The three parts are:

1. **Opening delimiter `"""`**: exactly three double quotes, optionally followed by horizontal whitespace, then **a mandatory line terminator**.
2. **Content body**: begins **immediately after** the opening delimiter's line terminator; can contain multiple lines, single `"` characters, and valid escapes.
3. **Closing delimiter `"""`**: three double quotes ending the content, not required to be on its own line. The `;` in the example terminates the Java statement and is **not** part of the text block.

According to Java syntax, the opening delimiter consists of `"""`, **zero or more** space, tab, or form feed characters, and then a line terminator (`LF`, `CR`, or `CRLF`). The horizontal whitespace right after the opening delimiter and the mandatory newline of the opening delimiter **do not belong to the string content**. A text block can represent a single-line value or an empty string, yet **the opening delimiter in source code must still be followed by a line break**.

### Valid and invalid examples

**Valid:**

~~~java
// Valid: content starts on the line after the opening delimiter.
String greeting = """
    Hello!
    """;

// Valid: closing delimiter can be at the end of the last content line.
String shortText = """
    Hello!""";

// Valid: no content characters between the opening and closing delimiters.
String empty = """
    """;
~~~

**Invalid; the following examples only illustrate syntax errors and will not compile:**

~~~java
// Invalid: missing line break immediately after the opening delimiter.
String invalid1 = """Hello!""";

// Invalid: content appears on the same line as the opening delimiter.
String invalid2 = """First line
    Second line
    """;

// Invalid: only two double quotes used to open, forming a broken regular string.
String invalid3 = ""
    Hello
    """;
~~~

Place the opening `"""` at the end of the declaration line, add a line break, and then write the content. Although the language allows whitespace after the opening `"""`, the most readable style is **not to add invisible spaces on the opening line**.

## 2. Closing delimiter rules and the trailing newline

The **closing** `"""` has two common positions, and they produce **two different values**.

### Case A: closing delimiter on its own line

~~~java
String withNewline = """
    red
    green
    """;
~~~

The value after Java processes it is equivalent to the traditional string `"red\ngreen\n"`.

- The `red` line ends with `\n`.
- The `green` line also ends with `\n` because in source code **there is a line break before the closing delimiter**.
- The closing delimiter itself **does not generate a newline**; the final newline comes from the content line before the closing delimiter.

### Case B: closing delimiter immediately after the last content character

~~~java
String withoutNewline = """
    red
    green""";
~~~

The value is equivalent to `"red\ngreen"`, **without** a trailing `\n`. The content still has two lines even though the closing delimiter is at the end of the `green` line. Similarly:

~~~java
String oneLine = """
    hello""";
~~~

The value is exactly `"hello"`. In terms of **value**, this string has only one line; in terms of **syntax**, the line break immediately after the opening `"""` is still mandatory.

### Runnable program: inspecting exact newlines

~~~java
// TextBlockDelimitersDemo.java
public class TextBlockDelimitersDemo {
    static String visible(String value) {
        if (value.isEmpty()) {
            return "(empty)";
        }
        return value.replace("\n", "\\n");
    }

    public static void main(String[] args) {
        String withNewline = """
            red
            green
            """;

        String withoutNewline = """
            red
            green""";

        String oneLine = """
            hello""";

        String empty = """
            """;

        System.out.println("with = [" + visible(withNewline) + "]");
        System.out.println("without = [" + visible(withoutNewline) + "]");
        System.out.println("one = [" + visible(oneLine) + "]");
        System.out.println("empty = [" + visible(empty) + "]");
    }
}
~~~

Save as `TextBlockDelimitersDemo.java`, run:

~~~bash
javac --release 17 TextBlockDelimitersDemo.java
java TextBlockDelimitersDemo
~~~

**Exact output** (the characters `\` and `n` in the output represent **one** newline converted by `visible()` into two easy-to-see characters):

~~~text
with = [red\ngreen\n]
without = [red\ngreen]
one = [hello]
empty = [(empty)]
~~~

You should not rely solely on `System.out.println(withNewline)` to infer whether a trailing `\n` is present: `println` itself adds a newline when printing. Use `equals(...)`, `length()`, or an escape-display helper as above to check accurately.

## 3. Where can the closing delimiter be placed?

The following table assumes the opening delimiter is on the line before the content and that indentation is processed by Java according to the rules:

| Placement of closing `"""` | Valid? | Main consequence |
| --- | --- | --- |
| On its own line after the last content line | Yes | Usually includes `\n` at the end of the value; the closing delimiter's column participates in determining indentation |
| Immediately after the last character of the content line | Yes | No trailing `\n`, unless explicitly created by an escape in the content |
| After spaces on the last content line | Yes | Spaces before the closing delimiter are in the source; the result also depends on trailing-whitespace stripping rules |
| At the start of its own line, flush with the left margin | Yes | Can preserve leading spaces on content lines |
| Inside the content without escaping, forming three consecutive quotes | Ends the text block early | Subsequent code may cause syntax errors or the string may be truncated unexpectedly |

**The closing delimiter is three consecutive `"` characters**; no whitespace may be inserted between them. Java does not require the opening and closing delimiters to align in the same column. In practice, a readable style puts the opening delimiter at the end of the declaration line, the content below it, and the closing delimiter on its own line aligned with the content margin; when you need to omit the trailing `\n`, consider placing the closing delimiter right against the end of the content.

Example of a closing delimiter after a real space:

~~~java
String value = """
    Hi """; // There is one space immediately before the closing triple quotes.
~~~

Whitespace before the closing delimiter on the last content line is part of the source data; however, trailing spaces on lines are easily removed by formatters or editors. If you need to preserve whitespace precisely, use the `\s` escape as shown in section 5.

## 4. Closing delimiter position controls indentation

When the closing delimiter stands **on its own line**, the number of spaces before it participates in computing the common indentation alongside non-blank content lines. Therefore, shifting the closing delimiter to the left can increase the spaces kept at the start of the string. For example:

~~~java
String aligned = """
        alpha
          beta
        """;
String preservedIndent = """
        alpha
          beta
    """;
System.out.println(aligned.equals("alpha\n  beta\n")); // true
System.out.println(preservedIndent.equals("    alpha\n      beta\n")); // true
~~~

In the first variable, the common indentation is eight spaces; in the second variable, the closing delimiter is only indented four spaces, so each line retains an extra four spaces. When the closing delimiter is right against the end of the last content line, there is no separate closing-delimiter line acting as an indentation reference. The lesson **Incidental indentation whitespace and closing delimiter position** dives deeper into the algorithm, remaining spaces, tabs, and verification cases.

## 5. Content with double quotes and triple double quotes

Inside a text block, single `"` and pairs `""` **normally do not need escaping**. For example:

~~~java
String json = """
    {"name": "Lan", "active": true}
    """;
~~~

The string value contains the JSON above followed by a trailing `\n`. This is just a `String`: the Java compiler **does not parse or validate JSON**.

By contrast, **three consecutive double quotes inside the content** can be interpreted as **the closing delimiter**. To represent them as data, escape at least one `"` using `\"`, or escape all three for clarity:

~~~java
String literalTripleQuotes = """
    \"\"\"
    """;
~~~

The resulting value is **three double quotes** followed by `\n`. The `\` characters in front of `"` are only source-code escape syntax and **do not appear in the result**.

For example, when you need to preserve a Java snippet containing triple double quotes, you must place an escape right where it could prematurely terminate the text block. Do not work around this by inserting fake spaces between the three quotes if the output data requires them to be adjacent.

## 6. Newlines, trailing spaces, and escapes around the closing delimiter

Before producing the `String` value, Java normalizes line terminators in a text block to `\n`, removes incidental indentation and trailing whitespace on lines, and only then processes escapes. Several useful escapes:

| Syntax in text block content | Effect |
| --- | --- |
| `\n` | Explicitly inserts an LF character |
| `\t` | Inserts a tab |
| `\s` | Inserts a single space, often used to **preserve trailing whitespace on a line** |
| `\\` | Inserts a single backslash |
| `\"` | Inserts a double quote, needed to avoid closing triple double quotes |
| `\` immediately before a line terminator | **Line continuation**: omits that line terminator from the result |

Example using `\` at the end of a line to join two content lines:

~~~java
String joined = """
    first\
    second""";
~~~

The value equals `"firstsecond"`: `\` at the end of the line removes the physical newline between the two parts, and the closing delimiter is right after `second` so there is no trailing `\n`.

Example preserving a space at the end of a line with `\s`:

~~~java
String withTrailingSpace = """
    A\s
    B""";
~~~

The value is equivalent to `"A \nB"`: after `A` there is **one space**, then a newline, then `B`. Invisible whitespace typed with the spacebar right before a line break can be stripped during text block processing; the `\s` escape expresses the intent more reliably.

If you want to ensure the result has **no** trailing newline, you can close right against the content as in section 2, or use a line-continuation escape before a closing delimiter on its own line when that layout is easier to read:

~~~java
String noFinalNewline = """
    red
    green\
    """;
~~~

The value equals `"red\ngreen"`. These forms are helpful when a downstream SQL/JSON/template consumer is sensitive to exact newline characters.

## 7. Practical rules: choosing where to place the closing delimiter

**Prefer placing the closing delimiter on its own line** if the string is a document, SQL query, or multiline HTML block where a trailing `\n` causes no issue. Keep the closing delimiter's indentation aligned with where the content begins, after considering the desired indentation. This style is easy to read and easy to add lines to.

**Close immediately after the last character of content** when you want to omit the trailing `\n` visually, such as for a single-line value or short snippet. Keep in mind that this choice can affect indentation when the content has multiple lines.

**Do not move the closing delimiter arbitrarily when formatting code.** The visual layout of a text block can alter its data when the closing delimiter changes columns, unlike ordinary re-indenting of regular Java expressions. For strings where whitespace is significant (snapshots, text protocols, test fixtures), assert the value by comparing directly:

~~~java
String expected = "red\ngreen\n";
String actual = """
    red
    green
    """;
System.out.println(expected.equals(actual)); // true
~~~

Here `equals` catches even differences invisible in an IDE; the expected output is `true`.

## 8. Common mistakes

1. **Placing text immediately after the opening `"""`**: `"""hello` is invalid. The opening delimiter must end with a line terminator before the content.
2. **Mistaking the opening newline for a leading `\n` in the string**: the newline right after the opening delimiter is part of the **delimiter**, not data. The string does not automatically begin with a blank line.
3. **Thinking the closing delimiter must always be on its own line**: the closing delimiter is allowed right against the end of the content; this is commonly used to omit the trailing `\n`.
4. **Thinking the closing delimiter creates `\n` by itself**: the trailing newline comes from the content immediately preceding the closing delimiter. Changing where the closing delimiter sits can make it disappear.
5. **Re-aligning the closing delimiter without checking the data**: the column of a standalone closing delimiter can dictate how much indentation is stripped; the resulting content changes even though the words stay the same.
6. **Putting literal `"""` into data**: three unescaped double quotes can close the text block prematurely. Escape at least one double quote.
7. **Keeping trailing spaces by typing literal spaces**: the compiler removes incidental trailing whitespace. Use `\s` if that space truly matters.
8. **Confusing text blocks with a template or parser**: a Java text block is a plain `String`; it does not interpolate variables, validate JSON/HTML/SQL, or protect data concatenated into SQL queries.
9. **Thinking `"""x"""` is a valid single-line text block**: even if the result has only one line, the declaration syntax still requires a line break after the opening triple quotes.
10. **Reading `println` output as raw content**: `println` always appends its own newline when printing, making it hard to tell whether a string ends with `\n`.

## 9. Self-check exercises

**Exercise 1.** Determine whether the following two declarations are valid, and state their exact values:

~~~java
String a = """
    one
    two
    """;
String b = """
    one
    two""";
~~~

**Answer:** Both are valid. `a` equals `"one\ntwo\n"`, and `b` equals `"one\ntwo"`. The two values differ because `a` has a line break before the closing delimiter.

**Exercise 2.** Why does this declaration report an error?

~~~java
String c = """hello
    world
    """;
~~~

**Answer:** The opening delimiter cannot be followed directly by the word `hello`. A line break is required immediately after the opening `"""` before writing the first word.

**Exercise 3.** How do you write a `String` consisting of exactly three consecutive double quotes followed by `\n`?

**Sample answer:**

~~~java
String d = """
    \"\"\"
    """;
~~~

**Exercise 4.** Someone moves only the closing `"""` to the left in a multiline block. What difference can that cause?

**Answer:** The amount of leading indentation stripped by Java may decrease; the resulting string will have **extra leading spaces** even though the words did not change. Compare with `equals(...)` or use a helper that prints whitespace visibly to verify.

## 10. Takeaways and references

- **Opening:** `"""` + optional horizontal whitespace + **mandatory line break**; content begins on the next line.
- **Closing:** `"""` **may be on its own line or on the same line as the final content**.
- **Own line:** usually produces a value containing a trailing `\n` because the content has a line break before the closing delimiter.
- **Same line:** usually has no trailing `\n`; no standalone closing-delimiter column participates in indentation calculation.
- **Triple double quotes in data:** use escapes, such as `\"\"\"`.
- **Whitespace:** the closing delimiter's position can affect indentation; `\s` preserves trailing spaces, and `\` immediately before a line terminator joins two lines.

Further reading: [Java Language Specification, §3.10.6 — Text Blocks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.10.6) and [Oracle Programmer’s Guide to Text Blocks](https://docs.oracle.com/en/java/javase/21/text-blocks/index.html). Both documents specify the exact delimiter and whitespace-processing rules when checking edge cases.
